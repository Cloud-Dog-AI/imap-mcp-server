"""RBAC resource-binding admin state operations (W28A-750 / IDAM-B2 §2.1)."""

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
from uuid import uuid4

from imap_hub_server.admin.state_models import RBACBindingRecord


class AdminStateBindingsMixin:
    """Persist RBAC resource bindings in the shared admin JSON snapshot.

    The binding rows are the group->resource edge that gives the cascade
    (group-admin adds U to G -> U accesses G's mailbox profile -> remove -> revoked)
    a data path. They are consumed at authorisation time by
    ``ImapBindingRepository.by_subject`` feeding the idam 0.5.0 resolver
    (``cloud_dog_idam.rbac.grants.authorise``). No SQLAlchemy table is used —
    imap stores identity + bindings in the same JSON snapshot.
    """

    def list_bindings(self) -> list[RBACBindingRecord]:
        """Return all configured RBAC bindings sorted by subject then resource."""
        snapshot = self._load()
        return sorted(
            snapshot.bindings.values(),
            key=lambda b: (b.subject_type, b.subject_id, b.resource_type, b.resource_id),
        )

    def get_binding(self, binding_id: str) -> RBACBindingRecord | None:
        """Return one RBAC binding record or None."""
        return self._load().bindings.get(binding_id)

    def list_bindings_by_subject(
        self, subject_type: str, subject_id: str
    ) -> list[RBACBindingRecord]:
        """Return bindings for one subject (the resolver's ``by_subject`` data path)."""
        snapshot = self._load()
        return [
            b
            for b in snapshot.bindings.values()
            if b.subject_type == subject_type and b.subject_id == subject_id
        ]

    def create_binding(self, payload: dict[str, Any]) -> RBACBindingRecord:
        """Create one RBAC binding from validated payload values."""
        with self._lock:
            snapshot = self._load()
            subject_type = str(payload.get("subject_type") or "").strip().lower()
            subject_id = str(payload.get("subject_id") or "").strip()
            resource_type = str(payload.get("resource_type") or "").strip()
            permission = str(payload.get("permission") or "").strip()
            if subject_type not in {"user", "group"}:
                raise ValueError("subject_type_must_be_user_or_group")
            if not subject_id or not resource_type or not permission:
                raise ValueError("subject_id_resource_type_permission_required")
            # Referential integrity against the identity store.
            if subject_type == "user" and subject_id not in snapshot.users:
                raise KeyError(f"user_not_found:{subject_id}")
            if subject_type == "group" and subject_id not in snapshot.groups:
                raise KeyError(f"group_not_found:{subject_id}")
            record = RBACBindingRecord(
                binding_id=str(payload.get("binding_id") or uuid4()),
                subject_type=subject_type,
                subject_id=subject_id,
                project=str(payload.get("project") or "imap-mcp").strip() or "imap-mcp",
                resource_type=resource_type,
                resource_id=str(payload.get("resource_id") or "*").strip() or "*",
                permission=permission,
                granted_by=str(payload.get("granted_by") or "").strip(),
            )
            # Idempotent: collapse an exact duplicate (same subject/resource/perm).
            for existing in snapshot.bindings.values():
                if (
                    existing.subject_type == record.subject_type
                    and existing.subject_id == record.subject_id
                    and existing.resource_type == record.resource_type
                    and existing.resource_id == record.resource_id
                    and existing.permission == record.permission
                ):
                    return existing
            snapshot.bindings[record.binding_id] = record
            self._save(snapshot)
            return record

    def delete_binding(self, binding_id: str) -> bool:
        """Delete one RBAC binding by id."""
        with self._lock:
            snapshot = self._load()
            if binding_id not in snapshot.bindings:
                return False
            snapshot.bindings.pop(binding_id, None)
            self._save(snapshot)
            return True


__all__ = ["AdminStateBindingsMixin"]
