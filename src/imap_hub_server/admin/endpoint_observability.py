"""Audit, log, and settings admin routes."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder

from imap_hub_core.audit.logger import AuditWriter
from imap_hub_core.storage_paths import read_storage_bytes, storage_for_file_path
from imap_hub_server.admin.endpoint_common import (
    emit_admin_audit,
    emit_config_event,
    normalise_log_entry,
    require_admin_role,
)
from imap_hub_server.admin.state import FileBackedAdminState


def register_observability_routes(
    router: APIRouter,
    *,
    admin_state: FileBackedAdminState,
    audit_writer: AuditWriter | None,
    audit_path: str | None,
    resolved_log_paths: dict[str, str],
    api_base_path: str,
    legacy_api_base_path: str,
) -> None:
    """Register audit, log, and WebUI settings routes."""

    @router.get(f"{api_base_path}/admin/audit/events")
    @router.get(f"{legacy_api_base_path}/admin/audit/events", include_in_schema=False)
    async def list_audit_events(
        request: Request,
        limit: int = Query(default=100, ge=1, le=500),
        contains: str = Query(default=""),
    ) -> dict[str, Any]:
        """Return recent audit events, optionally filtered by substring match."""
        require_admin_role(request)
        events: list[dict[str, Any]] = []
        if audit_path:
            storage, key = storage_for_file_path(audit_path)
            if storage.exists(key):
                lowered = contains.strip().lower()
                for line in reversed(read_storage_bytes(storage, key).decode("utf-8").splitlines()):
                    if lowered and lowered not in line.lower():
                        continue
                    try:
                        parsed = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(parsed, dict):
                        events.append(parsed)
                    if len(events) >= limit:
                        break
                events.reverse()
        emit_admin_audit(
            audit_writer,
            request,
            operation="admin.list_audit_events",
            status="success",
            params=jsonable_encoder({"limit": limit, "contains": contains}),
        )
        return {
            "ok": True,
            "result": {"items": events},
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.get(f"{api_base_path}/admin/logs")
    @router.get(f"{legacy_api_base_path}/admin/logs", include_in_schema=False)
    async def list_logs(
        request: Request,
        log_type: str = Query(default="audit"),
        lines: int = Query(default=200, ge=1, le=500),
        contains: str = Query(default=""),
    ) -> dict[str, Any]:
        """Return recent normalized log rows for one selected server log."""
        require_admin_role(request)
        selected_type = log_type.strip().lower() or "audit"
        log_path = resolved_log_paths.get(selected_type, resolved_log_paths["audit"])
        events: list[dict[str, Any]] = []
        storage, key = storage_for_file_path(log_path)
        if storage.exists(key):
            lowered = contains.strip().lower()
            for line in reversed(read_storage_bytes(storage, key).decode("utf-8").splitlines()):
                if lowered and lowered not in line.lower():
                    continue
                parsed = normalise_log_entry(selected_type, line)
                if parsed is None:
                    continue
                events.append(parsed)
                if len(events) >= lines:
                    break
            events.reverse()
        emit_admin_audit(
            audit_writer,
            request,
            operation="admin.list_logs",
            status="success",
            params=jsonable_encoder({"log_type": selected_type, "lines": lines, "contains": contains}),
        )
        return {
            "ok": True,
            "result": {"items": events},
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.get(f"{api_base_path}/admin/settings")
    @router.get(f"{legacy_api_base_path}/admin/settings", include_in_schema=False)
    async def get_settings(request: Request) -> dict[str, Any]:
        """Return persisted non-critical WebUI service settings."""
        require_admin_role(request)
        settings = admin_state.get_settings()
        emit_admin_audit(
            audit_writer,
            request,
            operation="admin.get_settings",
            status="success",
            params=settings,
        )
        return {
            "ok": True,
            "result": settings,
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @router.put(f"{api_base_path}/admin/settings")
    @router.put(f"{legacy_api_base_path}/admin/settings", include_in_schema=False)
    async def update_settings(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        """Persist non-critical WebUI service settings."""
        require_admin_role(request)
        try:
            settings = admin_state.update_settings(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        emit_config_event(
            admin_state,
            request,
            entity_type="settings",
            action="update",
            entity_id="service_settings",
            details=settings,
        )
        emit_admin_audit(
            audit_writer,
            request,
            operation="admin.update_settings",
            status="success",
            params=settings,
        )
        return {
            "ok": True,
            "result": settings,
            "warnings": [],
            "errors": [],
            "meta": {},
        }


__all__ = ["register_observability_routes"]
