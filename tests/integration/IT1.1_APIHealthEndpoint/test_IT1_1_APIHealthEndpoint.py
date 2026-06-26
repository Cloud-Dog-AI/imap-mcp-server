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

# Covers: FR-01

import re

import httpx
import pytest
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-01")


def test_it11_api_health_endpoint(integration_server) -> None:
    auth_headers = {"x-api-key": integration_server.api_key}
    with httpx.Client(base_url=integration_server.api_base_url, timeout=30.0) as client:
        response = client.get("/health")
        canonical_response = client.get(integration_server.api_path("/health"))
        legacy_response = client.get("/app/v1/health")
        unauth_admin = client.get("/api/v1/admin/profiles")
    with httpx.Client(base_url=integration_server.web_base_url, timeout=30.0) as web_client:
        web_root = web_client.get("/", headers=auth_headers, follow_redirects=False)
        login = web_client.get("/login")
        web = web_client.get("/ui/", headers=auth_headers)
        runtime_config = web_client.get("/runtime-config.js", headers=auth_headers)
    assert response.status_code == 200
    assert canonical_response.status_code == 200
    assert legacy_response.status_code == 200
    payload = response.json()
    canonical_payload = canonical_response.json()
    legacy_payload = legacy_response.json()
    if isinstance(payload.get("result"), dict):
        assert payload["result"].get("status") == "ok"
        assert payload["result"].get("service") == "imap-mcp-server"
    else:
        assert payload.get("status") == "ok"
        assert payload.get("application") == "imap-mcp-server"
    if isinstance(canonical_payload.get("result"), dict):
        assert canonical_payload["result"].get("status") == "ok"
        assert canonical_payload["result"].get("service") == "imap-mcp-server"
    else:
        assert canonical_payload.get("status") == "ok"
        assert canonical_payload.get("application") == "imap-mcp-server"
    if isinstance(legacy_payload.get("result"), dict):
        assert legacy_payload["result"].get("status") == "ok"
        assert legacy_payload["result"].get("service") == "imap-mcp-server"
    else:
        assert legacy_payload.get("status") == "ok"
        assert legacy_payload.get("application") == "imap-mcp-server"

    assert web_root.status_code == 200
    assert "<div id=\"root\"></div>" in web_root.text
    assert login.status_code == 200
    assert "<div id=\"root\"></div>" in login.text
    assert "/runtime-config.js" in login.text
    assert web.status_code == 200
    assert "<div id=\"root\"></div>" in web.text
    assert "/runtime-config.js" in web.text
    assert runtime_config.status_code == 200
    assert 'UI_BASE_PATH: "/ui"' in runtime_config.text
    assert unauth_admin.status_code == 401

    asset_match = re.search(r'src=\"(/assets/[^\"]+\.js)\"', web.text)
    assert asset_match is not None
    with httpx.Client(base_url=integration_server.web_base_url, timeout=30.0) as web_client:
        asset = web_client.get(asset_match.group(1), headers=auth_headers)
    assert asset.status_code == 200
