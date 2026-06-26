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

from imap_hub_core.duplicate.detector import DuplicateCandidate
from imap_hub_core.duplicate.policy import choose_keeper
import pytest
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-20")


def test_duplicate_selection_flagged_policy_prefers_flagged() -> None:
    now = datetime.now(timezone.utc)
    candidates = [
        DuplicateCandidate("m1", "<a>", None, "x@example.com", "s", now, 100, flagged=False),
        DuplicateCandidate("m2", "<a>", None, "x@example.com", "s", now, 100, flagged=True),
    ]
    keeper = choose_keeper(candidates, policy="flagged")
    assert keeper.message_id == "m2"
