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

# Covers: FR-08

import base64
import imaplib
import socket
import ssl
from dataclasses import dataclass

from imap_hub_core.storage_paths import storage_for_file_path


@dataclass(slots=True)
class IMAPConnectionConfig:
    """Normalised IMAP connection settings for a profile."""

    host: str
    port: int
    security: str
    timeout_seconds: int = 10
    ca_bundle_path: str | None = None
    allow_self_signed: bool = False


def validate_tls_policy(ca_bundle_path: str | None, allow_self_signed: bool) -> None:
    """Validate profile TLS policy before creating an IMAP session."""
    if allow_self_signed:
        return
    if ca_bundle_path is None:
        return
    storage, key = storage_for_file_path(ca_bundle_path)
    stat = storage.stat(key)
    if stat is None or stat.is_dir:
        raise FileNotFoundError(f"TLS CA bundle not found: {ca_bundle_path}")


def build_xoauth2_auth_string(username: str, access_token: str) -> str:
    """Build base64 encoded XOAUTH2 auth string for IMAP providers."""
    raw = f"user={username}\x01auth=Bearer {access_token}\x01\x01"
    return base64.b64encode(raw.encode("utf-8")).decode("ascii")


def probe_imap_connectivity(config: IMAPConnectionConfig) -> dict[str, str]:
    """Perform a lightweight connectivity probe for a profile endpoint."""
    validate_tls_policy(config.ca_bundle_path, config.allow_self_signed)

    context = ssl.create_default_context()
    if config.ca_bundle_path:
        context.load_verify_locations(cafile=config.ca_bundle_path)
    if config.allow_self_signed:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    if config.security == "ssl":
        with (
            socket.create_connection(
                (config.host, config.port), timeout=config.timeout_seconds
            ) as sock,
            context.wrap_socket(
                sock,
                server_hostname=config.host,
            ),
        ):
            return {"status": "ok", "mode": "ssl"}

    if config.security in {"starttls", "tls"}:
        with imaplib.IMAP4(
            host=config.host, port=config.port, timeout=config.timeout_seconds
        ) as client:
            client.starttls(ssl_context=context)
            return {"status": "ok", "mode": "starttls"}

    with socket.create_connection((config.host, config.port), timeout=config.timeout_seconds):
        return {"status": "ok", "mode": "plain"}
