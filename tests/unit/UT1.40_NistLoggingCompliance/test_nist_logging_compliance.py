# Covers: FR-09

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

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from imap_hub_core.audit.events import AuditActor, AuditRecord
from imap_hub_core.audit import logger as audit_logger_module
from imap_hub_core.audit.logger import AuditWriter, default_app_log_path
from imap_hub_server.auth.middleware import CompatAuthMiddleware, register_static_api_key
import pytest


def _last_json_line(path: Path) -> dict[str, object]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines, f"No log lines found in {path}"
    return json.loads(lines[-1])
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-09")


def test_audit_writer_emits_nist_au3_fields(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    writer = AuditWriter(
        str(audit_path),
        server_id="imap-node-test",
        environment="test",
    )
    try:
        writer.emit(
            AuditRecord(
                operation="admin.put_profile",
                status="success",
                correlation_id="corr-123",
                actor=AuditActor(
                    actor_id="admin-user",
                    roles=["admin"],
                    ip="127.0.0.1",
                    user_agent="pytest",
                ),
                component="imap_hub_server.admin.endpoints",
                source_identifier="user:admin-user",
                target_type="profile",
                target_id="ops",
                target_name="ops",
                server_id="imap-node-test",
                environment="test",
                params={"profile_id": "ops"},
            )
        )
    finally:
        writer.close()

    payload = _last_json_line(audit_path)
    assert payload["timestamp"]
    assert payload["event_type"] == "imap_mcp.admin.put_profile"
    assert payload["action"] == "admin.put_profile"
    assert payload["outcome"] == "success"
    assert payload["service_instance"] == "imap-node-test"
    assert payload["environment"] == "test"
    assert payload["actor"]["id"] == "admin-user"
    assert payload["actor"]["ip"] == "127.0.0.1"
    assert payload["details"]["component"] == "imap_hub_server.admin.endpoints"
    assert payload["details"]["source_identifier"] == "user:admin-user"
    assert payload["target"]["type"] == "profile"
    assert payload["target"]["id"] == "ops"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-09")


def test_auth_events_use_separate_app_and_audit_logs(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    app_log_path = Path(default_app_log_path(str(audit_path)))
    writer = AuditWriter(
        str(audit_path),
        server_id="imap-node-test",
        environment="test",
        app_log_path=str(app_log_path),
    )
    app = FastAPI()
    app.state.server_id = "imap-node-test"
    app.state.environment = "test"

    @app.get("/secure")
    async def secure() -> dict[str, bool]:
        return {"ok": True}

    from cloud_dog_idam import APIKeyManager

    api_key_manager = APIKeyManager()
    register_static_api_key(api_key_manager, "cd_test_key", owner_id="auth-user")
    app.add_middleware(
        CompatAuthMiddleware,
        api_key_manager=api_key_manager,
        auth_scheme="api_key",
        skip_paths=set(),
    )

    try:
        with TestClient(app) as client:
            denied = client.get("/secure", headers={"x-request-id": "corr-denied"})
            assert denied.status_code == 401
            allowed = client.get(
                "/secure",
                headers={"x-api-key": "cd_test_key", "x-request-id": "corr-allowed"},
            )
            assert allowed.status_code == 200
    finally:
        writer.close()

    audit_rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    app_rows = [json.loads(line) for line in app_log_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    assert any(row.get("event_type") == "imap_mcp.auth.authorise" for row in audit_rows)
    auth_audit = next(row for row in audit_rows if row.get("correlation_id") == "corr-allowed")
    assert auth_audit["actor"]["id"] == "auth-user"
    assert auth_audit["details"]["component"] == "imap_hub_server.auth.middleware"
    assert auth_audit["service_instance"] == "imap-node-test"

    auth_app = next(
        row
        for row in app_rows
        if row.get("message") == "auth_decision"
        and ((row.get("extra") or {}).get("correlation_id") == "corr-allowed")
    )
    assert auth_app["service_instance"] == "imap-node-test"
    assert auth_app["extra"]["component"] == "imap_hub_server.auth.middleware"
    assert auth_app["extra"]["outcome"] == "success"
    assert auth_app["extra"]["actor_id"] == "auth-user"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-09")


def test_audit_writer_adapts_to_legacy_actor_schema(monkeypatch, tmp_path: Path) -> None:
    class LegacyActor:
        def __init__(self, type: str, id: str, roles: list[str] | None = None) -> None:
            self.type = type
            self.id = id
            self.roles = roles

    class LegacyTarget:
        def __init__(self, type: str, id: str) -> None:
            self.type = type
            self.id = id

    class DummyAuditEvent:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class DummyLogger:
        def __init__(self) -> None:
            self.events: list[DummyAuditEvent] = []

        def emit(self, event: DummyAuditEvent) -> None:
            self.events.append(event)

    dummy_logger = DummyLogger()
    monkeypatch.setattr(audit_logger_module, "Actor", LegacyActor)
    monkeypatch.setattr(audit_logger_module, "Target", LegacyTarget)
    monkeypatch.setattr(audit_logger_module, "AuditEvent", DummyAuditEvent)
    monkeypatch.setattr(audit_logger_module, "setup_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(audit_logger_module, "get_audit_logger", lambda: dummy_logger)

    writer = AuditWriter(str(tmp_path / "audit.jsonl"))
    writer.emit(
        AuditRecord(
            operation="admin.list_profiles",
            status="success",
            correlation_id="corr-legacy",
            actor=AuditActor(
                actor_id="legacy-user",
                roles=["admin"],
                ip="127.0.0.1",
                user_agent="pytest",
            ),
            target_type="profile",
            target_id="operations",
            target_name="operations",
        )
    )

    assert len(dummy_logger.events) == 1
    actor = dummy_logger.events[0].kwargs["actor"]
    target = dummy_logger.events[0].kwargs["target"]
    assert isinstance(actor, LegacyActor)
    assert actor.id == "legacy-user"
    assert actor.roles == ["admin"]
    assert isinstance(target, LegacyTarget)
    assert target.id == "operations"
