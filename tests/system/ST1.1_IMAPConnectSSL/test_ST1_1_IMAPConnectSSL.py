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

# Covers: FR-08

from imap_hub_core.imap.connection import IMAPConnectionConfig, probe_imap_connectivity
import pytest
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-08")


def test_st11_imap_connect_ssl() -> None:
    result = probe_imap_connectivity(
        IMAPConnectionConfig(host="imap.gmail.com", port=993, security="ssl", timeout_seconds=10)
    )
    assert result["status"] == "ok"
    assert result["mode"] == "ssl"
