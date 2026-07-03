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

import imaplib

from tests.helpers.live_runtime import runtime_imap_settings
import pytest
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-05")


def test_st113_real_imap_login_search_fetch() -> None:
    """Connect to real IMAP, login, search INBOX, fetch real messages."""
    settings = runtime_imap_settings()

    assert settings.host, "IMAP host not configured"
    assert settings.username, "IMAP username not configured"
    assert settings.password, "IMAP password not configured — source env-public"

    client: imaplib.IMAP4 | None = None
    try:
        # 1. Connect
        client = imaplib.IMAP4(host=settings.host, port=settings.port, timeout=30)

        # 2. STARTTLS
        client.starttls()

        # 3. Login with REAL credentials
        status, _ = client.login(settings.username, settings.password)
        assert status == "OK", "IMAP login failed: %s" % status

        # 4. Select INBOX (readonly)
        status, count_data = client.select("INBOX", readonly=True)
        assert status == "OK", "INBOX select failed: %s" % status
        message_count = int(count_data[0].decode())
        assert message_count > 0, "INBOX is empty — expected real messages"

        # 5. Search ALL messages
        status, search_data = client.search(None, "ALL")
        assert status == "OK", "IMAP SEARCH failed: %s" % status
        all_ids = search_data[0].split()
        assert len(all_ids) > 0, "SEARCH returned 0 results"

        # 6. Fetch the LAST message headers
        last_id = all_ids[-1]
        status, msg_data = client.fetch(last_id, "(BODY[HEADER.FIELDS (SUBJECT FROM DATE)])")
        assert status == "OK", "FETCH failed for message %s" % last_id.decode()
        assert msg_data[0] is not None, "FETCH returned no data"

        raw_headers = msg_data[0][1].decode(errors="replace")
        assert "Subject:" in raw_headers or "From:" in raw_headers or "Date:" in raw_headers, (
            "FETCH returned data but no recognisable headers: %s" % raw_headers[:200]
        )

        # 7. Fetch the LAST message body (full RFC822)
        status, body_data = client.fetch(last_id, "(RFC822)")
        assert status == "OK", "Full FETCH failed for message %s" % last_id.decode()
        raw_bytes = body_data[0][1]
        assert len(raw_bytes) > 50, "Message body too small (%d bytes) — likely not real" % len(
            raw_bytes
        )

    finally:
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass
