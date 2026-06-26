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

# Covers: FR-05

from tests.helpers.live_runtime import api_client, api_path
import pytest
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-05")


def test_at11_fullworkflow_sync_search_retrieve() -> None:
    client, key = api_client()
    headers = {"x-api-key": key, "x-role": "admin"}

    search = client.post(
        api_path("/tools/mail_search"),
        headers=headers,
        json={"profile_id": "gmail_personal", "mode": "cache", "query": "status", "filters": {}},
    )
    assert search.status_code == 200
    assert search.json()["result"]["ok"] is True

    profile = client.get(api_path("/admin/profiles/gmail_personal"), headers=headers)
    assert profile.status_code == 200
