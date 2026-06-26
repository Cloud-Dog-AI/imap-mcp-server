"""Profile, archive, index, and RBAC admin routes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder

from imap_hub_core.archive.exporter import ArchiveExporter
from imap_hub_core.audit.logger import AuditWriter
from imap_hub_core.index.manager import IndexManager
from imap_hub_server.admin.endpoint_common import (
    authorise_read,
    emit_admin_audit,
    emit_config_event,
    require_admin_role,
)
from imap_hub_server.admin.state import FileBackedAdminState


def register_profile_routes(
    router: APIRouter,
    *,
    profile_store: dict[str, dict[str, Any]],
    archive_root: str,
    admin_state: FileBackedAdminState,
    audit_writer: AuditWriter | None,
    rbac_store: dict[str, list[str]],
    api_base_path: str,
    legacy_api_base_path: str,
) -> None:
    """Register profile, archive, index, and RBAC policy routes."""

    @router.get(f"{api_base_path}/admin/profiles")
    @router.get(f"{legacy_api_base_path}/admin/profiles", include_in_schema=False)
    async def list_profiles(request: Request) -> dict[str, Any]:
        """List configured profile identifiers."""
        authorise_read(request, admin_state, "profiles:read")
        emit_admin_audit(audit_writer, request, operation="admin.list_profiles", status="success")
        return {
            "ok": True,
            "result": {"profiles": admin_state.list_profiles(profile_store)},
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.get(f"{api_base_path}/admin/profiles/{{profile_id}}")
    @router.get(f"{legacy_api_base_path}/admin/profiles/{{profile_id}}", include_in_schema=False)
    async def get_profile(profile_id: str, request: Request) -> dict[str, Any]:
        """Return a single profile payload by ID."""
        authorise_read(request, admin_state, "profiles:read")
        profile = admin_state.get_profile(profile_id, profile_store)
        if profile is None:
            emit_admin_audit(
                audit_writer,
                request,
                operation="admin.get_profile",
                status="failure",
                profile_id=profile_id,
                params={"error": "profile_not_found"},
            )
            raise HTTPException(status_code=404, detail="profile_not_found")
        emit_admin_audit(
            audit_writer,
            request,
            operation="admin.get_profile",
            status="success",
            profile_id=profile_id,
        )
        return {
            "ok": True,
            "result": profile,
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.post(f"{api_base_path}/admin/profiles")
    @router.post(f"{legacy_api_base_path}/admin/profiles", include_in_schema=False)
    async def create_profile(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        """Create a new profile (POST with profile_id in body)."""
        profile_id = str(payload.pop("profile_id", payload.pop("id", payload.pop("name", ""))))
        if not profile_id:
            raise HTTPException(status_code=400, detail="profile_id (or name) required")
        require_admin_role(request)
        admin_state.upsert_profile(profile_id, payload)
        keys = sorted(payload.keys())
        emit_config_event(
            admin_state,
            request,
            entity_type="profile",
            action="create",
            entity_id=profile_id,
            details={"keys": keys},
        )
        emit_admin_audit(
            audit_writer,
            request,
            operation="admin.create_profile",
            status="success",
            profile_id=profile_id,
            params={"keys": keys},
        )
        return {"ok": True, "result": {"profile_id": profile_id}, "warnings": [], "errors": [], "meta": {}}

    @router.put(f"{api_base_path}/admin/profiles/{{profile_id}}")
    @router.put(f"{legacy_api_base_path}/admin/profiles/{{profile_id}}", include_in_schema=False)
    async def put_profile(
        profile_id: str, payload: dict[str, Any], request: Request
    ) -> dict[str, Any]:
        """Create or replace a profile payload."""
        require_admin_role(request)
        admin_state.upsert_profile(profile_id, payload)
        emit_config_event(
            admin_state,
            request,
            entity_type="profile",
            action="upsert",
            entity_id=profile_id,
            details={"keys": sorted(payload.keys())},
        )
        emit_admin_audit(
            audit_writer,
            request,
            operation="admin.put_profile",
            status="success",
            profile_id=profile_id,
            params={"keys": sorted(payload.keys())},
        )
        return {
            "ok": True,
            "result": {"profile_id": profile_id},
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.delete(f"{api_base_path}/admin/profiles/{{profile_id}}")
    @router.delete(f"{legacy_api_base_path}/admin/profiles/{{profile_id}}", include_in_schema=False)
    async def delete_profile(profile_id: str, request: Request) -> dict[str, Any]:
        """Delete a profile if it exists."""
        require_admin_role(request)
        admin_state.delete_profile(profile_id)
        emit_config_event(
            admin_state,
            request,
            entity_type="profile",
            action="delete",
            entity_id=profile_id,
        )
        emit_admin_audit(
            audit_writer,
            request,
            operation="admin.delete_profile",
            status="success",
            profile_id=profile_id,
        )
        return {
            "ok": True,
            "result": {"profile_id": profile_id},
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.post(f"{api_base_path}/admin/index/reconcile")
    @router.post(f"{legacy_api_base_path}/admin/index/reconcile", include_in_schema=False)
    async def reconcile_index(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        """Reconcile index documents from an admin-supplied payload (FR-12)."""
        require_admin_role(request)
        documents = payload.get("documents")
        if not isinstance(documents, list):
            emit_admin_audit(
                audit_writer,
                request,
                operation="admin.reconcile_index",
                status="failure",
                params={"error": "documents_must_be_list"},
            )
            raise HTTPException(status_code=400, detail="documents_must_be_list")

        manager = IndexManager(enabled=True)
        count = manager.upsert(documents)
        emit_admin_audit(
            audit_writer,
            request,
            operation="admin.reconcile_index",
            status="success",
            params={"count": count},
        )
        return {
            "ok": True,
            "result": {"count": count},
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.post(f"{api_base_path}/admin/archive/export")
    @router.post(f"{legacy_api_base_path}/admin/archive/export", include_in_schema=False)
    async def export_archive(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        """Export a message payload to archive storage."""
        require_admin_role(request)
        try:
            profile_id = str(payload["profile_id"])
            message_id = str(payload["message_id"])
            raw_eml = str(payload["raw_eml"])
        except KeyError as exc:
            emit_admin_audit(
                audit_writer,
                request,
                operation="admin.export_archive",
                status="failure",
                params={"error": f"missing_field:{exc.args[0]}"},
            )
            raise HTTPException(status_code=400, detail=f"missing_field:{exc.args[0]}") from exc

        received_at_raw = str(payload.get("received_at", "")).strip()
        if not received_at_raw:
            received_at = datetime.now(timezone.utc)
        else:
            try:
                received_at = datetime.fromisoformat(received_at_raw.replace("Z", "+00:00"))
            except ValueError as exc:
                emit_admin_audit(
                    audit_writer,
                    request,
                    operation="admin.export_archive",
                    status="failure",
                    profile_id=profile_id,
                    params={"error": "invalid_received_at"},
                )
                raise HTTPException(status_code=400, detail="invalid_received_at") from exc

        metadata_obj = payload.get("metadata", {})
        if not isinstance(metadata_obj, dict):
            emit_admin_audit(
                audit_writer,
                request,
                operation="admin.export_archive",
                status="failure",
                profile_id=profile_id,
                params={"error": "metadata_must_be_object"},
            )
            raise HTTPException(status_code=400, detail="metadata_must_be_object")

        payload_archive_root = payload.get("archive_root")
        effective_archive_root = (
            payload_archive_root.strip()
            if isinstance(payload_archive_root, str) and payload_archive_root.strip()
            else archive_root
        )
        exporter = ArchiveExporter(archive_root=effective_archive_root)
        path = exporter.export_message(
            profile_id=profile_id,
            received_at=received_at,
            message_id=message_id,
            raw_eml=raw_eml.encode("utf-8"),
            metadata_json=json.dumps(metadata_obj, sort_keys=True),
            force=bool(payload.get("force", False)),
        )
        emit_admin_audit(
            audit_writer,
            request,
            operation="admin.export_archive",
            status="success",
            profile_id=profile_id,
            params={"message_id": message_id, "path": str(path)},
        )
        return {
            "ok": True,
            "result": {"path": str(path)},
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.get(f"{api_base_path}/admin/rbac/policies")
    @router.get(f"{legacy_api_base_path}/admin/rbac/policies", include_in_schema=False)
    async def list_rbac_policies(request: Request) -> dict[str, Any]:
        """List current in-memory RBAC policy mappings."""
        authorise_read(request, admin_state, "rbac:read")
        emit_admin_audit(audit_writer, request, operation="admin.list_rbac", status="success")
        return {
            "ok": True,
            "result": {"roles": jsonable_encoder(rbac_store)},
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.put(f"{api_base_path}/admin/rbac/policies")
    @router.put(f"{legacy_api_base_path}/admin/rbac/policies", include_in_schema=False)
    async def put_rbac_policies(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        """Replace RBAC policies with validated role permissions."""
        require_admin_role(request)
        roles = payload.get("roles")
        if not isinstance(roles, dict):
            emit_admin_audit(
                audit_writer, request, operation="admin.put_rbac", status="failure", params=payload
            )
            raise HTTPException(status_code=400, detail="roles_must_be_object")
        normalised: dict[str, list[str]] = {}
        for role_name, values in roles.items():
            if not isinstance(values, list):
                raise HTTPException(status_code=400, detail=f"invalid_role_permissions:{role_name}")
            normalised[str(role_name)] = [str(item) for item in values]
        rbac_store.clear()
        rbac_store.update(normalised)
        emit_admin_audit(
            audit_writer, request, operation="admin.put_rbac", status="success", params=payload
        )
        return {
            "ok": True,
            "result": {"roles": rbac_store},
            "warnings": [],
            "errors": [],
            "meta": {},
        }


__all__ = ["register_profile_routes"]
