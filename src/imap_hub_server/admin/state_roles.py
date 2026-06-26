"""Canonical PS-71 §IW3A roles state, backed by cloud_dog_idam SqlAlchemyRoleStore."""

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

from typing import Any, Iterable

from cloud_dog_idam.domain.models import Role
from cloud_dog_idam.storage.sqlalchemy.role_store import (
    BaselineRoleProtected,
    SqlAlchemyRoleStore,
)


class RoleStateError(RuntimeError):
    """Structured roles error carrying an HTTP status and machine-readable code."""

    def __init__(self, code: str, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class RoleStoreState:
    """CRUD over the canonical cloud_dog_idam role tables via SqlAlchemyRoleStore.

    W28A-876 Gate 4b: the PS-71 §IW3A Roles page (``/api/v1/admin/roles``) is
    backed by the shared ``SqlAlchemyRoleStore`` rather than the bespoke imap
    role-policy concept. Each operation runs inside a cloud_dog_db session.
    """

    def __init__(self, *, session_manager: Any) -> None:
        self._session_manager = session_manager

    @staticmethod
    def _store(session: Any) -> SqlAlchemyRoleStore:
        return SqlAlchemyRoleStore(session)

    @staticmethod
    def _payload(role: Role, *, baseline: bool) -> dict[str, Any]:
        return {
            "role_id": role.role_id,
            "name": role.name,
            "description": role.description,
            "permissions": sorted(role.permissions),
            "baseline": baseline,
        }

    def ensure_roles_seed(self) -> None:
        """Idempotently seed the baseline ``admin``/``user`` roles (IW3A.4)."""
        with self._session_manager.session() as session:
            self._store(session).seed_baseline()

    def list_roles(self) -> list[dict[str, Any]]:
        """Return all roles in the PS-71 §IW3A.1 column shape."""
        with self._session_manager.session() as session:
            store = self._store(session)
            store.seed_baseline()
            return store.list_response()

    def get_role(self, role_id: str) -> dict[str, Any]:
        """Return one role by id, in the IW3A.1 column shape."""
        with self._session_manager.session() as session:
            for row in self._store(session).list_response():
                if row["role_id"] == role_id:
                    return row
        raise RoleStateError("role_not_found", f"unknown role: {role_id}", status=404)

    def create_role(
        self,
        *,
        name: str,
        description: str = "",
        permissions: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        """Create one role with a unique name and a normalised permission set."""
        clean_name = str(name or "").strip()
        if not clean_name:
            raise RoleStateError("name_required", "name is required")
        with self._session_manager.session() as session:
            store = self._store(session)
            if store.get_by_name(clean_name) is not None:
                raise RoleStateError(
                    "role_exists", f"role already exists: {clean_name}", status=409
                )
            role = store.save(
                Role(
                    name=clean_name,
                    description=str(description or ""),
                    permissions={
                        str(item).strip()
                        for item in (permissions or [])
                        if str(item).strip()
                    },
                )
            )
            return self._payload(role, baseline=False)

    def update_role(self, role_id: str, *, data: dict[str, Any]) -> dict[str, Any]:
        """Update a role's description and/or permission set."""
        with self._session_manager.session() as session:
            store = self._store(session)
            if store.get(role_id) is None:
                raise RoleStateError(
                    "role_not_found", f"unknown role: {role_id}", status=404
                )
            raw_perms = data.get("permissions")
            perms = (
                {str(item).strip() for item in raw_perms if str(item).strip()}
                if raw_perms is not None
                else None
            )
            description = data.get("description")
            role = store.update(
                role_id,
                description=str(description) if description is not None else None,
                permissions=perms,
            )
            baseline = role.name in {row["name"] for row in store.list_response() if row["baseline"]}
            return self._payload(role, baseline=baseline)

    def delete_role(self, role_id: str) -> bool:
        """Delete one role. Baseline roles are protected (403)."""
        with self._session_manager.session() as session:
            store = self._store(session)
            try:
                return store.delete(role_id)
            except BaselineRoleProtected as exc:
                raise RoleStateError(
                    "baseline_role_protected",
                    f"baseline role cannot be deleted: {exc}",
                    status=403,
                ) from exc


__all__ = ["RoleStateError", "RoleStoreState"]
