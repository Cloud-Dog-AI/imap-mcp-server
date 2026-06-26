"""Canonical PS-71 §IW3A roles admin routes (cloud_dog_idam SqlAlchemyRoleStore)."""

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

from fastapi import APIRouter, HTTPException, Request

from imap_hub_core.audit.logger import AuditWriter
from imap_hub_server.admin.endpoint_common import (
    authorise_read,
    emit_admin_audit,
    require_admin_role,
)
from imap_hub_server.admin.state import FileBackedAdminState
from imap_hub_server.admin.state_roles import RoleStateError, RoleStoreState


def _http_error(exc: RoleStateError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code, "message": str(exc)})


def register_roles_routes(
    router: APIRouter,
    *,
    admin_state: FileBackedAdminState,
    role_state: RoleStoreState,
    audit_writer: AuditWriter | None,
    api_base_path: str,
    legacy_api_base_path: str,
) -> None:
    """Register canonical PS-71 §IW3A role routes backed by SqlAlchemyRoleStore."""

    @router.get(f"{api_base_path}/admin/roles")
    @router.get(f"{legacy_api_base_path}/admin/roles", include_in_schema=False)
    async def list_roles(request: Request) -> dict[str, Any]:
        """List roles in the IW3A.1 column shape (seeds baseline admin/user)."""
        authorise_read(request, admin_state, "roles:read")
        return {
            "ok": True,
            "result": {"items": role_state.list_roles()},
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.get(f"{api_base_path}/admin/roles/{{role_id}}")
    @router.get(f"{legacy_api_base_path}/admin/roles/{{role_id}}", include_in_schema=False)
    async def get_role(role_id: str, request: Request) -> dict[str, Any]:
        """Return one role by id."""
        authorise_read(request, admin_state, "roles:read")
        try:
            record = role_state.get_role(role_id)
        except RoleStateError as exc:
            raise _http_error(exc) from exc
        return {
            "ok": True,
            "result": record,
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.post(f"{api_base_path}/admin/roles")
    @router.post(f"{legacy_api_base_path}/admin/roles", include_in_schema=False)
    async def create_role(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        """Create one role with a unique name and permission set."""
        require_admin_role(request)
        try:
            record = role_state.create_role(
                name=str(payload.get("name") or ""),
                description=str(payload.get("description") or ""),
                permissions=payload.get("permissions") or [],
            )
        except RoleStateError as exc:
            raise _http_error(exc) from exc
        emit_admin_audit(
            audit_writer,
            request,
            operation="admin.create_role",
            status="success",
            params={"role_id": record["role_id"], "name": record["name"]},
        )
        return {
            "ok": True,
            "result": record,
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    async def _update_role(role_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
        require_admin_role(request)
        try:
            record = role_state.update_role(role_id, data=payload)
        except RoleStateError as exc:
            raise _http_error(exc) from exc
        emit_admin_audit(
            audit_writer,
            request,
            operation="admin.update_role",
            status="success",
            params={"role_id": record["role_id"], "name": record["name"]},
        )
        return {
            "ok": True,
            "result": record,
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.put(f"{api_base_path}/admin/roles/{{role_id}}")
    @router.put(f"{legacy_api_base_path}/admin/roles/{{role_id}}", include_in_schema=False)
    async def put_role(role_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
        """Replace a role's description and/or permission set."""
        return await _update_role(role_id, payload, request)

    @router.patch(f"{api_base_path}/admin/roles/{{role_id}}")
    @router.patch(f"{legacy_api_base_path}/admin/roles/{{role_id}}", include_in_schema=False)
    async def patch_role(role_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
        """Partially update a role's description and/or permission set."""
        return await _update_role(role_id, payload, request)

    @router.delete(f"{api_base_path}/admin/roles/{{role_id}}")
    @router.delete(f"{legacy_api_base_path}/admin/roles/{{role_id}}", include_in_schema=False)
    async def delete_role(role_id: str, request: Request) -> dict[str, Any]:
        """Delete one role. Baseline admin/user roles are undeletable (403)."""
        require_admin_role(request)
        try:
            removed = role_state.delete_role(role_id)
        except RoleStateError as exc:
            raise _http_error(exc) from exc
        if not removed:
            raise HTTPException(status_code=404, detail="role_not_found")
        emit_admin_audit(
            audit_writer,
            request,
            operation="admin.delete_role",
            status="success",
            params={"role_id": role_id},
        )
        return {
            "ok": True,
            "result": {"role_id": role_id},
            "warnings": [],
            "errors": [],
            "meta": {},
        }


__all__ = ["register_roles_routes"]
