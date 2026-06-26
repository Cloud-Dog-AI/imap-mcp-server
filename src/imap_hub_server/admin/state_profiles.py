"""Profile overlay, settings, and config-event admin state operations."""

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

from imap_hub_core.storage_paths import join_fs_path, read_storage_bytes
from imap_hub_server.admin.state_models import ConfigEvent, _json_safe


class AdminStateProfileMixin:
    """Manage service-local profile overlays, settings, and event-log storage."""

    @property
    def event_path(self) -> str:
        """Return the append-only event log path used by A2A consumers."""
        return join_fs_path(self._data_dir, "config_events.jsonl")

    def event_log_size_bytes(self) -> int:
        """Return the current config-event log size in bytes."""
        stat = self._storage.stat(self._event_key)
        if stat is None or stat.size is None:
            return 0
        return int(stat.size)

    def read_event_lines_from(self, offset: int) -> tuple[list[str], int]:
        """Read config-event lines from a byte offset and return the new offset."""
        stat = self._storage.stat(self._event_key)
        if stat is None:
            return [], 0
        data = read_storage_bytes(self._storage, self._event_key)
        if offset < 0 or offset > len(data):
            offset = 0
        chunk = data[offset:]
        return [line for line in chunk.decode("utf-8").splitlines() if line.strip()], len(data)

    def emit_event(
        self,
        *,
        entity_type: str,
        action: str,
        entity_id: str,
        actor_id: str,
        source: str,
        outcome: str = "success",
        details: dict[str, Any] | None = None,
    ) -> ConfigEvent:
        """Append a config event for later A2A WebSocket delivery."""
        event = ConfigEvent(
            entity_type=entity_type,
            action=action,
            entity_id=entity_id,
            actor_id=actor_id,
            source=source,
            outcome=outcome,
            details=details or {},
        )
        with self._lock:
            self._storage.append_text(
                self._event_key, f"{event.model_dump_json(exclude_none=True)}\n"
            )
        return event

    @staticmethod
    def _clone_profiles(profiles: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Return a detached JSON-safe profile mapping."""
        return json.loads(json.dumps(_json_safe(profiles)))

    def export_profiles(self, base_profiles: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Merge seed profiles with persisted overrides and deletions.

        W28E-1803C: when a persisted override exists for a profile that is ALSO a
        seed profile, the override's blank/omitted secret credentials fall back to
        the seed's. The WebUI never round-trips secret mailbox credentials, so a
        persisted override of a seed profile (e.g. the `operations` mailbox)
        legitimately lacks the username/password; without this fallback the
        override would strip the seed/Vault credentials and break live IMAP.
        """
        snapshot = self._load()
        merged = self._clone_profiles(base_profiles)
        for profile_id in snapshot.deleted_profiles:
            merged.pop(profile_id, None)
        for profile_id, payload in snapshot.profiles.items():
            override = json.loads(json.dumps(payload))
            seed = merged.get(profile_id)
            if isinstance(seed, dict):
                override = self._restore_seed_credentials(seed, override)
            merged[profile_id] = override
        return merged

    @staticmethod
    def _restore_seed_credentials(
        seed: dict[str, Any], override: dict[str, Any]
    ) -> dict[str, Any]:
        """Fill blank/omitted override secret credentials from the seed profile.

        Non-empty override values still win; only empty or missing
        username/password/app_password fields fall back to the seed.
        """
        seed_creds = seed.get("credentials")
        if not isinstance(seed_creds, dict):
            return override
        over_creds = override.get("credentials")
        over_creds = dict(over_creds) if isinstance(over_creds, dict) else {}
        changed = False
        for key in ("username", "password", "app_password"):
            if not str(over_creds.get(key) or "").strip() and str(seed_creds.get(key) or "").strip():
                over_creds[key] = seed_creds.get(key)
                changed = True
        if changed:
            override = dict(override)
            override["credentials"] = over_creds
        return override

    def list_profiles(self, base_profiles: dict[str, dict[str, Any]]) -> list[str]:
        """Return visible profile identifiers across seed and dynamic state."""
        return sorted(self.export_profiles(base_profiles).keys())

    def get_profile(
        self,
        profile_id: str,
        base_profiles: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Return one visible profile payload or None."""
        return self.export_profiles(base_profiles).get(profile_id)

    def upsert_profile(self, profile_id: str, payload: dict[str, Any]) -> None:
        """Persist one dynamic profile payload for all runtimes."""
        with self._lock:
            snapshot = self._load()
            snapshot.profiles[profile_id] = json.loads(json.dumps(payload))
            snapshot.deleted_profiles = [
                item for item in snapshot.deleted_profiles if item != profile_id
            ]
            self._save(snapshot)

    def delete_profile(self, profile_id: str) -> None:
        """Delete one profile from the shared overlay and hide seed profiles when removed."""
        with self._lock:
            snapshot = self._load()
            snapshot.profiles.pop(profile_id, None)
            if profile_id not in snapshot.deleted_profiles:
                snapshot.deleted_profiles.append(profile_id)
            self._save(snapshot)

    def get_settings(self) -> dict[str, Any]:
        """Return persisted admin settings merged with stable defaults."""
        snapshot = self._load()
        settings = dict(self._DEFAULT_SETTINGS)
        settings.update(_json_safe(snapshot.settings))
        return settings

    def update_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist non-critical WebUI service settings and return the merged state."""
        with self._lock:
            snapshot = self._load()
            current = dict(self._DEFAULT_SETTINGS)
            current.update(_json_safe(snapshot.settings))
            for key in ("polling_interval_seconds", "request_timeout_seconds"):
                if key in payload:
                    value = int(payload[key])
                    if value < 1 or value > 3600:
                        raise ValueError(f"{key}_out_of_range")
                    current[key] = value
            snapshot.settings = current
            self._save(snapshot)
            return dict(current)


__all__ = ["AdminStateProfileMixin"]
