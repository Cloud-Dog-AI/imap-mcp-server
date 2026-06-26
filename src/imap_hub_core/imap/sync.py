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

from dataclasses import dataclass


@dataclass(slots=True)
class SyncState:
    """Persisted incremental sync cursor for one folder."""

    uidvalidity: int
    last_uid: int
    last_modseq: int | None


def compute_next_sync_cursor(
    current: SyncState,
    discovered_uid_max: int,
    discovered_modseq_max: int | None,
) -> SyncState:
    """Merge current and discovered folder cursors using high-water semantics."""
    if discovered_uid_max < current.last_uid:
        discovered_uid_max = current.last_uid

    modseq: int | None
    if current.last_modseq is None:
        modseq = discovered_modseq_max
    elif discovered_modseq_max is None:
        modseq = current.last_modseq
    else:
        modseq = max(current.last_modseq, discovered_modseq_max)

    return SyncState(
        uidvalidity=current.uidvalidity, last_uid=discovered_uid_max, last_modseq=modseq
    )
