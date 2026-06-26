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

# Covers: FR-10

import re
from uuid import uuid4

from tests.helpers.live_runtime import api_client, api_path
import pytest
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-03")


def test_at15_fullworkflow_admin_profile_setup() -> None:
    client, key = api_client()
    profile_name = f"workflow_profile_{uuid4().hex[:8]}"
    headers = {
        "x-api-key": key,
        "Authorization": f"Bearer {key}",
        "x-role": "admin",
    }

    web_root = client.get("/", headers=headers, follow_redirects=False)
    assert web_root.status_code == 307
    assert web_root.headers["location"] == "/ui/"

    web_shell = client.get("/ui/", headers=headers)
    assert web_shell.status_code == 200
    assert "<div id=\"root\"></div>" in web_shell.text
    assert "/runtime-config.js" in web_shell.text

    asset_match = re.search(r'src=\"(/assets/[^\"]+\.js)\"', web_shell.text)
    assert asset_match is not None
    web_js = client.get(asset_match.group(1), headers=headers)
    assert web_js.status_code == 200

    runtime_config = client.get("/runtime-config.js", headers=headers)
    assert runtime_config.status_code == 200
    assert 'UI_BASE_PATH: "/ui"' in runtime_config.text

    create = client.put(
        api_path(f"/admin/profiles/{profile_name}"),
        headers=headers,
        json={"provider": "imap_generic", "enabled": True},
    )
    assert create.status_code == 200

    update = client.put(
        api_path(f"/admin/profiles/{profile_name}"),
        headers=headers,
        json={"provider": "imap_generic", "enabled": False},
    )
    assert update.status_code == 200

    delete = client.delete(api_path(f"/admin/profiles/{profile_name}"), headers=headers)
    assert delete.status_code == 200
