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

from imap_hub_core.cache.retention import select_messages_for_eviction
from imap_hub_core.cache.store import CachedMessage
import pytest
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-03")


def test_retention_eviction_prefers_oldest_messages() -> None:
    now = datetime(2026, 2, 19, 12, 0, 0, tzinfo=timezone.utc)
    messages = [
        CachedMessage("m1", "p", "INBOX", now - timedelta(days=1), 60, "s1"),
        CachedMessage("m2", "p", "INBOX", now - timedelta(days=2), 60, "s2"),
        CachedMessage("m3", "p", "INBOX", now - timedelta(days=3), 60, "s3"),
    ]
    evicted = select_messages_for_eviction(
        messages, max_age_days=30, max_total_bytes=120, max_messages=2, now_utc=now
    )
    assert [item.message_id for item in evicted] == ["m3"]
