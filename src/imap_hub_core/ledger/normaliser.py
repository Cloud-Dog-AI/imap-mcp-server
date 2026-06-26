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

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

VOLATILE_FIELDS = {"limit", "sort", "page", "cursor", "dry_run", "record_search"}


def _rfc3339_z(timestamp: str) -> str:
    """
    Purpose: Implement `_rfc3339_z` behaviour for this module.
    Inputs: Parameters are defined by the function/class signature.
    Outputs: Returns values according to the module contract.
    Dependencies: Uses internal project modules and configured services.
    Related tests: See TESTS.md and tests/ for coverage mapping.
    """
    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


def normalise_query_text(query: str) -> str:
    """Normalise free-text query using NFKC, trim, lowercase, and whitespace collapse."""
    value = unicodedata.normalize("NFKC", query or "")
    value = value.strip().lower()
    return re.sub(r"\s+", " ", value)


def canonicalise_filters(
    filters: dict[str, Any] | None,
    pins: list[str] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Canonicalise filter payload and exclude volatile fields unless pinned."""
    pinned = set(pins or [])
    canonical: dict[str, Any] = {}

    for key, value in (filters or {}).items():
        if key in VOLATILE_FIELDS and key not in pinned:
            continue
        if value is None:
            continue
        if isinstance(value, list):
            entries = sorted({str(item).strip() for item in value if str(item).strip()})
            if entries:
                canonical[key] = entries
            continue
        if key in {"date_from_utc", "date_to_utc"}:
            canonical[key] = _rfc3339_z(str(value))
            continue
        if isinstance(value, (int, float)) and key.startswith("size_"):
            canonical[key] = int(value)
            continue
        canonical[key] = value

    return canonical, sorted(pinned)
