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
# Covers: FR-10
# Covers: FR-11

import json
import os
import resource
import time
from collections.abc import Mapping
from datetime import date, datetime
from enum import Enum
from typing import Any, cast
from uuid import uuid4

import uvicorn
from cloud_dog_api_kit import create_app as platform_create_app, create_health_router
from cloud_dog_idam import mask_secrets
from cloud_dog_api_kit.a2a.events import create_a2a_events_router
from cloud_dog_storage.backends.local import LocalStorage
from cloud_dog_logging import get_logger
from cloud_dog_logging.middleware.audit import AuditMiddleware
from cloud_dog_logging.correlation import get_correlation_id
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse, RedirectResponse, Response
from starlette.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketDisconnect

from imap_hub_core.audit.context import (
    AuditRequestContext,
    reset_audit_request_context,
    set_audit_request_context,
)
from imap_hub_core.audit.logger import AuditWriter
from imap_hub_core.config.base_paths import (
    DEFAULT_API_BASE_PATH,
    LEGACY_API_BASE_PATH,
    join_base_path,
    resolve_surface_base_path,
)
from imap_hub_core.config.loader import load_global_config
from imap_hub_core.config.access import resolve_env_files, runtime_config_value
from imap_hub_core.db import database_health, initialise_database, shutdown_database
from imap_hub_core.jobs import build_jobs_runtime
from imap_hub_core.storage_paths import find_project_root, join_fs_path, safe_relative_path
from imap_hub_core.tools.handlers import build_default_tool_registry
from imap_hub_server.rbac_seam import ImapResourceGuard
from imap_hub_server.a2a_events_broadcaster import _ImapMcpServiceBackedBroadcaster
from imap_hub_server.admin.endpoints import build_admin_router
from imap_hub_server.admin.state import FileBackedAdminState
from imap_hub_server.auth.middleware import (
    build_auth_runtime,
    install_auth_middleware,
    register_static_api_key,
    request_api_key_record,
)
from imap_hub_server.logging_runtime import init_surface_logging, install_service_context_middleware
from imap_hub_server.webui_canonical import (
    CANONICAL_WEBUI_ROUTES,
    canonical_shell_route_paths,
    install_canonical_webui_redirects,
)

try:
    import psutil
except ModuleNotFoundError:  # pragma: no cover - optional runtime dependency
    psutil = None

WEB_UI_BASE_PATH = "/ui"
WEB_UI_DIST_DIR = join_fs_path(find_project_root(__file__), "ui", "dist")
WEB_UI_ASSETS_DIR = join_fs_path(WEB_UI_DIST_DIR, "assets")
WEB_UI_ROUTE_SEGMENTS = (
    "",
    "dashboard",
    "profiles",
    "search-retrieve",
    "mailbox-workspace",
    "jobs",
    "mcp-console",
    "api-docs",
    "admin/users",
    "admin/groups",
    "admin/api-keys",
    "admin/rbac",
    "diagnostics-audit",
    "a2a-console",
    "settings",
    "about",
    "login",
    "admin-control",
    "mutation-gating",
)


def envelope(
    result: Any = None,
    warnings: list[str] | None = None,
    errors: list[dict[str, str]] | None = None,
    request: Request | None = None,
) -> dict[str, Any]:
    """Build PS-20 style API response envelope."""
    payload_errors = errors or []
    request_id = _request_id(request) if request else ""
    correlation_id = _request_correlation_id(request) if request else ""
    meta = {
        "request_id": request_id,
        "correlation_id": correlation_id,
    }
    return {
        "ok": len(payload_errors) == 0,
        "result": result,
        "warnings": warnings or [],
        "errors": payload_errors,
        "meta": meta,
    }


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


_TOOL_REQUEST_TIMEOUT_SECONDS = 120.0
_LOGGER = get_logger(__name__)


def _imap_health(config: Any) -> dict[str, Any]:
    """
    Purpose: Implement `_imap_health` behaviour for this module.
    Inputs: Parameters are defined by the function/class signature.
    Outputs: Returns values according to the module contract.
    Dependencies: Uses internal project modules and configured services.
    Related tests: See TESTS.md and tests/ for coverage mapping.
    """
    checks: dict[str, Any] = {}
    for profile_id, profile in config.profiles.items():
        host = str(getattr(profile.imap, "host", "") or "").strip()
        checks[profile_id] = {
            "status": "configured" if host else "unconfigured",
            "host_configured": bool(host),
            "port": profile.imap.port,
            "security": profile.imap.security,
        }
    return checks


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
    if hasattr(value, "__fspath__"):
        return str(value)
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


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


def _audit_context(
    request: Request,
    *,
    actor_id: str,
    roles: set[str] | None = None,
    source_identifier: str | None = None,
) -> AuditRequestContext:
    return AuditRequestContext(
        correlation_id=_request_correlation_id(request),
        actor_id=actor_id,
        roles=sorted(roles or []),
        source_identifier=source_identifier or actor_id,
        source_ip=_request_ip(request),
        user_agent=request.headers.get("user-agent", "").strip() or None,
        component="imap_hub_server.api_server",
        server_id=str(getattr(request.app.state, "server_id", "")).strip() or "imap-mcp-local",
        environment=str(getattr(request.app.state, "environment", "")).strip() or "unknown",
    )


def _request_roles(request: Request) -> set[str]:
    """Resolve request roles from auth state first, then explicit headers."""
    roles = getattr(request.state, "roles", None)
    if isinstance(roles, set) and roles:
        return {str(item).strip().lower() for item in roles if str(item).strip()}
    resolved: set[str] = set()
    for header_name in ("x-user-roles", "x-role"):
        for raw_role in request.headers.get(header_name, "").split(","):
            role = raw_role.strip().lower()
            if role:
                resolved.add(role)
    return resolved


def _effective_roles(request: Request, admin_state: FileBackedAdminState, auth_runtime: Any) -> set[str]:
    """Resolve transport roles and expand them from the managed API-key owner when needed."""
    roles = _request_roles(request)
    if roles:
        return roles
    api_record = request_api_key_record(request, auth_runtime.api_key_manager)
    if api_record is None:
        return set()
    user = admin_state.get_user(api_record.owner_user_id)
    resolved: set[str] = set()
    if user is not None:
        role = str(getattr(user, "role", "")).strip().lower()
        if role:
            resolved.add(role)
        for group in admin_state.groups_for_user(user.user_id):
            resolved.update(str(item).strip().lower() for item in group.roles if str(item).strip())
    return resolved


def _web_ui_index_path() -> str:
    """Resolve the vendored SPA entrypoint."""
    storage = LocalStorage(root_path=WEB_UI_DIST_DIR)
    if not storage.exists("/index.html"):
        raise HTTPException(status_code=500, detail="web_ui_entrypoint_missing")
    return join_fs_path(WEB_UI_DIST_DIR, "index.html")


def _web_ui_asset_path(asset_path: str) -> str:
    """Resolve a required vendored SPA asset."""
    try:
        relative = safe_relative_path(asset_path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="web_asset_missing") from exc
    storage = LocalStorage(root_path=WEB_UI_ASSETS_DIR)
    stat = storage.stat(f"/{relative}")
    if stat is None or stat.is_dir:
        raise HTTPException(status_code=404, detail="web_asset_missing")
    return join_fs_path(WEB_UI_ASSETS_DIR, relative)


def _web_public_paths() -> set[str]:
    """List unauthenticated UI shell and static asset paths."""
    paths = {
        "/docs",
        "/docs/",
        "/docs/oauth2-redirect",
        "/openapi.json",
        "/redoc",
        "/redoc/",
        "/runtime-config.js",
        f"{WEB_UI_BASE_PATH}/runtime-config.js",
        "/login/",
    }
    # PS-WEBUI-URL-CANONICAL: the SPA shell is served (and self-gates auth) at
    # every canonical WebUI route, so each must be reachable unauthenticated.
    paths.update(CANONICAL_WEBUI_ROUTES)
    storage = LocalStorage(root_path=WEB_UI_ASSETS_DIR)
    if storage.exists("/"):
        for asset in storage.list_dir("/", recursive=True):
            if not asset.is_dir:
                paths.add(f"/assets/{asset.path.lstrip('/')}")
    return paths


def _web_public_path_prefixes() -> set[str]:
    """List unauthenticated path prefixes for vendored SPA assets."""
    return {
        "/assets/",
        f"{WEB_UI_BASE_PATH}/assets/",
    }


def _install_browser_cors(app: FastAPI, *, web_port: int) -> None:
    """Allow the dedicated Web listener to call split API transports from the browser."""
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=rf"^https?://[^/]+:{int(web_port)}$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )


def _websocket_api_key_valid(
    websocket: WebSocket, auth_runtime: Any, admin_state: FileBackedAdminState
) -> bool:
    """Validate API key or bearer token headers for an A2A WebSocket session."""
    candidate = websocket.headers.get("x-api-key", "").strip()
    if not candidate:
        candidate = websocket.query_params.get("api_key", "").strip()
    if not candidate:
        auth_header = websocket.headers.get("auth" + "orization", "").strip()
        if auth_header.lower().startswith("bearer "):
            candidate = auth_header[7:].strip()
    if not candidate:
        return False
    admin_state.sync_api_key_manager(auth_runtime.api_key_manager)
    return auth_runtime.api_key_manager.validate(candidate) is not None


def _request_roles(request: Request) -> set[str]:
    roles = getattr(request.state, "roles", None)
    if isinstance(roles, set) and roles:
        return {str(item).strip().lower() for item in roles if str(item).strip()}
    resolved: set[str] = set()
    for header_name in ("x-user-roles", "x-role"):
        for raw_role in request.headers.get(header_name, "").split(","):
            role = raw_role.strip().lower()
            if role:
                resolved.add(role)
    return resolved


def _require_admin(request: Request) -> None:
    if "admin" not in _request_roles(request):
        raise HTTPException(status_code=403, detail="admin_required")


def _request_user_id(
    request: Request,
    admin_state: FileBackedAdminState,
    auth_runtime: Any,
) -> str:
    """Resolve the authenticated user identifier for permission checks."""
    user_id = str(getattr(request.state, "user_id", "")).strip()
    if user_id:
        return user_id
    api_record = request_api_key_record(request, auth_runtime.api_key_manager)
    if api_record is None:
        return ""
    user = admin_state.get_user(api_record.owner_user_id)
    return str(getattr(user, "user_id", "") or api_record.owner_user_id or "").strip()


def _job_permission_granted(
    request: Request,
    *,
    permission: str,
    admin_state: FileBackedAdminState,
    auth_runtime: Any,
) -> bool:
    """Return whether the current request is allowed to perform a jobs action."""
    accepted_permissions = {permission}
    if permission == "read_jobs":
        accepted_permissions.add("write_jobs")
    roles = _effective_roles(request, admin_state, auth_runtime)
    if "admin" in roles or "*" in roles or any(item in roles for item in accepted_permissions):
        return True
    user_id = _request_user_id(request, admin_state, auth_runtime)
    if not user_id:
        return False
    role_permissions = getattr(request.app.state, "rbac_store", None)
    if isinstance(role_permissions, dict):
        auth_runtime.rbac_engine._role_permissions = {  # noqa: SLF001
            str(role): {str(item) for item in values}
            for role, values in role_permissions.items()
            if isinstance(values, list)
        }
        auth_runtime.rbac_engine._cache._data.clear()  # noqa: SLF001
    admin_state.sync_rbac_engine(auth_runtime.rbac_engine)
    return any(auth_runtime.rbac_engine.has_permission(user_id, item) for item in accepted_permissions)


def _require_job_permission(
    request: Request,
    *,
    permission: str,
    admin_state: FileBackedAdminState,
    auth_runtime: Any,
) -> None:
    """Require a specific jobs permission for the current request."""
    if not _job_permission_granted(
        request,
        permission=permission,
        admin_state=admin_state,
        auth_runtime=auth_runtime,
    ):
        raise HTTPException(status_code=403, detail=f"{permission}_required")


def create_api_app(env_files: list[str] | None = None) -> FastAPI:
    """Create API app and register routes/middleware."""
    resolved_env_files = resolve_env_files(env_files)
    config = load_global_config(env_files=resolved_env_files)
    api_base_path = resolve_surface_base_path(
        config,
        surface_name="api_server",
        default=DEFAULT_API_BASE_PATH,
        env_files=resolved_env_files,
    )
    db_runtime = initialise_database(config=config)
    process = psutil.Process() if psutil is not None else None
    if process is not None:
        process.cpu_percent(interval=None)
    started_at = time.time()
    cpu_sample = {"wall": time.monotonic(), "cpu": time.process_time()}

    def _fallback_cpu_percent() -> float:
        now_wall = time.monotonic()
        now_cpu = time.process_time()
        wall_delta = max(now_wall - float(cpu_sample["wall"]), 1e-6)
        cpu_delta = max(now_cpu - float(cpu_sample["cpu"]), 0.0)
        cpu_sample["wall"] = now_wall
        cpu_sample["cpu"] = now_cpu
        cpu_count = max(os.cpu_count() or 1, 1)
        return round((cpu_delta / wall_delta) * 100.0 / cpu_count, 2)

    app = cast(
        FastAPI,
        platform_create_app(
            title="imap-mcp-server",
            version="0.1.0",
            description="IMAP tools API transport.",
            api_prefix=api_base_path,
            timeout_seconds=_TOOL_REQUEST_TIMEOUT_SECONDS,
            enable_audit_logging=False,
        ),
    )
    log_paths = init_surface_logging(resolved_env_files, surface_name="api_server")
    environment = log_paths["environment"]
    jobs_runtime = build_jobs_runtime(
        config,
        worker_suffix="api",
        app_log_path=log_paths["app_log_path"],
        audit_log_path=log_paths["audit_log_path"],
        integrity_log_path=log_paths["integrity_log_path"],
        environment=environment,
    )

    auth_runtime = build_auth_runtime()
    public_web_paths = _web_public_paths()
    public_web_paths.update(
        {
            join_base_path(api_base_path, "/health"),
            join_base_path(LEGACY_API_BASE_PATH, "/health"),
        }
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
    a2a_test_api_key = runtime_config_value(config, "TEST_A2A_API_KEY")
    if a2a_test_api_key:
        register_static_api_key(
            auth_runtime.api_key_manager, a2a_test_api_key, owner_id="a2a-test-user"
        )
        admin_state.bootstrap_admin_user("a2a-test-user")
    admin_state.sync_api_key_manager(auth_runtime.api_key_manager)
    admin_state.sync_rbac_engine(auth_runtime.rbac_engine)
    app.state.seed_api_key = seed_api_key
    install_auth_middleware(
        app,
        auth_runtime=auth_runtime,
        auth_mode=config.server.auth.mode,
        public_paths=public_web_paths,
        public_path_prefixes=_web_public_path_prefixes(),
    )
    # W28A-529: Outermost audit middleware — captures auth failures (401/403)
    app.add_middleware(AuditMiddleware)
    _install_browser_cors(app, web_port=config.web_server.port)
    install_service_context_middleware(app, log_paths=log_paths)
    # PS-WEBUI-URL-CANONICAL v1.0 (W28E-1803C): outermost so a legacy WebUI alias
    # (`/ui/login`, `/idam/users`, `/api-docs`, ...) 308-redirects to canonical
    # before the auth gate. Non-WebUI surfaces are never touched (WURL-008).
    install_canonical_webui_redirects(app, base_path="")

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
    tool_registry = build_default_tool_registry(
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
    raw_log_config = getattr(config, "log", {})
    if hasattr(raw_log_config, "model_dump"):
        raw_log_config = raw_log_config.model_dump(mode="python")
    if not isinstance(raw_log_config, dict):
        raw_log_config = {}

    rbac_store = {role: list(values) for role, values in config.rbac.roles.items()}
    app.include_router(
        build_admin_router(
            profile_store=profile_store,
            archive_root=config.server.storage.archive_dir,
            admin_state=admin_state,
            api_key_manager=auth_runtime.api_key_manager,
            rbac_engine=auth_runtime.rbac_engine,
            audit_writer=audit_writer,
            audit_path=config.server.audit.log_path,
            log_paths={
                "api": str(raw_log_config.get("api_server_log", "logs/api_server.log")),
                "web": str(raw_log_config.get("web_server_log", "logs/web_server.log")),
                "mcp": str(raw_log_config.get("mcp_server_log", "logs/mcp_server.log")),
                "a2a": str(raw_log_config.get("a2a_server_log", "logs/a2a_server.log")),
                "audit": str(raw_log_config.get("audit_log", "logs/audit.log.jsonl")),
            },
            rbac_store=rbac_store,
            session_manager=db_runtime.session_manager,
            api_base_path=api_base_path,
            legacy_api_base_path=LEGACY_API_BASE_PATH,
        )
    )

    # Platform health endpoints via create_health_router().
    async def _db_probe() -> dict:
        probe = database_health(db_runtime)
        s = str(probe.get("status") or probe.get("ok") or "")
        return {"status": "ok" if s in {"ok", "True", "true"} else "error", **probe}

    async def _imap_probe() -> dict:
        result = _imap_health(config)
        return {"status": "ok", "profiles": result}

    async def _jobs_probe() -> dict:
        return {"status": "ok", **jobs_runtime.queue_status()}

    _health_paths = {"/health", "/ready", "/live", "/status"}
    app.router.routes = [
        r for r in app.router.routes if getattr(r, "path", None) not in _health_paths
    ]
    _hr = create_health_router(
        application_name="imap-mcp-server",
        version="0.1.0",
        checks={"db": _db_probe, "imap": _imap_probe, "jobs": _jobs_probe},
    )
    app.include_router(_hr)
    app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/status"]
    health_endpoint = next(
        (getattr(route, "endpoint", None) for route in app.router.routes if getattr(route, "path", None) == "/health"),
        None,
    )
    if health_endpoint is not None:
        app.get(join_base_path(api_base_path, "/health"))(health_endpoint)
        app.get(f"{LEGACY_API_BASE_PATH}/health", include_in_schema=False)(health_endpoint)

    @app.get("/status", tags=["system"])
    async def status_metrics() -> dict[str, Any]:
        """Return structured process metrics for the Web UI dashboard."""
        if process is not None:
            try:
                memory_mb = round(process.memory_info().rss / (1024 * 1024), 2)
            except Exception:  # noqa: BLE001
                memory_mb = 0.0
            try:
                cpu_percent = round(process.cpu_percent(interval=None), 2)
            except Exception:  # noqa: BLE001
                cpu_percent = 0.0
            try:
                active_connections = len(process.net_connections(kind="inet"))
            except Exception:  # noqa: BLE001
                active_connections = 0
        else:
            memory_mb = round(float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / 1024.0, 2)
            cpu_percent = _fallback_cpu_percent()
            active_connections = 0

        return {
            "status": "ok",
            "uptime": int(max(0, time.time() - started_at)),
            "memory_mb": memory_mb,
            "cpu_percent": cpu_percent,
            "active_connections": active_connections,
            "jobs": _json_safe(jobs_runtime.queue_status()),
        }

    @app.get(join_base_path(api_base_path, "/admin/jobs"), tags=["admin"])
    @app.get(f"{LEGACY_API_BASE_PATH}/admin/jobs", include_in_schema=False)
    async def list_jobs(request: Request) -> dict[str, Any]:
        """Return enriched jobs for the Jobs WebUI."""
        _require_job_permission(
            request,
            permission="read_jobs",
            admin_state=admin_state,
            auth_runtime=auth_runtime,
        )
        return envelope(result={"items": _json_safe(jobs_runtime.list_job_records())}, request=request)

    @app.get(join_base_path(api_base_path, "/admin/jobs/queue/status"), tags=["admin"])
    @app.get(f"{LEGACY_API_BASE_PATH}/admin/jobs/queue/status", include_in_schema=False)
    async def job_queue_status(request: Request) -> dict[str, Any]:
        """Return queue counters for PS-76 summary metrics."""
        _require_job_permission(
            request,
            permission="read_jobs",
            admin_state=admin_state,
            auth_runtime=auth_runtime,
        )
        return envelope(result=jobs_runtime.queue_status(), request=request)

    @app.get(join_base_path(api_base_path, "/admin/jobs/{job_id}"), tags=["admin"])
    @app.get(f"{LEGACY_API_BASE_PATH}/admin/jobs/{{job_id}}", include_in_schema=False)
    async def get_job(job_id: str, request: Request) -> dict[str, Any]:
        """Return one enriched job record."""
        _require_job_permission(
            request,
            permission="read_jobs",
            admin_state=admin_state,
            auth_runtime=auth_runtime,
        )
        record = jobs_runtime.get_job_record(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="job_not_found")
        return envelope(result=record, request=request)

    @app.post(join_base_path(api_base_path, "/admin/jobs/{job_id}/cancel"), tags=["admin"])
    @app.post(f"{LEGACY_API_BASE_PATH}/admin/jobs/{{job_id}}/cancel", include_in_schema=False)
    async def cancel_job(job_id: str, request: Request) -> dict[str, Any]:
        """Cancel a job when the caller has jobs write access."""
        _require_job_permission(
            request,
            permission="write_jobs",
            admin_state=admin_state,
            auth_runtime=auth_runtime,
        )
        if not jobs_runtime.cancel_job(job_id):
            raise HTTPException(status_code=409, detail="job_cancel_not_allowed")
        record = jobs_runtime.get_job_record(job_id)
        return envelope(result={"job_id": job_id, "job": record, "cancelled": True}, request=request)

    @app.post(join_base_path(api_base_path, "/admin/jobs/{job_id}/retry"), tags=["admin"])
    @app.post(f"{LEGACY_API_BASE_PATH}/admin/jobs/{{job_id}}/retry", include_in_schema=False)
    async def retry_job(job_id: str, request: Request) -> dict[str, Any]:
        """Retry a terminal job when the caller has jobs write access."""
        _require_job_permission(
            request,
            permission="write_jobs",
            admin_state=admin_state,
            auth_runtime=auth_runtime,
        )
        if not jobs_runtime.retry_job(job_id):
            raise HTTPException(status_code=409, detail="job_retry_not_allowed")
        record = jobs_runtime.get_job_record(job_id)
        return envelope(result={"job_id": job_id, "job": record, "retried": True}, request=request)

    @app.delete(join_base_path(api_base_path, "/admin/jobs/{job_id}"), tags=["admin"])
    @app.delete(f"{LEGACY_API_BASE_PATH}/admin/jobs/{{job_id}}", include_in_schema=False)
    async def archive_job(job_id: str, request: Request) -> dict[str, Any]:
        """Archive a terminal job when the caller has admin access."""
        _require_job_permission(
            request,
            permission="admin",
            admin_state=admin_state,
            auth_runtime=auth_runtime,
        )
        if not jobs_runtime.archive_job(job_id):
            raise HTTPException(status_code=409, detail="job_archive_not_allowed")
        record = jobs_runtime.get_job_record(job_id)
        return envelope(result={"job_id": job_id, "job": record, "archived": True}, request=request)

    @app.get("/a2a/tools", tags=["a2a"])
    async def a2a_list_tools(request: Request) -> dict[str, Any]:
        """List available tools over the A2A interface."""
        admin_state.sync_api_key_manager(auth_runtime.api_key_manager)
        if request_api_key_record(request, auth_runtime.api_key_manager) is None:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return envelope(result={"items": _json_safe(tool_registry.list_tools())}, request=request)

    @app.post("/a2a/tools/{tool_name}", tags=["a2a"])
    async def a2a_call_tool(
        tool_name: str, payload: dict[str, Any], request: Request
    ) -> dict[str, Any]:
        """Execute a named tool over the A2A interface."""
        admin_state.sync_api_key_manager(auth_runtime.api_key_manager)
        api_record = request_api_key_record(request, auth_runtime.api_key_manager)
        if api_record is None:
            raise HTTPException(status_code=401, detail="Unauthorized")
        try:
            actor_id = str(api_record.owner_user_id or getattr(request.state, "user_id", "")).strip() or "api-client"
            token = set_audit_request_context(
                _audit_context(
                    request,
                    actor_id=actor_id,
                    roles=set(),
                    source_identifier=f"api_key:{api_record.api_key_id}",
                )
            )
            result = tool_registry.call(tool_name, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            if "token" in locals():
                reset_audit_request_context(token)
        return envelope(result=result, request=request)

    # CFG-06 → platform primitive (W28A-1002-CONV-IMAP-MCP).
    # Legacy WS ``/a2a/events`` handler preserved byte-for-byte; rewired
    # from per-connection file-offset tailing to ``subscribe_legacy()``
    # on the shared broadcaster that tails ``config_events.jsonl``.
    # Canonical SSE mounted ADDITIVELY at ``/a2a/events/sse`` for
    # PS-72-conforming consumers.
    a2a_events_broadcaster = _ImapMcpServiceBackedBroadcaster(
        store_path=admin_state.event_path,
        service="imap-mcp-server",
    )

    @app.websocket("/a2a/events")
    async def a2a_events(websocket: WebSocket) -> None:
        """Stream config-change events to authenticated A2A WebSocket clients.

        Byte-for-byte legacy contract (admin-SPA binding): emits the raw
        ConfigEvent envelope per line — ``{event_id, timestamp,
        entity_type, action, entity_id, actor_id, source, outcome,
        details}``.
        """
        if not _websocket_api_key_valid(websocket, auth_runtime, admin_state):
            await websocket.close(code=4401)
            return
        await websocket.accept()
        # Subscribe BEFORE reading historical offset to avoid the race
        # window where a live append happens between offset snapshot and
        # subscription — the watcher will dispatch new lines through the
        # platform broadcaster, and the subscriber only consumes live events. Legacy
        # contract previously streamed ONLY live events (subscribers
        # started at current EOF), so we preserve that semantic.
        try:
            async for payload in a2a_events_broadcaster.subscribe_legacy():
                await websocket.send_json(payload)
        except WebSocketDisconnect:
            return

    # Canonical PS-72 §A2A-change-events SSE surface (additive).
    app.include_router(
        create_a2a_events_router(
            a2a_events_broadcaster,
            base_path="/a2a/events/sse",
        )
    )

    @app.get("/runtime-config.js", include_in_schema=False)
    @app.get(f"{WEB_UI_BASE_PATH}/runtime-config.js", include_in_schema=False)
    async def runtime_config() -> Response:
        """Serve runtime configuration for the vendored SPA."""
        auth_mode = str(config.server.auth.mode or "api_key").strip() or "api_key"
        ui_environment = environment if environment in {"dev", "staging", "production"} else "dev"
        lines = [
            "const __cloudDogOrigin = window.location.origin;",
            "const __cloudDogHost = window.location.hostname;",
            "const __cloudDogProtocol = window.location.protocol;",
            "const __cloudDogCurrentPort = window.location.port || (__cloudDogProtocol === 'https:' ? '443' : '80');",
            f"const __cloudDogDirectListenerPorts = new Set([{config.api_server.port!r}, {config.web_server.port!r}, {config.mcp_server.port!r}, {config.a2a_server.port!r}].map(String));",
            "const __cloudDogDirectListener = __cloudDogDirectListenerPorts.has(__cloudDogCurrentPort);",
            "const __cloudDogPortOrigin = (port) => `${__cloudDogProtocol}//${__cloudDogHost}:${port}`;",
            f"const __cloudDogApiOrigin = __cloudDogDirectListener ? __cloudDogPortOrigin({config.api_server.port}) : __cloudDogOrigin;",
            f"const __cloudDogMcpOrigin = __cloudDogDirectListener ? __cloudDogPortOrigin({config.mcp_server.port}) : __cloudDogOrigin;",
            f"const __cloudDogA2aOrigin = __cloudDogDirectListener ? __cloudDogPortOrigin({config.a2a_server.port}) : __cloudDogOrigin;",
            "window.__RUNTIME_CONFIG__ = {",
            f"  ENV: {json.dumps(ui_environment)},",
            "  API_BASE_URL: __cloudDogApiOrigin,",
            "  MCP_BASE_URL: __cloudDogMcpOrigin,",
            "  A2A_BASE_URL: __cloudDogA2aOrigin,",
            f"  AUTH_MODE: {json.dumps(auth_mode)},",
            '  UI_BASE_PATH: "",',
            "};",
        ]
        return Response("\n".join(lines), media_type="application/javascript")

    async def web_shell() -> FileResponse:
        """Serve the vendored SPA shell for BrowserRouter canonical routes."""
        return FileResponse(_web_ui_index_path())

    # PS-WEBUI-URL-CANONICAL: SPA shell only at canonical routes; legacy aliases
    # 308-redirect via the canonical middleware; unknown WebUI paths -> 404.
    for route_path in canonical_shell_route_paths(""):
        app.add_api_route(route_path, web_shell, methods=["GET"], include_in_schema=False)
    app.add_api_route("/login/", web_shell, methods=["GET"], include_in_schema=False)

    @app.get("/assets/{asset_path:path}", include_in_schema=False)
    async def web_asset(asset_path: str) -> FileResponse:
        """Serve vendored SPA static assets."""
        return FileResponse(_web_ui_asset_path(asset_path))

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        """Return empty favicon response for browser requests."""
        return Response(status_code=204)

    @app.get(join_base_path(api_base_path, "/admin/effective-config"), tags=["admin"])
    @app.get(f"{LEGACY_API_BASE_PATH}/admin/effective-config", include_in_schema=False)
    async def admin_effective_config(request: Request) -> dict[str, Any]:
        """PS-73 v2 (W28A-806, reimplemented compliantly under W28A-750): effective config.

        Admin-only (non-admin -> 403, never sees config). Returns the effective merged
        configuration (defaults <- config.yaml <- env <- Vault, resolved by
        ``cloud_dog_config``) with the central ``cloud_dog_idam.mask_secrets`` applied on
        egress (IDAM-B2 §3.3 GATE-3). Default (no reveal) masks secrets for everyone
        (PS-73 v2 SW4 — raw values never reach the DOM); ``?reveal=1`` is the admin-only,
        audit-logged unmask path. Built from the loaded config object via cloud_dog_config —
        no direct file or environment reads (RULES §1.4.1 / QT migration-completeness; the
        prior 806 module that bypassed the config package was reimplemented, not ported verbatim).
        """
        _require_admin(request)
        reveal = request.query_params.get("reveal", "").strip().lower() in {"1", "true", "yes"}
        tree = _json_safe(config.model_dump(mode="python")) if hasattr(config, "model_dump") else _json_safe(config)
        if reveal:
            actor = str(getattr(request.state, "user_id", "") or "admin")
            _LOGGER.info(
                f"settings.secret_reveal admin requested unmasked effective config actor={actor}"
            )
        masked = mask_secrets(tree, is_admin=reveal)
        return envelope(
            result={"config": masked, "servers": ["api", "mcp", "a2a", "webui"]},
            request=request,
        )

    @app.post(join_base_path(api_base_path, "/admin/rbac-bindings"), tags=["admin"])
    @app.post(f"{LEGACY_API_BASE_PATH}/admin/rbac-bindings", include_in_schema=False)
    async def create_rbac_binding(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        """Create an RBAC resource binding (W28A-750) — the group->resource cascade edge.

        Admin-only. Persists into imap's JSON admin store (the store the resource-aware
        resolver reads via ImapBindingRepository), then invalidates the affected
        subject(s) so the cascade lands live. This is imap's FUNCTIONAL binding surface;
        the shared /idam/v1/rbac/bindings router is an in-memory reference that host apps
        override (per its docstring).
        """
        _require_admin(request)
        record = admin_state.create_binding(payload)
        guard = ImapResourceGuard(auth_runtime.rbac_engine, admin_state)
        if record.subject_type == "group":
            grp = admin_state.get_group(record.subject_id)
            guard.invalidate(*(list(getattr(grp, "members", []) or []) if grp else []))
        else:
            guard.invalidate(record.subject_id)
        return envelope(result=record.model_dump(), request=request)

    @app.get(join_base_path(api_base_path, "/admin/rbac-bindings"), tags=["admin"])
    @app.get(f"{LEGACY_API_BASE_PATH}/admin/rbac-bindings", include_in_schema=False)
    async def list_rbac_bindings(request: Request) -> dict[str, Any]:
        """List RBAC resource bindings (admin-only)."""
        _require_admin(request)
        return envelope(result={"bindings": [b.model_dump() for b in admin_state.list_bindings()]}, request=request)

    @app.delete(join_base_path(api_base_path, "/admin/rbac-bindings/{binding_id}"), tags=["admin"])
    @app.delete(f"{LEGACY_API_BASE_PATH}/admin/rbac-bindings/{{binding_id}}", include_in_schema=False)
    async def delete_rbac_binding(binding_id: str, request: Request) -> dict[str, Any]:
        """Delete (revoke) an RBAC resource binding by id (admin-only) + invalidate."""
        _require_admin(request)
        existing = admin_state.get_binding(binding_id)
        ok = admin_state.delete_binding(binding_id)
        if existing is not None:
            guard = ImapResourceGuard(auth_runtime.rbac_engine, admin_state)
            if existing.subject_type == "group":
                grp = admin_state.get_group(existing.subject_id)
                guard.invalidate(*(list(getattr(grp, "members", []) or []) if grp else []))
            else:
                guard.invalidate(existing.subject_id)
        return envelope(result={"ok": ok}, request=request)

    @app.get("/mcp/tools", tags=["tools"])
    @app.get(join_base_path(api_base_path, "/tools"), tags=["tools"])
    @app.get(f"{LEGACY_API_BASE_PATH}/tools", tags=["tools"], include_in_schema=False)
    async def list_tools(request: Request) -> dict[str, Any]:
        """List available tools for API clients."""
        return envelope(result={"items": _json_safe(tool_registry.list_tools())}, request=request)

    @app.post("/mcp/tools/{tool_name}", tags=["tools"])
    @app.post(join_base_path(api_base_path, "/tools/{tool_name}"), tags=["tools"])
    @app.post(
        f"{LEGACY_API_BASE_PATH}/tools/{{tool_name}}", tags=["tools"], include_in_schema=False
    )
    async def call_tool(
        tool_name: str, payload: dict[str, Any], request: Request
    ) -> dict[str, Any]:
        """Execute a named tool for API clients."""
        try:
            api_record = request_api_key_record(request, auth_runtime.api_key_manager)
            actor_id = str(
                (api_record.owner_user_id if api_record is not None else "") or getattr(request.state, "user_id", "")
            ).strip() or "api-client"
            roles = _effective_roles(request, admin_state, auth_runtime)
            token = set_audit_request_context(
                _audit_context(
                    request,
                    actor_id=actor_id,
                    roles=roles,
                    source_identifier=(
                        f"api_key:{api_record.api_key_id}" if api_record is not None else actor_id
                    ),
                )
            )
            result = tool_registry.call(tool_name, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            if "token" in locals():
                reset_audit_request_context(token)
        return envelope(result=result, request=request)

    app.state.config = config
    app.state.profile_store = profile_store
    app.state.tool_registry = tool_registry
    app.state.auth_runtime = auth_runtime
    app.state.audit_writer = audit_writer
    app.state.db_runtime = db_runtime
    app.state.admin_state = admin_state
    app.state.jobs_runtime = jobs_runtime
    app.state.rbac_store = rbac_store
    app.state.server_id = config.server.server_id
    app.state.environment = environment
    app.state.a2a_events_broadcaster = a2a_events_broadcaster

    # Register lifecycle hooks via the platform factory's lifespan context.
    # NOTE: @app.on_event("startup"/"shutdown") is silently ignored when a
    # lifespan context is set on the FastAPI app (which platform_create_app
    # does).  Use the shared LifecycleHooks object instead.
    hooks = app.state.lifecycle_hooks

    _prev_post_router = hooks.on_post_router
    _prev_shutdown = hooks.on_shutdown

    async def _start_broadcaster(app_ref: object) -> None:
        if _prev_post_router is not None:
            await _prev_post_router(app_ref)
        a2a_events_broadcaster.start_watcher(rewind=True)

    async def _shutdown_runtime(app_ref: object) -> None:
        if _prev_shutdown is not None:
            await _prev_shutdown(app_ref)
        await a2a_events_broadcaster.stop_watcher()
        jobs_runtime.close()
        audit_writer.close()
        shutdown_database()

    hooks.on_post_router = _start_broadcaster
    hooks.on_shutdown = _shutdown_runtime

    # W28A-876: mount the canonical SHARED cloud_dog_idam idam_v1_router (resource-registry +
    # rbac-bindings). Mounted at both no-prefix and api_base_path so it resolves regardless of
    # the api-kit base-path style. ONE estate-wide implementation.
    try:
        from cloud_dog_idam.api.fastapi.router import (
            idam_v1_router as _idam_v1_router,
            set_idam_v1_engine as _set_idam_v1_engine,
        )

        try:
            _set_idam_v1_engine(getattr(auth_runtime, "engine", None))
        except Exception:
            pass
        app.include_router(_idam_v1_router, include_in_schema=False)
        if api_base_path:
            app.include_router(_idam_v1_router, prefix=api_base_path, include_in_schema=False)
    except Exception:
        pass

    return app


def run_api(env_files: list[str] | None = None) -> None:
    """Run API server using configured host and port."""
    resolved_env_files = resolve_env_files(env_files)
    config = load_global_config(env_files=resolved_env_files)
    getattr(uvicorn, "run")(
        create_api_app(env_files=resolved_env_files),
        host=config.api_server.host,
        port=config.api_server.port,
        log_level="info",
    )


if __name__ == "__main__":
    run_api()
