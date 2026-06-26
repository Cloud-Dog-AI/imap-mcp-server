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

import json
from typing import Any

from cloud_dog_storage.backends.local import LocalStorage

from imap_hub_core.storage_paths import read_storage_bytes, storage_for_file_path


def _storage_for_path(path: str) -> tuple[LocalStorage, str]:
    """Return a LocalStorage rooted at the parent dir and the filename key."""
    return storage_for_file_path(path)


def append_audit_line(path: str, event: dict[str, Any]) -> None:
    """Append one audit event to a JSONL file."""
    storage, key = _storage_for_path(path)
    storage.append_text(key, f"{json.dumps(event, sort_keys=True)}\n")


def read_audit_lines(path: str) -> list[dict[str, Any]]:
    """Read all audit events from a JSONL file."""
    storage, key = _storage_for_path(path)
    if not storage.exists(key):
        return []

    data = read_storage_bytes(storage, key)
    events: list[dict[str, Any]] = []
    for line in data.decode("utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        events.append(json.loads(raw))
    return events
