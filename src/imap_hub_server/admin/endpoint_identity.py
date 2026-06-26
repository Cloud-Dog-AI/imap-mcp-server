"""User, group, and API-key admin routes."""

from __future__ import annotations

from typing import Any

from cloud_dog_idam import APIKeyManager, RBACEngine
from fastapi import APIRouter, HTTPException, Request

from imap_hub_core.audit.logger import AuditWriter
from imap_hub_server.admin.endpoint_common import (
    authorise_read,
    emit_admin_audit,
    emit_config_event,
    require_admin_role,
    require_group_admin_create_scope,
)
from imap_hub_server.admin.state import FileBackedAdminState


def register_identity_routes(
    router: APIRouter,
    *,
    admin_state: FileBackedAdminState,
    api_key_manager: APIKeyManager,
    rbac_engine: RBACEngine,
    audit_writer: AuditWriter | None,
    api_base_path: str,
    legacy_api_base_path: str,
) -> None:
    """Register user, group, and managed API-key routes."""

    @router.post(f"{api_base_path}/admin/users")
    @router.post(f"{legacy_api_base_path}/admin/users", include_in_schema=False)
    async def create_user(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        """Create one user via the admin API."""
        group_id = require_group_admin_create_scope(request, admin_state, payload)
        try:
            record = admin_state.create_user(payload)
            if group_id:
                admin_state.add_group_member(group_id, record.user_id)
            admin_state.sync_rbac_engine(rbac_engine)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        emit_config_event(
            admin_state,
            request,
            entity_type="user",
            action="create",
            entity_id=record.user_id,
            details={"username": record.username},
        )
        emit_admin_audit(
            audit_writer,
            request,
            operation="admin.create_user",
            status="success",
            params={"user_id": record.user_id, "username": record.username, "group_id": group_id},
        )
        return {
            "ok": True,
            "result": admin_state.export_user(record),
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.get(f"{api_base_path}/admin/users")
    @router.get(f"{legacy_api_base_path}/admin/users", include_in_schema=False)
    async def list_users(request: Request) -> dict[str, Any]:
        """List configured users."""
        authorise_read(request, admin_state, "users:read")
        return {
            "ok": True,
            "result": {"items": [admin_state.export_user(item) for item in admin_state.list_users()]},
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.get(f"{api_base_path}/admin/users/{{user_id}}")
    @router.get(f"{legacy_api_base_path}/admin/users/{{user_id}}", include_in_schema=False)
    async def get_user(user_id: str, request: Request) -> dict[str, Any]:
        """Return one configured user."""
        authorise_read(request, admin_state, "users:read")
        record = admin_state.get_user(user_id)
        if record is None:
            raise HTTPException(status_code=404, detail="user_not_found")
        return {
            "ok": True,
            "result": admin_state.export_user(record),
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.put(f"{api_base_path}/admin/users/{{user_id}}")
    @router.put(f"{legacy_api_base_path}/admin/users/{{user_id}}", include_in_schema=False)
    async def update_user(user_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
        """Update one configured user."""
        require_admin_role(request)
        try:
            record = admin_state.update_user(user_id, payload)
            admin_state.sync_rbac_engine(rbac_engine)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="user_not_found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        emit_config_event(
            admin_state,
            request,
            entity_type="user",
            action="update",
            entity_id=record.user_id,
            details={"username": record.username},
        )
        emit_admin_audit(
            audit_writer,
            request,
            operation="admin.update_user",
            status="success",
            params={"user_id": record.user_id},
        )
        return {
            "ok": True,
            "result": admin_state.export_user(record),
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.delete(f"{api_base_path}/admin/users/{{user_id}}")
    @router.delete(f"{legacy_api_base_path}/admin/users/{{user_id}}", include_in_schema=False)
    async def delete_user(user_id: str, request: Request) -> dict[str, Any]:
        """Delete one configured user."""
        require_admin_role(request)
        if not admin_state.delete_user(user_id):
            raise HTTPException(status_code=404, detail="user_not_found")
        admin_state.sync_rbac_engine(rbac_engine)
        emit_config_event(
            admin_state,
            request,
            entity_type="user",
            action="delete",
            entity_id=user_id,
        )
        emit_admin_audit(
            audit_writer,
            request,
            operation="admin.delete_user",
            status="success",
            params={"user_id": user_id},
        )
        return {
            "ok": True,
            "result": {"user_id": user_id},
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.post(f"{api_base_path}/admin/groups")
    @router.post(f"{legacy_api_base_path}/admin/groups", include_in_schema=False)
    async def create_group(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        """Create one group with optional role assignments and members."""
        require_admin_role(request)
        try:
            record = admin_state.create_group(payload)
            admin_state.sync_rbac_engine(rbac_engine)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        emit_config_event(
            admin_state,
            request,
            entity_type="group",
            action="create",
            entity_id=record.group_id,
            details={"name": record.name, "roles": record.roles},
        )
        emit_admin_audit(
            audit_writer,
            request,
            operation="admin.create_group",
            status="success",
            params={"group_id": record.group_id, "name": record.name},
        )
        return {
            "ok": True,
            "result": admin_state.export_group(record),
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.get(f"{api_base_path}/admin/groups")
    @router.get(f"{legacy_api_base_path}/admin/groups", include_in_schema=False)
    async def list_groups(request: Request) -> dict[str, Any]:
        """List configured groups."""
        authorise_read(request, admin_state, "groups:read")
        return {
            "ok": True,
            "result": {"items": [admin_state.export_group(item) for item in admin_state.list_groups()]},
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.get(f"{api_base_path}/admin/groups/{{group_id}}")
    @router.get(f"{legacy_api_base_path}/admin/groups/{{group_id}}", include_in_schema=False)
    async def get_group(group_id: str, request: Request) -> dict[str, Any]:
        """Return one configured group with roles and members."""
        authorise_read(request, admin_state, "groups:read")
        record = admin_state.get_group(group_id)
        if record is None:
            raise HTTPException(status_code=404, detail="group_not_found")
        return {
            "ok": True,
            "result": admin_state.export_group(record),
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.put(f"{api_base_path}/admin/groups/{{group_id}}")
    @router.put(f"{legacy_api_base_path}/admin/groups/{{group_id}}", include_in_schema=False)
    async def update_group(group_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
        """Update one configured group."""
        require_admin_role(request)
        try:
            record = admin_state.update_group(group_id, payload)
            admin_state.sync_rbac_engine(rbac_engine)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="group_not_found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        emit_config_event(
            admin_state,
            request,
            entity_type="group",
            action="update",
            entity_id=record.group_id,
            details={"name": record.name, "roles": record.roles},
        )
        emit_admin_audit(
            audit_writer,
            request,
            operation="admin.update_group",
            status="success",
            params={"group_id": record.group_id},
        )
        return {
            "ok": True,
            "result": admin_state.export_group(record),
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.delete(f"{api_base_path}/admin/groups/{{group_id}}")
    @router.delete(f"{legacy_api_base_path}/admin/groups/{{group_id}}", include_in_schema=False)
    async def delete_group(group_id: str, request: Request) -> dict[str, Any]:
        """Delete one configured group."""
        require_admin_role(request)
        if not admin_state.delete_group(group_id):
            raise HTTPException(status_code=404, detail="group_not_found")
        admin_state.sync_rbac_engine(rbac_engine)
        emit_config_event(
            admin_state,
            request,
            entity_type="group",
            action="delete",
            entity_id=group_id,
        )
        emit_admin_audit(
            audit_writer,
            request,
            operation="admin.delete_group",
            status="success",
            params={"group_id": group_id},
        )
        return {
            "ok": True,
            "result": {"group_id": group_id},
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.post(f"{api_base_path}/admin/groups/{{group_id}}/members")
    @router.post(f"{legacy_api_base_path}/admin/groups/{{group_id}}/members", include_in_schema=False)
    async def add_group_member(group_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
        """Add one user to a configured group."""
        require_admin_role(request)
        user_id = str(payload.get("user_id") or "").strip()
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id_required")
        try:
            record = admin_state.add_group_member(group_id, user_id)
            admin_state.sync_rbac_engine(rbac_engine)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        emit_config_event(
            admin_state,
            request,
            entity_type="group",
            action="add_member",
            entity_id=group_id,
            details={"user_id": user_id},
        )
        emit_admin_audit(
            audit_writer,
            request,
            operation="admin.add_group_member",
            status="success",
            params={"group_id": group_id, "user_id": user_id},
        )
        return {
            "ok": True,
            "result": admin_state.export_group(record),
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.delete(f"{api_base_path}/admin/groups/{{group_id}}/members/{{user_id}}")
    @router.delete(
        f"{legacy_api_base_path}/admin/groups/{{group_id}}/members/{{user_id}}",
        include_in_schema=False,
    )
    async def remove_group_member(group_id: str, user_id: str, request: Request) -> dict[str, Any]:
        """Remove one user from a configured group."""
        require_admin_role(request)
        try:
            record = admin_state.remove_group_member(group_id, user_id)
            admin_state.sync_rbac_engine(rbac_engine)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        emit_config_event(
            admin_state,
            request,
            entity_type="group",
            action="remove_member",
            entity_id=group_id,
            details={"user_id": user_id},
        )
        emit_admin_audit(
            audit_writer,
            request,
            operation="admin.remove_group_member",
            status="success",
            params={"group_id": group_id, "user_id": user_id},
        )
        return {
            "ok": True,
            "result": admin_state.export_group(record),
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.post(f"{api_base_path}/admin/api-keys")
    @router.post(f"{legacy_api_base_path}/admin/api-keys", include_in_schema=False)
    async def create_api_key(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        """Create one scoped API key."""
        require_admin_role(request)
        try:
            raw_key, record = admin_state.create_api_key(
                payload=payload, api_key_manager=api_key_manager
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        emit_config_event(
            admin_state,
            request,
            entity_type="api_key",
            action="create",
            entity_id=record.api_key_id,
            details={"owner_user_id": record.owner_user_id, "scopes": record.scopes},
        )
        emit_admin_audit(
            audit_writer,
            request,
            operation="admin.create_api_key",
            status="success",
            params={"api_key_id": record.api_key_id, "owner_user_id": record.owner_user_id},
        )
        result = admin_state.export_api_key(record)
        result["raw_key"] = raw_key
        return {
            "ok": True,
            "result": result,
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.get(f"{api_base_path}/admin/api-keys")
    @router.get(f"{legacy_api_base_path}/admin/api-keys", include_in_schema=False)
    async def list_api_keys(request: Request) -> dict[str, Any]:
        """List managed API keys without exposing raw secret values."""
        authorise_read(request, admin_state, "api_keys:read")
        items = [admin_state.export_api_key(item) for item in admin_state.list_api_keys()]
        emit_admin_audit(
            audit_writer,
            request,
            operation="admin.list_api_keys",
            status="success",
            params={"count": len(items)},
        )
        return {
            "ok": True,
            "result": {"items": items},
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.delete(f"{api_base_path}/admin/api-keys/{{api_key_id}}")
    @router.delete(f"{legacy_api_base_path}/admin/api-keys/{{api_key_id}}", include_in_schema=False)
    # W28A-735-R5: the shared @cloud-dog/idam IdamApiKeysPage revokes via
    # POST .../api-keys/{id}/revoke; expose that alias additively alongside the
    # native DELETE so the WebUI revoke action resolves (was 404).
    @router.post(f"{api_base_path}/admin/api-keys/{{api_key_id}}/revoke", include_in_schema=False)
    @router.post(f"{legacy_api_base_path}/admin/api-keys/{{api_key_id}}/revoke", include_in_schema=False)
    async def revoke_api_key(api_key_id: str, request: Request) -> dict[str, Any]:
        """Revoke one managed API key."""
        require_admin_role(request)
        if not admin_state.revoke_api_key(api_key_id, api_key_manager):
            raise HTTPException(status_code=404, detail="api_key_not_found")
        emit_config_event(
            admin_state,
            request,
            entity_type="api_key",
            action="revoke",
            entity_id=api_key_id,
        )
        emit_admin_audit(
            audit_writer,
            request,
            operation="admin.revoke_api_key",
            status="success",
            params={"api_key_id": api_key_id},
        )
        return {
            "ok": True,
            "result": {"api_key_id": api_key_id},
            "warnings": [],
            "errors": [],
            "meta": {},
        }


__all__ = ["register_identity_routes"]
