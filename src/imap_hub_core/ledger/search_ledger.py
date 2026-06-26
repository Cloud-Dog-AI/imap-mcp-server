"""imap-mcp-server module."""

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
from typing import Any
from uuid import uuid4

from imap_hub_core.ledger.store import LedgerEntry, SearchLedgerStore


def record_search(
    ledger: SearchLedgerStore,
    actor_id: str,
    profile_id: str,
    similarity_key: str,
    high_water_mark: dict[str, Any],
    result_ids: list[str],
) -> LedgerEntry:
    """Create and append a ledger entry for one executed search."""
    entry = LedgerEntry(
        search_id=f"search-{uuid4().hex[:12]}",
        actor_id=actor_id,
        profile_id=profile_id,
        similarity_key=similarity_key,
        created_at=datetime.now(timezone.utc),
        high_water_mark=high_water_mark,
        result_ids=result_ids,
    )
    ledger.append(entry)
    return entry


def find_baseline(
    ledger: SearchLedgerStore,
    actor_id: str,
    profile_id: str,
    similarity_key: str,
) -> LedgerEntry | None:
    """Return the latest baseline entry for a similarity key."""
    return ledger.find_last_similar(
        actor_id=actor_id,
        profile_id=profile_id,
        similarity_key=similarity_key,
    )
