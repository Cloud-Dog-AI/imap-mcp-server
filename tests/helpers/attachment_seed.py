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

"""Helpers to guarantee a real attachment message for IMAP integration tests."""

from __future__ import annotations

import smtplib
import ssl
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formatdate
from typing import Any

import httpx

from tests.helpers.live_runtime import runtime_imap_settings


def _call_tool(
    client: httpx.Client,
    api_key: str,
    api_base_path: str,
    tool_name: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    response = client.post(
        f"{api_base_path}/tools/{tool_name}",
        headers={"x-api-key": api_key},
        json=payload,
    )
    assert response.status_code == 200, f"{tool_name} returned HTTP {response.status_code}"
    result = response.json().get("result", {})
    assert result.get("ok") is True, f"{tool_name} failed: {result.get('errors', [])}"
    payload_result = result.get("result", {})
    assert isinstance(payload_result, dict), f"{tool_name} returned non-dict result"
    return payload_result


def _sorted_uid_desc(messages: list[dict[str, Any]]) -> list[str]:
    return [
        str(item.get("uid"))
        for item in sorted(
            messages,
            key=lambda msg: int(str(msg.get("uid", "0")) or "0"),
            reverse=True,
        )
        if str(item.get("uid", "")).isdigit()
    ]


def _list_attachments_for_uid(
    client: httpx.Client,
    api_key: str,
    api_base_path: str,
    profile_id: str,
    folder: str,
    uid: str,
) -> list[dict[str, Any]]:
    listing = _call_tool(
        client,
        api_key,
        api_base_path,
        "mail_list_attachments",
        {
            "profile_id": profile_id,
            "uid": uid,
            "folder": folder,
        },
    )
    attachments = listing.get("attachments", [])
    assert isinstance(attachments, list), f"mail_list_attachments returned non-list for UID {uid}"
    return attachments


def _send_seed_attachment_message(subject: str) -> None:
    settings = runtime_imap_settings()
    if not settings.host or not settings.username or not settings.password:
        raise RuntimeError("Missing IMAP runtime settings for attachment seed message.")

    message = EmailMessage()
    message["From"] = settings.username
    message["To"] = settings.username
    message["Date"] = formatdate(localtime=True)
    message["Subject"] = subject
    message.set_content("W24A attachment seed message for real IMAP integration tests.")
    message.add_attachment(
        b"w24a-seed-attachment-payload\n",
        maintype="text",
        subtype="plain",
        filename="w24a-seed.txt",
    )

    # Try authenticated SMTP delivery first, then fallback to unauthenticated relay.
    errors: list[str] = []
    candidates = [
        {"port": 587, "starttls": True, "ssl": False, "auth": True},
        {"port": 465, "starttls": False, "ssl": True, "auth": True},
        {"port": 25, "starttls": False, "ssl": False, "auth": False},
    ]
    for candidate in candidates:
        try:
            if candidate["ssl"]:
                with smtplib.SMTP_SSL(
                    settings.host,
                    candidate["port"],
                    timeout=20,
                    context=ssl.create_default_context(),
                ) as smtp:
                    if candidate["auth"]:
                        smtp.login(settings.username, settings.password)
                    smtp.send_message(message)
            else:
                with smtplib.SMTP(settings.host, candidate["port"], timeout=20) as smtp:
                    smtp.ehlo()
                    if candidate["starttls"]:
                        smtp.starttls(context=ssl.create_default_context())
                        smtp.ehlo()
                    if candidate["auth"]:
                        smtp.login(settings.username, settings.password)
                    smtp.send_message(message)
            return
        except Exception as exc:  # noqa: BLE001
            errors.append(
                f"port={candidate['port']} starttls={candidate['starttls']} "
                f"ssl={candidate['ssl']} auth={candidate['auth']} -> {exc!r}"
            )
    raise RuntimeError("SMTP seed send failed: " + " | ".join(errors))


def find_or_seed_attachment_message(
    client: httpx.Client,
    api_key: str,
    api_base_path: str,
    *,
    profile_id: str = "operations",
    folder: str = "INBOX",
    recent_scan_limit: int = 80,
    seed_wait_seconds: int = 90,
) -> tuple[str, list[dict[str, Any]]]:
    """Return (uid, attachments) for a real message that contains attachments."""
    search = _call_tool(
        client,
        api_key,
        api_base_path,
        "mail_search",
        {
            "profile_id": profile_id,
            "mode": "imap",
            "query": "ALL",
            "filters": {"folder": folder},
        },
    )
    messages = search.get("messages", [])
    assert isinstance(messages, list), "mail_search did not return messages list"
    assert messages, "mail_search returned no real IMAP messages"

    for uid in _sorted_uid_desc(messages)[:recent_scan_limit]:
        attachments = _list_attachments_for_uid(
            client, api_key, api_base_path, profile_id, folder, uid
        )
        if attachments:
            return uid, attachments

    marker = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    subject = f"W24A Attachment Seed {marker}"
    _send_seed_attachment_message(subject)

    deadline = time.monotonic() + float(seed_wait_seconds)
    while time.monotonic() < deadline:
        seeded = _call_tool(
            client,
            api_key,
            api_base_path,
            "mail_search",
            {
                "profile_id": profile_id,
                "mode": "imap",
                "query": f'HEADER Subject "{subject}"',
                "filters": {"folder": folder},
            },
        )
        seeded_messages = seeded.get("messages", [])
        if isinstance(seeded_messages, list) and seeded_messages:
            for uid in _sorted_uid_desc(seeded_messages):
                attachments = _list_attachments_for_uid(
                    client, api_key, api_base_path, profile_id, folder, uid
                )
                if attachments:
                    return uid, attachments
        time.sleep(2.0)

    raise AssertionError(
        "No attachment-bearing message available after SMTP seed attempt; "
        "cannot validate real attachment tool flows."
    )
