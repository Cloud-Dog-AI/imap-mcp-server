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

# Covers: FR-03
# Covers: FR-05

import copy
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest


def _admin_headers(api_key: str) -> dict[str, str]:
    return {
        "x-api-key": api_key,
        "Authorization": f"Bearer {api_key}",
        "x-role": "admin",
    }


def _user_headers(api_key: str) -> dict[str, str]:
    return {
        "x-api-key": api_key,
        "Authorization": f"Bearer {api_key}",
    }


def _extract_result(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    if isinstance(data, dict):
        if isinstance(data.get("result"), dict):
            return data["result"]
        return data
    result = payload.get("result")
    if isinstance(result, dict):
        if isinstance(result.get("result"), dict):
            return result["result"]
        return result
    return {}


def _api_get(client: httpx.Client, api_base_path: str, api_key: str, path: str) -> httpx.Response:
    return client.get(f"{api_base_path}{path}", headers=_admin_headers(api_key))


def _api_post(
    client: httpx.Client,
    api_base_path: str,
    api_key: str,
    path: str,
    payload: dict,
) -> httpx.Response:
    return client.post(f"{api_base_path}{path}", headers=_admin_headers(api_key), json=payload)


def _api_put(
    client: httpx.Client,
    api_base_path: str,
    api_key: str,
    path: str,
    payload: dict,
) -> httpx.Response:
    return client.put(f"{api_base_path}{path}", headers=_admin_headers(api_key), json=payload)


def _api_delete(
    client: httpx.Client, api_base_path: str, api_key: str, path: str
) -> httpx.Response:
    return client.delete(f"{api_base_path}{path}", headers=_admin_headers(api_key))


def _mcp_call(
    client: httpx.Client,
    mcp_base_path: str,
    api_key: str,
    tool_name: str,
    payload: dict,
) -> dict:
    response = client.post(
        f"{mcp_base_path}/tools/{tool_name}",
        headers=_user_headers(api_key),
        json=payload,
    )
    assert response.status_code == 200, (
        f"MCP {tool_name} failed: {response.status_code} {response.text}"
    )
    body = response.json() if response.content else {}
    if isinstance(body, dict):
        envelope = body.get("data")
        if not isinstance(envelope, dict):
            envelope = body.get("result")
        if isinstance(envelope, dict) and envelope.get("ok") is False:
            raise AssertionError(f"MCP {tool_name} failed: {envelope.get('errors', [])}")
    result = _extract_result(body)
    assert isinstance(result, dict), f"MCP {tool_name} returned non-dict result"
    return result


def _patch_profile_for_spam_folder(
    profile: dict,
    *,
    spam_folder: str,
    retention_days: int,
    message_limit: int,
) -> dict:
    patched = copy.deepcopy(profile)
    sync_cfg = patched.setdefault("sync", {})
    retention_cfg = sync_cfg.setdefault("retention", {})
    retention_cfg["max_age_days"] = retention_days
    retention_cfg["max_messages"] = message_limit

    folder_policy = sync_cfg.setdefault("folder_policy", {})
    include_globs = folder_policy.get("include_globs")
    if not isinstance(include_globs, list):
        include_globs = []
    include: list[str] = []
    for item in ["INBOX", spam_folder, *include_globs]:
        value = str(item).strip()
        if value and value not in include:
            include.append(value)
    folder_policy["include_globs"] = include

    username = str(os.environ.get("IMAP_OPERATIONS_USERNAME") or "").strip()
    password = str(os.environ.get("IMAP_OPERATIONS_PASSWORD") or "").strip()
    if username or password:
        creds = patched.setdefault("credentials", {})
        if username:
            creds["username"] = username
        if password:
            creds["password"] = password
            creds["app_password"] = password

    return patched


def _expected_since(days_back: int) -> str:
    marker = datetime.now(timezone.utc) - timedelta(days=days_back)
    return f"SINCE {marker.strftime('%d-%b-%Y')}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-03")


def test_spam_profile_lifecycle(application_server) -> None:
    api_key = application_server.api_key
    suffix = uuid4().hex[:8]
    profile_id = f"w28a256_spam_{suffix}"
    user_id = f"w28a256_user_{suffix}"
    spam_folder = str(os.environ.get("IMAP_SPAM_FOLDER") or "SPAM").strip() or "SPAM"

    with httpx.Client(base_url=application_server.api_base_url, timeout=120.0) as api_client:
        list_resp = _api_get(
            api_client, application_server.api_base_path, api_key, "/admin/profiles"
        )
        assert list_resp.status_code == 200, list_resp.text
        profile_ids = list_resp.json().get("result", {}).get("profiles", [])
        assert isinstance(profile_ids, list) and profile_ids, "No base profiles available"

        source_profile_id = (
            "operations"
            if "operations" in profile_ids
            else "operations_cloud_dog"
            if "operations_cloud_dog" in profile_ids
            else str(profile_ids[0])
        )
        source_resp = _api_get(
            api_client,
            application_server.api_base_path,
            api_key,
            f"/admin/profiles/{source_profile_id}",
        )
        assert source_resp.status_code == 200, source_resp.text
        source_profile = source_resp.json().get("result")
        assert isinstance(source_profile, dict), "Source profile payload is not a JSON object"

        create_profile_resp = _api_put(
            api_client,
            application_server.api_base_path,
            api_key,
            f"/admin/profiles/{profile_id}",
            _patch_profile_for_spam_folder(
                source_profile,
                spam_folder=spam_folder,
                retention_days=7,
                message_limit=200,
            ),
        )
        assert create_profile_resp.status_code == 200, create_profile_resp.text
        assert create_profile_resp.json()["result"]["profile_id"] == profile_id

        managed_api_key_id = ""
        scoped_api_key = ""
        profile_created = True
        user_created = False
        try:
            create_user_resp = _api_post(
                api_client,
                application_server.api_base_path,
                api_key,
                "/admin/users",
                {
                    "user_id": user_id,
                    "username": user_id,
                    "email": f"{user_id}@example.com",
                    "display_name": "W28A-256 Spam Profile User",
                    "role": "viewer",
                },
            )
            assert create_user_resp.status_code == 200, create_user_resp.text
            user_created = True

            create_key_resp = _api_post(
                api_client,
                application_server.api_base_path,
                api_key,
                "/admin/api-keys",
                {
                    "owner_user_id": user_id,
                    "scopes": ["profiles:read"],
                    "description": f"W28A-256 key for {profile_id}",
                },
            )
            assert create_key_resp.status_code == 200, create_key_resp.text
            key_result = create_key_resp.json()["result"]
            managed_api_key_id = str(key_result["api_key_id"])
            scoped_api_key = str(key_result["raw_key"])
            assert scoped_api_key.startswith("cd_")

            with httpx.Client(
                base_url=application_server.mcp_base_url,
                timeout=120.0,
            ) as mcp_client:
                profile_list = _mcp_call(
                    mcp_client,
                    application_server.mcp_base_path,
                    scoped_api_key,
                    "profile_list",
                    {"include_disabled": False},
                )
                visible_profiles = profile_list.get("profiles", [])
                assert profile_id in visible_profiles, (
                    f"Scoped MCP key cannot see profile {profile_id}: {visible_profiles}"
                )

                folder_probe = _mcp_call(
                    mcp_client,
                    application_server.mcp_base_path,
                    scoped_api_key,
                    "mail_headlines",
                    {
                        "profile_id": profile_id,
                        "mode": "imap",
                        "query": "ALL",
                        "filters": {"folder": spam_folder},
                        "limit": 1,
                    },
                )
                if folder_probe.get("count", 0) < 1:
                    pytest.fail(
                        f"BLOCKED: SPAM folder '{spam_folder}' is empty or unavailable for profile {profile_id}"
                    )

                first_listing = _mcp_call(
                    mcp_client,
                    application_server.mcp_base_path,
                    scoped_api_key,
                    "mail_headlines",
                    {
                        "profile_id": profile_id,
                        "mode": "imap",
                        "query": "",
                        "filters": {"folder": spam_folder},
                        "limit": 200,
                    },
                )
                first_headlines = first_listing.get("headlines", [])
                assert isinstance(first_headlines, list), "mail_headlines returned non-list items"
                assert first_listing.get("effective_limit") == 200
                assert first_listing.get("query") == _expected_since(7)
                assert len(first_headlines) <= 200
                assert first_listing.get("count", 0) == len(first_headlines)
                assert first_headlines, "SPAM folder listing returned no real email data"

                for item in first_headlines[:5]:
                    assert str(item.get("headline") or "").strip(), "Missing message subject"
                    assert str(item.get("date_utc") or "").strip(), "Missing message date"
                    uid = str(item.get("uid") or "").strip()
                    assert uid, "Missing message UID"
                    message = _mcp_call(
                        mcp_client,
                        application_server.mcp_base_path,
                        scoped_api_key,
                        "mail_get_message",
                        {
                            "profile_id": profile_id,
                            "folder": spam_folder,
                            "uid": uid,
                        },
                    )
                    raw_eml = str(message.get("raw_eml") or "")
                    assert "Subject:" in raw_eml, f"Missing Subject header for uid={uid}"
                    assert "Date:" in raw_eml, f"Missing Date header for uid={uid}"

                update_profile_resp = _api_put(
                    api_client,
                    application_server.api_base_path,
                    api_key,
                    f"/admin/profiles/{profile_id}",
                    _patch_profile_for_spam_folder(
                        source_profile,
                        spam_folder=spam_folder,
                        retention_days=14,
                        message_limit=200,
                    ),
                )
                assert update_profile_resp.status_code == 200, update_profile_resp.text

                second_listing = _mcp_call(
                    mcp_client,
                    application_server.mcp_base_path,
                    scoped_api_key,
                    "mail_headlines",
                    {
                        "profile_id": profile_id,
                        "mode": "imap",
                        "query": "",
                        "filters": {"folder": spam_folder},
                        "limit": 200,
                    },
                )
                second_headlines = second_listing.get("headlines", [])
                assert isinstance(second_headlines, list), "Updated mail_headlines returned non-list"
                assert second_listing.get("effective_limit") == 200
                assert second_listing.get("query") == _expected_since(14)
                assert len(second_headlines) <= 200
                assert second_listing.get("count", 0) == len(second_headlines)
                assert len(second_headlines) >= len(first_headlines)
        finally:
            if managed_api_key_id:
                revoke_key_resp = _api_delete(
                    api_client,
                    application_server.api_base_path,
                    api_key,
                    f"/admin/api-keys/{managed_api_key_id}",
                )
                assert revoke_key_resp.status_code == 200, revoke_key_resp.text
            if user_created:
                delete_user_resp = _api_delete(
                    api_client,
                    application_server.api_base_path,
                    api_key,
                    f"/admin/users/{user_id}",
                )
                assert delete_user_resp.status_code == 200, delete_user_resp.text
            if profile_created:
                delete_profile_resp = _api_delete(
                    api_client,
                    application_server.api_base_path,
                    api_key,
                    f"/admin/profiles/{profile_id}",
                )
                assert delete_profile_resp.status_code == 200, delete_profile_resp.text
                verify_delete_resp = _api_get(
                    api_client,
                    application_server.api_base_path,
                    api_key,
                    f"/admin/profiles/{profile_id}",
                )
                assert verify_delete_resp.status_code == 404, verify_delete_resp.text
