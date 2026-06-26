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

# Covers: CFG-09
# Covers: CFG-10
# Covers: CFG-11
# Covers: CFG-13

from uuid import uuid4

from tests.helpers.live_runtime import mcp_client
import pytest


def _tool_payload(response) -> dict:
    body = response.json()
    return body.get("data") or body.get("result") or {}
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-11")


def test_it120_mcp_admin_config_parity() -> None:
    suffix = uuid4().hex[:8]
    user_id = f"it120_user_{suffix}"
    group_id = f"it120_group_{suffix}"
    api_key_id = ""

    client = mcp_client(env_files=["tests/env-IT"])
    seed_api_key = str(getattr(client.app.state, "seed_api_key", "") or "")
    admin_headers = {
        "x-api-key": seed_api_key,
        "Authorization": f"Bearer {seed_api_key}",
        "x-role": "admin",
    }
    viewer_headers = {
        "x-api-key": seed_api_key,
        "Authorization": f"Bearer {seed_api_key}",
        "x-role": "viewer",
    }

    try:
        denied = client.post("/mcp/tools/user_list", json={"include_disabled": False})
        assert denied.status_code == 401

        denied_role = client.post(
            "/mcp/tools/user_list",
            headers=viewer_headers,
            json={"include_disabled": False},
        )
        assert denied_role.status_code == 403
        assert denied_role.json()["detail"]["code"] == "admin_required"

        create_user = client.post(
            "/mcp/tools/user_create",
            headers=admin_headers,
            json={
                "user_id": user_id,
                "username": user_id,
                "email": f"{user_id}@example.com",
            },
        )
        assert create_user.status_code == 200
        assert _tool_payload(create_user)["result"]["user_id"] == user_id

        user_list = client.post(
            "/mcp/tools/user_list",
            headers=admin_headers,
            json={"include_disabled": False},
        )
        assert user_list.status_code == 200
        ids = {item["user_id"] for item in _tool_payload(user_list)["result"]["items"]}
        assert user_id in ids

        create_group = client.post(
            "/mcp/tools/group_create",
            headers=admin_headers,
            json={
                "group_id": group_id,
                "name": group_id,
                "roles": ["admin"],
                "members": [user_id],
            },
        )
        assert create_group.status_code == 200
        assert _tool_payload(create_group)["result"]["group_id"] == group_id

        group_list = client.post(
            "/mcp/tools/group_list",
            headers=admin_headers,
            json={"include_disabled": False},
        )
        assert group_list.status_code == 200
        group_ids = {item["group_id"] for item in _tool_payload(group_list)["result"]["items"]}
        assert group_id in group_ids

        create_key = client.post(
            "/mcp/tools/api_key_create",
            headers=admin_headers,
            json={
                "owner_user_id": user_id,
                "scopes": ["profiles:read"],
                "description": "IT120 MCP scoped key",
            },
        )
        assert create_key.status_code == 200
        api_key_id = _tool_payload(create_key)["result"]["api_key_id"]
        assert _tool_payload(create_key)["result"]["raw_key"].startswith("cd_")

        revoke_key = client.post(
            "/mcp/tools/api_key_revoke",
            headers=admin_headers,
            json={"api_key_id": api_key_id},
        )
        assert revoke_key.status_code == 200
        assert _tool_payload(revoke_key)["result"]["api_key_id"] == api_key_id
        api_key_id = ""
    finally:
        if api_key_id:
            client.post(
                "/mcp/tools/api_key_revoke",
                headers=admin_headers,
                json={"api_key_id": api_key_id},
            )
        client.post(
            "/mcp/tools/group_delete",
            headers=admin_headers,
            json={"group_id": group_id},
        )
        client.post(
            "/mcp/tools/user_delete",
            headers=admin_headers,
            json={"user_id": user_id},
        )
        client.close()
