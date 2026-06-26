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

from typing import Literal

from imap_hub_core.duplicate.detector import DuplicateCandidate


def choose_keeper(
    group: list[DuplicateCandidate],
    policy: Literal["newest", "oldest", "flagged", "first_seen"],
) -> DuplicateCandidate:
    """Choose which message to keep from a duplicate group."""
    if not group:
        raise ValueError("Duplicate group cannot be empty")

    if policy == "newest":
        return max(group, key=lambda item: item.received_at_utc)
    if policy == "oldest" or policy == "first_seen":
        return min(group, key=lambda item: item.received_at_utc)
    flagged = [item for item in group if item.flagged]
    if flagged:
        return min(flagged, key=lambda item: item.received_at_utc)
    return min(group, key=lambda item: item.received_at_utc)
