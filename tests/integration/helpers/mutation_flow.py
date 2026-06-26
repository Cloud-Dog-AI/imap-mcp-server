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
import time
from contextlib import suppress
from email.utils import formatdate
from typing import Any

import httpx

from tests.helpers.live_runtime import runtime_imap_settings


def imap_login() -> imaplib.IMAP4 | imaplib.IMAP4_SSL:
    """Create a real IMAP connection and authenticate with runtime settings."""
    settings = runtime_imap_settings()
    if not settings.host or not settings.username or not settings.password:
        raise RuntimeError("Missing runtime IMAP credentials for mutation flow tests.")

    if settings.port == 993:
        client: imaplib.IMAP4 | imaplib.IMAP4_SSL = imaplib.IMAP4_SSL(
            host=settings.host,
            port=settings.port,
            timeout=15,
        )
    else:
        client = imaplib.IMAP4(host=settings.host, port=settings.port, timeout=15)
        client.starttls(ssl_context=ssl.create_default_context())

    status, _ = client.login(settings.username, settings.password)
    if status != "OK":
        raise RuntimeError(f"IMAP login failed with status={status}")
    return client


def send_seed_message(subject: str, body: str) -> None:
    """Append a seed message into INBOX for mutation tests."""
    settings = runtime_imap_settings()
    if not settings.username:
        raise RuntimeError("Missing runtime IMAP username for mutation flow tests.")

    client = imap_login()
    try:
        raw = (
            f"From: {settings.username}\r\n"
            f"To: {settings.username}\r\n"
            f"Subject: {subject}\r\n"
            f"Date: {formatdate(localtime=True)}\r\n"
            "\r\n"
            f"{body}\r\n"
        ).encode("utf-8")
        status, _ = client.append("INBOX", None, None, raw)
        if status != "OK":
            raise RuntimeError(f"IMAP APPEND failed with status={status}")
    finally:
        with suppress(Exception):
            client.logout()


def search_uid_via_api(
    client: httpx.Client,
    integration_server: Any,
    profile_id: str,
    subject: str,
    *,
    folder: str = "INBOX",
    timeout_seconds: float = 120.0,
) -> str:
    """Find a message UID by subject via live API search."""
    deadline = time.monotonic() + timeout_seconds
    headers = {"x-api-key": integration_server.api_key}
    while time.monotonic() < deadline:
        response = client.post(
            integration_server.api_path("/tools/mail_search"),
            headers=headers,
            json={
                "profile_id": profile_id,
                "mode": "imap",
                "query": "ALL",
                "filters": {"folder": folder},
            },
        )
        if response.status_code != 200:
            time.sleep(1.0)
            continue
        envelope = response.json().get("result", {})
        if envelope.get("ok") is not True:
            time.sleep(1.0)
            continue
        messages = envelope.get("result", {}).get("messages", [])
        if isinstance(messages, list):
            for item in messages:
                if not isinstance(item, dict):
                    continue
                if subject in str(item.get("subject", "")):
                    uid = str(item.get("uid", "")).strip()
                    if uid:
                        return uid
        time.sleep(2.0)
    raise AssertionError("Timed out waiting for seed message to appear in API search results.")


def search_uid_via_imap(
    subject: str,
    *,
    folder: str = "INBOX",
    timeout_seconds: float = 60.0,
) -> str:
    """Find a seeded message UID directly via real IMAP for mutation setup flows."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        client = None
        try:
            client = imap_login()
            uids = search_uids_in_folder(client, folder, subject)
            if uids:
                return uids[-1]
        finally:
            with suppress(Exception):
                if client is not None:
                    client.logout()
        time.sleep(2.0)
    raise AssertionError("Timed out waiting for seed message to appear in IMAP search results.")


def subject_present_via_api(
    client: httpx.Client,
    integration_server: Any,
    profile_id: str,
    subject: str,
    *,
    folder: str = "INBOX",
) -> bool:
    """Check whether a subject is present in API search results."""
    response = client.post(
        integration_server.api_path("/tools/mail_search"),
        headers={"x-api-key": integration_server.api_key},
        json={
            "profile_id": profile_id,
            "mode": "imap",
            "query": "ALL",
            "filters": {"folder": folder},
        },
    )
    if response.status_code != 200:
        return False
    envelope = response.json().get("result", {})
    if envelope.get("ok") is not True:
        return False
    messages = envelope.get("result", {}).get("messages", [])
    if not isinstance(messages, list):
        return False
    return any(subject in str(item.get("subject", "")) for item in messages if isinstance(item, dict))


def search_uids_in_folder(
    imap_client: imaplib.IMAP4 | imaplib.IMAP4_SSL,
    folder: str,
    subject: str,
) -> list[str]:
    """Find message UIDs by subject in a concrete IMAP folder."""
    select_status, _ = imap_client.select(folder, readonly=True)
    if select_status != "OK":
        return []
    search_status, data = imap_client.uid("SEARCH", None, "HEADER", "Subject", subject)
    if search_status != "OK" or not data or not data[0]:
        return []
    return [token.decode("utf-8", "ignore") for token in data[0].split() if token]


def message_has_seen_flag(
    imap_client: imaplib.IMAP4 | imaplib.IMAP4_SSL,
    uid: str,
    *,
    folder: str = "INBOX",
    timeout_seconds: float = 20.0,
) -> bool:
    """Read current \\Seen state for a message with short retry budget."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        select_status, _ = imap_client.select(folder, readonly=True)
        if select_status != "OK":
            time.sleep(0.5)
            continue
        status, data = imap_client.uid("FETCH", uid, "(FLAGS)")
        if status == "OK":
            return "\\Seen" in str(data)
        time.sleep(0.5)
    raise AssertionError(f"Unable to fetch message flags for uid={uid}")
