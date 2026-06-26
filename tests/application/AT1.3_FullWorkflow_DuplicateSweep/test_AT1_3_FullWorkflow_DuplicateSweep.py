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

from tests.helpers.live_runtime import api_client, api_path
import pytest
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-20")


def test_at13_fullworkflow_duplicate_sweep() -> None:
    client, key = api_client()
    headers = {"x-api-key": key}

    response = client.post(
        api_path("/tools/mail_move_duplicates_since_last_search"),
        headers=headers,
        json={
            "profile_id": "gmail_personal",
            "query": "duplicate",
            "destination_folder": "Duplicates",
            "dry_run": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["result"]["result"]["dry_run"] is True
