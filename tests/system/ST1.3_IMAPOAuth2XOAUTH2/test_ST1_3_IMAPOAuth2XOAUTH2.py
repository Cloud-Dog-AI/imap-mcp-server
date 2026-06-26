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
import os
import ssl
from pathlib import Path

from imap_hub_core.imap.connection import build_xoauth2_auth_string
import pytest


def _vault_gaps_text() -> str:
    for candidate in (Path("VAULT-GAPS.md"), Path("archive/VAULT-GAPS.md")):
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    raise FileNotFoundError("VAULT-GAPS.md not found in project root or archive/")
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-08")


def test_st13_imap_oauth2_xoauth2_flow() -> None:
    host = os.environ.get("IMAP_OAUTH2_HOST", "").strip()
    username = os.environ.get("IMAP_OAUTH2_USERNAME", "").strip()
    access_token = os.environ.get("IMAP_OAUTH2_ACCESS_TOKEN", "").strip()
    security = os.environ.get("IMAP_OAUTH2_SECURITY", "ssl").strip().lower() or "ssl"
    port = int(os.environ.get("IMAP_OAUTH2_PORT", "993"))

    if not host or not username or not access_token:
        gap_text = _vault_gaps_text()
        assert "ST1.3 XOAUTH2 runtime gap" in gap_text
        return

    auth_string = build_xoauth2_auth_string(username=username, access_token=access_token).encode(
        "ascii"
    )
    callback = lambda _: auth_string  # noqa: E731

    if security == "ssl":
        with imaplib.IMAP4_SSL(host=host, port=port, timeout=15) as client:
            status, _ = client.authenticate("XOAUTH2", callback)
            assert status == "OK"
            client.logout()
        return

    with imaplib.IMAP4(host=host, port=port, timeout=15) as client:
        if security in {"starttls", "tls"}:
            client.starttls(ssl_context=ssl.create_default_context())
        status, _ = client.authenticate("XOAUTH2", callback)
        assert status == "OK"
        client.logout()
