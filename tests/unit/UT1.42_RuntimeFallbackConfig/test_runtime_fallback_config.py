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

# Covers: FR-02

import pytest

from imap_hub_core.tools.handlers import ImapToolHandlers


def _fallback_profile() -> dict[str, object]:
    return {
        "imap": {
            "host": "mail.cloud-dog.net",
            "port": 143,
            "security": "starttls",
            "tls": {"ca_bundle_path": "", "allow_self_signed": False},
        },
        "credentials": {
            "username": "operations@cloud-dog.net",
            "password": "<password>",
        },
    }
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-02")


def test_runtime_fallback_uses_resolved_config_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing profile credentials fall back to the resolved operations config, not env."""
    monkeypatch.setenv("IMAP_OPERATIONS_HOST", "wrong.example.invalid")
    monkeypatch.setenv("IMAP_OPERATIONS_PORT", "993")
    monkeypatch.setenv("IMAP_OPERATIONS_USERNAME", "wrong-user")
    monkeypatch.setenv("IMAP_OPERATIONS_PASSWORD", "wrong-password")

    handlers = ImapToolHandlers(
        profiles={
            "gmail_personal": {
                "imap": {"host": "imap.gmail.com", "port": 993, "security": "ssl"},
                "auth": {"mode": "oauth2"},
                "credentials": {},
            }
        },
        runtime_fallback_profile=_fallback_profile(),
    )

    resolved = handlers._resolve_connection(handlers._profile("gmail_personal"))

    assert resolved.host == "mail.cloud-dog.net"
    assert resolved.port == 143
    assert resolved.security == "starttls"
    assert resolved.username == "operations@cloud-dog.net"
    assert resolved.password == "resolved-unit-password"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-02")


def test_runtime_fallback_refuses_incomplete_config() -> None:
    """Fallback must fail closed before any IMAP connection can be attempted."""
    handlers = ImapToolHandlers(
        profiles={
            "broken": {
                "imap": {"host": "", "port": 143, "security": "starttls"},
                "auth": {"mode": "app_password"},
                "credentials": {},
            }
        },
        runtime_fallback_profile={
            "imap": {"host": "mail.cloud-dog.net", "port": 143, "security": "starttls"},
            "credentials": {"username": "operations@cloud-dog.net", "password": ""},
        },
    )

    with pytest.raises(ValueError, match="runtime fallback is not configured"):
        handlers._resolve_connection(handlers._profile("broken"))
