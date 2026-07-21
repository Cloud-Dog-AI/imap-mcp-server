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

# Covers: FR-21

from datetime import datetime

from cloud_dog_storage.backends.local import LocalStorage

from imap_hub_core.storage_paths import join_fs_path, write_storage_bytes


def build_archive_message_path(
    root: str,
    profile_id: str,
    received_at: datetime,
    message_id: str,
) -> str:
    """Build deterministic archive path: root/profile/YYYY/MM/DD/message_id."""
    return join_fs_path(
        root,
        profile_id,
        received_at.strftime("%Y"),
        received_at.strftime("%m"),
        received_at.strftime("%d"),
        message_id,
    )


def _relative_archive_path(
    profile_id: str,
    received_at: datetime,
    message_id: str,
) -> str:
    """Build the archive-relative POSIX path for a message folder."""
    return "/".join([
        profile_id,
        received_at.strftime("%Y"),
        received_at.strftime("%m"),
        received_at.strftime("%d"),
        message_id,
    ])


class ArchiveExporter:
    """Export message payloads into deterministic archive folders."""

    def __init__(self, archive_root: str) -> None:
        """
        Purpose: Implement `__init__` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        self.archive_root = archive_root
        self._storage = LocalStorage(root_path=archive_root)

    def export_message(
        self,
        profile_id: str,
        received_at: datetime,
        message_id: str,
        raw_eml: bytes,
        metadata_json: str,
        force: bool = False,
    ) -> str:
        """Write message archive artefacts and return the message folder path."""
        rel = _relative_archive_path(profile_id, received_at, message_id)
        eml_key = f"{rel}/message.eml"
        json_key = f"{rel}/message.json"

        if not force and self._storage.exists(eml_key) and self._storage.exists(json_key):
            return build_archive_message_path(
                self.archive_root, profile_id, received_at, message_id
            )

        write_storage_bytes(self._storage, eml_key, raw_eml)
        write_storage_bytes(self._storage, json_key, metadata_json.encode("utf-8"))
        return build_archive_message_path(
            self.archive_root, profile_id, received_at, message_id
        )
