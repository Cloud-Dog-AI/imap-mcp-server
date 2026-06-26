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

# Covers: FR-03
# Covers: FR-05

from imap_hub_core.audit.context import AuditRequestContext, reset_audit_request_context, set_audit_request_context
from imap_hub_core.tools.handlers import ImapToolHandlers
import pytest
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-03")


def test_ut138_mail_headlines_uses_profile_retention_defaults(monkeypatch) -> None:
    handlers = ImapToolHandlers(
        profiles={
            "spam-profile": {
                "sync": {
                    "retention": {
                        "max_age_days": 14,
                        "max_messages": 200,
                    }
                }
            }
        },
        max_search_results=200,
    )
    captured: dict[str, object] = {}

    def _fake_search_live_messages(
        *,
        profile_id: str,
        query: str,
        folder: str = "INBOX",
        limit: int = 50,
    ) -> tuple[list[dict[str, str]], dict[str, str], list[str]]:
        captured["profile_id"] = profile_id
        captured["query"] = query
        captured["folder"] = folder
        captured["limit"] = limit
        return (
            [
                {
                    "uid": "10",
                    "subject": "Spam subject",
                    "from": "ops@example.com",
                    "date_utc": "2026-01-01T00:00:00Z",
                }
            ],
            {"per_folder_uid_max": {folder: 10}},
            ["10"],
        )

    monkeypatch.setattr(handlers, "_search_live_messages", _fake_search_live_messages)

    token = set_audit_request_context(
        AuditRequestContext(
            correlation_id="ut138-profile-search-defaults",
            actor_id="unit-admin",
            roles=["admin"],
            source_identifier="unit-test",
            component="unit-test",
            server_id="imap-mcp-unit",
            environment="test",
        )
    )
    try:
        result = handlers.mail_headlines(
            {
                "profile_id": "spam-profile",
                "mode": "imap",
                "query": "",
                "filters": {"folder": "SPAM"},
            }
        )
    finally:
        reset_audit_request_context(token)

    assert result["ok"] is True
    assert captured["profile_id"] == "spam-profile"
    assert captured["folder"] == "SPAM"
    assert captured["limit"] == 200
    assert str(captured["query"]).startswith("SINCE ")
    assert result["result"]["effective_limit"] == 200
    assert result["result"]["count"] == 1
