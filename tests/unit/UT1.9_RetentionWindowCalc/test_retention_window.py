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

from imap_hub_core.cache.retention import expiry_cutoff_utc
import pytest
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-03")


def test_retention_cutoff_uses_max_age_days() -> None:
    now = datetime(2026, 2, 19, 12, 0, 0, tzinfo=timezone.utc)
    cutoff = expiry_cutoff_utc(max_age_days=30, now_utc=now)
    assert cutoff.isoformat() == "2026-01-20T12:00:00+00:00"
