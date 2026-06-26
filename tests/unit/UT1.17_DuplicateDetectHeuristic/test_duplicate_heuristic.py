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

from datetime import datetime, timezone

from imap_hub_core.duplicate.detector import DuplicateCandidate, group_duplicates
import pytest
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-20")


def test_duplicate_grouping_by_heuristic() -> None:
    now = datetime(2026, 2, 19, 12, 30, 45, tzinfo=timezone.utc)
    candidates = [
        DuplicateCandidate("m1", None, None, "a@example.com", "Subject", now, 200),
        DuplicateCandidate(
            "m2", None, None, "a@example.com", "Subject", now.replace(second=15), 200
        ),
    ]
    groups = group_duplicates(candidates, strategy="heuristic")
    assert len(groups) == 1
