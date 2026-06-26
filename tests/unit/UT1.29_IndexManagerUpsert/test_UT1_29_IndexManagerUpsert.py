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

from imap_hub_core.index.manager import IndexManager
import pytest
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-12")


def test_ut129_index_manager_upsert() -> None:
    manager = IndexManager(enabled=True)
    count = manager.upsert(
        [
            {
                "profile_id": "p1",
                "message_id": "m1",
                "folder": "INBOX",
                "uid": 1,
                "uidvalidity": 1,
                "date_utc": "2026-02-19T12:00:00Z",
                "from": "a@example.com",
                "to": "b@example.com",
                "cc": "",
                "subject": "subject",
                "source": "message",
                "content_type": "text/plain",
                "chunk_id": "c1",
                "content_hash": "hash-1",
            }
        ]
    )
    assert count == 1
