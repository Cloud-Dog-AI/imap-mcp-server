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

from imap_hub_core.audit.context import AuditRequestContext, reset_audit_request_context, set_audit_request_context
from imap_hub_core.tools.handlers import ImapToolHandlers
import pytest
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-07")


def test_st19_search_ledger_record() -> None:
    handlers = ImapToolHandlers(profiles={"p1": {}})
    token = set_audit_request_context(
        AuditRequestContext(
            correlation_id="st19-search-ledger",
            actor_id="system-test",
            roles=["admin"],
            source_identifier="system-test",
            component="system-test",
            server_id="imap-mcp-st",
            environment="test",
        )
    )
    try:
        handlers.mail_search({"profile_id": "p1", "mode": "cache", "query": "new mail", "filters": {}})
        delta = handlers.mail_search_since_last(
            {"profile_id": "p1", "mode": "cache", "query": "new mail", "filters": {}}
        )
    finally:
        reset_audit_request_context(token)
    assert delta["ok"] is True
    assert delta["result"]["baseline"] is not None
