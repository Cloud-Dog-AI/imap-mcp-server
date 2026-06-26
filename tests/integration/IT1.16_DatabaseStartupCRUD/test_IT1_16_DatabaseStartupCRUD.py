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

from uuid import uuid4

from tests.helpers.live_runtime import api_client, api_path
import pytest
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-23")


def test_it116_database_startup_and_profile_crud() -> None:
    client, key = api_client()
    headers = {"x-api-key": key, "Authorization": f"Bearer {key}", "x-role": "admin"}
    profile_id = f"it16_profile_{uuid4().hex[:8]}"

    health = client.get("/health")
    assert health.status_code == 200

    create = client.put(
        api_path(f"/admin/profiles/{profile_id}"),
        headers=headers,
        json={"provider": "imap_generic", "enabled": True},
    )
    assert create.status_code == 200

    fetch = client.get(api_path(f"/admin/profiles/{profile_id}"), headers=headers)
    assert fetch.status_code == 200
    assert fetch.json()["result"]["provider"] == "imap_generic"

    delete = client.delete(api_path(f"/admin/profiles/{profile_id}"), headers=headers)
    assert delete.status_code == 200
