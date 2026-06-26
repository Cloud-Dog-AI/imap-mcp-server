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

# Covers: FR-01
# Covers: FR-05
# Covers: CFG-11

import json
from collections.abc import Mapping
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import uvicorn
from cloud_dog_api_kit import create_app as platform_create_app
from cloud_dog_logging.correlation import get_correlation_id
from fastapi import APIRouter, FastAPI, HTTPException, Request

from imap_hub_core.audit.context import (
    AuditRequestContext,
    reset_audit_request_context,
    set_audit_request_context,
)
from imap_hub_core.audit.logger import AuditWriter
from imap_hub_core.config.base_paths import (
    DEFAULT_MCP_BASE_PATH,
    join_base_path,
    resolve_surface_base_path,
)
from imap_hub_core.config.loader import load_global_config
from imap_hub_core.config.access import resolve_env_files, runtime_config_value
from imap_hub_core.jobs import JobEnvelope, build_jobs_runtime
from imap_hub_core.tools.handlers import build_default_tool_registry
from imap_hub_server.rbac_seam import ImapResourceGuard
from imap_hub_server.admin.state import FileBackedAdminState
from imap_hub_server.api_server import _install_browser_cors
from imap_hub_server.auth.middleware import (
    build_auth_runtime,
    install_auth_middleware,
    register_static_api_key,
    request_api_key_record,
)
from imap_hub_server.logging_runtime import init_surface_logging, install_service_context_middleware

MCP_TOOLS_ALIAS_PATH = "/tools"
_ADMIN_TOOL_PREFIXES = ("user_", "group_", "api_key_")
_TOOL_REQUEST_TIMEOUT_SECONDS = 120.0
_ASYNC_SEARCH_FLAGS = ("run_async", "async")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def _async_search_requested(payload: Mapping[str, Any]) -> bool:
    return any(_truthy(payload.get(key)) for key in _ASYNC_SEARCH_FLAGS)


def _without_async_flags(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in payload.items() if str(key) not in _ASYNC_SEARCH_FLAGS}


def _request_roles(request: Request) -> set[str]:
    """Resolve MCP roles from request headers or auth context."""
    state_roles = getattr(request.state, "roles", None)
    if isinstance(state_roles, set) and state_roles:
        return {str(item).strip().lower() for item in state_roles if str(item).strip()}
    roles: set[str] = set()
    for header_name in ("x-user-roles", "x-role"):
        for value in request.headers.get(header_name, "").split(","):
            role = value.strip().lower()
            if role:
                roles.add(role)
    auth_context = getattr(request.state, "auth_context", None)
    if isinstance(auth_context, dict):
        values = auth_context.get("roles", [])
        if isinstance(values, list):
            for item in values:
                role = str(item).strip().lower()
                if role:
                    roles.add(role)
    return roles


def _effective_roles(request: Request, admin_state: FileBackedAdminState, auth_runtime: Any) -> set[str]:
    """Resolve transport roles, DENYING the unauthenticated MCP client (default-DENY).

    W28A-735-R5 / D-IMAP-IDENTITY-COLLAPSE-1 (PS-82 §3.1/§8.3): an unauthenticated
    MCP client MUST resolve to an EMPTY/DENY role set — NEVER ``{admin}``. The
    previous behaviour silently escalated any anonymous MCP caller to admin. The
    fix is fail-closed: return ``set()`` for a caller with no roles header and no
    valid API key. The transport auth gate (``install_auth_middleware`` in
    ``create_mcp_app``) rejects such a caller with 401 before tool execution; this
    function is the second line of defence so an empty role set can never grant
    admin even if a caller reaches role resolution.
    """
    roles = _request_roles(request)
    if roles:
        return roles
    # Sync dynamic API keys from admin_state so that keys created via
    # the admin API are recognized by the MCP server's key manager.
    admin_state.sync_api_key_manager(auth_runtime.api_key_manager)
    api_record = request_api_key_record(request, auth_runtime.api_key_manager)
    if api_record is not None:
        user = admin_state.get_user(api_record.owner_user_id)
        if user is not None and str(getattr(user, "status", "")).strip().lower() == "disabled":
            raise HTTPException(status_code=403, detail="User account is disabled")
        role = str(getattr(user, "role", "")).strip().lower()
        if role:
            return {role}
    # Default-DENY: an unauthenticated caller (no roles, no valid API key) gets an
    # EMPTY role set — never admin. (D-IMAP-IDENTITY-COLLAPSE-1)
    return set()


def _require_admin_tool_access(
    request: Request, auth_runtime: Any, admin_state: FileBackedAdminState
) -> None:
    """Require an admin role and valid API key for admin MCP tools."""
    if request_api_key_record(request, auth_runtime.api_key_manager) is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if "admin" not in _effective_roles(request, admin_state, auth_runtime):
        raise HTTPException(
            status_code=403,
            detail={"code": "admin_required", "message": "Admin role is required for this action."},
        )


def _request_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    client = getattr(request, "client", None)
    host = getattr(client, "host", "") if client is not None else ""
    return host or "unknown"


def _request_correlation_id(request: Request) -> str:
    """Return a non-empty correlation identifier for this request."""
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


def _request_id(request: Request) -> str:
    """Return a non-empty request identifier for this request."""
    raw = getattr(request.state, "request_id", None)
    candidate = str(raw).strip() if raw is not None else ""
    if candidate and candidate.lower() != "none":
        return candidate
    header = request.headers.get("x-request-id", "").strip()
    generated = header or uuid4().hex
    request.state.request_id = generated
    return generated


def _audit_context(request: Request) -> AuditRequestContext:
    admin_state = cast(FileBackedAdminState, request.app.state.admin_state)
    auth_runtime = request.app.state.auth_runtime
    roles = sorted(_effective_roles(request, admin_state, auth_runtime))
    # Resolve actor from API key record, falling back to header then default.
    actor_id = request.headers.get("x-user-id", "").strip()
    source_identifier = actor_id
    admin_state.sync_api_key_manager(auth_runtime.api_key_manager)
    api_record = request_api_key_record(request, auth_runtime.api_key_manager)
    if not actor_id:
        if api_record is not None:
            actor_id = str(api_record.owner_user_id or "").strip()
    if not actor_id:
        actor_id = "mcp-client"
    if api_record is not None:
        source_identifier = f"api_key:{api_record.api_key_id}"
    elif not source_identifier:
        source_identifier = actor_id
    return AuditRequestContext(
        correlation_id=_request_correlation_id(request),
        actor_id=actor_id,
        roles=roles,
        source_identifier=source_identifier,
        source_ip=_request_ip(request),
        user_agent=request.headers.get("user-agent", "").strip() or None,
        component="imap_hub_server.mcp_server",
        server_id=str(getattr(request.app.state, "server_id", "")).strip() or "imap-mcp-local",
        environment=str(getattr(request.app.state, "environment", "")).strip() or "unknown",
    )


def _register_tool_router_compat(
    app: FastAPI,
    tool_routes: dict[str, dict[str, Any]],
    auth_runtime: Any,
    base_path: str,
    root_path: str,
    alias_paths: tuple[str, ...] = (),
) -> None:
    """Register compatibility MCP routes when api-kit helper is unavailable."""
    router = APIRouter()

    def _list_tools_payload() -> dict[str, Any]:
        items = []
        for name, spec in tool_routes.items():
            items.append(
                {
                    "name": name,
                    "description": spec.get("description", ""),
                    "input_schema": spec.get("input_schema", {"type": "object"}),
                    "output_schema": spec.get("output_schema", {"type": "object"}),
                }
            )
        return {
            "ok": True,
            "data": items,
            "meta": {"request_id": "", "correlation_id": None, "version": "v1"},
        }

    @router.get(base_path)
    async def list_tools() -> dict[str, Any]:
        return _list_tools_payload()

    @router.get(root_path, include_in_schema=False)
    async def mcp_descriptor() -> dict[str, Any]:
        return {
            "ok": True,
            "result": {
                "service": "imap-mcp-server",
                "interface": "mcp",
                "tools_path": base_path,
            },
            "warnings": [],
            "errors": [],
            "meta": {"request_id": "", "correlation_id": None},
        }

    @router.post(root_path, include_in_schema=False)
    async def mcp_jsonrpc(request: Request) -> dict[str, Any]:
        """Handle JSON-RPC requests at the MCP root for service discovery."""
        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")
        if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
            raise HTTPException(status_code=400, detail="Invalid JSON-RPC request")
        request_id = payload.get("id")
        method = payload.get("method")
        if method == "tools/list":
            tools = [
                {
                    "name": name,
                    "description": spec.get("description", ""),
                    "inputSchema": spec.get("input_schema", {"type": "object"}),
                }
                for name, spec in tool_routes.items()
            ]
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": tools}}
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "imap-mcp-server", "version": "0.1.0"},
                },
            }
        if method == "tools/call":
            params = payload.get("params", {})
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            if not tool_name:
                return {"jsonrpc": "2.0", "id": request_id,
                        "error": {"code": -32600, "message": "Missing tool name in params.name"}}
            try:
                result = await _call_tool(tool_name, tool_args or {}, request)
                tool_result = result.get("result", result)
                return {"jsonrpc": "2.0", "id": request_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(tool_result, default=str)}]}}
            except HTTPException as exc:
                return {"jsonrpc": "2.0", "id": request_id,
                        "error": {"code": -32602 if exc.status_code == 404 else -32603,
                                  "message": str(exc.detail)}}
            except Exception as exc:
                return {"jsonrpc": "2.0", "id": request_id,
                        "error": {"code": -32603, "message": str(exc)}}
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    for alias_path in alias_paths:

        @router.get(alias_path, include_in_schema=False)
        async def list_tools_alias(_alias_path: str = alias_path) -> dict[str, Any]:
            return _list_tools_payload()

    async def _call_tool(
        tool_name: str, payload: dict[str, Any], request: Request
    ) -> dict[str, Any]:
        if tool_name not in tool_routes:
            raise HTTPException(status_code=404, detail="tool_not_found")
        # Reject disabled users early, before any tool execution.
        api_record = request_api_key_record(request, auth_runtime.api_key_manager)
        if api_record is not None:
            _admin_state = cast(FileBackedAdminState, request.app.state.admin_state)
            user = _admin_state.get_user(api_record.owner_user_id)
            if user is not None and str(getattr(user, "status", "")).strip().lower() == "disabled":
                raise HTTPException(status_code=403, detail="User account is disabled")
        if tool_name.startswith(_ADMIN_TOOL_PREFIXES):
            _require_admin_tool_access(request, auth_runtime, cast(FileBackedAdminState, request.app.state.admin_state))
        if tool_name == "mail_search" and _async_search_requested(payload):
            jobs_runtime = request.app.state.jobs_runtime
            registry = request.app.state.tool_registry
            job_payload = _without_async_flags(payload)
            request_context = _audit_context(request)

            def _run_search(envelope: JobEnvelope) -> dict[str, Any]:
                token = set_audit_request_context(request_context)
                try:
                    return registry.call("mail_search", envelope.payload)
                finally:
                    reset_audit_request_context(token)

            jobs_runtime.register_handler("mail_search", _run_search)
            job_id = jobs_runtime.submit(
                JobEnvelope(
                    job_type="mail_search",
                    profile_id=str(job_payload.get("profile_id") or ""),
                    queue_name="mcp",
                    payload=job_payload,
                    correlation_id=request_context.correlation_id,
                )
            )
            jobs_runtime.run_once()
            record = jobs_runtime.get_job_record(job_id) or {}
            return {
                "ok": True,
                "result": {
                    "job_id": job_id,
                    "status": str(record.get("status") or "queued"),
                    "job": record,
                    "result": jobs_runtime.last_result(job_id) or {},
                },
                "warnings": [],
                "errors": [],
                "meta": {
                    "request_id": _request_id(request),
                    "correlation_id": request_context.correlation_id,
                },
            }
        handler = tool_routes[tool_name]["handler"]
        try:
            result = handler(payload, request)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return {
            "ok": True,
            "result": result,
            "warnings": [],
            "errors": [],
            "meta": {
                "request_id": _request_id(request),
                "correlation_id": _request_correlation_id(request),
            },
        }

    @router.post(f"{base_path}" + "/{tool_name}")
    async def call_tool(
        tool_name: str, payload: dict[str, Any], request: Request
    ) -> dict[str, Any]:
        return await _call_tool(tool_name, payload, request)

    for alias_path in alias_paths:

        @router.post(f"{alias_path}" + "/{tool_name}", include_in_schema=False)
        async def call_tool_alias(
            tool_name: str,
            payload: dict[str, Any],
            request: Request,
            _alias_path: str = alias_path,
        ) -> dict[str, Any]:
            return await _call_tool(tool_name, payload, request)

    app.include_router(router)


def _json_safe(value: Any) -> Any:
    """
    Purpose: Implement `_json_safe` behaviour for this module.
    Inputs: Parameters are defined by the function/class signature.
    Outputs: Returns values according to the module contract.
    Dependencies: Uses internal project modules and configured services.
    Related tests: See TESTS.md and tests/ for coverage mapping.
    """
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, set, frozenset)):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def create_mcp_app(env_files: list[str] | None = None) -> FastAPI:
    """Create MCP app and register tool contracts."""
    resolved_env_files = resolve_env_files(env_files)
    config = load_global_config(env_files=resolved_env_files)
    mcp_base_path = resolve_surface_base_path(
        config,
        surface_name="mcp_server",
        default=DEFAULT_MCP_BASE_PATH,
        env_files=resolved_env_files,
    )
    mcp_tools_path = join_base_path(mcp_base_path, "/tools")
    log_paths = init_surface_logging(resolved_env_files, surface_name="mcp_server")
    environment = log_paths["environment"]
    auth_runtime = build_auth_runtime()

    profile_store: dict[str, dict[str, Any]] = {}
    for profile_id, profile in config.profiles.items():
        profile_store[profile_id] = _json_safe(profile.model_dump(mode="python"))

    audit_writer = AuditWriter(
        audit_path=config.server.audit.log_path,
        server_id=config.server.server_id,
        environment=environment,
        app_log_path=log_paths["app_log_path"],
        platform_audit_path=log_paths["audit_log_path"],
        integrity_log_path=log_paths["integrity_log_path"],
    )
    admin_state = FileBackedAdminState(config.server.storage.data_dir)
    admin_state.bootstrap_admin_user("integration-user")
    configured_api_key = runtime_config_value(
        config, "IMAP_API_KEY", "CLOUD_DOG__IMAP__API_KEY", "API_KEY"
    )
    if configured_api_key:
        register_static_api_key(
            auth_runtime.api_key_manager, configured_api_key, owner_id="integration-user"
        )
        seed_api_key = configured_api_key
    else:
        seed_api_key, _ = auth_runtime.api_key_manager.generate("integration-user")
    admin_state.sync_api_key_manager(auth_runtime.api_key_manager)
    registry = build_default_tool_registry(
        profiles=profile_store,
        downloads_dir=config.server.storage.downloads_dir,
        audit_writer=audit_writer,
        admin_state=admin_state,
        api_key_manager=auth_runtime.api_key_manager,
        rbac_engine=auth_runtime.rbac_engine,
        resource_guard=ImapResourceGuard(auth_runtime.rbac_engine, admin_state),
        rbac_roles={role: list(values) for role, values in config.rbac.roles.items()},
        max_search_results=config.server.limits.max_search_results,
        profile_provider=lambda: admin_state.export_profiles(profile_store),
        runtime_fallback_profile=profile_store.get("operations_cloud_dog")
        or profile_store.get("operations"),
    )

    app = cast(
        FastAPI,
        platform_create_app(
            title="imap-mcp-server-mcp",
            version="0.1.0",
            description="MCP transport for IMAP tools.",
            api_prefix=mcp_base_path,
            timeout_seconds=_TOOL_REQUEST_TIMEOUT_SECONDS,
        ),
    )
    jobs_runtime = build_jobs_runtime(
        config,
        worker_suffix="mcp",
        app_log_path=log_paths["app_log_path"],
        audit_log_path=log_paths["audit_log_path"],
        integrity_log_path=log_paths["integrity_log_path"],
        environment=environment,
    )
    _install_browser_cors(app, web_port=config.web_server.port)
    install_service_context_middleware(app, log_paths=log_paths)
    # W28A-735-R5 / D-IMAP-IDENTITY-COLLAPSE-1: gate the MCP transport so an
    # unauthenticated caller is rejected with 401 BEFORE any tool execution or
    # role resolution. Previously the MCP app installed NO auth gate and
    # _effective_roles defaulted anon to {admin} — an anonymous MCP client could
    # execute tools as admin. With the gate, only a caller presenting a valid
    # API key (x-api-key / bearer) reaches the tool routes; anon -> 401. Health
    # probes (/health, /ready, /live, /status) stay public (default skip set).
    install_auth_middleware(
        app,
        auth_runtime=auth_runtime,
        auth_mode=config.server.auth.mode,
    )

    tool_routes: dict[str, dict[str, Any]] = {}
    for contract in registry.contracts().values():

        def _handler(
            payload: dict[str, Any], request: Request, _name: str = contract.name
        ) -> dict[str, Any]:
            token = set_audit_request_context(_audit_context(request))
            try:
                return registry.call(_name, payload)
            finally:
                reset_audit_request_context(token)

        tool_routes[contract.name] = {
            "handler": _handler,
            "description": contract.description,
            "input_schema": contract.input_model.model_json_schema(),
            "output_schema": {"type": "object"},
        }
    _register_tool_router_compat(
        app,
        tool_routes,
        auth_runtime=auth_runtime,
        base_path=mcp_tools_path,
        root_path=mcp_base_path or "/",
        alias_paths=(MCP_TOOLS_ALIAS_PATH,),
    )

    app.state.config = config
    app.state.tool_registry = registry
    app.state.audit_writer = audit_writer
    app.state.auth_runtime = auth_runtime
    app.state.admin_state = admin_state
    app.state.seed_api_key = seed_api_key
    app.state.jobs_runtime = jobs_runtime
    app.state.server_id = config.server.server_id
    app.state.environment = environment

    # Register lifecycle hooks via the platform factory's lifespan context.
    # NOTE: @app.on_event("shutdown") is silently ignored when a lifespan
    # context is set (which platform_create_app does).
    hooks = app.state.lifecycle_hooks
    _prev_shutdown = hooks.on_shutdown

    async def _shutdown_runtime(app_ref: object) -> None:
        if _prev_shutdown is not None:
            await _prev_shutdown(app_ref)
        jobs_runtime.close()
        audit_writer.close()

    hooks.on_shutdown = _shutdown_runtime

    return app


def run_mcp(env_files: list[str] | None = None) -> None:
    """Run MCP server using configured MCP listener settings."""
    resolved_env_files = resolve_env_files(env_files)
    config = load_global_config(env_files=resolved_env_files)
    getattr(uvicorn, "run")(
        create_mcp_app(env_files=resolved_env_files),
        host=config.mcp_server.host,
        port=config.mcp_server.port,
        log_level="info",
    )


if __name__ == "__main__":
    run_mcp()
