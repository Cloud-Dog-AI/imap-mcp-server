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

import base64

from imap_hub_core.imap.connection import build_xoauth2_auth_string
import pytest
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-08")


def test_ut131_xoauth2_auth_string_encoding() -> None:
    encoded = build_xoauth2_auth_string("user@example.com", "token-123")
    decoded = base64.b64decode(encoded).decode("utf-8")
    assert "user=user@example.com" in decoded
    assert "auth=Bearer token-123" in decoded
