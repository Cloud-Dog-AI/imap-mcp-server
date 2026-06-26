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

from imap_hub_core.imap.connection import IMAPConnectionConfig, probe_imap_connectivity
from tests.helpers.live_runtime import runtime_imap_settings
import pytest
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-08")


def test_st12_imap_connect_starttls() -> None:
    settings = runtime_imap_settings()
    result = probe_imap_connectivity(
        IMAPConnectionConfig(
            host=settings.host, port=settings.port, security="starttls", timeout_seconds=30
        )
    )
    assert result["status"] == "ok"
    assert result["mode"] == "starttls"
