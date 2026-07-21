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
import json
import imaplib
import socket
import ssl
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from imap_hub_core.storage_paths import storage_for_file_path


_HTTPS_PREFIX = "https" + "://"
DEFAULT_OAUTH_TOKEN_URI = _HTTPS_PREFIX + "oauth2.googleapis.com/token"


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
    return base64.b64encode(build_xoauth2_auth_bytes(username, access_token)).decode("ascii")


def build_xoauth2_auth_bytes(username: str, access_token: str) -> bytes:
    """Build the raw SASL XOAUTH2 response expected by ``imaplib.authenticate``."""
    return f"user={username}\x01auth=Bearer {access_token}\x01\x01".encode("utf-8")


def load_oauth_state_sidecar(
    profile_id: str,
    *,
    state_dir: str | None = None,
) -> dict[str, str]:
    """Load the allow-listed durable OAuth grant fields for one profile."""
    safe_profile_id = profile_id.strip()
    if not safe_profile_id or any(
        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
        for character in safe_profile_id
    ):
        return {}
    root = Path(
        state_dir
        or "/app/logs"
    )
    path = root / f"gmail_oauth_state-{safe_profile_id}.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(raw, dict):
        return {}

    field_map = {
        "account_email": "IMAP_MCP_GMAIL_USER_EMAIL",
        "refresh_token": "IMAP_MCP_GMAIL_REFRESH_TOKEN",
        "redirect_uri": "IMAP_MCP_GMAIL_REDIRECT_URI",
        "token_uri": "IMAP_MCP_GMAIL_TOKEN_URI",
        "oauth_scope": "IMAP_MCP_GMAIL_OAUTH_SCOPE",
        "client_id": "IMAP_MCP_GMAIL_CLIENT_ID",
    }
    return {
        field: value.strip()
        for field, source_key in field_map.items()
        if isinstance((value := raw.get(source_key)), str) and value.strip()
    }


def refresh_oauth_access_token(
    *,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    token_uri: str,
    timeout: float = 30.0,
) -> str:
    """Exchange a durable OAuth refresh token for a short-lived access token."""
    if not token_uri.lower().startswith(_HTTPS_PREFIX):
        raise ValueError("OAuth token URI must use HTTPS.")
    required = {
        "client_id": client_id.strip(),
        "client_secret": client_secret.strip(),
        "refresh_token": refresh_token.strip(),
    }
    missing = [name for name, value in required.items() if not value or value.startswith("$")]
    if missing:
        raise ValueError(f"OAuth profile is missing resolved fields: {', '.join(missing)}")

    payload = urllib.parse.urlencode({
        **required,
        "grant_type": "refresh_token",
    }).encode("utf-8")
    request = urllib.request.Request(
        token_uri,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        body = json.loads(response.read().decode("utf-8"))
    access_token = str(body.get("access_token", "")).strip()
    if not access_token:
        raise RuntimeError("OAuth refresh response missing access_token")
    return access_token


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
