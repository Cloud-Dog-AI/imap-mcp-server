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

from imap_hub_core.cache.store import CachedMessage, CacheStore
import pytest
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-22")


def test_st17_cache_store_and_retrieve() -> None:
    store = CacheStore()
    item = CachedMessage(
        "mid-1", "profile", "INBOX", datetime.now(timezone.utc), 42, "subject", "body"
    )
    store.upsert_message(item)
    loaded = store.get_message("mid-1")
    assert loaded is not None
    assert loaded.subject == "subject"
