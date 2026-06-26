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

# Covers: CFG-08
# Covers: CFG-09
# Covers: CFG-10
# Covers: CFG-11
# Covers: CFG-12

from cloud_dog_idam import APIKeyManager, RBACEngine

from imap_hub_core.tools.handlers import build_default_tool_registry
from imap_hub_server.admin.state import FileBackedAdminState
import pytest
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-03")


def test_ut137_admin_tool_handlers_cover_crud_lifecycle(tmp_path) -> None:
    admin_state = FileBackedAdminState(str(tmp_path))
    manager = APIKeyManager()
    rbac_engine = RBACEngine()
    registry = build_default_tool_registry(
        profiles={"operations": {"provider": "imap_generic", "enabled": True}},
        downloads_dir=str(tmp_path / "downloads"),
        admin_state=admin_state,
        api_key_manager=manager,
        rbac_engine=rbac_engine,
    )

    user_create = registry.call(
        "user_create",
        {
            "user_id": "tool-user-1",
            "username": "tool-user-1",
            "email": "tool-user-1@example.com",
            "role": "viewer",
        },
    )
    assert user_create["ok"] is True
    assert user_create["result"]["user_id"] == "tool-user-1"

    group_create = registry.call(
        "group_create",
        {
            "group_id": "tool-group-1",
            "name": "tool-group-1",
            "roles": ["admin"],
            "members": ["tool-user-1"],
        },
    )
    assert group_create["ok"] is True
    assert group_create["result"]["members"] == ["tool-user-1"]

    api_key_create = registry.call(
        "api_key_create",
        {
            "owner_user_id": "tool-user-1",
            "scopes": ["profiles:read"],
            "description": "tool scoped key",
        },
    )
    assert api_key_create["ok"] is True
    assert api_key_create["result"]["raw_key"].startswith("cd_")
    api_key_id = api_key_create["result"]["api_key_id"]

    api_key_revoke = registry.call("api_key_revoke", {"api_key_id": api_key_id})
    assert api_key_revoke["ok"] is True
    assert admin_state.get_api_key(api_key_id).status == "revoked"

    user_delete = registry.call("user_delete", {"user_id": "tool-user-1"})
    assert user_delete["ok"] is True
    assert admin_state.get_user("tool-user-1") is None
