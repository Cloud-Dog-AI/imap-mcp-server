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

from imap_hub_core.ledger.similarity import build_similarity_key
import pytest
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-07")


def test_similarity_key_excludes_limit_and_sort_by_default() -> None:
    key_one, canonical_one = build_similarity_key(
        "p1", "cache", "abc", {"limit": 10, "sort": "date_desc"}
    )
    key_two, canonical_two = build_similarity_key(
        "p1", "cache", "abc", {"limit": 25, "sort": "date_asc"}
    )
    assert key_one == key_two
    assert "limit" not in canonical_one["filters_norm"]
    assert "sort" not in canonical_two["filters_norm"]
