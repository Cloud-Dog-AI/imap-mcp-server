"""File-backed admin state compatibility surface."""

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

# Covers: CFG-06
# Covers: CFG-08
# Covers: CFG-09
# Covers: CFG-10
# Covers: CFG-11
# Covers: CFG-12
# Covers: CFG-13
# Covers: FR-13

import os
from threading import Lock
from uuid import uuid4

from cloud_dog_storage.backends.local import LocalStorage

from imap_hub_core.storage_paths import join_fs_path, read_storage_bytes, write_storage_bytes
from imap_hub_server.admin.state_bindings import AdminStateBindingsMixin
from imap_hub_server.admin.state_idam import AdminStateIDAMMixin
from imap_hub_server.admin.state_models import (
    APIKeyRecord,
    AdminStateSnapshot,
    ConfigEvent,
    GroupRecord,
    RBACBindingRecord,
    UserRecord,
)
from imap_hub_server.admin.state_profiles import AdminStateProfileMixin


class FileBackedAdminState(AdminStateProfileMixin, AdminStateIDAMMixin, AdminStateBindingsMixin):
    """Manage shared admin state stored in cloud_dog_storage local files.

    The runtime IDAM concerns delegate to cloud_dog_idam managers in the mixins.
    This class owns the IMAP-specific shared JSON snapshot and event-log contract.
    """

    _DEFAULT_SETTINGS = {
        "polling_interval_seconds": 30,
        "request_timeout_seconds": 15,
    }

    def __init__(self, data_dir: str) -> None:
        self._data_dir = join_fs_path(data_dir)
        self._storage = LocalStorage(root_path=self._data_dir)
        self._state_path = join_fs_path(self._data_dir, "admin_state.json")
        self._state_key = "/admin_state.json"
        self._event_key = "/config_events.jsonl"
        self._lock = Lock()

    def _load(self) -> AdminStateSnapshot:
        if not self._storage.exists(self._state_key):
            return AdminStateSnapshot()
        raw = read_storage_bytes(self._storage, self._state_key).decode("utf-8").strip()
        if not raw:
            return AdminStateSnapshot()
        return AdminStateSnapshot.model_validate_json(raw)

    def _save(self, snapshot: AdminStateSnapshot) -> None:
        tmp_key = f"{self._state_key}.{uuid4().hex}.tmp"
        write_storage_bytes(
            self._storage,
            tmp_key,
            snapshot.model_dump_json(indent=2, exclude_none=True).encode("utf-8"),
        )
        os.replace(join_fs_path(self._data_dir, tmp_key), self._state_path)


__all__ = [
    "APIKeyRecord",
    "AdminStateSnapshot",
    "ConfigEvent",
    "FileBackedAdminState",
    "GroupRecord",
    "RBACBindingRecord",
    "UserRecord",
]
