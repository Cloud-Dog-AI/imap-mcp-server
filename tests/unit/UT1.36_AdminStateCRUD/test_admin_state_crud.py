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

# Covers: CFG-06
# Covers: CFG-08
# Covers: CFG-09
# Covers: CFG-10
# Covers: CFG-11
# Covers: CFG-12
# Covers: CFG-13

import json
from pathlib import Path

from cloud_dog_idam import APIKeyManager, RBACEngine
from fastapi import FastAPI
from fastapi.testclient import TestClient

from imap_hub_server.admin.endpoints import build_admin_router
from imap_hub_server.admin.state import FileBackedAdminState
import pytest
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-03")


def test_ut136_admin_state_persists_crud_records_and_scopes(tmp_path) -> None:
    admin_state = FileBackedAdminState(str(tmp_path))
    manager = APIKeyManager()

    user = admin_state.create_user(
        {
            "user_id": "cfg-user-1",
            "username": "cfg-user-1",
            "email": "cfg-user-1@example.com",
            "role": "viewer",
        }
    )
    group = admin_state.create_group(
        {
            "group_id": "cfg-group-1",
            "name": "cfg-group-1",
            "roles": ["admin"],
            "members": [user.user_id],
        }
    )
    raw_key, key_record = admin_state.create_api_key(
        payload={
            "owner_user_id": user.user_id,
            "scopes": ["profiles:read", "users:*"],
            "description": "cfg scoped read key",
        },
        api_key_manager=manager,
    )
    admin_state.emit_event(
        entity_type="user",
        action="create",
        entity_id=user.user_id,
        actor_id="integration-user",
        source="api",
        details={"username": user.username},
    )
    admin_state.upsert_profile(
        "dynamic-profile",
        {
            "provider": "imap_generic",
            "enabled": True,
            "sync": {"retention": {"max_age_days": 7, "max_messages": 200}},
        },
    )

    reloaded = FileBackedAdminState(str(tmp_path))
    assert reloaded.get_user(user.user_id) is not None
    assert reloaded.get_group(group.group_id) is not None
    assert reloaded.key_has_scope(key_record.api_key_id, "profiles:read") is True
    assert reloaded.key_has_scope(key_record.api_key_id, "users:read") is True
    assert reloaded.key_has_scope(key_record.api_key_id, "groups:read") is False
    assert raw_key.startswith(key_record.key_prefix)
    assert reloaded.list_profiles({"operations": {"enabled": True}}) == [
        "dynamic-profile",
        "operations",
    ]
    dynamic_profile = reloaded.get_profile("dynamic-profile", {"operations": {"enabled": True}})
    assert dynamic_profile is not None
    assert dynamic_profile["sync"]["retention"]["max_messages"] == 200

    exported = reloaded.export_api_key(key_record)
    assert exported["api_key_id"] == key_record.api_key_id
    assert "key_hash" not in exported

    lines = Path(reloaded.event_path).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["entity_type"] == "user"
    assert event["action"] == "create"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-03")


def test_ut136_admin_state_syncs_rbac_and_revokes_owned_keys_on_user_delete(tmp_path) -> None:
    admin_state = FileBackedAdminState(str(tmp_path))
    manager = APIKeyManager()
    rbac_engine = RBACEngine()

    user = admin_state.create_user(
        {
            "user_id": "cfg-user-2",
            "username": "cfg-user-2",
            "email": "cfg-user-2@example.com",
            "role": "viewer",
        }
    )
    admin_state.create_group(
        {
            "group_id": "cfg-group-2",
            "name": "cfg-group-2",
            "roles": ["admin"],
            "members": [user.user_id],
        }
    )
    _, key_record = admin_state.create_api_key(
        payload={"owner_user_id": user.user_id, "scopes": ["profiles:read"]},
        api_key_manager=manager,
    )

    admin_state.sync_rbac_engine(rbac_engine)
    assert rbac_engine._user_roles[user.user_id] == {"viewer"}  # noqa: SLF001
    assert rbac_engine._group_roles["cfg-group-2"] == {"admin"}  # noqa: SLF001
    assert rbac_engine._group_memberships[user.user_id] == {"cfg-group-2"}  # noqa: SLF001

    assert admin_state.delete_user(user.user_id) is True
    deleted_user = admin_state.get_user(user.user_id)
    group = admin_state.get_group("cfg-group-2")
    key_record_after = admin_state.get_api_key(key_record.api_key_id)

    assert deleted_user is None
    assert group is not None
    assert user.user_id not in group.members
    assert key_record_after is not None
    assert key_record_after.status == "revoked"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-03")


def test_ut136_admin_state_clones_profiles_with_path_values(tmp_path) -> None:
    admin_state = FileBackedAdminState(str(tmp_path))

    profiles = {
        "operations": {
            "provider": "imap_generic",
            "archive": {"root": Path("/tmp/archive")},
            "sync": {"folders": {"include": {"INBOX", "Junk"}}},
        }
    }

    exported = admin_state.export_profiles(profiles)

    assert exported["operations"]["archive"]["root"] == "/tmp/archive"
    assert sorted(exported["operations"]["sync"]["folders"]["include"]) == ["INBOX", "Junk"]
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-03")


def test_ut136_admin_routes_encode_profile_and_rbac_payloads(tmp_path) -> None:
    admin_state = FileBackedAdminState(str(tmp_path))
    admin_state.bootstrap_admin_user("integration-user")

    app = FastAPI()
    app.include_router(
        build_admin_router(
            profile_store={
                "operations": {
                    "provider": "imap_generic",
                    "archive": {"root": Path("/tmp/archive")},
                    "sync": {"folders": {"include": {"INBOX", "Junk"}}},
                }
            },
            archive_root=str(tmp_path / "archive"),
            admin_state=admin_state,
            api_key_manager=APIKeyManager(),
            rbac_engine=RBACEngine(),
            rbac_store={"admin": {"profiles:read", "rbac:read"}},
        )
    )

    @app.middleware("http")
    async def _inject_admin_context(request, call_next):  # type: ignore[no-untyped-def]
        request.state.roles = {"admin"}
        request.state.api_key = "seed"
        request.state.request_id = "req-ut136"
        request.state.correlation_id = "corr-ut136"
        return await call_next(request)

    client = TestClient(app)

    profiles_response = client.get("/api/v1/admin/profiles")
    assert profiles_response.status_code == 200
    assert profiles_response.json()["result"]["profiles"] == ["operations"]

    profile_response = client.get("/api/v1/admin/profiles/operations")
    assert profile_response.status_code == 200
    profile_payload = profile_response.json()["result"]
    assert profile_payload["archive"]["root"] == "/tmp/archive"
    assert sorted(profile_payload["sync"]["folders"]["include"]) == ["INBOX", "Junk"]

    rbac_response = client.get("/api/v1/admin/rbac/policies")
    assert rbac_response.status_code == 200
    assert sorted(rbac_response.json()["result"]["roles"]["admin"]) == [
        "profiles:read",
        "rbac:read",
    ]


@pytest.mark.UT
@pytest.mark.internal
@pytest.mark.req("FR-03")
def test_ut136_export_preserves_seed_credentials_when_override_blanks_them(tmp_path) -> None:
    """W28E-1803C: a persisted override that omits/blanks secret credentials must
    fall back to the seed profile's credentials (the WebUI never round-trips the
    mailbox password, so a seed override legitimately lacks it)."""
    admin_state = FileBackedAdminState(str(tmp_path))
    seed_profiles = {
        "operations": {
            "imap": {"host": "mail.cloud-dog.net", "port": 143, "security": "starttls"},
            "auth": {"mode": "app_password"},
            "credentials": {"username": "operations@cloud-dog.net", "password": "seed-secret"},
        }
    }
    # Persist an override that keeps the host but blanks the secret credentials,
    # exactly as a WebUI profile edit would (it never re-sends the password).
    admin_state.upsert_profile(
        "operations",
        {
            "imap": {"host": "mail.cloud-dog.net", "port": 143, "security": "starttls"},
            "auth": {"mode": "app_password"},
            "credentials": {"username": "", "password": ""},
        },
    )
    exported = admin_state.export_profiles(seed_profiles)["operations"]
    assert exported["credentials"]["username"] == "operations@cloud-dog.net"
    assert exported["credentials"]["password"] == "seed-secret"

    # A non-empty override value still wins over the seed.
    admin_state.upsert_profile(
        "operations",
        {"credentials": {"username": "rotated@cloud-dog.net", "password": ""}},
    )
    exported2 = admin_state.export_profiles(seed_profiles)["operations"]
    assert exported2["credentials"]["username"] == "rotated@cloud-dog.net"
    assert exported2["credentials"]["password"] == "seed-secret"
