"""Runtime logging helpers for imap-mcp server surfaces."""

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

import os
from typing import Any

from cloud_dog_logging import setup_logging
from cloud_dog_logging.correlation import set_environment, set_service_instance, set_service_name
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from imap_hub_core.config.loader import load_raw_config
from imap_hub_core.config.access import resolve_env_files

_KNOWN_SURFACES = frozenset({"api_server", "web_server", "mcp_server", "a2a_server"})
_APP_LOG_MODE = 0o644
_AUDIT_LOG_MODE = 0o600
_AUDIT_DIR_MODE = 0o700


class ServiceContextMiddleware(BaseHTTPMiddleware):
    """Bind service metadata into cloud_dog_logging contextvars per request."""

    def __init__(
        self,
        app: FastAPI,
        *,
        service_name: str,
        service_instance: str,
        environment: str,
        app_log_path: str,
        audit_log_path: str,
        integrity_log_path: str,
    ) -> None:
        super().__init__(app)
        self._service_name = service_name
        self._service_instance = service_instance
        self._environment = environment
        self._app_log_path = app_log_path
        self._audit_log_path = audit_log_path
        self._integrity_log_path = integrity_log_path

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        set_service_name(self._service_name)
        set_service_instance(self._service_instance)
        set_environment(self._environment)
        try:
            return await call_next(request)
        finally:
            ensure_runtime_log_permissions(
                app_log_path=self._app_log_path,
                audit_log_path=self._audit_log_path,
                integrity_log_path=self._integrity_log_path,
            )


def _config_value(config: Any, key: str, default: Any) -> Any:
    """Read a value from GlobalConfig safely with a default fallback."""
    try:
        value = config.get(key, default)
    except Exception:
        value = default
    return default if value is None else value


def _ensure_file(path: str, *, mode: int, directory_mode: int | None = None) -> str:
    """Create a log file if missing and normalise its permissions."""
    resolved = os.path.abspath(str(path))
    parent = os.path.dirname(resolved) or "."
    os.makedirs(parent, exist_ok=True)
    if directory_mode is not None:
        try:
            os.chmod(parent, directory_mode)
        except PermissionError:
            # Docker bind mounts may be writable without allowing chmod
            # from the container's non-root runtime user.
            pass
    with open(resolved, "a", encoding="utf-8"):
        pass
    try:
        os.chmod(resolved, mode)
    except PermissionError:
        pass
    return resolved


def build_platform_log_config(config: Any, *, surface_name: str) -> dict[str, Any]:
    """Build cloud_dog_logging config for one runtime surface."""
    if surface_name not in _KNOWN_SURFACES:
        raise ValueError(f"Unsupported logging surface: {surface_name}")

    service_instance = str(
        _config_value(
            config,
            "log.service_instance",
            _config_value(config, "server.server_id", "imap-mcp-local"),
        )
    ).strip() or "imap-mcp-local"
    environment = str(
        _config_value(config, "log.environment", _config_value(config, "environment", "unknown"))
    ).strip() or "unknown"
    app_log_path = _ensure_file(
        str(_config_value(config, f"log.{surface_name}_log", f"logs/{surface_name}.log")),
        mode=_APP_LOG_MODE,
    )
    audit_log_path = _ensure_file(
        str(_config_value(config, "log.audit_log", "logs/audit.log.jsonl")),
        mode=_AUDIT_LOG_MODE,
        directory_mode=_AUDIT_DIR_MODE,
    )
    integrity_log_path = _ensure_file(
        str(_config_value(config, "log.integrity.log_file", "logs/audit-integrity.log")),
        mode=_APP_LOG_MODE,
    )

    return {
        "service_name": "imap-mcp-server",
        "service_instance": service_instance,
        "environment": environment,
        "log": {
            "level": str(_config_value(config, "log.level", "INFO")),
            "format": str(_config_value(config, "log.format", "json")),
            "console": bool(_config_value(config, "log.console", False)),
            "app_log": app_log_path,
            "audit_log": audit_log_path,
            "rotation": {
                "mode": str(_config_value(config, "log.rotation.mode", "size")),
                "max_bytes": int(_config_value(config, "log.rotation.max_bytes", 104857600)),
                "backup_count": int(_config_value(config, "log.rotation.backup_count", 10)),
                "when": str(_config_value(config, "log.rotation.when", "midnight")),
                "interval": int(_config_value(config, "log.rotation.interval", 1)),
                "compress": bool(_config_value(config, "log.rotation.compress", True)),
            },
            "integrity": {
                "enabled": bool(_config_value(config, "log.integrity.enabled", True)),
                "interval_seconds": int(_config_value(config, "log.integrity.interval_seconds", 300)),
                "log_file": integrity_log_path,
                "hash_algorithm": str(_config_value(config, "log.integrity.hash_algorithm", "sha256")),
            },
            "retention": {
                "hot_days": int(_config_value(config, "log.retention.hot_days", 14)),
                "cold_days": int(_config_value(config, "log.retention.cold_days", 60)),
                "archive_format": str(_config_value(config, "log.retention.archive_format", "gz")),
            },
            "levels": _config_value(config, "log.levels", {}),
        },
    }


def init_surface_logging(
    env_files: list[str] | None,
    *,
    surface_name: str,
) -> dict[str, str]:
    """Initialise cloud_dog_logging for one service surface."""
    resolved_env_files = resolve_env_files(env_files)
    raw_config = load_raw_config(env_files=resolved_env_files)
    logging_config = build_platform_log_config(raw_config, surface_name=surface_name)
    setup_logging(logging_config)
    log_paths = {
        "app_log_path": str(logging_config["log"]["app_log"]),
        "audit_log_path": str(logging_config["log"]["audit_log"]),
        "integrity_log_path": str(logging_config["log"]["integrity"]["log_file"]),
        "service_instance": str(logging_config["service_instance"]),
        "environment": str(logging_config["environment"]),
    }
    ensure_runtime_log_permissions(
        app_log_path=log_paths["app_log_path"],
        audit_log_path=log_paths["audit_log_path"],
        integrity_log_path=log_paths["integrity_log_path"],
    )
    return log_paths


def ensure_runtime_log_permissions(
    *,
    app_log_path: str | None = None,
    audit_log_path: str | None = None,
    integrity_log_path: str | None = None,
    canonical_audit_path: str | None = None,
) -> None:
    """Normalise PS-40 file permissions after sinks create or rotate files."""
    if app_log_path:
        _ensure_file(app_log_path, mode=_APP_LOG_MODE)
    if integrity_log_path:
        _ensure_file(integrity_log_path, mode=_APP_LOG_MODE)
    if audit_log_path:
        _ensure_file(audit_log_path, mode=_AUDIT_LOG_MODE, directory_mode=_AUDIT_DIR_MODE)
    if canonical_audit_path:
        _ensure_file(canonical_audit_path, mode=_AUDIT_LOG_MODE, directory_mode=_AUDIT_DIR_MODE)


def install_service_context_middleware(app: FastAPI, *, log_paths: dict[str, str]) -> None:
    """Install per-request service metadata binding for platform middleware logs."""
    app.add_middleware(
        ServiceContextMiddleware,
        service_name="imap-mcp-server",
        service_instance=log_paths["service_instance"],
        environment=log_paths["environment"],
        app_log_path=log_paths["app_log_path"],
        audit_log_path=log_paths["audit_log_path"],
        integrity_log_path=log_paths["integrity_log_path"],
    )
