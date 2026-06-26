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
import ssl
from contextlib import suppress

import pytest

from tests.helpers.live_runtime import runtime_imap_settings
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-05")


def test_it111_real_imap_sync_flow() -> None:
    settings = runtime_imap_settings()
    if not settings.host:
        pytest.fail("Missing IMAP runtime host: set IMAP_OPERATIONS_HOST via Vault/env.")
    if not settings.username or not settings.password:
        pytest.fail(
            "Missing IMAP runtime credentials: set IMAP_OPERATIONS_USERNAME and IMAP_OPERATIONS_PASSWORD via Vault/env."
        )

    client: imaplib.IMAP4 | imaplib.IMAP4_SSL
    if settings.port == 993:
        client = imaplib.IMAP4_SSL(host=settings.host, port=settings.port, timeout=15)
    else:
        client = imaplib.IMAP4(host=settings.host, port=settings.port, timeout=15)
        client.starttls(ssl_context=ssl.create_default_context())

    try:
        login_status, _ = client.login(settings.username, settings.password)
        assert login_status == "OK"

        list_status, mailboxes = client.list()
        assert list_status == "OK"
        assert mailboxes

        select_status, _ = client.select("INBOX", readonly=True)
        assert select_status == "OK"

        search_status, data = client.search(None, "ALL")
        assert search_status == "OK"
        if not data or not data[0]:
            pytest.fail("INBOX contains no messages to fetch headers from.")

        first_id = data[0].split()[0]
        fetch_status, fetched = client.fetch(
            first_id, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])"
        )
        assert fetch_status == "OK"
        assert any(
            isinstance(item, tuple) and bool(item[1]) for item in fetched if item is not None
        )
    finally:
        with suppress(Exception):
            client.logout()
