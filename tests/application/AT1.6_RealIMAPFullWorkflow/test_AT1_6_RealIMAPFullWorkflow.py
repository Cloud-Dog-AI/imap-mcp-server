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
@pytest.mark.req("FR-05")


def test_at16_real_imap_full_workflow() -> None:
    """Full workflow: search real mail, delta search, probe connectivity."""
    client, key = api_client()
    headers = {"x-api-key": key, "x-role": "admin"}

    # ── Step 1: Search real INBOX ─────────────────────────────────────
    search_resp = client.post(
        api_path("/tools/mail_search"),
        headers=headers,
        json={
            "profile_id": "operations",
            "mode": "imap",
            "query": "ALL",
            "filters": {"folder": "INBOX"},
        },
    )
    assert search_resp.status_code == 200
    search_payload = search_resp.json()["result"]
    assert search_payload["ok"] is True, "mail_search failed: %s" % search_payload.get("errors")

    messages = search_payload.get("result", {}).get("messages", [])
    assert len(messages) > 0, "ZERO messages — handler did NOT connect to real IMAP"

    # Verify message structure has real data
    first = messages[0]
    assert first.get("subject"), "First message has no subject — not real"
    assert first.get("from"), "First message has no from — not real"
    assert first.get("uid"), "First message has no uid — not real"

    # ── Step 2: Delta search (since last) ─────────────────────────────
    delta_resp = client.post(
        api_path("/tools/mail_search_since_last"),
        headers=headers,
        json={
            "profile_id": "operations",
            "mode": "imap",
            "query": "ALL",
            "filters": {"folder": "INBOX"},
        },
    )
    assert delta_resp.status_code == 200
    delta_payload = delta_resp.json()["result"]
    assert delta_payload["ok"] is True, "delta search failed: %s" % delta_payload.get("errors")
    # Delta should reference a baseline from Step 1
    delta_result = delta_payload.get("result", {})
    assert delta_result.get("baseline") is not None, "Delta has no baseline reference"

    # ── Step 3: Tool catalogue lists mail tools ─────────────────────────
    tools_resp = client.get(api_path("/tools"), headers=headers)
    assert tools_resp.status_code == 200
    tools_payload = tools_resp.json()
    items = tools_payload.get("result", {}).get("items", [])
    tool_names = [t.get("name", "") for t in items]
    assert any("mail_search" in n for n in tool_names), (
        "mail_search not in tool catalogue: %s" % tool_names
    )

    # ── Step 4: Profile listing works ─────────────────────────────────
    profiles_resp = client.get(api_path("/admin/profiles"), headers=headers)
    assert profiles_resp.status_code == 200
