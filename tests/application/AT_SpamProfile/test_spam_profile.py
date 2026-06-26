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

import copy
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest


def _headers(api_key: str) -> dict[str, str]:
    return {
        "x-api-key": api_key,
        "Authorization": f"Bearer {api_key}",
        "x-role": "admin",
    }


def _extract_result(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {}

    if isinstance(payload.get("result"), dict) and "ok" in payload.get("result", {}):
        inner = payload["result"]
        if isinstance(inner.get("result"), dict):
            return inner["result"]
        return {}

    if isinstance(payload.get("result"), dict):
        return payload["result"]

    if isinstance(payload.get("data"), dict):
        data = payload["data"]
        if isinstance(data.get("result"), dict):
            return data["result"]
        return data

    return {}


def _api_get(client: httpx.Client, api_base_path: str, api_key: str, path: str) -> httpx.Response:
    return client.get(f"{api_base_path}{path}", headers=_headers(api_key))


def _api_put(
    client: httpx.Client,
    api_base_path: str,
    api_key: str,
    path: str,
    payload: dict,
) -> httpx.Response:
    return client.put(f"{api_base_path}{path}", headers=_headers(api_key), json=payload)


def _api_delete(
    client: httpx.Client, api_base_path: str, api_key: str, path: str
) -> httpx.Response:
    return client.delete(f"{api_base_path}{path}", headers=_headers(api_key))


def _mcp_call(client: httpx.Client, mcp_base_path: str, tool_name: str, payload: dict) -> dict:
    response = client.post(f"{mcp_base_path}/tools/{tool_name}", json=payload)
    assert response.status_code == 200, (
        f"MCP {tool_name} failed: {response.status_code} {response.text}"
    )
    body = response.json() if response.content else {}
    data = body.get("data") if isinstance(body, dict) else None
    if isinstance(data, dict) and data.get("ok") is False:
        raise AssertionError(f"MCP {tool_name} failed: {data.get('errors', [])}")
    return _extract_result(body)


def _patch_profile_for_spam_folder(profile: dict, spam_folder: str) -> dict:
    patched = copy.deepcopy(profile)

    search_cfg = patched.get("search")
    if isinstance(search_cfg, dict):
        if "default_folder" in search_cfg:
            search_cfg["default_folder"] = spam_folder
        if "folder" in search_cfg:
            search_cfg["folder"] = spam_folder

    sync_cfg = patched.get("sync")
    if isinstance(sync_cfg, dict):
        folders = sync_cfg.get("folders")
        if isinstance(folders, list) and folders:
            folders[0] = spam_folder
        folder_policy = sync_cfg.get("folder_policy")
        if isinstance(folder_policy, dict):
            folder_policy["include_globs"] = ["INBOX", spam_folder]

    username = str(os.environ.get("IMAP_OPERATIONS_USERNAME") or "").strip()
    password = str(os.environ.get("IMAP_OPERATIONS_PASSWORD") or "").strip()
    if username or password:
        creds = patched.get("credentials")
        if not isinstance(creds, dict):
            creds = {}
            patched["credentials"] = creds
        if username:
            creds["username"] = username
        if password:
            creds["password"] = password
            creds["app_password"] = password

    return patched
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-03")


def test_at_spam_profile_lifecycle(application_server) -> None:
    """AT_SpamProfile dynamic SPAM profile lifecycle over real API and MCP transports.

    Required env keys:
    - TEST_API_BASE_URL
    - TEST_MCP_BASE_URL
    - IMAP_API_KEY
    """

    api_key = application_server.api_key
    profile_id = f"w26a-spam-{uuid4().hex[:10]}"
    spam_folder = str(os.environ.get("IMAP_SPAM_FOLDER") or "SPAM").strip() or "SPAM"

    with httpx.Client(base_url=application_server.api_base_url, timeout=90.0) as api_client:
        list_resp = _api_get(
            api_client, application_server.api_base_path, api_key, "/admin/profiles"
        )
        assert list_resp.status_code == 200, list_resp.text
        listed = list_resp.json().get("result", {}).get("profiles", [])
        assert isinstance(listed, list) and listed, "No base profiles available for dynamic clone"

        source_profile_id = "operations" if "operations" in listed else str(listed[0])
        source_resp = _api_get(
            api_client,
            application_server.api_base_path,
            api_key,
            f"/admin/profiles/{source_profile_id}",
        )
        assert source_resp.status_code == 200, source_resp.text
        source_profile = source_resp.json().get("result")
        assert isinstance(source_profile, dict), "Source profile payload is not a JSON object"

        dynamic_profile_payload = _patch_profile_for_spam_folder(source_profile, spam_folder)

        created = False
        try:
            create_resp = _api_put(
                api_client,
                application_server.api_base_path,
                api_key,
                f"/admin/profiles/{profile_id}",
                dynamic_profile_payload,
            )
            assert create_resp.status_code == 200, create_resp.text
            create_json = create_resp.json()
            assert create_json.get("ok") is True
            assert str(create_json.get("result", {}).get("profile_id") or "") == profile_id
            created = True

            verify_resp = _api_get(
                api_client,
                application_server.api_base_path,
                api_key,
                f"/admin/profiles/{profile_id}",
            )
            assert verify_resp.status_code == 200, verify_resp.text

            # W28A-735-R5: the MCP transport now requires a valid API key
            # (anon -> 401); authenticate every MCP call on this client.
            with httpx.Client(
                base_url=application_server.mcp_base_url,
                timeout=120.0,
                headers=_headers(api_key),
            ) as mcp_client:
                tools_resp = mcp_client.get(application_server.mcp_path("/tools"))
                assert tools_resp.status_code == 200, tools_resp.text

                mcp_profile_id = profile_id
                profile_list = _mcp_call(
                    mcp_client,
                    application_server.mcp_base_path,
                    "profile_list",
                    {},
                )
                profile_ids = profile_list.get("profiles")
                if isinstance(profile_ids, list) and profile_id not in profile_ids:
                    mcp_profile_id = source_profile_id

                since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%d-%b-%Y")
                search_result = _mcp_call(
                    mcp_client,
                    application_server.mcp_base_path,
                    "mail_search",
                    {
                        "profile_id": mcp_profile_id,
                        "mode": "imap",
                        "query": f"SINCE {since}",
                        "filters": {"folder": spam_folder},
                    },
                )

                folder_probe = _mcp_call(
                    mcp_client,
                    application_server.mcp_base_path,
                    "mail_search",
                    {
                        "profile_id": mcp_profile_id,
                        "mode": "imap",
                        "query": "ALL",
                        "filters": {"folder": spam_folder},
                    },
                )
                folder_messages = folder_probe.get("messages")
                if folder_messages is None:
                    folder_messages = folder_probe.get("results")
                if folder_messages is None:
                    folder_messages = []
                if len(folder_messages) < 1:
                    pytest.fail("PREREQUISITE: SPAM folder is empty - cannot test")

                messages = search_result.get("messages")
                if messages is None:
                    messages = search_result.get("results")
                if messages is None:
                    messages = []
                if len(messages) < 1:
                    fallback = _mcp_call(
                        mcp_client,
                        application_server.mcp_base_path,
                        "mail_search",
                        {
                            "profile_id": mcp_profile_id,
                            "mode": "imap",
                            "query": "ALL",
                            "filters": {"folder": spam_folder},
                        },
                    )
                    messages = fallback.get("messages")
                    if messages is None:
                        messages = fallback.get("results")
                    if messages is None:
                        messages = []

                assert isinstance(messages, list), "mail_search result must be a list"
                reviewed_messages = messages[:200]
                assert len(reviewed_messages) <= 200

                sample_subjects: list[str] = []
                for message in reviewed_messages:
                    if not isinstance(message, dict):
                        continue
                    subject = str(message.get("subject") or "").strip()
                    if subject and len(sample_subjects) < 5:
                        sample_subjects.append(subject)

                    uid = str(message.get("uid") or message.get("id") or "").strip()
                    if not uid:
                        continue

                    fetched = _mcp_call(
                        mcp_client,
                        application_server.mcp_base_path,
                        "mail_get_message",
                        {
                            "profile_id": mcp_profile_id,
                            "folder": spam_folder,
                            "uid": uid,
                        },
                    )
                    raw_eml = str(fetched.get("raw_eml") or "")
                    assert raw_eml.strip(), f"mail_get_message returned empty content for uid={uid}"
                    assert "Subject:" in raw_eml, f"Missing Subject in uid={uid}"
                    assert "Date:" in raw_eml, f"Missing Date in uid={uid}"

                print(
                    "[AT1.10] profile=%s folder=%s total=%d reviewed=%d sample_subjects=%s"
                    % (
                        profile_id,
                        spam_folder,
                        len(messages),
                        len(reviewed_messages),
                        sample_subjects,
                    )
                )
        finally:
            if created:
                delete_resp = _api_delete(
                    api_client,
                    application_server.api_base_path,
                    api_key,
                    f"/admin/profiles/{profile_id}",
                )
                assert delete_resp.status_code == 200, delete_resp.text

                after_delete = _api_get(
                    api_client,
                    application_server.api_base_path,
                    api_key,
                    f"/admin/profiles/{profile_id}",
                )
                assert after_delete.status_code == 404, after_delete.text
