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

from imap_hub_core.config.models import ProfileConfig
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-03")


def test_profile_requires_valid_provider() -> None:
    with pytest.raises(ValidationError):
        ProfileConfig.model_validate(
            {
                "provider": "unsupported",
                "imap": {"host": "imap.local", "port": 993, "security": "ssl"},
                "auth": {"mode": "basic"},
                "sync": {
                    "retention": {"max_age_days": 30, "max_total_bytes": 10, "max_messages": 10},
                    "folder_policy": {"include_globs": ["INBOX"], "exclude_globs": []},
                    "parts_policy": {
                        "cache_headers": True,
                        "cache_bodies": True,
                        "max_body_bytes": 10,
                        "cache_raw_rfc822": False,
                        "max_raw_bytes": 10,
                        "cache_attachments": False,
                        "max_attachment_bytes": 10,
                        "max_total_attachments_bytes": 10,
                    },
                },
            }
        )
