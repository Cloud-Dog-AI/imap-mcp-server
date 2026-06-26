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
import pytest
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-07")


def test_it19_delta_search_via_api(integration_server) -> None:
    with httpx.Client(base_url=integration_server.api_base_url, timeout=30.0) as client:
        first = client.post(
            integration_server.api_path("/tools/mail_search"),
            headers={"x-api-key": integration_server.api_key},
            json={
                "profile_id": "gmail_personal",
                "query": "invoice",
                "mode": "cache",
                "filters": {},
            },
        )
    assert first.status_code == 200
    first_payload = first.json()["result"]
    assert first_payload["ok"] is True

    with httpx.Client(base_url=integration_server.api_base_url, timeout=30.0) as client:
        second = client.post(
            integration_server.api_path("/tools/mail_search_since_last"),
            headers={"x-api-key": integration_server.api_key},
            json={
                "profile_id": "gmail_personal",
                "query": "invoice",
                "mode": "cache",
                "filters": {},
            },
        )
    assert second.status_code == 200
    second_payload = second.json()["result"]
    assert second_payload["ok"] is True
