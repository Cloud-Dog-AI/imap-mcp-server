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

from imap_hub_core.imap.sync import SyncState, compute_next_sync_cursor
import pytest
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-07")


def test_ut132_sync_incremental_cursor() -> None:
    current = SyncState(uidvalidity=1, last_uid=10, last_modseq=5)
    next_state = compute_next_sync_cursor(current, discovered_uid_max=14, discovered_modseq_max=6)
    assert next_state.last_uid == 14
    assert next_state.last_modseq == 6
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-07")


def test_ut132_sync_uidvalidity_change_behaviour() -> None:
    current = SyncState(uidvalidity=88, last_uid=100, last_modseq=20)
    next_state = compute_next_sync_cursor(current, discovered_uid_max=10, discovered_modseq_max=30)
    assert next_state.uidvalidity == 88
    assert next_state.last_uid == 100
    assert next_state.last_modseq == 30
