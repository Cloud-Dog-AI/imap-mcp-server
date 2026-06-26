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

import pytest
from pydantic import ValidationError

from imap_hub_core.config.models import GlobalConfigModel
from tests.helpers.ports import listener_host, listener_port
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-02")


def test_invalid_api_server_port_rejected() -> None:
    with pytest.raises(ValidationError):
        GlobalConfigModel.model_validate(
            {
                "server": {
                    "auth": {"mode": "api_key"},
                    "audit": {"log_path": "./audit.jsonl"},
                    "storage": {
                        "data_dir": "./data",
                        "downloads_dir": "./data/downloads",
                        "archive_dir": "./data/archive",
                    },
                    "limits": {
                        "max_search_results": 100,
                        "max_message_bytes": 1000,
                        "max_attachment_bytes": 1000,
                        "extractor_timeout_sec": 10,
                    },
                },
                "api_server": {
                    "host": listener_host("CLOUD_DOG__API_SERVER__HOST"),
                    "port": "not-an-int",
                },
                "web_server": {
                    "host": listener_host("CLOUD_DOG__WEB_SERVER__HOST"),
                    "port": listener_port("CLOUD_DOG__WEB_SERVER__PORT"),
                },
                "mcp_server": {
                    "host": listener_host("CLOUD_DOG__MCP_SERVER__HOST"),
                    "port": listener_port("CLOUD_DOG__MCP_SERVER__PORT"),
                    "transport": "streamable-http",
                },
                "a2a_server": {
                    "host": listener_host("CLOUD_DOG__A2A_SERVER__HOST"),
                    "port": listener_port("CLOUD_DOG__A2A_SERVER__PORT"),
                },
                "sync": {"schedule_sec": 60},
                "index": {"schedule_sec": 60},
                "rbac": {"enabled": True, "roles": {}},
                "profiles": {},
            }
        )
