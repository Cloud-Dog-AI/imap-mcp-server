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

from pathlib import Path

from sqlalchemy import text

from imap_hub_core.db.models import ImapPlatformDbState
from imap_hub_core.db.runtime import initialise_database, shutdown_database
import pytest


_BASELINE_REVISION = "20260305_0001"


def _configure_sqlite_env(monkeypatch, db_path: Path) -> None:
    monkeypatch.setenv("CLOUD_DOG__DB__DIALECT", "sqlite")
    monkeypatch.setenv("CLOUD_DOG__DB__DATABASE", str(db_path))
    monkeypatch.delenv("CLOUD_DOG__DB__URL", raising=False)
    monkeypatch.delenv("CLOUD_DOG_DB__URL", raising=False)
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-23")


def test_st_db_01_migration_upgrade_on_fresh_sqlite(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "imap-mcp-st-migration.db"
    _configure_sqlite_env(monkeypatch, db_path)

    runtime = initialise_database(force_reinit=True)
    try:
        assert db_path.exists() is True
        with runtime.engine.connect() as conn:
            revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert revision == _BASELINE_REVISION
    finally:
        shutdown_database()
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-23")


def test_st_db_02_crud_via_session_manager(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "imap-mcp-st-crud.db"
    _configure_sqlite_env(monkeypatch, db_path)

    runtime = initialise_database(force_reinit=True)
    try:
        with runtime.session_manager.session() as session:
            session.add(ImapPlatformDbState(service="imap-st", status="ready"))

        with runtime.session_manager.session() as session:
            row = session.query(ImapPlatformDbState).filter_by(service="imap-st").one()
            row.status = "verified"

        with runtime.session_manager.session() as session:
            verified = session.query(ImapPlatformDbState).filter_by(service="imap-st").one()
            assert verified.status == "verified"
    finally:
        shutdown_database()
