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

import httpx
import pytest
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-01")


def test_it15_mcp_tool_catalogue(integration_server) -> None:
    # W28A-735-R5 / D-IMAP-IDENTITY-COLLAPSE-1: the MCP transport now requires a
    # valid API key. An unauthenticated caller is DENIED (401), never handed the
    # catalogue and never resolved to admin.
    with httpx.Client(base_url=integration_server.mcp_base_url, timeout=30.0) as client:
        anon = client.get(integration_server.mcp_path("/tools"))
        assert anon.status_code == 401, f"anon MCP /tools must be 401, got {anon.status_code}"
        response = client.get(
            integration_server.mcp_path("/tools"),
            headers={"x-api-key": integration_server.api_key},
        )
    assert response.status_code == 200
    tools = response.json().get("data", [])
    assert isinstance(tools, list), "MCP tools/list did not return a list"

    by_name = {item.get("name"): item for item in tools if isinstance(item, dict)}
    required = {
        "mail_search": {"profile_id", "mode", "query", "filters"},
        "mail_get_message": {"profile_id", "uid", "folder"},
        "mail_extract_message": {"profile_id", "uid", "folder", "format"},
        "mail_list_attachments": {"profile_id", "uid", "folder"},
        "mail_download_attachment": {"profile_id", "uid", "part_id", "folder"},
    }
    for tool_name, required_fields in required.items():
        assert tool_name in by_name, f"Required MCP tool missing: {tool_name}"
        schema = by_name[tool_name].get("input_schema", {})
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        assert isinstance(properties, dict), f"{tool_name} input_schema.properties missing"
        missing = [field for field in required_fields if field not in properties]
        assert not missing, f"{tool_name} schema missing required fields: {missing}"
