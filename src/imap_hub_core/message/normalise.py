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

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any


def _to_utc_iso(value: str | datetime | None) -> str | None:
    """
    Purpose: Implement `_to_utc_iso` behaviour for this module.
    Inputs: Parameters are defined by the function/class signature.
    Outputs: Returns values according to the module contract.
    Dependencies: Uses internal project modules and configured services.
    Related tests: See TESTS.md and tests/ for coverage mapping.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            dt = parsedate_to_datetime(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalise_message_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise message metadata to canonical UTC and key naming conventions."""
    normalised = dict(raw)
    if "date" in normalised and "date_utc" not in normalised:
        normalised["date_utc"] = _to_utc_iso(str(normalised["date"]))
    if "received_at" in normalised and "received_at_utc" not in normalised:
        normalised["received_at_utc"] = _to_utc_iso(str(normalised["received_at"]))

    for field in ("from", "to", "cc", "subject"):
        if field in normalised and isinstance(normalised[field], str):
            normalised[field] = normalised[field].strip()

    return normalised
