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

# Covers: FR-07

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class LedgerEntry:
    """Stored search execution entry."""

    search_id: str
    actor_id: str
    profile_id: str
    similarity_key: str
    created_at: datetime
    high_water_mark: dict[str, Any] = field(default_factory=dict)
    result_ids: list[str] = field(default_factory=list)


class SearchLedgerStore:
    """Append-only in-memory search ledger for delta baselines."""

    def __init__(self) -> None:
        """
        Purpose: Implement `__init__` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        self._entries: list[LedgerEntry] = []

    def append(self, entry: LedgerEntry) -> None:
        """Store a ledger entry."""
        self._entries.append(entry)

    def find_last_similar(
        self, actor_id: str, profile_id: str, similarity_key: str
    ) -> LedgerEntry | None:
        """Find the newest entry matching actor/profile/similarity key."""
        for entry in reversed(self._entries):
            if (
                entry.actor_id == actor_id
                and entry.profile_id == profile_id
                and entry.similarity_key == similarity_key
            ):
                return entry
        return None

    def resolve_high_water_mark(self, entry: LedgerEntry) -> tuple[str, Any] | None:
        """Resolve delta baseline priority MODSEQ > UID > timestamp."""
        hwm = entry.high_water_mark
        if "per_folder_modseq_max" in hwm:
            return "per_folder_modseq_max", hwm["per_folder_modseq_max"]
        if "per_folder_uid_max" in hwm:
            return "per_folder_uid_max", hwm["per_folder_uid_max"]
        if "max_received_at_utc" in hwm:
            return "max_received_at_utc", hwm["max_received_at_utc"]
        return None
