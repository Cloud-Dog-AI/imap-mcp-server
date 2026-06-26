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

from imap_hub_core.imap.folder_policy import filter_folders
import pytest
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-03")


def test_folder_policy_filters_expected_folders() -> None:
    folders = ["INBOX", "Archive/2025", "[Gmail]/Spam", "[Gmail]/Trash"]
    selected = filter_folders(
        folders=folders,
        include_globs=["INBOX", "Archive/*", "[Gmail]/*"],
        exclude_globs=["[Gmail]/Spam", "[Gmail]/Trash"],
    )
    assert selected == ["INBOX", "Archive/2025"]
