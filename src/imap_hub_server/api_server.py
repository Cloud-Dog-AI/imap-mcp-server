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
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from starlette.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketDisconnect

from imap_hub_server import __version__
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


def _build_watch_service(db_runtime: Any, audit_writer: Any) -> Any:
    """Build the durable mail-profile change-watch adapter (W28E-1870-D, PS-102 §4.2).

    Consumes the common ``cloud_dog_api_kit.change_stream`` foundation: a
    ``WatchCoordinator`` with a durable ``SqlJournal`` over the service's real
    ``cloud_dog_db`` engine (backlog survives restart, CSTREAM-007), live fan-out
    via a dedicated ``a2a.events`` ``InMemoryEventBroadcaster`` through
    ``make_broadcast_hook`` (PS-102 §9 reuse), and audit via the shared
    ``AuditWriter`` (CSTREAM-010). Falls back to a bounded in-memory journal when
    the DB engine / broadcaster is unavailable so change-watch never blocks
    startup on a database.
    """
    from imap_hub_core.change_stream import WatchService, make_audit_sink

    engine = None
    try:
        engine = db_runtime.engine
    except Exception:  # pragma: no cover - no DB runtime in this tier
        engine = None
    broadcaster = None
    try:
        from cloud_dog_api_kit.a2a.events import InMemoryEventBroadcaster

        broadcaster = InMemoryEventBroadcaster()
    except Exception:  # pragma: no cover - broadcaster surface unavailable
        broadcaster = None
    return WatchService(
        engine=engine,
        broadcaster=broadcaster,
        audit_sink=make_audit_sink(audit_writer) if audit_writer is not None else None,
    )


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
            version=__version__,
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
            # W28E-1863 fix-wave-d (WSC-014): the About-page build-identity /version
            # must be reachable unauthenticated (like the shared api-kit /version and
            # /health) so the status bar / About page can render before login.
            join_base_path(api_base_path, "/version"),
            join_base_path(LEGACY_API_BASE_PATH, "/version"),
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
    # W28E-1870-D: build the durable mail-profile change-watch adapter (PS-102 §4.2)
    # over the common change-stream foundation BEFORE the registry so the watch
    # tools bind to the same instance the REST /v1/watches* surface serves. The
    # journal is durable via the service ``cloud_dog_db`` engine (survives restart,
    # CSTREAM-007); live fan-out goes through a dedicated a2a.events broadcaster.
    watch_service = _build_watch_service(db_runtime, audit_writer)
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
        watch_service=watch_service,
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
        version=__version__,
        checks={"db": _db_probe, "imap": _imap_probe, "jobs": _jobs_probe},
    )
    app.include_router(_hr)
    app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/status"]
    # W28E-1863 WS-A: source the /health endpoint from the health router itself,
    # not from ``app.router.routes`` after inclusion. FastAPI (>=0.139) includes a
    # sub-router *lazily* — ``include_router`` appends a single ``_IncludedRouter``
    # marker instead of flattening each ``APIRoute`` onto ``app.router.routes`` — so
    # a post-include scan for ``route.path == "/health"`` finds nothing, leaving
    # ``health_endpoint`` None and SILENTLY skipping the canonical
    # ``{api_base_path}/health`` and legacy ``/app/v1/health`` re-registration
    # (canonical + legacy health then 404). ``_hr.routes`` still exposes the flat
    # health APIRoute + its endpoint callable regardless of inclusion strategy.
    health_endpoint = next(
        (
            getattr(route, "endpoint", None)
            for route in _hr.routes
            if getattr(route, "path", None) == "/health"
        ),
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

    def _api_build_identity() -> dict[str, str]:
        """Build/deploy identity for WSC-014 (config-routed, git-HEAD dev fallback).

        Reads the container build ENV via ``runtime_config_value`` (RULES
        §1.4.1-compliant — config-routed, no direct-environment read).
        W28E-1863 fix-wave-d.
        """
        commit = runtime_config_value(
            config, "build.source_commit", "CLOUD_DOG__BUILD__SOURCE_COMMIT"
        ).strip()
        if not commit or commit == "unknown":
            try:
                import subprocess
                from pathlib import Path as _Path

                _root = _Path(__file__).resolve().parents[2]
                _out = subprocess.run(
                    ["git", "-C", str(_root), "rev-parse", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False,
                )
                commit = _out.stdout.strip() if _out.returncode == 0 else ""
            except Exception:  # noqa: BLE001 - build identity must never crash a request
                commit = ""
        branch = runtime_config_value(
            config, "build.source_branch", "CLOUD_DOG__BUILD__SOURCE_BRANCH"
        ).strip()
        if branch == "unknown":
            branch = ""
        build_date = runtime_config_value(
            config, "build.build_date", "CLOUD_DOG__BUILD__BUILD_DATE"
        ).strip()
        digest = runtime_config_value(
            config, "build.container_digest", "CLOUD_DOG__BUILD__CONTAINER_DIGEST"
        ).strip()
        return {
            "source_commit": commit,
            "source_branch": branch,
            "build_date": build_date,
            "container_digest": digest,
        }

    @app.get(join_base_path(api_base_path, "/version"), include_in_schema=False)
    async def api_build_version() -> JSONResponse:
        """Build-identity /version for the shared About page (WSC-014).

        W28E-1863 fix-wave-d / PS-30 UI-R7.3: the FE ``getVersion()`` fetches
        ``{apiPath}/version`` (``/api/v1/version`` or the ``/webapi/v1/version``
        proxy alias). The shared cloud_dog_api_kit factory already registers a
        same-path ``/version`` emitting only application/version/api_version; this
        route adds source_commit + build_date + deployment identity (config-routed,
        git-HEAD dev fallback) and is promoted to the FRONT of the router below so
        it takes precedence (first-match-wins) without forking the factory.
        """
        _build = _api_build_identity()
        return JSONResponse(
            {
                "service": "imap-mcp-server",
                "application": "imap-mcp-server",
                "version": __version__,
                "appVersion": __version__,
                "app_version": __version__,
                "source_commit": _build["source_commit"],
                "source_branch": _build["source_branch"],
                "build_date": _build["build_date"],
                "container_digest": _build["container_digest"],
                "environment": environment,
                "commit": _build["source_commit"],
            }
        )

    # W28E-1863 fix-wave-d (WSC-014): promote the build-identity /version route to
    # the front so it takes precedence over the shared api-kit factory's own
    # same-path /version endpoint (first-match-wins) without forking the factory.
    for _idx, _route in enumerate(list(app.router.routes)):
        if getattr(_route, "endpoint", None) is api_build_version:
            app.router.routes.insert(0, app.router.routes.pop(_idx))
            break

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

    # -- W28E-1870-D mail-profile change-watch REST surface (PS-102 §5.5 / CSTREAM-IMAP) --
    # Anonymous callers are rejected with 401 by the auth middleware (the routes are
    # not public). Read verbs need an authenticated role; mutating lifecycle verbs
    # need a writer/admin role. Tenant/profile ownership is enforced inside the
    # WatchService adapter (cross-tenant = hard 404, no existence leak).
    from cloud_dog_api_kit.change_stream.errors import (
        ChangeStreamError as _ChangeStreamError,
    )
    from cloud_dog_api_kit.change_stream.errors import (
        CursorExpired as _CursorExpired,
    )
    from cloud_dog_api_kit.change_stream.errors import (
        RateLimited as _RateLimited,
    )
    from cloud_dog_api_kit.change_stream.errors import (
        WatchNotFound as _WatchNotFound,
    )

    _WATCH_WRITE_ROLES = {"admin", "writer", "*"}

    def _watch_error(exc: _ChangeStreamError) -> HTTPException:
        detail = exc.to_dict() if hasattr(exc, "to_dict") else {"code": "error", "message": str(exc)}
        if isinstance(exc, _WatchNotFound):
            return HTTPException(status_code=404, detail=detail)
        if isinstance(exc, _RateLimited):
            return HTTPException(status_code=429, detail=detail)
        if isinstance(exc, _CursorExpired):
            return HTTPException(status_code=409, detail=detail)
        return HTTPException(status_code=400, detail=detail)

    def _watch_actor(request: Request) -> str:
        api_record = request_api_key_record(request, auth_runtime.api_key_manager)
        actor_id = str(
            (api_record.owner_user_id if api_record is not None else "")
            or getattr(request.state, "user_id", "")
        ).strip()
        return actor_id or "api-client"

    def _watch_require_write(request: Request) -> None:
        roles = _effective_roles(request, admin_state, auth_runtime)
        if not (roles & _WATCH_WRITE_ROLES):
            raise HTTPException(
                status_code=403,
                detail={"code": "unauthorised", "message": "writer or admin role required"},
            )

    def _watch_tenant(payload_or_query: dict[str, Any]) -> str:
        return str(payload_or_query.get("profile") or payload_or_query.get("profile_id") or "default")

    async def _watch_body(request: Request) -> dict[str, Any]:
        try:
            body = await request.body()
        except Exception:
            return {}
        if not body or not body.strip():
            return {}
        try:
            parsed = json.loads(body)
        except Exception as exc:
            raise HTTPException(status_code=422, detail="invalid JSON body") from exc
        return parsed if isinstance(parsed, dict) else {}

    async def watches_create(request: Request) -> dict[str, Any]:
        _watch_require_write(request)
        payload = await _watch_body(request)
        tenant = _watch_tenant(payload)
        try:
            return watch_service.create_watch(
                profile_id=tenant,
                tenant_id=tenant,
                actor=_watch_actor(request),
                criteria=payload.get("criteria") if isinstance(payload.get("criteria"), dict) else None,
                max_batch=int(payload.get("max_batch", 100)),
                max_inflight=int(payload.get("max_inflight", 4)),
                journal_max=int(payload.get("journal_max", 1000)),
                journal_ttl_seconds=(
                    float(payload["journal_ttl_seconds"])
                    if payload.get("journal_ttl_seconds") not in (None, "")
                    else None
                ),
            )
        except _ChangeStreamError as exc:
            raise _watch_error(exc) from exc

    def watches_list(request: Request, profile: str = "default") -> dict[str, Any]:
        return {"watches": watch_service.list_watches(tenant_id=str(profile or "default"))}

    def watches_get(watch_id: str, request: Request, profile: str = "default") -> dict[str, Any]:
        try:
            return watch_service.get_watch(watch_id, tenant_id=str(profile or "default"))
        except _ChangeStreamError as exc:
            raise _watch_error(exc) from exc

    def watches_status(watch_id: str, request: Request, profile: str = "default") -> dict[str, Any]:
        try:
            return watch_service.get_status(watch_id, tenant_id=str(profile or "default"))
        except _ChangeStreamError as exc:
            raise _watch_error(exc) from exc

    def watches_events(
        watch_id: str,
        request: Request,
        profile: str = "default",
        since_cursor: str | None = None,
        max_batch: int | None = None,
        wait_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Bounded pull-batch / long-poll retrieval (PS-102 §5.2 base mode).

        ``wait_seconds`` is accepted and bounded but never holds a worker: an empty
        batch + current cursor is returned immediately when no events are pending
        (CSTREAM-002). SSE is additive.
        """
        try:
            return watch_service.get_batch(
                watch_id,
                tenant_id=str(profile or "default"),
                since_cursor=since_cursor or None,
                max_batch=int(max_batch) if max_batch else None,
            )
        except _ChangeStreamError as exc:
            raise _watch_error(exc) from exc

    async def watches_ack(watch_id: str, request: Request) -> dict[str, Any]:
        payload = await _watch_body(request)
        try:
            return watch_service.ack(
                watch_id, tenant_id=_watch_tenant(payload), ack_cursor=str(payload["ack_cursor"])
            )
        except KeyError as exc:
            raise HTTPException(status_code=422, detail="ack_cursor is required") from exc
        except _ChangeStreamError as exc:
            raise _watch_error(exc) from exc

    async def watches_recover(watch_id: str, request: Request) -> dict[str, Any]:
        payload = await _watch_body(request)
        try:
            return watch_service.recover(
                watch_id, tenant_id=_watch_tenant(payload),
                since_cursor=payload.get("since_cursor") or None,
            )
        except _ChangeStreamError as exc:
            raise _watch_error(exc) from exc

    async def watches_pause(watch_id: str, request: Request) -> dict[str, Any]:
        _watch_require_write(request)
        payload = await _watch_body(request)
        try:
            return watch_service.pause(watch_id, tenant_id=_watch_tenant(payload))
        except _ChangeStreamError as exc:
            raise _watch_error(exc) from exc

    async def watches_resume(watch_id: str, request: Request) -> dict[str, Any]:
        _watch_require_write(request)
        payload = await _watch_body(request)
        try:
            return watch_service.resume(watch_id, tenant_id=_watch_tenant(payload))
        except _ChangeStreamError as exc:
            raise _watch_error(exc) from exc

    async def watches_test_event(watch_id: str, request: Request) -> dict[str, Any]:
        _watch_require_write(request)
        payload = await _watch_body(request)
        extra = {
            k: v for k, v in payload.items()
            if k not in {"profile", "profile_id", "action", "object_ref"}
        }
        try:
            return watch_service.test_event(
                watch_id,
                tenant_id=_watch_tenant(payload),
                action=str(payload.get("action", "created")),
                object_ref=str(payload.get("object_ref", "test")),
                **extra,
            )
        except _ChangeStreamError as exc:
            raise _watch_error(exc) from exc

    def watches_delete(watch_id: str, request: Request, profile: str = "default") -> dict[str, Any]:
        _watch_require_write(request)
        try:
            return watch_service.delete(watch_id, tenant_id=str(profile or "default"))
        except _ChangeStreamError as exc:
            raise _watch_error(exc) from exc

    # Register on the canonical ``/v1`` (Traefik stripprefix=/api), the resolved
    # service base path, and the legacy base path so the surface is reachable both
    # edge-routed and direct.
    _watch_bases = {"/v1", api_base_path, LEGACY_API_BASE_PATH}
    for _wb in _watch_bases:
        _hidden = _wb != "/v1"
        app.post(f"{_wb}/watches", tags=["watches"], include_in_schema=not _hidden)(watches_create)
        app.get(f"{_wb}/watches", tags=["watches"], include_in_schema=not _hidden)(watches_list)
        app.get(f"{_wb}/watches/{{watch_id}}", tags=["watches"], include_in_schema=not _hidden)(watches_get)
        app.get(f"{_wb}/watches/{{watch_id}}/status", tags=["watches"], include_in_schema=not _hidden)(watches_status)
        app.get(f"{_wb}/watches/{{watch_id}}/events", tags=["watches"], include_in_schema=not _hidden)(watches_events)
        app.post(f"{_wb}/watches/{{watch_id}}/ack", tags=["watches"], include_in_schema=not _hidden)(watches_ack)
        app.post(f"{_wb}/watches/{{watch_id}}/recover", tags=["watches"], include_in_schema=not _hidden)(watches_recover)
        app.post(f"{_wb}/watches/{{watch_id}}/pause", tags=["watches"], include_in_schema=not _hidden)(watches_pause)
        app.post(f"{_wb}/watches/{{watch_id}}/resume", tags=["watches"], include_in_schema=not _hidden)(watches_resume)
        app.post(f"{_wb}/watches/{{watch_id}}/test-event", tags=["watches"], include_in_schema=not _hidden)(watches_test_event)
        app.delete(f"{_wb}/watches/{{watch_id}}", tags=["watches"], include_in_schema=not _hidden)(watches_delete)

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
    app.state.watch_service = watch_service
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
    # W28E-1863 fix-wave-e: mount the router FIRST and keep the optional engine
    # setter import/call fully independent. ``set_idam_v1_engine`` does NOT exist
    # in the pinned/deployed cloud_dog_idam (0.5.3); importing it in the SAME
    # statement as ``idam_v1_router`` raised ImportError, which the outer
    # ``except Exception: pass`` swallowed BEFORE the mount ran — so BOTH the
    # rbac-bindings AND resource-registry routes were never mounted (RBAC page
    # showed two "Not Found" banners). Mounting the router is not conditional on
    # the engine setter being present.
    try:
        from cloud_dog_idam.api.fastapi.router import (
            idam_v1_router as _idam_v1_router,
        )

        app.include_router(_idam_v1_router, include_in_schema=False)
        if api_base_path:
            app.include_router(_idam_v1_router, prefix=api_base_path, include_in_schema=False)
        # Best-effort engine injection — optional across idam versions; a missing
        # symbol or a raising call MUST NOT unmount the router above.
        try:
            from cloud_dog_idam.api.fastapi.router import (
                set_idam_v1_engine as _set_idam_v1_engine,
            )

            try:
                _set_idam_v1_engine(getattr(auth_runtime, "engine", None))
            except Exception:
                pass
        except Exception:
            pass
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
