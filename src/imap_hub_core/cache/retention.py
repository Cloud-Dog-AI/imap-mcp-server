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

from datetime import datetime, timedelta, timezone

from imap_hub_core.cache.store import CachedMessage


def expiry_cutoff_utc(max_age_days: int, now_utc: datetime | None = None) -> datetime:
    """Return UTC cutoff timestamp used to expire cached messages."""
    reference = now_utc or datetime.now(timezone.utc)
    return reference - timedelta(days=max_age_days)


def select_messages_for_eviction(
    messages: list[CachedMessage],
    max_age_days: int,
    max_total_bytes: int,
    max_messages: int,
    now_utc: datetime | None = None,
) -> list[CachedMessage]:
    """Select messages for eviction using age-first then oldest-first ordering."""
    cutoff = expiry_cutoff_utc(max_age_days=max_age_days, now_utc=now_utc)
    outside_window = [item for item in messages if item.received_at_utc < cutoff]

    kept = [item for item in messages if item.received_at_utc >= cutoff]
    kept_sorted = sorted(kept, key=lambda entry: entry.received_at_utc)

    evicted: list[CachedMessage] = list(outside_window)
    total_bytes = sum(item.size_bytes for item in kept_sorted)

    while kept_sorted and (len(kept_sorted) > max_messages or total_bytes > max_total_bytes):
        candidate = kept_sorted.pop(0)
        evicted.append(candidate)
        total_bytes -= candidate.size_bytes

    return evicted
