"""imap-mcp-server module."""

# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

# Covers: FR-23

from dataclasses import dataclass
from threading import Lock
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.engine import make_url

from cloud_dog_storage.backends.local import LocalStorage
from cloud_dog_config import get_config
from cloud_dog_config.errors import ConfigError
from cloud_dog_db import (
    DatabaseSettings,
    MigrationRunner,
    SyncSessionManager,
    build_sync_engine,
    probe_database,
)
from cloud_dog_db.migrations.runner import MigrationConfig

from imap_hub_core.config.access import runtime_config_value
from imap_hub_core.storage_paths import (
    find_project_root,
    is_absolute_fs_path,
    join_fs_path,
    parent_fs_path,
)


@dataclass(slots=True)
class PlatformDatabaseRuntime:
    settings: DatabaseSettings
    engine: Engine
    session_manager: SyncSessionManager
    migration_runner: MigrationRunner


_RUNTIME_LOCK = Lock()
_RUNTIME: PlatformDatabaseRuntime | None = None


def _project_root() -> str:
    """Return the repository root for relative runtime assets."""
    return find_project_root(__file__)


def _default_sqlite_path(config: Any | None) -> str:
    data_dir = ""
    if config is not None:
        data_dir = str(
            getattr(getattr(config.server, "storage", None), "data_dir", "") or ""
        ).strip()
    if data_dir:
        return join_fs_path(data_dir, "imap_mcp.db")
    return "./data/imap_mcp.db"


def _env_value(config: Any | None, *names: str) -> str | None:
    value = runtime_config_value(config, *names)
    return value or None


def _settings_from_config(config: Any | None) -> DatabaseSettings:
    if config is None:
        try:
            config = get_config()
        except ConfigError:
            from imap_hub_core.config.loader import load_raw_config

            config = load_raw_config(unresolved_policy="warn")

    explicit_url = _env_value(
        config, "CLOUD_DOG__DB__URL", "CLOUD_DOG_DB__URL", "IMAP_DB_URL"
    )
    if explicit_url:
        return DatabaseSettings(url=explicit_url)

    payload: dict[str, Any] = {}
    env_map = {
        "dialect": ("CLOUD_DOG_DB__DIALECT", "CLOUD_DOG__DB__DIALECT"),
        "driver": ("CLOUD_DOG_DB__DRIVER", "CLOUD_DOG__DB__DRIVER"),
        "host": ("CLOUD_DOG_DB__HOST", "CLOUD_DOG__DB__HOST"),
        "port": ("CLOUD_DOG_DB__PORT", "CLOUD_DOG__DB__PORT"),
        "username": ("CLOUD_DOG_DB__USERNAME", "CLOUD_DOG__DB__USERNAME"),
        "password": ("CLOUD_DOG_DB__PASSWORD", "CLOUD_DOG__DB__PASSWORD"),
        "database": ("CLOUD_DOG_DB__DATABASE", "CLOUD_DOG__DB__DATABASE"),
        "path": ("CLOUD_DOG_DB__PATH", "CLOUD_DOG__DB__PATH"),
        "schema_name": ("CLOUD_DOG_DB__SCHEMA", "CLOUD_DOG__DB__SCHEMA"),
    }
    for field, names in env_map.items():
        value = _env_value(config, *names)
        if value is not None:
            payload[field] = value

    if payload:
        if (
            not str(payload.get("database") or "").strip()
            and not str(payload.get("url") or "").strip()
        ):
            payload["database"] = _default_sqlite_path(config)
        return DatabaseSettings.model_validate(payload)

    return DatabaseSettings(
        dialect="sqlite",
        database=_default_sqlite_path(config),
    )


def _sqlite_path(settings: DatabaseSettings) -> str | None:
    url = make_url(settings.to_sync_url())
    if url.get_backend_name() != "sqlite":
        return None
    if not url.database or url.database == ":memory:":
        return None
    path = str(url.database)
    if not is_absolute_fs_path(path):
        path = join_fs_path(_project_root(), path)
    return path


def _migration_script_location() -> str:
    return join_fs_path(_project_root(), "database", "migrations", "cloud_dog_db")


def initialise_database(
    config: Any | None = None, *, force_reinit: bool = False
) -> PlatformDatabaseRuntime:
    """Initialise engine/session/migrations through cloud_dog_db."""
    global _RUNTIME
    with _RUNTIME_LOCK:
        if _RUNTIME is not None and not force_reinit:
            return _RUNTIME

        settings = _settings_from_config(config)
        sqlite_path = _sqlite_path(settings)
        if sqlite_path is not None:
            LocalStorage(root_path=parent_fs_path(sqlite_path))

        engine = build_sync_engine(settings)
        session_manager = SyncSessionManager(engine)
        runner = MigrationRunner(
            MigrationConfig(
                script_location=_migration_script_location(),
                sqlalchemy_url=settings.to_sync_url(),
            )
        )
        runner.upgrade("head")

        # W28A-876 Gate 4b: ensure the canonical cloud_dog_idam role tables exist
        # so the PS-71 §IW3A Roles page (/api/v1/admin/roles) is backed by the
        # shared SqlAlchemyRoleStore. Only the role-related tables are created
        # here; other idam tables are not part of this service's schema.
        from cloud_dog_idam.storage.sqlalchemy.models import (
            PermissionORM as _PermissionORM,
            RoleORM as _RoleORM,
            RolePermissionORM as _RolePermissionORM,
        )

        _RoleORM.metadata.create_all(
            bind=engine,
            checkfirst=True,
            tables=[
                _RoleORM.__table__,
                _PermissionORM.__table__,
                _RolePermissionORM.__table__,
            ],
        )

        _RUNTIME = PlatformDatabaseRuntime(
            settings=settings,
            engine=engine,
            session_manager=session_manager,
            migration_runner=runner,
        )
        return _RUNTIME


def database_health(runtime: PlatformDatabaseRuntime | None = None) -> dict[str, Any]:
    """Return DB probe details for health handlers."""
    active = runtime or _RUNTIME
    if active is None:
        return {"ok": False, "status": "not_initialised"}
    try:
        probe = probe_database(active.engine)
        return {"ok": bool(probe.get("ok", False)), "probe": probe}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def shutdown_database() -> None:
    """Dispose database engine."""
    global _RUNTIME
    with _RUNTIME_LOCK:
        if _RUNTIME is None:
            return
        _RUNTIME.engine.dispose()
        _RUNTIME = None
