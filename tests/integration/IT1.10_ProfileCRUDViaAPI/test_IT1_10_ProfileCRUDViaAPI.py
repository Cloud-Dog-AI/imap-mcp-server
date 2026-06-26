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

import httpx
from uuid import uuid4
import pytest
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-03")


def test_it110_profile_crud_via_api(integration_server) -> None:
    profile_name = f"test_profile_{uuid4().hex[:8]}"
    scoped_user_id = f"test_profile_user_{uuid4().hex[:8]}"
    headers = {
        "x-api-key": integration_server.api_key,
        "Authorization": f"Bearer {integration_server.api_key}",
        "x-role": "admin",
    }
    with httpx.Client(base_url=integration_server.api_base_url, timeout=30.0) as client:
        create_user = client.post(
            integration_server.api_path("/admin/users"),
            headers=headers,
            json={
                "user_id": scoped_user_id,
                "username": scoped_user_id,
                "email": f"{scoped_user_id}@example.com",
                "role": "viewer",
            },
        )
        assert create_user.status_code == 200
        create_key = client.post(
            integration_server.api_path("/admin/api-keys"),
            headers=headers,
            json={
                "owner_user_id": scoped_user_id,
                "scopes": ["profiles:read"],
                "description": "IT1.10 read-only profile key",
            },
        )
        assert create_key.status_code == 200
        raw_scoped_key = create_key.json()["result"]["raw_key"]
        scoped_key_id = create_key.json()["result"]["api_key_id"]
        non_admin_headers = {
            "x-api-key": raw_scoped_key,
            "Authorization": f"Bearer {raw_scoped_key}",
        }
        denied = client.put(
            integration_server.api_path(f"/admin/profiles/{profile_name}-denied"),
            headers=non_admin_headers,
            json={"provider": "imap_generic"},
        )
        create = client.put(
            integration_server.api_path(f"/admin/profiles/{profile_name}"),
            headers=headers,
            json={"provider": "imap_generic"},
        )
        assert denied.status_code == 403
        assert denied.json().get("detail", {}).get("code") == "admin_required"
        assert create.status_code == 200
        fetch = client.get(
            integration_server.api_path(f"/admin/profiles/{profile_name}"), headers=headers
        )
        assert fetch.status_code == 200
        assert fetch.json()["result"]["provider"] == "imap_generic"
        delete = client.delete(
            integration_server.api_path(f"/admin/profiles/{profile_name}"), headers=headers
        )
        assert delete.status_code == 200
        revoke = client.delete(
            integration_server.api_path(f"/admin/api-keys/{scoped_key_id}"),
            headers=headers,
        )
        assert revoke.status_code == 200
        delete_user = client.delete(
            integration_server.api_path(f"/admin/users/{scoped_user_id}"),
            headers=headers,
        )
        assert delete_user.status_code == 200
