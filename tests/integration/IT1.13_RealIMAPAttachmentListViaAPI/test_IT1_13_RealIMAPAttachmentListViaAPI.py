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

from typing import Any

import httpx

from tests.helpers.attachment_seed import find_or_seed_attachment_message
import pytest


API_TIMEOUT = 60.0


def _call_tool(
    client: httpx.Client,
    api_key: str,
    api_base_path: str,
    tool_name: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    response = client.post(
        f"{api_base_path}/tools/{tool_name}",
        headers={"x-api-key": api_key},
        json=payload,
    )
    assert response.status_code == 200, f"{tool_name} returned HTTP {response.status_code}"
    result = response.json().get("result", {})
    assert result.get("ok") is True, f"{tool_name} failed: {result.get('errors', [])}"
    payload_result = result.get("result", {})
    assert isinstance(payload_result, dict), f"{tool_name} returned non-dict result"
    return payload_result
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-05")


def test_it113_real_imap_attachment_list_json_shape(integration_server) -> None:
    with httpx.Client(base_url=integration_server.api_base_url, timeout=API_TIMEOUT) as client:
        uid, attachments = find_or_seed_attachment_message(
            client,
            integration_server.api_key,
            integration_server.api_base_path,
            profile_id="operations",
            folder="INBOX",
        )
        first = attachments[0]
        part_id = str(first.get("part_id", "")).strip()
        filename = str(first.get("filename", "")).strip()
        content_type = str(first.get("content_type", "")).strip()
        size = int(first.get("size", first.get("size_bytes", 0)) or 0)

        assert part_id, f"Attachment part_id missing for UID {uid}"
        assert filename, f"Attachment filename missing for UID {uid}"
        assert content_type, f"Attachment content_type missing for UID {uid}"
        assert size > 0, f"Attachment size invalid for UID {uid}: {size}"
