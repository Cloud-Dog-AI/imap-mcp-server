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
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-05")


def test_it112_real_imap_search_via_api() -> None:
    """Call mail_search through HTTP API and verify real IMAP messages returned."""
    client, key = api_client()
    headers = {"x-api-key": key}

    response = client.post(
        api_path("/tools/mail_search"),
        headers=headers,
        json={
            "profile_id": "gmail_personal",
            "mode": "imap",
            "query": "ALL",
            "filters": {"folder": "INBOX"},
        },
    )
    assert response.status_code == 200, "API returned %d" % response.status_code

    payload = response.json()
    result = payload.get("result", {})
    assert result.get("ok") is True, "mail_search not ok: %s" % result.get("errors", [])

    messages = result.get("result", {}).get("messages", [])
    assert len(messages) > 0, (
        "mail_search returned 0 messages — handler is NOT connecting to real IMAP"
    )

    # Verify first message has real content
    first = messages[0]
    assert "subject" in first, "Message missing 'subject' field"
    assert "from" in first, "Message missing 'from' field"
    assert "uid" in first, "Message missing 'uid' field"
    assert first["subject"], "Subject is empty — not a real message"
    assert first["from"], "From is empty — not a real message"

    # Verify we got multiple messages (INBOX has 2758+)
    assert len(messages) >= 10, "Only %d messages returned — real INBOX has thousands" % len(
        messages
    )
