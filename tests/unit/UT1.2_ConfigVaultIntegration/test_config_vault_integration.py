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

from imap_hub_core.config.loader import bind_global_config
from tests.helpers.ports import listener_host, listener_port
import pytest
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-02")


def test_bind_global_config_accepts_vault_expansion_shape() -> None:
    config = bind_global_config(
        {
            "server": {
                "auth": {"mode": "api_key"},
                "audit": {"log_path": "./data/audit/audit.jsonl"},
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
                "port": listener_port("CLOUD_DOG__API_SERVER__PORT"),
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
            "rbac": {"enabled": True, "roles": {"reader": ["mail_search"]}},
            "profiles": {
                "gmail_personal": {
                    "provider": "gmail",
                    "imap": {
                        "host": "imap.gmail.com",
                        "port": 993,
                        "security": "ssl",
                        "tls": {"ca_bundle_path": "/tmp/ca.pem", "allow_self_signed": False},
                    },
                    "auth": {
                        "mode": "oauth2",
                        "oauth": {
                            "client_id": "${vault.dev.email.gmail.client_id}",
                            "client_secret": "${vault.dev.email.gmail.client_secret}",
                        },
                    },
                    "sync": {
                        "retention": {
                            "max_age_days": 30,
                            "max_total_bytes": 100,
                            "max_messages": 10,
                        },
                        "folder_policy": {"include_globs": ["INBOX"], "exclude_globs": []},
                        "parts_policy": {
                            "cache_headers": True,
                            "cache_bodies": True,
                            "max_body_bytes": 100,
                            "cache_raw_rfc822": False,
                            "max_raw_bytes": 100,
                            "cache_attachments": False,
                            "max_attachment_bytes": 100,
                            "max_total_attachments_bytes": 100,
                        },
                    },
                }
            },
        }
    )

    assert (
        config.profiles["gmail_personal"].auth.oauth.client_id
        == "${vault.dev.email.gmail.client_id}"
    )
