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

import hashlib
import json
from typing import Any

from imap_hub_core.ledger.normaliser import canonicalise_filters, normalise_query_text


def build_similarity_key(
    profile_id: str,
    mode: str,
    query: str,
    filters: dict[str, Any] | None,
    similarity_pins: list[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return SHA-256 similarity key and canonical payload for a search request."""
    query_norm = normalise_query_text(query)
    filters_norm, pins = canonicalise_filters(filters, pins=similarity_pins)

    canonical = {
        "profile_id": profile_id,
        "mode": mode,
        "query_norm": query_norm,
        "filters_norm": filters_norm,
        "pinned": pins,
    }
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest(), canonical
