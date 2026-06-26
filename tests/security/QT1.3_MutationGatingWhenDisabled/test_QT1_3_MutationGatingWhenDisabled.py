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
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-06")


def test_qt13_mutation_gating_when_disabled() -> None:
    client, key = api_client()
    response = client.post(
        api_path("/tools/mail_delete_messages"),
        headers={"x-api-key": key},
        json={"profile_id": "operations_cloud_dog", "uids": ["1"], "folder": "INBOX"},
    )
    assert response.status_code == 200
    payload = response.json()["result"]
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "write_disabled"
