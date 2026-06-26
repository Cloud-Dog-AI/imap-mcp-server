"""IDAM-backed user, group, API-key, and scope admin state operations."""

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

import fnmatch
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from cloud_dog_idam import APIKeyManager, RBACEngine
from cloud_dog_idam.domain.enums import UserStatus
from cloud_dog_idam.domain.models import ApiKey

from imap_hub_server.admin.state_models import APIKeyRecord, GroupRecord, UserRecord, _ts


class AdminStateIDAMMixin:
    """Persist IMAP admin records and hydrate cloud_dog_idam runtime components."""

    def list_users(self) -> list[UserRecord]:
        """Return all configured users sorted by username then ID."""
        snapshot = self._load()
        return sorted(snapshot.users.values(), key=lambda item: (item.username, item.user_id))

    def get_user(self, user_id: str) -> UserRecord | None:
        """Return one configured user or None."""
        return self._load().users.get(user_id)

    def create_user(self, payload: dict[str, Any]) -> UserRecord:
        """Create one user record from validated payload values."""
        payload = self._normalise_idam_user_payload(payload)
        with self._lock:
            snapshot = self._load()
            user_id = str(payload.get("user_id") or uuid4())
            username = str(payload.get("username") or "").strip()
            email = str(payload.get("email") or "").strip()
            if not username or not email:
                raise ValueError("username_and_email_required")
            for existing in snapshot.users.values():
                if existing.user_id == user_id:
                    raise ValueError("user_id_exists")
                if existing.username.lower() == username.lower():
                    raise ValueError("username_exists")

            record = UserRecord(
                user_id=user_id,
                username=username,
                email=email,
                display_name=str(payload.get("display_name") or "").strip(),
                status=str(payload.get("status") or "active").strip().lower() or "active",
                role=str(payload.get("role") or "viewer").strip().lower() or "viewer",
                is_system_user=bool(payload.get("is_system_user", False)),
                tenant_id=str(payload.get("tenant_id") or "").strip() or None,
            )
            snapshot.users[record.user_id] = record
            self._save(snapshot)
            return record

    def update_user(self, user_id: str, payload: dict[str, Any]) -> UserRecord:
        """Update mutable user fields and return the new persisted record."""
        payload = self._normalise_idam_user_payload(payload)
        with self._lock:
            snapshot = self._load()
            record = snapshot.users.get(user_id)
            if record is None:
                raise KeyError(user_id)
            updates = record.model_dump()
            for key in (
                "username",
                "email",
                "display_name",
                "status",
                "role",
                "is_system_user",
                "tenant_id",
            ):
                if key in payload:
                    value = payload[key]
                    if key in {"username", "email", "display_name", "role", "tenant_id"}:
                        value = str(value or "").strip()
                    if key == "status":
                        value = str(value or "active").strip().lower()
                    updates[key] = value
            updates["updated_at"] = _ts()
            updated = UserRecord.model_validate(updates)
            for existing_id, existing in snapshot.users.items():
                if existing_id == user_id:
                    continue
                if existing.username.lower() == updated.username.lower():
                    raise ValueError("username_exists")
            snapshot.users[user_id] = updated
            self._save(snapshot)
            return updated

    def delete_user(self, user_id: str) -> bool:
        """Delete one user and clean up memberships and owned keys."""
        with self._lock:
            snapshot = self._load()
            if user_id not in snapshot.users:
                return False
            snapshot.users.pop(user_id, None)
            for group_id, group in list(snapshot.groups.items()):
                members = [member for member in group.members if member != user_id]
                group_admins = [admin_id for admin_id in group.group_admins if admin_id != user_id]
                snapshot.groups[group_id] = group.model_copy(
                    update={"members": members, "group_admins": group_admins, "updated_at": _ts()}
                )
            for key_id, key_record in list(snapshot.api_keys.items()):
                if key_record.owner_user_id == user_id:
                    snapshot.api_keys[key_id] = key_record.model_copy(
                        update={"status": "revoked", "updated_at": _ts()}
                    )
            self._save(snapshot)
            return True

    def list_groups(self) -> list[GroupRecord]:
        """Return all configured groups sorted by name then ID."""
        snapshot = self._load()
        return sorted(snapshot.groups.values(), key=lambda item: (item.name, item.group_id))

    def get_group(self, group_id: str) -> GroupRecord | None:
        """Return one configured group or None."""
        return self._load().groups.get(group_id)

    def create_group(self, payload: dict[str, Any]) -> GroupRecord:
        """Create one group record with optional roles and members."""
        with self._lock:
            snapshot = self._load()
            group_id = str(payload.get("group_id") or uuid4())
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ValueError("group_name_required")
            for existing in snapshot.groups.values():
                if existing.group_id == group_id:
                    raise ValueError("group_id_exists")
                if existing.name.lower() == name.lower():
                    raise ValueError("group_name_exists")

            roles = sorted(
                {str(item).strip().lower() for item in payload.get("roles", []) if str(item).strip()}
            )
            members = sorted(
                {str(item).strip() for item in payload.get("members", []) if str(item).strip()}
            )
            for member in members:
                if member not in snapshot.users:
                    raise KeyError(f"user_not_found:{member}")
            group_admins = sorted(
                {str(item).strip() for item in payload.get("group_admins", []) if str(item).strip()}
            )
            for admin_id in group_admins:
                if admin_id not in snapshot.users:
                    raise KeyError(f"user_not_found:{admin_id}")
                if admin_id not in members:
                    raise ValueError(f"group_admin_not_member:{admin_id}")

            record = GroupRecord(
                group_id=group_id,
                name=name,
                description=str(payload.get("description") or "").strip(),
                roles=roles,
                members=members,
                group_admins=group_admins,
                tenant_id=str(payload.get("tenant_id") or "").strip() or None,
            )
            snapshot.groups[record.group_id] = record
            self._save(snapshot)
            return record

    def update_group(self, group_id: str, payload: dict[str, Any]) -> GroupRecord:
        """Update group metadata and role assignments."""
        with self._lock:
            snapshot = self._load()
            record = snapshot.groups.get(group_id)
            if record is None:
                raise KeyError(group_id)
            updates = record.model_dump()
            for key in ("name", "description", "tenant_id"):
                if key in payload:
                    updates[key] = str(payload.get(key) or "").strip()
            if "roles" in payload:
                updates["roles"] = sorted(
                    {
                        str(item).strip().lower()
                        for item in payload.get("roles", [])
                        if str(item).strip()
                    }
                )
            if "group_admins" in payload:
                updates["group_admins"] = sorted(
                    {str(item).strip() for item in payload.get("group_admins", []) if str(item).strip()}
                )
            updates["updated_at"] = _ts()
            updated = GroupRecord.model_validate(updates)
            for admin_id in updated.group_admins:
                if admin_id not in snapshot.users:
                    raise KeyError(f"user_not_found:{admin_id}")
                if admin_id not in updated.members:
                    raise ValueError(f"group_admin_not_member:{admin_id}")
            for existing_id, existing in snapshot.groups.items():
                if existing_id == group_id:
                    continue
                if existing.name.lower() == updated.name.lower():
                    raise ValueError("group_name_exists")
            snapshot.groups[group_id] = updated
            self._save(snapshot)
            return updated

    def delete_group(self, group_id: str) -> bool:
        """Delete one group from the shared state."""
        with self._lock:
            snapshot = self._load()
            if group_id not in snapshot.groups:
                return False
            snapshot.groups.pop(group_id, None)
            self._save(snapshot)
            return True

    def add_group_member(self, group_id: str, user_id: str) -> GroupRecord:
        """Add one user to a group and return the new group record."""
        with self._lock:
            snapshot = self._load()
            group = snapshot.groups.get(group_id)
            if group is None:
                raise KeyError(group_id)
            if user_id not in snapshot.users:
                raise KeyError(f"user_not_found:{user_id}")
            members = sorted(set(group.members) | {user_id})
            updated = group.model_copy(update={"members": members, "updated_at": _ts()})
            snapshot.groups[group_id] = updated
            self._save(snapshot)
            return updated

    def remove_group_member(self, group_id: str, user_id: str) -> GroupRecord:
        """Remove one user from a group and return the new group record."""
        with self._lock:
            snapshot = self._load()
            group = snapshot.groups.get(group_id)
            if group is None:
                raise KeyError(group_id)
            members = [member for member in group.members if member != user_id]
            group_admins = [admin_id for admin_id in group.group_admins if admin_id != user_id]
            updated = group.model_copy(
                update={"members": members, "group_admins": group_admins, "updated_at": _ts()}
            )
            snapshot.groups[group_id] = updated
            self._save(snapshot)
            return updated

    def list_api_keys(self) -> list[APIKeyRecord]:
        """Return active managed API keys sorted by creation time then ID."""
        snapshot = self._load()
        active = [item for item in snapshot.api_keys.values() if item.status == "active"]
        return sorted(active, key=lambda item: (item.created_at, item.api_key_id))

    def get_api_key(self, api_key_id: str) -> APIKeyRecord | None:
        """Return one managed API key record or None."""
        return self._load().api_keys.get(api_key_id)

    def create_api_key(
        self,
        *,
        payload: dict[str, Any],
        api_key_manager: APIKeyManager,
    ) -> tuple[str, APIKeyRecord]:
        """Generate, persist, and return one scoped API key."""
        with self._lock:
            snapshot = self._load()
            payload = self._normalise_idam_api_key_payload(payload)
            owner_user_id = str(payload.get("owner_user_id") or "").strip()
            if not owner_user_id:
                raise ValueError("owner_user_id_required")
            if owner_user_id not in snapshot.users:
                raise KeyError(f"user_not_found:{owner_user_id}")
            ttl_days = payload.get("ttl_days")
            ttl_value = int(ttl_days) if ttl_days not in (None, "") else None
            raw_key, metadata = api_key_manager.generate(
                owner_user_id,
                ttl_days=ttl_value,
                key_prefix=str(payload.get("key_prefix") or "cd_").strip() or "cd_",
            )
            generated = api_key_manager._keys[metadata.api_key_id]  # noqa: SLF001
            scopes = sorted(
                {str(item).strip().lower() for item in payload.get("scopes", []) if str(item).strip()}
            )
            record = APIKeyRecord(
                api_key_id=metadata.api_key_id,
                owner_user_id=owner_user_id,
                key_prefix=metadata.key_prefix,
                key_hash=generated.key_hash,
                status="active",
                scopes=scopes,
                description=str(payload.get("description") or "").strip(),
                expires_at=_ts(metadata.expires_at) if metadata.expires_at else None,
            )
            snapshot.api_keys[record.api_key_id] = record
            self._save(snapshot)
            return raw_key, record

    def revoke_api_key(self, api_key_id: str, api_key_manager: APIKeyManager) -> bool:
        """Revoke one API key in both persistence and runtime manager."""
        with self._lock:
            snapshot = self._load()
            record = snapshot.api_keys.get(api_key_id)
            if record is None:
                return False
            api_key_manager.revoke(api_key_id)
            snapshot.api_keys[api_key_id] = record.model_copy(
                update={"status": "revoked", "updated_at": _ts()}
            )
            self._save(snapshot)
            return True

    def sync_api_key_manager(self, api_key_manager: APIKeyManager) -> None:
        """Load persisted managed API keys into the runtime key manager."""
        snapshot = self._load()
        for record in snapshot.api_keys.values():
            api_key_manager._keys[record.api_key_id] = ApiKey(  # noqa: SLF001
                api_key_id=record.api_key_id,
                owner_user_id=record.owner_user_id,
                key_prefix=record.key_prefix,
                key_hash=record.key_hash,
                status=record.status,
                expires_at=datetime.fromisoformat(record.expires_at.replace("Z", "+00:00"))
                if record.expires_at
                else None,
            )

    def sync_rbac_engine(self, rbac_engine: RBACEngine) -> None:
        """Rebuild the runtime RBAC engine from persisted users and groups."""
        snapshot = self._load()
        rbac_engine._user_roles = {}  # noqa: SLF001
        rbac_engine._group_memberships = {}  # noqa: SLF001
        rbac_engine._group_roles = {}  # noqa: SLF001
        rbac_engine._cache._data.clear()  # noqa: SLF001
        for record in snapshot.users.values():
            if record.role:
                rbac_engine.assign_role_to_user(record.user_id, record.role)
        for record in snapshot.groups.values():
            for role in record.roles:
                rbac_engine.assign_role_to_group(record.group_id, role)
            for user_id in record.members:
                rbac_engine.add_user_to_group(user_id, record.group_id)

    def key_has_scope(self, api_key_id: str | None, required_scope: str) -> bool:
        """Return True when the managed API key record grants the required scope."""
        if not api_key_id:
            return False
        record = self.get_api_key(api_key_id)
        if record is None:
            # Static environment keys are not managed here and remain unrestricted.
            return True
        scopes = record.scopes
        if not scopes:
            return False
        for scope in scopes:
            if scope == "*" or fnmatch.fnmatch(required_scope, scope) or fnmatch.fnmatch(scope, required_scope):
                return True
        return False

    def groups_for_user(self, user_id: str) -> list[GroupRecord]:
        """Return groups that contain the provided user."""
        return [group for group in self.list_groups() if user_id in group.members]

    def group_admin_groups_for_user(self, user_id: str) -> list[GroupRecord]:
        """Return groups where the provided user has delegated group-admin rights."""
        return [group for group in self.list_groups() if user_id in group.group_admins]

    def is_group_member(self, user_id: str, group_id: str) -> bool:
        """Return whether the user is a member of the named group."""
        group = self.get_group(group_id)
        return bool(group is not None and user_id in group.members)

    def is_group_admin(self, user_id: str, group_id: str) -> bool:
        """Return whether the user has delegated admin rights in the named group."""
        group = self.get_group(group_id)
        return bool(group is not None and user_id in group.group_admins)

    @staticmethod
    def _normalise_idam_user_payload(payload: dict[str, Any]) -> dict[str, Any]:
        """Map shared @cloud-dog/idam WebUI field names onto native UserRecord fields.

        W28A-735-R5: the shared ``IdamUsersPage`` (used by the imap WebUI) submits
        ``{name, disabled, is_system_admin}``; translate them to the native
        ``{display_name, status, role}`` when the native key is absent. Additive
        and non-destructive: native callers that already send the native field
        names are untouched.
        """
        out = dict(payload)
        if "name" in out and "display_name" not in out:
            out["display_name"] = out.pop("name")
        if "disabled" in out and "status" not in out:
            out["status"] = "disabled" if out.pop("disabled") else "active"
        if "is_system_admin" in out and "role" not in out:
            out["role"] = "admin" if out.pop("is_system_admin") else "user"
        return out

    @staticmethod
    def _normalise_idam_api_key_payload(payload: dict[str, Any]) -> dict[str, Any]:
        """Map shared @cloud-dog/idam WebUI api-key field names onto native keys.

        W28A-735-R5: the shared ``IdamApiKeysPage`` (used by the imap WebUI)
        submits ``{user_id, name, groups, expires_at}``; translate them to the
        native ``{owner_user_id, description, scopes, ttl_days}`` when the native
        key is absent. Owner ids are kept as strings (imap user ids such as
        ``"admin"`` are non-numeric). Additive and non-destructive: native
        callers that already send the native field names are untouched.
        """
        out = dict(payload)
        if "owner_user_id" not in out and out.get("user_id") not in (None, ""):
            out["owner_user_id"] = str(out["user_id"]).strip()
        if "description" not in out and "name" in out:
            out["description"] = out["name"]
        if "scopes" not in out and "groups" in out:
            groups = out["groups"]
            out["scopes"] = list(groups) if isinstance(groups, (list, tuple)) else [groups]
        if "ttl_days" not in out and out.get("expires_at"):
            try:
                expiry = datetime.fromisoformat(str(out["expires_at"]).replace("Z", "+00:00"))
                delta_days = (expiry - datetime.now(timezone.utc)).days
                if delta_days > 0:
                    out["ttl_days"] = delta_days
            except ValueError:
                pass
        return out

    def export_user(self, record: UserRecord) -> dict[str, Any]:
        """Return a stable JSON-safe user payload for API and tool responses.

        W28A-735-R5: also expose the shared @cloud-dog/idam WebUI contract aliases
        (``id`` / ``name`` / ``disabled`` / ``is_system_admin``) ALONGSIDE the
        native fields. The shared ``IdamUsersPage`` binds the record id from
        ``row.id`` for edit/delete; without ``id`` the WebUI edit issues
        ``PUT /admin/users/undefined`` (404). Aliases are additive — native
        consumers that read ``user_id`` / ``display_name`` / ``status`` / ``role``
        are unaffected.
        """
        payload = record.model_dump()
        payload.setdefault("id", record.user_id)
        payload.setdefault("name", record.display_name or record.username)
        payload.setdefault("disabled", record.status.strip().lower() != "active")
        payload.setdefault("is_system_admin", record.role.strip().lower() == "admin")
        return payload

    def export_group(self, record: GroupRecord) -> dict[str, Any]:
        """Return a stable JSON-safe group payload for API and tool responses.

        W28A-735-R5: also expose the shared @cloud-dog/idam WebUI contract aliases
        (``id`` + ``member_count``) alongside the native fields so the shared
        ``IdamGroupsPage`` can bind the group id for edit/delete. Additive.
        """
        payload = record.model_dump()
        payload.setdefault("id", record.group_id)
        payload.setdefault("member_count", len(record.members))
        return payload

    def export_api_key(self, record: APIKeyRecord) -> dict[str, Any]:
        """Return API key metadata without exposing raw key material.

        W28A-735-R5: also expose the shared @cloud-dog/idam WebUI contract aliases
        (``id`` / ``name`` / ``user_id`` / ``groups``) alongside the native fields
        so the shared ``IdamApiKeysPage`` can bind the key id for revoke. Additive.
        """
        payload = record.model_dump()
        payload.pop("key_hash", None)
        payload.setdefault("id", record.api_key_id)
        payload.setdefault("name", record.description or record.api_key_id)
        payload.setdefault("user_id", record.owner_user_id)
        payload.setdefault("groups", list(record.scopes))
        return payload

    def bootstrap_admin_user(self, user_id: str = "integration-user") -> None:
        """Ensure a default admin user exists for seeded integration keys."""
        if self.get_user(user_id) is not None:
            return
        self.create_user(
            {
                "user_id": user_id,
                "username": user_id,
                "email": f"{user_id}@example.com",
                "display_name": "Integration Admin",
                "role": "admin",
                "status": UserStatus.ACTIVE.value,
                "is_system_user": True,
            }
        )


__all__ = ["AdminStateIDAMMixin"]
