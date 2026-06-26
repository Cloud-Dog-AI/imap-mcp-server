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

# Covers: FR-22

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class CachedMessage:
    """In-memory representation of a cached message."""

    message_id: str
    profile_id: str
    folder: str
    received_at_utc: datetime
    size_bytes: int
    subject: str
    body_text: str | None = None
    flags: set[str] = field(default_factory=set)


class CacheStore:
    """Simple cache abstraction used by tools and tests."""

    def __init__(self) -> None:
        """
        Purpose: Implement `__init__` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        self._messages: dict[str, CachedMessage] = {}

    def upsert_message(self, message: CachedMessage) -> None:
        """Insert or replace a cached message by ID."""
        self._messages[message.message_id] = message

    def get_message(self, message_id: str) -> CachedMessage | None:
        """Return cached message by ID if present."""
        return self._messages.get(message_id)

    def list_messages(self, profile_id: str | None = None) -> list[CachedMessage]:
        """List cached messages optionally filtered by profile."""
        if profile_id is None:
            return list(self._messages.values())
        return [item for item in self._messages.values() if item.profile_id == profile_id]

    def delete_messages(self, message_ids: list[str]) -> int:
        """Delete messages by ID and return the number removed."""
        removed = 0
        for message_id in message_ids:
            if self._messages.pop(message_id, None) is not None:
                removed += 1
        return removed
