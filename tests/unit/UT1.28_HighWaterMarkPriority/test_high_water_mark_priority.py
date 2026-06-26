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

from imap_hub_core.ledger.store import LedgerEntry, SearchLedgerStore
import pytest
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-07")


def test_high_water_mark_priority() -> None:
    store = SearchLedgerStore()
    entry = LedgerEntry(
        search_id="s1",
        actor_id="a1",
        profile_id="p1",
        similarity_key="k1",
        created_at=datetime.now(timezone.utc),
        high_water_mark={
            "per_folder_modseq_max": {"INBOX": 9},
            "per_folder_uid_max": {"INBOX": 11},
            "max_received_at_utc": "2026-02-19T12:00:00Z",
        },
    )
    store.append(entry)
    selected = store.resolve_high_water_mark(entry)
    assert selected is not None
    assert selected[0] == "per_folder_modseq_max"
