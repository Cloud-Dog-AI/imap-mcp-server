"""Shared helpers for admin endpoint route groups."""

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

from cloud_dog_idam import RBACEngine
from cloud_dog_logging import get_logger
from cloud_dog_logging.correlation import get_correlation_id
from fastapi import HTTPException, Request

from imap_hub_core.audit.events import AuditActor, AuditRecord
from imap_hub_core.audit.logger import AuditWriter
from imap_hub_server.admin.state import FileBackedAdminState
from imap_hub_server.auth.middleware import request_api_key_record


ADMIN_LOG = get_logger("imap_hub_server.admin.endpoints")

_LOG_TYPE_LABELS = {
    "api": "API",
    "web": "WebUI",
    "mcp": "MCP",
    "a2a": "A2A",
    "audit": "Audit",
}


def request_roles(request: Request) -> set[str]:
    """Resolve caller roles from auth context or request headers."""
    state_roles = getattr(request.state, "roles", None)
    if isinstance(state_roles, set) and state_roles:
        return {str(item).strip().lower() for item in state_roles if str(item).strip()}
    header_roles: set[str] = set()
    role_headers = [request.headers.get("x-user-roles", ""), request.headers.get("x-role", "")]
    for header in role_headers:
        for value in header.split(","):
            role = value.strip().lower()
            if role:
                header_roles.add(role)
    if header_roles:
        return header_roles

    roles: set[str] = set()
    auth_context = getattr(request.state, "auth_context", None)
    if isinstance(auth_context, dict):
        values = auth_context.get("roles", [])
        if isinstance(values, list):
            roles.update(str(item).strip().lower() for item in values if str(item).strip())
    return roles


def require_admin_role(request: Request) -> set[str]:
    """Enforce admin-only access with explicit machine-readable error details."""
    roles = request_roles(request)
    if "admin" not in roles:
        log_admin_event(request, operation="admin.access", status="denied")
        emit_admin_audit(
            getattr(request.app.state, "audit_writer", None),
            request,
            operation="admin.access",
            status="denied",
            params={"error": "admin_required"},
        )
        raise HTTPException(
            status_code=403,
            detail={"code": "admin_required", "message": "Admin role is required for this action."},
        )
    return roles


def actor_id(request: Request) -> str:
    """Resolve an audit-friendly actor identifier from request context."""
    candidate = (
        request.headers.get("x-actor-id", "").strip()
        or request.headers.get("x-user-id", "").strip()
        or str(getattr(request.state, "user_id", "")).strip()
    )
    return candidate or "system"


def request_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    client = getattr(request, "client", None)
    host = getattr(client, "host", "") if client is not None else ""
    return host or "unknown"


def server_id(request: Request) -> str:
    return str(getattr(request.app.state, "server_id", "")).strip() or "imap-mcp-local"


def environment(request: Request) -> str:
    return str(getattr(request.app.state, "environment", "")).strip() or "unknown"


def _as_record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _log_source_label(log_type: str) -> str:
    return _LOG_TYPE_LABELS.get(log_type.strip().lower(), log_type.strip().upper() or "LOG")


def _infer_outcome(parsed: dict[str, Any], extra: dict[str, Any], severity: str) -> str:
    explicit = str(parsed.get("outcome") or extra.get("outcome") or "").strip().lower()
    if explicit:
        return explicit
    status_code = extra.get("status_code")
    if isinstance(status_code, int):
        if 200 <= status_code < 400:
            return "success"
        if status_code in {401, 403}:
            return "denied"
        return "error"
    if severity in {"ERROR", "CRITICAL"}:
        return "error"
    if severity == "WARNING":
        return "partial"
    return "success"


def _normalise_actor(parsed: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    actor = _as_record(parsed.get("actor"))
    actor_id_value = str(
        actor.get("id")
        or actor.get("actor_id")
        or extra.get("actor_id")
        or extra.get("user")
        or "system"
    ).strip() or "system"
    actor_type = str(actor.get("type") or "").strip().lower()
    if not actor_type:
        actor_type = "user" if actor_id_value not in {"system", "anonymous"} else "system"
    return {
        "type": actor_type,
        "id": actor_id_value,
        "roles": _as_string_list(actor.get("roles") or extra.get("roles")),
        "ip": str(actor.get("ip") or extra.get("source_ip") or extra.get("client_ip") or "").strip(),
        "user_agent": str(actor.get("user_agent") or extra.get("user_agent") or "").strip(),
    }


def _normalise_target(log_type: str, parsed: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    target = _as_record(parsed.get("target"))
    method = str(extra.get("method") or "").strip().upper()
    path = str(extra.get("path") or "").strip()
    target_type = str(target.get("type") or extra.get("target_type") or "").strip()
    if not target_type:
        target_type = "route" if path else "log"
    target_id = str(target.get("id") or extra.get("target_id") or path or log_type).strip()
    target_name = str(target.get("name") or extra.get("target_name") or "").strip()
    if not target_name and method and path:
        target_name = f"{method} {path}"
    return {
        "type": target_type,
        "id": target_id,
        "name": target_name,
    }


def normalise_log_entry(log_type: str, line: str) -> dict[str, Any] | None:
    """Return one admin-log row in the WebUI event schema."""
    stripped = line.strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        parsed = {"message": stripped}
    if not isinstance(parsed, dict):
        parsed = {"message": stripped, "value": parsed}
    extra = _as_record(parsed.get("extra"))
    severity = str(parsed.get("severity") or parsed.get("level") or "INFO").strip().upper() or "INFO"
    message = str(parsed.get("message") or "").strip() or stripped
    logger = str(parsed.get("logger") or "").strip()
    event_type = str(parsed.get("event_type") or extra.get("event") or logger or message).strip()
    action = str(parsed.get("action") or extra.get("event") or message).strip()
    correlation_id = str(parsed.get("correlation_id") or extra.get("correlation_id") or "").strip()
    trace_id = str(parsed.get("trace_id") or correlation_id).strip()
    request_id = str(parsed.get("request_id") or extra.get("request_id") or trace_id).strip()
    details = _as_record(parsed.get("details")) or extra
    return {
        "source": _log_source_label(log_type),
        "timestamp": str(parsed.get("timestamp") or "").strip(),
        "event_type": event_type,
        "action": action,
        "outcome": _infer_outcome(parsed, extra, severity),
        "severity": severity,
        "trace_id": trace_id,
        "request_id": request_id,
        "correlation_id": correlation_id,
        "service": str(parsed.get("service") or "imap-mcp-server").strip(),
        "service_instance": str(parsed.get("service_instance") or "").strip(),
        "actor": _normalise_actor(parsed, extra),
        "target": _normalise_target(log_type, parsed, extra),
        "message": message,
        "logger": logger,
        "details": details,
        "raw": parsed,
    }


def source_identifier(request: Request) -> str:
    api_key = str(getattr(request.state, "api_key", "")).strip()
    if api_key:
        return f"api_key:{api_key}"
    current_actor = actor_id(request)
    if current_actor and current_actor != "system":
        return f"user:{current_actor}"
    return request_ip(request)


def request_correlation_id(request: Request) -> str:
    """Return a non-empty request correlation identifier."""
    header = (
        request.headers.get("x-request-id", "").strip()
        or request.headers.get("x-correlation-id", "").strip()
    )
    if header:
        request.state.correlation_id = header
        return header
    raw = getattr(request.state, "correlation_id", None)
    candidate = str(raw).strip() if raw is not None else ""
    if candidate and candidate.lower() != "none":
        return candidate
    generated = get_correlation_id()
    request.state.correlation_id = generated
    return generated


def authorise_read(
    request: Request, admin_state: FileBackedAdminState, capability: str
) -> set[str]:
    """Allow admin users or scoped API keys to perform read-only admin operations."""
    roles = request_roles(request)
    if "admin" in roles:
        return roles
    api_key_id = str(getattr(request.state, "api_key", "")).strip() or None
    if admin_state.key_has_scope(api_key_id, capability):
        return roles
    log_admin_event(
        request,
        operation="admin.read_access",
        status="denied",
        params={"capability": capability},
    )
    emit_admin_audit(
        getattr(request.app.state, "audit_writer", None),
        request,
        operation="admin.read_access",
        status="denied",
        params={"capability": capability},
    )
    raise HTTPException(
        status_code=403,
        detail={
            "code": "insufficient_scope",
            "message": f"Capability {capability!r} is required for this action.",
        },
    )


def request_user_id(request: Request) -> str:
    """Resolve the authenticated user identifier for scoped admin checks."""
    return (
        str(getattr(request.state, "user_id", "")).strip()
        or request.headers.get("x-user-id", "").strip()
        or actor_id(request)
    )


def deny_admin_access(
    request: Request,
    *,
    code: str,
    message: str,
    params: dict[str, Any] | None = None,
) -> None:
    """Emit a denied admin audit event and raise a machine-readable 403."""
    log_admin_event(request, operation="admin.access", status="denied", params=params)
    emit_admin_audit(
        getattr(request.app.state, "audit_writer", None),
        request,
        operation="admin.access",
        status="denied",
        params=params or {"error": code},
    )
    raise HTTPException(status_code=403, detail={"code": code, "message": message})


def require_group_admin_create_scope(
    request: Request,
    admin_state: FileBackedAdminState,
    payload: dict[str, Any],
) -> str | None:
    """Allow system admins or delegated group admins to create scoped users."""
    roles = request_roles(request)
    group_id = str(payload.get("group_id") or "").strip() or None
    if "admin" in roles:
        return group_id

    actor_user_id = request_user_id(request)
    delegated_groups = (
        admin_state.group_admin_groups_for_user(actor_user_id) if actor_user_id else []
    )
    if not group_id:
        if not delegated_groups:
            deny_admin_access(
                request,
                code="admin_required",
                message="Admin role is required for this action.",
                params={"error": "admin_required"},
            )
        deny_admin_access(
            request,
            code="group_scope_required",
            message="Group admins must supply group_id when creating a user.",
            params={"error": "group_scope_required"},
        )
    if not actor_user_id or not admin_state.is_group_admin(actor_user_id, group_id):
        deny_admin_access(
            request,
            code="group_admin_required",
            message="Delegated group-admin rights are required for this group.",
            params={"error": "group_admin_required", "group_id": group_id},
        )

    requested_role = str(payload.get("role") or "viewer").strip().lower() or "viewer"
    escalation_check = RBACEngine(
        role_overlay={requested_role: {"*"} if requested_role in ("admin",) else set()}
    )
    if escalation_check.has_permission(requested_role, "*") or bool(payload.get("is_system_user", False)):
        deny_admin_access(
            request,
            code="group_admin_scope_violation",
            message="Group admins cannot create system-level administrators.",
            params={"error": "group_admin_scope_violation", "group_id": group_id},
        )
    return group_id


def target_details(
    request: Request,
    operation: str,
    profile_id: str | None,
    params: dict[str, Any] | None,
) -> tuple[str, str, str]:
    values = params or {}
    if profile_id:
        return ("profile", profile_id, profile_id)
    for key, target_type in (
        ("user_id", "user"),
        ("group_id", "group"),
        ("api_key_id", "api_key"),
        ("role", "rbac"),
    ):
        value = str(values.get(key, "")).strip()
        if value:
            return (target_type, value, value)
    return ("route", request.url.path, f"{request.method} {request.url.path}")


def log_admin_event(
    request: Request,
    *,
    operation: str,
    status: str,
    profile_id: str | None = None,
    params: dict[str, Any] | None = None,
) -> None:
    target_type, target_id, target_name = target_details(request, operation, profile_id, params)
    ADMIN_LOG.info(
        "admin_event",
        event=operation,
        component="imap_hub_server.admin.endpoints",
        correlation_id=request_correlation_id(request),
        source_ip=request_ip(request),
        source_identifier=source_identifier(request),
        outcome=status,
        actor_id=actor_id(request),
        target_type=target_type,
        target_id=target_id,
        target_name=target_name,
        server_id=server_id(request),
    )


def emit_config_event(
    admin_state: FileBackedAdminState,
    request: Request,
    *,
    entity_type: str,
    action: str,
    entity_id: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Append a config-change event for A2A subscribers."""
    admin_state.emit_event(
        entity_type=entity_type,
        action=action,
        entity_id=entity_id,
        actor_id=actor_id(request),
        source="api",
        details=details or {},
    )


def emit_admin_audit(
    audit_writer: AuditWriter | None,
    request: Request,
    operation: str,
    status: str,
    profile_id: str | None = None,
    params: dict[str, Any] | None = None,
) -> None:
    """Write an audit record for every admin action."""
    if audit_writer is None:
        return
    correlation_id = request_correlation_id(request)
    actor_id_value = (
        request.headers.get("x-actor-id", "").strip()
        or request.headers.get("x-user-id", "").strip()
        or str(getattr(request.state, "user_id", "")).strip()
    )
    if not actor_id_value:
        auth_runtime = getattr(request.app.state, "auth_runtime", None)
        api_key_manager = getattr(auth_runtime, "api_key_manager", None)
        if api_key_manager is not None:
            api_record = request_api_key_record(request, api_key_manager)
            if api_record is not None:
                actor_id_value = (
                    str(api_record.owner_user_id or api_record.api_key_id).strip() or "system"
                )
    if not actor_id_value:
        actor_id_value = "system"
    target_type, target_id, target_name = target_details(request, operation, profile_id, params)
    log_admin_event(
        request,
        operation=operation,
        status=status,
        profile_id=profile_id,
        params=params,
    )
    audit_writer.emit(
        AuditRecord(
            operation=operation,
            status=status,
            correlation_id=correlation_id,
            actor=AuditActor(
                actor_id=actor_id_value,
                roles=sorted(request_roles(request)),
                ip=request_ip(request),
                user_agent=request.headers.get("user-agent", "").strip() or None,
            ),
            profile_id=profile_id,
            component="imap_hub_server.admin.endpoints",
            source_identifier=source_identifier(request),
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            server_id=server_id(request),
            environment=environment(request),
            params=params or {},
        )
    )


__all__ = [
    "authorise_read",
    "emit_admin_audit",
    "emit_config_event",
    "normalise_log_entry",
    "require_admin_role",
    "require_group_admin_create_scope",
]
