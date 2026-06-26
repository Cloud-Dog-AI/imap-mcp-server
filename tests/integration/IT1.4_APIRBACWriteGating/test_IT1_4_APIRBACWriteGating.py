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
import json
import ssl
import time
from contextlib import suppress
from email.utils import formatdate
from uuid import uuid4

import httpx

from tests.helpers.live_runtime import runtime_imap_settings
import pytest


def _send_seed_message(subject: str) -> None:
    settings = runtime_imap_settings()
    if not settings.host or not settings.username or not settings.password:
        raise RuntimeError("Missing runtime IMAP credentials for mutation flow test.")

    client = _imap_login()
    try:
        raw = (
            f"From: {settings.username}\r\n"
            f"To: {settings.username}\r\n"
            f"Subject: {subject}\r\n"
            f"Date: {formatdate(localtime=True)}\r\n"
            "\r\n"
            "IT1.4 mutation seed message.\r\n"
        ).encode("utf-8")
        status, _ = client.append("INBOX", None, None, raw)
        if status != "OK":
            raise RuntimeError(f"IMAP APPEND failed with status={status}")
    finally:
        with suppress(Exception):
            client.logout()


def _imap_login() -> imaplib.IMAP4 | imaplib.IMAP4_SSL:
    settings = runtime_imap_settings()
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
    assert status == "OK"
    return client


def _search_uid_via_api(
    client: httpx.Client,
    api_base_path: str,
    api_key: str,
    profile_id: str,
    subject: str,
    timeout_seconds: float = 120.0,
) -> str:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        imap_client = None
        try:
            imap_client = _imap_login()
            uids = _search_uid_in_folder(imap_client, "INBOX", subject)
            if uids:
                return uids[-1]
        finally:
            with suppress(Exception):
                if imap_client is not None:
                    imap_client.logout()
        time.sleep(2.0)
    raise AssertionError("Timed out waiting for seed message to appear in INBOX via direct IMAP.")


def _search_uid_in_folder(
    imap_client: imaplib.IMAP4 | imaplib.IMAP4_SSL, folder: str, subject: str
) -> list[str]:
    select_status, _ = imap_client.select(folder, readonly=True)
    assert select_status == "OK"
    search_status, data = imap_client.uid("SEARCH", None, "HEADER", "Subject", subject)
    assert search_status == "OK"
    if not data or not data[0]:
        return []
    return [token.decode("utf-8", "ignore") for token in data[0].split() if token]
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-04")
@pytest.mark.req("CS-002")
@pytest.mark.req("CS-008")


def test_it14_api_rbac_write_gating(integration_server) -> None:
    profile_id = f"it14-write-enabled-{uuid4().hex[:8]}"
    destination_folder = f"IT1_4_{uuid4().hex[:6]}"
    subject = f"IT14MutationSeed{uuid4().hex[:10]}"

    admin_headers = {
        "x-api-key": integration_server.api_key,
        "Authorization": f"Bearer {integration_server.api_key}",
        "x-role": "admin",
    }

    with httpx.Client(base_url=integration_server.api_base_url, timeout=60.0) as client:
        # Disabled policy must still block mutation attempts.
        response = client.post(
            integration_server.api_path("/tools/mail_delete_messages"),
            headers={"x-api-key": integration_server.api_key},
            json={"profile_id": "operations_cloud_dog", "uids": ["1"], "folder": "INBOX"},
        )
        assert response.status_code == 200
        payload = response.json()["result"]
        assert payload["ok"] is False
        assert payload["errors"][0]["code"] == "write_disabled"

        # Create a write-enabled profile for real mutation execution.
        create_profile = client.put(
            integration_server.api_path(f"/admin/profiles/{profile_id}"),
            headers=admin_headers,
            json={"provider": "imap_generic", "write": {"enabled": True}},
        )
        assert create_profile.status_code == 200

        imap_client: imaplib.IMAP4 | imaplib.IMAP4_SSL | None = None
        try:
            _send_seed_message(subject)
            uid = _search_uid_via_api(
                client,
                integration_server.api_base_path,
                integration_server.api_key,
                profile_id,
                subject,
            )

            imap_client = _imap_login()
            with suppress(Exception):
                imap_client.create(destination_folder)

            set_seen = client.post(
                integration_server.api_path("/tools/mail_set_seen"),
                headers={"x-api-key": integration_server.api_key},
                json={
                    "profile_id": profile_id,
                    "uids": [uid],
                    "seen": True,
                    "folder": "INBOX",
                },
            )
            assert set_seen.status_code == 200
            set_seen_payload = set_seen.json()["result"]
            assert set_seen_payload["ok"] is True
            assert uid in set_seen_payload["result"]["updated"]

            select_status, _ = imap_client.select("INBOX", readonly=True)
            assert select_status == "OK"
            fetch_status, fetch_data = imap_client.uid("FETCH", uid, "(FLAGS)")
            assert fetch_status == "OK"
            assert "\\Seen" in str(fetch_data)

            move = client.post(
                integration_server.api_path("/tools/mail_move_messages"),
                headers={"x-api-key": integration_server.api_key},
                json={
                    "profile_id": profile_id,
                    "uids": [uid],
                    "folder": "INBOX",
                    "destination_folder": destination_folder,
                },
            )
            assert move.status_code == 200
            move_payload = move.json()["result"]
            assert move_payload["ok"] is True
            assert uid in move_payload["result"]["moved"]

            inbox_after_move = _search_uid_in_folder(imap_client, "INBOX", subject)
            assert uid not in inbox_after_move
            moved_uids = _search_uid_in_folder(imap_client, destination_folder, subject)
            assert moved_uids

            delete = client.post(
                integration_server.api_path("/tools/mail_delete_messages"),
                headers={"x-api-key": integration_server.api_key},
                json={
                    "profile_id": profile_id,
                    "uids": [moved_uids[0]],
                    "folder": destination_folder,
                },
            )
            assert delete.status_code == 200
            delete_payload = delete.json()["result"]
            assert delete_payload["ok"] is True
            assert moved_uids[0] in delete_payload["result"]["deleted"]

            after_delete = _search_uid_in_folder(imap_client, destination_folder, subject)
            assert not after_delete

            audit = client.get(
                integration_server.api_path("/admin/audit/events?limit=300&contains=mail_"),
                headers=admin_headers,
            )
            assert audit.status_code == 200
            items = (audit.json().get("result") or {}).get("items") or []
            assert isinstance(items, list)
            serialised = json.dumps(items)
            assert "mail_set_seen" in serialised
            assert "mail_move_messages" in serialised
            assert "mail_delete_messages" in serialised
        finally:
            with suppress(Exception):
                if imap_client is not None:
                    imap_client.select(destination_folder)
                    imap_client.close()
                    imap_client.delete(destination_folder)
            with suppress(Exception):
                if imap_client is not None:
                    imap_client.logout()
            client.delete(
                integration_server.api_path(f"/admin/profiles/{profile_id}"),
                headers=admin_headers,
            )
