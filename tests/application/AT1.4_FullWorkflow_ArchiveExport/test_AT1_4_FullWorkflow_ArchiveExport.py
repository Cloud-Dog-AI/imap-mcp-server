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

from pathlib import Path

from tests.helpers.live_runtime import api_client, api_path
import pytest
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-21")


def test_at14_fullworkflow_archive_export(tmp_path) -> None:
    client, key = api_client()
    headers = {"x-api-key": key, "x-role": "admin"}
    response = client.post(
        api_path("/admin/archive/export"),
        headers=headers,
        json={
            "archive_root": str(tmp_path / "archive"),
            "profile_id": "gmail_personal",
            "received_at": "2026-02-20T12:00:00Z",
            "message_id": "at14-message-1",
            "raw_eml": "Subject: test\n\nbody",
            "metadata": {"subject": "test"},
            "force": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    archive_path = Path(payload["result"]["path"])
    assert archive_path.exists()
    assert (archive_path / "message.eml").exists()
    assert (archive_path / "message.json").exists()
