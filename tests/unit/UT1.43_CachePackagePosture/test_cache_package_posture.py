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
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-22")


def test_cache_store_is_typed_mailbox_message_store_not_generic_cache() -> None:
    store = CacheStore()
    first = CachedMessage(
        message_id="mid-1",
        profile_id="operations",
        folder="INBOX",
        received_at_utc=datetime(2026, 5, 10, tzinfo=timezone.utc),
        size_bytes=128,
        subject="Operational status",
        body_text="status body",
    )
    second = CachedMessage(
        message_id="mid-2",
        profile_id="security",
        folder="Alerts",
        received_at_utc=datetime(2026, 5, 10, tzinfo=timezone.utc),
        size_bytes=256,
        subject="Security alert",
        body_text=None,
    )

    store.upsert_message(first)
    store.upsert_message(second)

    assert store.get_message("mid-1") == first
    assert store.list_messages("operations") == [first]
    assert store.list_messages("security") == [second]
    assert store.delete_messages(["mid-1", "missing"]) == 1
    assert store.get_message("mid-1") is None
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-22")


def test_cache_store_does_not_expose_generic_key_value_cache_api() -> None:
    store = CacheStore()

    assert not hasattr(store, "get")
    assert not hasattr(store, "set")
    assert not hasattr(store, "memoize")
