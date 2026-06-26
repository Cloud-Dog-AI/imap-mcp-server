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

import pytest
from cloud_dog_idam import APIKeyManager, RBACEngine
from fastapi.testclient import TestClient

from imap_hub_core.audit.context import (
    AuditRequestContext,
    reset_audit_request_context,
    set_audit_request_context,
)
from imap_hub_core.tools.definitions import ProfileListInput
from imap_hub_core.tools.handlers import ToolContract, ToolRegistry, build_default_tool_registry
from imap_hub_server.api_server import create_api_app
from imap_hub_server.admin.state import FileBackedAdminState


def _audit_context(*, actor_id: str, source_identifier: str | None = None) -> AuditRequestContext:
    return AuditRequestContext(
        correlation_id="ut-imap-profile-rbac",
        actor_id=actor_id,
        roles=[],
        source_identifier=source_identifier,
        component="unit-test",
        server_id="imap-mcp-unit",
        environment="test",
    )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-04")


def test_profile_list_filters_to_profiles_granted_by_group_role(tmp_path) -> None:
    admin_state = FileBackedAdminState(str(tmp_path / "state"))
    api_key_manager = APIKeyManager()
    rbac_engine = RBACEngine()
    admin_state.create_user(
        {
            "user_id": "scoped-user",
            "username": "scoped-user",
            "email": "scoped-user@example.test",
            "role": "viewer",
        }
    )
    admin_state.create_group(
        {
            "group_id": "mail-alpha",
            "name": "mail-alpha",
            "roles": ["profile:alpha"],
            "members": ["scoped-user"],
        }
    )
    admin_state.sync_rbac_engine(rbac_engine)

    registry = build_default_tool_registry(
        profiles={
            "alpha": {"enabled": True},
            "beta": {"enabled": True},
        },
        downloads_dir=str(tmp_path / "downloads"),
        admin_state=admin_state,
        api_key_manager=api_key_manager,
        rbac_engine=rbac_engine,
    )

    token = set_audit_request_context(_audit_context(actor_id="scoped-user"))
    try:
        result = registry.call("profile_list", {"include_disabled": False})
    finally:
        reset_audit_request_context(token)

    assert result["ok"] is True
    assert result["result"]["profiles"] == ["alpha"]
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-04")


def test_mail_probe_denies_managed_api_key_without_profile_scope(tmp_path) -> None:
    admin_state = FileBackedAdminState(str(tmp_path / "state"))
    api_key_manager = APIKeyManager()
    rbac_engine = RBACEngine()
    admin_state.create_user(
        {
            "user_id": "api-user",
            "username": "api-user",
            "email": "api-user@example.test",
            "role": "viewer",
        }
    )
    _, key_record = admin_state.create_api_key(
        payload={
            "owner_user_id": "api-user",
            "scopes": ["profile:alpha"],
            "description": "scoped-imap-key",
        },
        api_key_manager=api_key_manager,
    )

    registry = build_default_tool_registry(
        profiles={
            "alpha": {"enabled": True},
            "beta": {"enabled": True},
        },
        downloads_dir=str(tmp_path / "downloads"),
        admin_state=admin_state,
        api_key_manager=api_key_manager,
        rbac_engine=rbac_engine,
    )

    token = set_audit_request_context(
        _audit_context(actor_id="api-user", source_identifier=f"api_key:{key_record.api_key_id}")
    )
    try:
        with pytest.raises(PermissionError, match="Access denied to profile 'beta'"):
            registry.call(
                "mail_probe",
                {
                    "profile_id": "beta",
                    "folder": "INBOX",
                },
            )
    finally:
        reset_audit_request_context(token)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-04")


def test_managed_key_profiles_read_scope_can_execute_profile_read_tools_with_role_patterns(
    tmp_path,
) -> None:
    admin_state = FileBackedAdminState(str(tmp_path / "state"))
    api_key_manager = APIKeyManager()
    admin_state.create_user(
        {
            "user_id": "managed-user",
            "username": "managed-user",
            "email": "managed-user@example.test",
            "role": "viewer",
        }
    )
    _, key_record = admin_state.create_api_key(
        payload={
            "owner_user_id": "managed-user",
            "scopes": ["profiles:read"],
            "description": "profile-read-only",
        },
        api_key_manager=api_key_manager,
    )
    registry = ToolRegistry(
        role_patterns={"reader": ["mail_search"], "admin": ["*"]},
        admin_state=admin_state,
    )
    registry.register(
        ToolContract(
            name="mail_headlines",
            description="dummy",
            input_model=ProfileListInput,
            handler=lambda payload: {"ok": True, "payload": payload},
        )
    )

    token = set_audit_request_context(
        _audit_context(actor_id="managed-user", source_identifier=f"api_key:{key_record.api_key_id}")
    )
    try:
        result = registry.call("mail_headlines", {})
    finally:
        reset_audit_request_context(token)

    assert result["ok"] is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-04")


def test_api_mail_search_honours_owner_group_roles_and_profile_scopes(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / "ut-api-profile-rbac.env"
    data_dir = tmp_path / "data"
    env_file.write_text(
        "\n".join(
            [
                "CLOUD_DOG__SERVER__AUTH__MODE=api_key",
                f"CLOUD_DOG__SERVER__STORAGE__DATA_DIR={data_dir.as_posix()}",
                "CLOUD_DOG__API_SERVER__PORT=18070",
                "CLOUD_DOG__WEB_SERVER__PORT=18071",
                "CLOUD_DOG__MCP_SERVER__PORT=18072",
                "CLOUD_DOG__A2A_SERVER__PORT=18073",
                "CLOUD_DOG__PROFILES__OPERATIONS__IMAP__HOST=127.0.0.1",
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("TEST_ENV_TIER", "UT")
    monkeypatch.setenv("API_KEY", "unit-admin-key")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "unit-google-secret")
    monkeypatch.setenv("MS_CLIENT_SECRET", "unit-ms-secret")
    monkeypatch.setenv("IMAP_OPERATIONS_HOST", "127.0.0.1")
    monkeypatch.setenv("IMAP_OPERATIONS_PORT", "993")
    monkeypatch.setenv("IMAP_OPERATIONS_USERNAME", "unit-operations")
    monkeypatch.setenv("IMAP_OPERATIONS_PASSWORD", "unit-password")
    monkeypatch.setenv("CLOUD_DOG__PROFILES__OPERATIONS__IMAP__PORT", "993")
    monkeypatch.setenv("CLOUD_DOG__PROFILES__OPERATIONS_CLOUD_DOG__IMAP__PORT", "993")
    app = create_api_app(env_files=[str(env_file)])
    client = TestClient(app)
    admin_headers = {"x-api-key": str(app.state.seed_api_key), "x-role": "admin"}
    user_id = "api-profile-rbac-user"
    group_id = "api-profile-rbac-group"
    denied_key_id = ""
    allow_key_id = ""

    try:
        created_user = client.post(
            "/api/v1/admin/users",
            headers=admin_headers,
            json={
                "user_id": user_id,
                "username": user_id,
                "email": f"{user_id}@example.test",
                "role": "viewer",
            },
        )
        assert created_user.status_code == 200, created_user.text

        created_group = client.post(
            "/api/v1/admin/groups",
            headers=admin_headers,
            json={
                "group_id": group_id,
                "name": group_id,
                "description": "reader role only",
                "roles": ["reader"],
                "members": [user_id],
            },
        )
        assert created_group.status_code == 200, created_group.text

        denied_key = client.post(
            "/api/v1/admin/api-keys",
            headers=admin_headers,
            json={"owner_user_id": user_id, "description": "denied", "scopes": []},
        )
        assert denied_key.status_code == 200, denied_key.text
        denied_payload = denied_key.json()["result"]
        denied_key_id = denied_payload["api_key_id"]

        denied = client.post(
            "/api/v1/tools/mail_search",
            headers={"x-api-key": denied_payload["raw_key"]},
            json={
                "profile_id": "operations",
                "mode": "imap",
                "query": "ALL",
                "filters": {"folder": "INBOX"},
            },
        )
        assert denied.status_code == 403, denied.text
        assert denied.json()["detail"] == "Access denied to profile 'operations'"

        allowed_key = client.post(
            "/api/v1/admin/api-keys",
            headers=admin_headers,
            json={
                "owner_user_id": user_id,
                "description": "allowed",
                "scopes": ["profile:operations"],
            },
        )
        assert allowed_key.status_code == 200, allowed_key.text
        allowed_payload = allowed_key.json()["result"]
        allow_key_id = allowed_payload["api_key_id"]

        allowed = client.post(
            "/api/v1/tools/mail_search",
            headers={"x-api-key": allowed_payload["raw_key"]},
            json={
                "profile_id": "operations",
                "mode": "imap",
                "query": "ALL",
                "filters": {"folder": "INBOX"},
            },
        )
        assert allowed.status_code == 200, allowed.text
        assert "Access denied to profile 'operations'" not in str(allowed.json())
    finally:
        if allow_key_id:
            client.delete(f"/api/v1/admin/api-keys/{allow_key_id}", headers=admin_headers)
        if denied_key_id:
            client.delete(f"/api/v1/admin/api-keys/{denied_key_id}", headers=admin_headers)
        client.delete(f"/api/v1/admin/groups/{group_id}", headers=admin_headers)
        client.delete(f"/api/v1/admin/users/{user_id}", headers=admin_headers)
        client.close()
