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

# Covers: FR-06

from contextlib import suppress
from uuid import uuid4

import httpx

from tests.integration.helpers.mutation_flow import (
    imap_login,
    search_uid_via_imap,
    search_uids_in_folder,
    send_seed_message,
)
import pytest
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-06")


def test_it117_delete_mutation_removes_message_from_inbox(integration_server) -> None:
    profile_id = f"it17-delete-enabled-{uuid4().hex[:8]}"
    subject = f"IT17DeleteSeed{uuid4().hex[:10]}"
    admin_headers = {
        "x-api-key": integration_server.api_key,
        "Authorization": f"Bearer {integration_server.api_key}",
        "x-role": "admin",
    }

    with httpx.Client(base_url=integration_server.api_base_url, timeout=60.0) as client:
        create_profile = client.put(
            integration_server.api_path(f"/admin/profiles/{profile_id}"),
            headers=admin_headers,
            json={"provider": "imap_generic", "write": {"enabled": True}},
        )
        assert create_profile.status_code == 200

        imap_client = None
        try:
            send_seed_message(subject, "IT1.17 dedicated delete mutation seed message.")
            uid = search_uid_via_imap(subject)

            delete = client.post(
                integration_server.api_path("/tools/mail_delete_messages"),
                headers={"x-api-key": integration_server.api_key},
                json={"profile_id": profile_id, "uids": [uid], "folder": "INBOX"},
            )
            assert delete.status_code == 200
            payload = delete.json()["result"]
            assert payload["ok"] is True
            assert uid in payload["result"]["deleted"]

            imap_client = imap_login()
            assert uid not in search_uids_in_folder(imap_client, "INBOX", subject)
        finally:
            with suppress(Exception):
                if imap_client is not None:
                    imap_client.logout()
            client.delete(
                integration_server.api_path(f"/admin/profiles/{profile_id}"),
                headers=admin_headers,
            )
