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

# Covers: CFG-06
# Covers: CFG-08
# Covers: CFG-10
# Covers: CFG-11

import os
import re
from uuid import uuid4

from fastapi.testclient import TestClient

from imap_hub_server.api_server import create_api_app
from imap_hub_server.mcp_server import create_mcp_app
import pytest


def _headers(app) -> dict[str, str]:
    key = str(getattr(app.state, "seed_api_key", "") or "")
    assert key
    return {"x-api-key": key, "Authorization": f"Bearer {key}", "x-role": "admin"}


def _runtime_env_files() -> list[str] | None:
    raw = os.getenv("TEST_ENV_FILES", "").strip()
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]

    mode = os.getenv("TEST_RUNTIME_MODE", "").strip().lower()
    if mode == "local-docker":
        return ["tests/env-AT-local-docker"]
    if mode == "local-server":
        return ["tests/env-AT-local-server"]
    return ["tests/env-AT"]
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-11")


def test_at112_config_crud_a2a_event_and_webui_surface() -> None:
    app = create_api_app(env_files=_runtime_env_files())
    headers = _headers(app)
    user_id = f"at112_user_{uuid4().hex[:8]}"

    with TestClient(app) as client:
        index_redirect = client.get("/", follow_redirects=False)
        assert index_redirect.status_code == 307
        assert index_redirect.headers["location"] == "/ui/"

        index = client.get("/ui/")
        assert index.status_code == 200
        assert "<div id=\"root\"></div>" in index.text
        assert "/runtime-config.js" in index.text
        assert "cloud-dog" in index.text

        asset_match = re.search(r'src=\"(/assets/[^\"]+\.js)\"', index.text)
        assert asset_match is not None
        script = client.get(asset_match.group(1))
        assert script.status_code == 200

        runtime_config = client.get("/runtime-config.js")
        assert runtime_config.status_code == 200
        assert 'UI_BASE_PATH: "/ui"' in runtime_config.text
        assert "AUTH_MODE" in runtime_config.text

        mcp_tools = client.get("/mcp/tools", headers=headers)
        assert mcp_tools.status_code == 200
        mcp_body = mcp_tools.json()
        mcp_payload = mcp_body.get("data") or mcp_body.get("result") or {}
        assert isinstance(mcp_payload.get("items"), list)

        with client.websocket_connect(f"/a2a/events?api_key={app.state.seed_api_key}") as websocket:
            create_user = client.post(
                "/api/v1/admin/users",
                headers=headers,
                json={
                    "user_id": user_id,
                    "username": user_id,
                    "email": f"{user_id}@example.com",
                },
            )
            assert create_user.status_code == 200
            event = websocket.receive_json()

        assert event["entity_type"] == "user"
        assert event["action"] == "create"
        assert event["entity_id"] == user_id
        assert event["source"] == "api"
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-11")


def test_at112_mcp_tools_compat_aliases() -> None:
    app = create_mcp_app(env_files=_runtime_env_files())
    headers = _headers(app)

    with TestClient(app) as client:
        prefixed = client.get("/mcp/tools", headers=headers)
        assert prefixed.status_code == 200

        stripped = client.get("/tools", headers=headers)
        assert stripped.status_code == 200
        assert stripped.json() == prefixed.json()
