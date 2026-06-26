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

import httpx
import pytest
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-04")


def test_at18_a2a_health_auth_flow(application_server) -> None:
    a2a_api_key = application_server.api_key

    with httpx.Client(base_url=application_server.a2a_base_url, timeout=30.0) as client:
        no_auth = client.get(f"{application_server.a2a_base_path}/health")
        wrong_auth = client.get(
            f"{application_server.a2a_base_path}/health",
            headers={"Authorization": "Bearer wrong-key"},
        )
        good_auth = client.get(
            f"{application_server.a2a_base_path}/health",
            headers={"Authorization": f"Bearer {a2a_api_key}"},
        )
        tools = client.get(
            f"{application_server.a2a_base_path}/tools",
            headers={
                "Authorization": f"Bearer {a2a_api_key}",
                "x-api-key": a2a_api_key,
            },
        )
        execute = client.post(
            f"{application_server.a2a_base_path}/tools/profile_list",
            headers={
                "Authorization": f"Bearer {a2a_api_key}",
                "x-api-key": a2a_api_key,
            },
            json={"include_disabled": False},
        )

    assert no_auth.status_code == 401
    assert wrong_auth.status_code == 401
    assert good_auth.status_code == 200
    payload = good_auth.json()
    assert payload.get("ok") is True
    assert payload.get("result", {}).get("interface") == "a2a"
    assert tools.status_code == 200
    assert isinstance(tools.json().get("result", {}).get("items", []), list)
    assert execute.status_code == 200
    assert execute.json().get("result", {}).get("ok") is True
