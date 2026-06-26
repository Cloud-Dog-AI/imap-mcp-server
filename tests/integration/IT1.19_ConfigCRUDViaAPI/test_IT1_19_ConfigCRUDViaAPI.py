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
# Covers: CFG-12
# Covers: CFG-13

from uuid import uuid4

from tests.helpers.live_runtime import api_client
import pytest
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-11")


def test_it119_config_crud_via_api() -> None:
    suffix = uuid4().hex[:8]
    user_id = f"it119_user_{suffix}"
    group_id = f"it119_group_{suffix}"
    managed_api_key_id = ""

    client, seed_api_key = api_client(env_files=["tests/env-IT"])
    admin_headers = {
        "x-api-key": seed_api_key,
        "Authorization": f"Bearer {seed_api_key}",
        "x-role": "admin",
    }
    try:
        create_user = client.post(
            "/api/v1/admin/users",
            headers=admin_headers,
            json={
                "user_id": user_id,
                "username": user_id,
                "email": f"{user_id}@example.com",
                "display_name": "IT119 User",
                "role": "viewer",
            },
        )
        assert create_user.status_code == 200
        assert create_user.json()["result"]["user_id"] == user_id

        list_users = client.get("/api/v1/admin/users", headers=admin_headers)
        assert list_users.status_code == 200
        assert user_id in {item["user_id"] for item in list_users.json()["result"]["items"]}

        update_user = client.put(
            f"/api/v1/admin/users/{user_id}",
            headers=admin_headers,
            json={"display_name": "IT119 User Updated", "role": "reader"},
        )
        assert update_user.status_code == 200
        assert update_user.json()["result"]["display_name"] == "IT119 User Updated"

        create_group = client.post(
            "/api/v1/admin/groups",
            headers=admin_headers,
            json={
                "group_id": group_id,
                "name": group_id,
                "description": "IT119 Admin Group",
                "roles": ["viewer"],
                "members": [user_id],
            },
        )
        assert create_group.status_code == 200
        assert create_group.json()["result"]["group_id"] == group_id

        get_group = client.get(f"/api/v1/admin/groups/{group_id}", headers=admin_headers)
        assert get_group.status_code == 200
        assert user_id in get_group.json()["result"]["members"]

        create_key = client.post(
            "/api/v1/admin/api-keys",
            headers=admin_headers,
            json={
                "owner_user_id": user_id,
                "scopes": ["profiles:read", "users:read", "groups:read", "api_keys:read"],
                "description": "IT119 scoped read key",
            },
        )
        assert create_key.status_code == 200
        managed_api_key_id = create_key.json()["result"]["api_key_id"]
        raw_scoped_key = create_key.json()["result"]["raw_key"]

        scoped_headers = {
            "x-api-key": raw_scoped_key,
            "Authorization": f"Bearer {raw_scoped_key}",
        }
        profile_list = client.get("/api/v1/admin/profiles", headers=scoped_headers)
        assert profile_list.status_code == 200
        assert isinstance(profile_list.json()["result"]["profiles"], list)

        non_admin_write = client.post(
            "/api/v1/admin/users",
            headers=scoped_headers,
            json={
                "user_id": f"blocked_{suffix}",
                "username": f"blocked_{suffix}",
                "email": f"blocked_{suffix}@example.com",
            },
        )
        assert non_admin_write.status_code == 403
        assert non_admin_write.json()["detail"]["code"] == "admin_required"

        revoke_key = client.delete(
            f"/api/v1/admin/api-keys/{managed_api_key_id}",
            headers=admin_headers,
        )
        assert revoke_key.status_code == 200
        managed_api_key_id = ""

        revoked_read = client.get("/api/v1/admin/profiles", headers=scoped_headers)
        assert revoked_read.status_code == 401
    finally:
        if managed_api_key_id:
            client.delete(
                f"/api/v1/admin/api-keys/{managed_api_key_id}",
                headers=admin_headers,
            )
        client.delete(f"/api/v1/admin/groups/{group_id}", headers=admin_headers)
        client.delete(f"/api/v1/admin/users/{user_id}", headers=admin_headers)
        client.close()
