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

import base64
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


def test_it114_real_imap_attachment_download_content(integration_server) -> None:
    with httpx.Client(base_url=integration_server.api_base_url, timeout=API_TIMEOUT) as client:
        uid, attachments = find_or_seed_attachment_message(
            client,
            integration_server.api_key,
            integration_server.api_base_path,
            profile_id="operations",
            folder="INBOX",
        )
        part_id = str(attachments[0].get("part_id", "")).strip()
        assert part_id, f"Attachment part_id missing for UID {uid}"

        download = _call_tool(
            client,
            integration_server.api_key,
            integration_server.api_base_path,
            "mail_download_attachment",
            {
                "profile_id": "operations",
                "uid": uid,
                "part_id": part_id,
                "folder": "INBOX",
            },
        )
        content = str(download.get("content", ""))
        encoding = str(download.get("content_encoding", "")).strip().lower()
        size_bytes = int(download.get("size_bytes", 0) or 0)

        assert content, f"mail_download_attachment returned empty content for UID {uid}"
        assert size_bytes > 0, (
            f"mail_download_attachment returned invalid size for UID {uid}: {size_bytes}"
        )
        assert encoding in {"text", "base64"}, f"Unsupported attachment encoding '{encoding}'"

        if encoding == "text":
            assert any(ch.isprintable() for ch in content), (
                "Text attachment content is not readable"
            )
        else:
            decoded = base64.b64decode(content, validate=True)
            assert len(decoded) > 0, "Base64 attachment content decodes to zero bytes"
