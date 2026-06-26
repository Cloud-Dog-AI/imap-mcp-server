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

from datetime import datetime

from imap_hub_core.archive.exporter import build_archive_message_path
import pytest
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-21")


def test_archive_path_is_deterministic() -> None:
    path = build_archive_message_path(
        "/archive", "profile-a", datetime(2026, 2, 19, 12, 0, 0), "msg-1"
    )
    assert str(path).endswith("/profile-a/2026/02/19/msg-1")
