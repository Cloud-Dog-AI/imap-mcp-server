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

# Covers: FR-20

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(slots=True)
class DuplicateCandidate:
    """Normalised message summary used by duplicate detection."""

    message_id: str
    header_message_id: str | None
    content_hash: str | None
    sender: str
    subject: str
    received_at_utc: datetime
    size_bytes: int
    flagged: bool = False


def _heuristic_key(item: DuplicateCandidate) -> str:
    """
    Purpose: Implement `_heuristic_key` behaviour for this module.
    Inputs: Parameters are defined by the function/class signature.
    Outputs: Returns values according to the module contract.
    Dependencies: Uses internal project modules and configured services.
    Related tests: See TESTS.md and tests/ for coverage mapping.
    """
    bucket = item.received_at_utc.replace(second=0, microsecond=0).isoformat()
    return f"{item.sender.lower()}|{item.subject.lower()}|{bucket}|{item.size_bytes}"


def group_duplicates(
    candidates: list[DuplicateCandidate],
    strategy: Literal["message_id", "content_hash", "heuristic"],
) -> list[list[DuplicateCandidate]]:
    """Group duplicate candidates by selected strategy and return groups with at least two members."""
    grouped: dict[str, list[DuplicateCandidate]] = {}

    for item in candidates:
        key: str | None
        if strategy == "message_id":
            key = item.header_message_id
        elif strategy == "content_hash":
            key = item.content_hash
        else:
            key = _heuristic_key(item)

        if not key:
            continue
        grouped.setdefault(key, []).append(item)

    return [group for group in grouped.values() if len(group) > 1]
