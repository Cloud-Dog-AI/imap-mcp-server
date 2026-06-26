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

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from tests.helpers.attachment_seed import find_or_seed_attachment_message
import pytest


def _tool_api(
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
    assert response.status_code == 200, f"{tool_name} HTTP status={response.status_code}"
    envelope = response.json().get("result", {})
    assert envelope.get("ok") is True, f"{tool_name} failed: {envelope.get('errors', [])}"
    result = envelope.get("result", {})
    assert isinstance(result, dict), f"{tool_name} returned non-dict result"
    return result


def _tool_mcp(
    client: httpx.Client, mcp_base_path: str, tool_name: str, payload: dict[str, Any]
) -> dict[str, Any]:
    response = client.post(f"{mcp_base_path}/tools/{tool_name}", json=payload)
    assert response.status_code == 200, f"MCP {tool_name} HTTP status={response.status_code}"
    body = response.json()
    data = body.get("data", body.get("result", {}))
    assert isinstance(data, dict), f"MCP {tool_name} returned non-dict envelope"
    assert data.get("ok") is True, f"MCP {tool_name} failed: {data.get('errors', [])}"
    result = data.get("result", {})
    assert isinstance(result, dict), f"MCP {tool_name} returned non-dict result"
    return result


def _subject_token(subject: str) -> str:
    for token in re.findall(r"[A-Za-z0-9]{4,}", subject):
        if not token.isdigit():
            return token
    return "status"


def _since_query(days_back: int = 30) -> str:
    marker = datetime.now(timezone.utc) - timedelta(days=days_back)
    return f"SINCE {marker.strftime('%d-%b-%Y')}"


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


def _assert_latest_and_field_searches_via_api(
    client: httpx.Client, api_key: str, api_base_path: str
) -> list[str]:
    base_payload = {
        "profile_id": "operations",
        "mode": "imap",
        "filters": {"folder": "INBOX"},
    }

    latest = _tool_api(
        client, api_key, api_base_path, "mail_search", {**base_payload, "query": "ALL"}
    )
    latest_messages = latest.get("messages", [])
    assert isinstance(latest_messages, list), "mail_search did not return messages list"
    assert latest_messages, "mail_search ALL returned no messages from real IMAP"

    newest = sorted(
        latest_messages,
        key=lambda msg: int(str(msg.get("uid", "0")) or "0"),
    )[-1]
    newest_uid = str(newest.get("uid", ""))
    assert newest_uid.isdigit(), f"Latest message UID invalid: {newest_uid}"

    _tool_api(client, api_key, api_base_path, "mail_search", {**base_payload, "query": "UNSEEN"})
    _tool_api(
        client, api_key, api_base_path, "mail_search", {**base_payload, "query": _since_query(45)}
    )

    subject_token = _subject_token(str(newest.get("subject", "")))
    by_subject = _tool_api(
        client,
        api_key,
        api_base_path,
        "mail_search",
        {**base_payload, "query": f'SUBJECT "{subject_token}"'},
    )
    assert by_subject.get("messages"), (
        f"SUBJECT search returned no messages for token '{subject_token}'"
    )

    by_text = _tool_api(
        client,
        api_key,
        api_base_path,
        "mail_search",
        {**base_payload, "query": f'TEXT "{subject_token}"'},
    )
    assert isinstance(by_text.get("messages", []), list), "TEXT search did not return messages list"

    message_id_source = next(
        (
            item
            for item in sorted(
                latest_messages,
                key=lambda msg: int(str(msg.get("uid", "0")) or "0"),
                reverse=True,
            )
            if str(item.get("header_message_id", "")).strip()
        ),
        None,
    )
    assert message_id_source is not None, (
        "No Message-ID-bearing message found in latest search window"
    )

    message_id = str(message_id_source.get("header_message_id", "")).strip()
    by_message_id = _tool_api(
        client,
        api_key,
        api_base_path,
        "mail_search",
        {**base_payload, "query": f'HEADER Message-ID "{message_id}"'},
    )
    assert by_message_id.get("messages"), "Message-ID header search returned no messages"

    headlines = _tool_api(
        client,
        api_key,
        api_base_path,
        "mail_headlines",
        {**base_payload, "query": "ALL", "limit": 8},
    )
    assert headlines.get("count", 0) > 0, "mail_headlines returned no summary items"
    assert headlines.get("headlines"), "mail_headlines returned empty headlines list"

    return _sorted_uid_desc(latest_messages)


def _assert_get_and_attachment_flows_via_api(
    client: httpx.Client,
    api_key: str,
    api_base_path: str,
    uid_desc: list[str],
) -> None:
    base_payload = {
        "profile_id": "operations",
        "folder": "INBOX",
    }

    # Get latest messages one by one.
    for uid in uid_desc[:3]:
        message = _tool_api(
            client, api_key, api_base_path, "mail_get_message", {**base_payload, "uid": uid}
        )
        raw_eml = str(message.get("raw_eml", ""))
        assert "Subject:" in raw_eml or "From:" in raw_eml, (
            f"mail_get_message returned invalid message content for UID {uid}"
        )

    extracted = _tool_api(
        client,
        api_key,
        api_base_path,
        "mail_extract_message",
        {**base_payload, "uid": uid_desc[0], "format": "both"},
    )
    assert isinstance(extracted.get("json"), dict), "mail_extract_message JSON payload missing"
    assert isinstance(extracted.get("markdown"), str), (
        "mail_extract_message Markdown payload missing"
    )
    assert extracted["markdown"].strip(), "mail_extract_message Markdown output empty"

    uid, attachments = find_or_seed_attachment_message(
        client,
        api_key,
        api_base_path,
        profile_id="operations",
        folder="INBOX",
    )
    part_id = str(attachments[0].get("part_id", "")).strip()
    assert part_id, f"Attachment part_id missing for UID {uid}"

    download = _tool_api(
        client,
        api_key,
        api_base_path,
        "mail_download_attachment",
        {**base_payload, "uid": uid, "part_id": part_id},
    )
    path = Path(str(download.get("path", "")))
    assert path.exists(), f"Downloaded attachment path missing: {path}"
    assert int(download.get("size_bytes", 0)) > 0, "Downloaded attachment size is zero"
    content = str(download.get("content", ""))
    content_encoding = str(download.get("content_encoding", "")).strip().lower()
    assert content, "Downloaded attachment content is empty"
    assert content_encoding in {"text", "base64"}, (
        f"Unexpected content encoding: {content_encoding}"
    )


def _assert_mcp_interface_flows(client: httpx.Client, mcp_base_path: str) -> None:
    base_payload = {
        "profile_id": "operations",
        "mode": "imap",
        "filters": {"folder": "INBOX"},
    }

    search = _tool_mcp(client, mcp_base_path, "mail_search", {**base_payload, "query": "ALL"})
    messages = search.get("messages", [])
    assert isinstance(messages, list), "MCP mail_search did not return messages list"
    assert messages, "MCP mail_search ALL returned no messages"

    _tool_mcp(client, mcp_base_path, "mail_search", {**base_payload, "query": "UNSEEN"})
    _tool_mcp(client, mcp_base_path, "mail_search", {**base_payload, "query": _since_query(30)})

    headlines = _tool_mcp(
        client, mcp_base_path, "mail_headlines", {**base_payload, "query": "ALL", "limit": 5}
    )
    assert headlines.get("count", 0) > 0, "MCP mail_headlines returned no items"

    _tool_mcp(client, mcp_base_path, "mail_search", {**base_payload, "query": "ALL"})
    delta = _tool_mcp(
        client, mcp_base_path, "mail_search_since_last", {**base_payload, "query": "ALL"}
    )
    assert delta.get("baseline") is not None, "MCP mail_search_since_last returned no baseline"

    newest_uid = _sorted_uid_desc(messages)[0]
    got = _tool_mcp(
        client,
        mcp_base_path,
        "mail_get_message",
        {
            "profile_id": "operations",
            "folder": "INBOX",
            "uid": newest_uid,
        },
    )
    raw_eml = str(got.get("raw_eml", ""))
    assert "Subject:" in raw_eml or "From:" in raw_eml, (
        "MCP mail_get_message returned invalid content"
    )

    extracted = _tool_mcp(
        client,
        mcp_base_path,
        "mail_extract_message",
        {
            "profile_id": "operations",
            "folder": "INBOX",
            "uid": newest_uid,
            "format": "both",
        },
    )
    assert isinstance(extracted.get("json"), dict), "MCP mail_extract_message JSON payload missing"
    assert isinstance(extracted.get("markdown"), str), (
        "MCP mail_extract_message Markdown payload missing"
    )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-05")


def test_at17_real_imap_api_and_mcp_advanced_search_retrieve(application_server: Any) -> None:
    with httpx.Client(base_url=application_server.api_base_url, timeout=60.0) as api_client:
        uid_desc = _assert_latest_and_field_searches_via_api(
            api_client,
            application_server.api_key,
            application_server.api_base_path,
        )
        _assert_get_and_attachment_flows_via_api(
            api_client,
            application_server.api_key,
            application_server.api_base_path,
            uid_desc,
        )

    # W28A-735-R5: the MCP transport now requires a valid API key (anon -> 401);
    # authenticate every MCP call on this client.
    with httpx.Client(
        base_url=application_server.mcp_base_url,
        timeout=60.0,
        headers={"x-api-key": application_server.api_key},
    ) as mcp_client:
        _assert_mcp_interface_flows(mcp_client, application_server.mcp_base_path)
