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

from contextlib import suppress
from uuid import uuid4

import httpx

from tests.integration.helpers.mutation_flow import (
    imap_login,
    message_has_seen_flag,
    search_uid_via_imap,
    send_seed_message,
)
import pytest
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-06")


def test_it118_flag_mutation_sets_and_unsets_seen(integration_server) -> None:
    profile_id = f"it18-flag-enabled-{uuid4().hex[:8]}"
    subject = f"IT18FlagSeed{uuid4().hex[:10]}"
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
            send_seed_message(subject, "IT1.18 dedicated flag mutation seed message.")
            uid = search_uid_via_imap(subject)

            set_seen = client.post(
                integration_server.api_path("/tools/mail_set_seen"),
                headers={"x-api-key": integration_server.api_key},
                json={"profile_id": profile_id, "uids": [uid], "seen": True, "folder": "INBOX"},
            )
            assert set_seen.status_code == 200
            set_payload = set_seen.json()["result"]
            assert set_payload["ok"] is True
            assert uid in set_payload["result"]["updated"]

            imap_client = imap_login()
            assert message_has_seen_flag(imap_client, uid) is True

            unset_seen = client.post(
                integration_server.api_path("/tools/mail_set_seen"),
                headers={"x-api-key": integration_server.api_key},
                json={"profile_id": profile_id, "uids": [uid], "seen": False, "folder": "INBOX"},
            )
            assert unset_seen.status_code == 200
            unset_payload = unset_seen.json()["result"]
            assert unset_payload["ok"] is True
            assert uid in unset_payload["result"]["updated"]
            assert message_has_seen_flag(imap_client, uid) is False
        finally:
            with suppress(Exception):
                if imap_client is not None:
                    imap_client.logout()
            client.delete(
                integration_server.api_path(f"/admin/profiles/{profile_id}"),
                headers=admin_headers,
            )
