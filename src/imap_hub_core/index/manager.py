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

from typing import Any

REQUIRED_INDEX_FIELDS = {
    "profile_id",
    "message_id",
    "folder",
    "uid",
    "uidvalidity",
    "date_utc",
    "from",
    "to",
    "cc",
    "subject",
    "source",
    "content_type",
    "chunk_id",
    "content_hash",
}


def validate_index_metadata(metadata: dict[str, Any]) -> None:
    """Validate strict metadata schema for indexed chunks."""
    missing = REQUIRED_INDEX_FIELDS.difference(metadata.keys())
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(f"Index metadata missing fields: {names}")


class IndexManager:
    """Minimal index manager contract for managed reconcile workflows."""

    def __init__(self, enabled: bool) -> None:
        """
        Purpose: Implement `__init__` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        self.enabled = enabled

    def upsert(self, documents: list[dict[str, Any]]) -> int:
        """Validate metadata and return number of prepared documents."""
        if not self.enabled:
            return 0

        for document in documents:
            validate_index_metadata(document)
        return len(documents)
