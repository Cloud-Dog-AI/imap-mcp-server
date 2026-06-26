"""imap-mcp-server module."""

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
from dataclasses import dataclass

from imap_hub_core.imap.connection import IMAPConnectionConfig, validate_tls_policy


@dataclass(slots=True)
class IMAPCredentials:
    """Credentials for IMAP login."""

    username: str
    password: str


def build_ssl_context(config: IMAPConnectionConfig) -> ssl.SSLContext:
    """Create TLS context for IMAP connections from profile policy."""
    validate_tls_policy(config.ca_bundle_path, config.allow_self_signed)
    context = ssl.create_default_context()
    if config.ca_bundle_path:
        context.load_verify_locations(cafile=config.ca_bundle_path)
    if config.allow_self_signed:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


def open_authenticated_client(
    config: IMAPConnectionConfig,
    credentials: IMAPCredentials,
    folder: str = "INBOX",
    readonly: bool = True,
) -> imaplib.IMAP4 | imaplib.IMAP4_SSL:
    """Open an authenticated IMAP client and select the target folder."""
    context = build_ssl_context(config)
    client: imaplib.IMAP4 | imaplib.IMAP4_SSL
    if config.security == "ssl":
        client = imaplib.IMAP4_SSL(
            host=config.host,
            port=config.port,
            timeout=config.timeout_seconds,
            ssl_context=context,
        )
    else:
        client = imaplib.IMAP4(host=config.host, port=config.port, timeout=config.timeout_seconds)
        if config.security in {"starttls", "tls"}:
            client.starttls(ssl_context=context)

    status, _ = client.login(credentials.username, credentials.password)
    if status != "OK":
        client.logout()
        raise RuntimeError(f"IMAP login failed: {status}")

    select_status, _ = client.select(folder, readonly=readonly)
    if select_status != "OK":
        client.logout()
        raise RuntimeError(f"IMAP select failed: {select_status}")
    return client
