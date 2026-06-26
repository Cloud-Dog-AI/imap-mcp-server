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
# Covers: CFG-06

import json
from typing import Any, cast

import uvicorn
from cloud_dog_api_kit import create_app as platform_create_app, create_health_router
from cloud_dog_api_kit.a2a.card import create_a2a_card_router, A2ASkill
from cloud_dog_api_kit.a2a.events import create_a2a_events_router
from fastapi import FastAPI, HTTPException, Request, WebSocket
from starlette.websockets import WebSocketDisconnect

from imap_hub_core.audit.context import (
    reset_audit_request_context,
    set_audit_request_context,
)
from imap_hub_core.audit.logger import AuditWriter
from imap_hub_core.config.base_paths import (
    DEFAULT_A2A_BASE_PATH,
    join_base_path,
    resolve_surface_base_path,
)
from imap_hub_core.config.loader import load_global_config
from imap_hub_core.config.access import resolve_env_files, runtime_config_value
from imap_hub_core.tools.handlers import build_default_tool_registry
from imap_hub_server.rbac_seam import ImapResourceGuard
from imap_hub_server.a2a_events_broadcaster import _ImapMcpServiceBackedBroadcaster
from imap_hub_server.admin.state import FileBackedAdminState
from imap_hub_server.api_server import (
    _audit_context,
    _install_browser_cors,
    _json_safe,
    _websocket_api_key_valid,
    envelope,
)
from imap_hub_server.auth.middleware import (
    build_auth_runtime,
    install_auth_middleware,
    register_static_api_key,
    request_api_key_record,
)
from imap_hub_server.logging_runtime import init_surface_logging, install_service_context_middleware

_TOOL_REQUEST_TIMEOUT_SECONDS = 120.0


def create_a2a_app(env_files: list[str] | None = None) -> FastAPI:
    """Create the dedicated A2A server."""
    resolved_env_files = resolve_env_files(env_files)
    config = load_global_config(env_files=resolved_env_files)
    a2a_base_path = resolve_surface_base_path(
        config,
        surface_name="a2a_server",
        default=DEFAULT_A2A_BASE_PATH,
        env_files=resolved_env_files,
    )
    log_paths = init_surface_logging(resolved_env_files, surface_name="a2a_server")
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
    a2a_test_api_key = runtime_config_value(config, "TEST_A2A_API_KEY")
    if a2a_test_api_key:
        register_static_api_key(
            auth_runtime.api_key_manager, a2a_test_api_key, owner_id="a2a-test-user"
        )
        admin_state.bootstrap_admin_user("a2a-test-user")
    admin_state.sync_api_key_manager(auth_runtime.api_key_manager)
    admin_state.sync_rbac_engine(auth_runtime.rbac_engine)

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

    app = cast(
        FastAPI,
        platform_create_app(
            title="imap-mcp-server-a2a",
            version="0.1.0",
            description="A2A transport for IMAP tools.",
            api_prefix=a2a_base_path,
            timeout_seconds=_TOOL_REQUEST_TIMEOUT_SECONDS,
        ),
    )

    install_auth_middleware(
        app,
        auth_runtime=auth_runtime,
        auth_mode=config.server.auth.mode,
        public_paths={
            join_base_path(a2a_base_path, "/"),
            "/.well-known/agent.json",
            "/tasks",
            join_base_path(a2a_base_path, "/tasks"),
            join_base_path(a2a_base_path, "/health"),
        },
        # Let tool endpoints handle their own auth after syncing the
        # key manager from admin_state — the middleware's key manager
        # may not have dynamically-created user keys yet.
        public_path_prefixes={
            join_base_path(a2a_base_path, "/tools"),
            join_base_path(a2a_base_path, "/events"),
        },
    )
    _install_browser_cors(app, web_port=config.web_server.port)
    install_service_context_middleware(app, log_paths=log_paths)

    @app.get(join_base_path(a2a_base_path, "/"), include_in_schema=False)
    async def a2a_descriptor() -> dict[str, Any]:
        """Return the A2A interface descriptor."""
        return {
            "ok": True,
            "result": {
                "service": "imap-mcp-server",
                "interface": "a2a",
                "tools_path": join_base_path(a2a_base_path, "/tools"),
                "events_path": join_base_path(a2a_base_path, "/events"),
            },
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    # Platform health via create_health_router().
    _health_paths = {"/health", "/ready", "/live", "/status"}
    app.router.routes = [
        r for r in app.router.routes if getattr(r, "path", None) not in _health_paths
    ]
    app.include_router(create_health_router(
        application_name="imap-mcp-server",
        version="0.1.0",
    ))

    @app.get(join_base_path(a2a_base_path, "/health"), include_in_schema=False)
    async def a2a_health_alias(request: Request) -> dict[str, Any]:
        """A2A transport-scoped health — authenticated per FR-04 / PS-82 FR1.46.

        W28A-750 (imap analog of file-mcp F-741-1): ``GET /a2a/health`` SHALL enforce
        authentication with the same API-key authority as the rest of the A2A surface
        — anon / wrong key -> 401; a valid key (strict-local ``Bearer 12345678``) -> 200.
        The container/Traefik liveness probe uses the PUBLIC root ``/health`` (unchanged),
        so gating this transport-scoped alias does not affect orchestration health.
        """
        admin_state.sync_api_key_manager(auth_runtime.api_key_manager)
        if request_api_key_record(request, auth_runtime.api_key_manager) is None:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return {
            "ok": True,
            "result": {
                "interface": "a2a",
                "status": "ok",
                "application": "imap-mcp-server",
                "version": "0.1.0",
                "env_file": None,
            },
            "warnings": [],
            "errors": [],
            "meta": {},
        }

    @app.get(join_base_path(a2a_base_path, "/tools"), tags=["a2a"])
    async def a2a_list_tools(request: Request) -> dict[str, Any]:
        """List available tools over the A2A interface."""
        admin_state.sync_api_key_manager(auth_runtime.api_key_manager)
        api_record = request_api_key_record(request, auth_runtime.api_key_manager)
        if api_record is None:
            raise HTTPException(status_code=401, detail="Invalid API key")
        # Reject disabled users.
        user = admin_state.get_user(api_record.owner_user_id)
        if user is not None and str(getattr(user, "status", "")).strip().lower() == "disabled":
            raise HTTPException(status_code=403, detail="User account is disabled")
        return envelope(result={"items": _json_safe(tool_registry.list_tools())}, request=request)

    @app.post(join_base_path(a2a_base_path, "/tools/{tool_name}"), tags=["a2a"])
    async def a2a_call_tool(
        tool_name: str, payload: dict[str, Any], request: Request
    ) -> dict[str, Any]:
        """Execute a named tool over the A2A interface.

        Any valid API key (not just admin) may call A2A tools.  The
        handler is invoked directly so that registry-level RBAC role
        patterns do not gate A2A access — the API-key check above is
        the sole authorisation gate.
        """
        admin_state.sync_api_key_manager(auth_runtime.api_key_manager)
        api_record = request_api_key_record(request, auth_runtime.api_key_manager)
        if api_record is None:
            raise HTTPException(status_code=401, detail="Unauthorized")
        # Reject disabled users.
        user = admin_state.get_user(api_record.owner_user_id)
        if user is not None and str(getattr(user, "status", "")).strip().lower() == "disabled":
            raise HTTPException(status_code=403, detail="User account is disabled")
        try:
            actor_id = str(api_record.owner_user_id or api_record.api_key_id).strip() or "a2a-client"
            roles: set[str] = set()
            if user is not None:
                role = str(getattr(user, "role", "")).strip().lower()
                if role:
                    roles.add(role)
                for group in admin_state.groups_for_user(user.user_id):
                    roles.update(
                        str(item).strip().lower() for item in group.roles if str(item).strip()
                    )
            token = set_audit_request_context(
                _audit_context(
                    request,
                    actor_id=actor_id,
                    roles=roles,
                    source_identifier=f"api_key:{api_record.api_key_id}",
                )
            )
            # Look up the tool contract and call its handler directly,
            # bypassing ToolRegistry._authorise so that any valid API
            # key can invoke A2A tools regardless of RBAC role patterns.
            contract = tool_registry.contracts().get(tool_name)
            if contract is None:
                raise KeyError(f"tool_not_found:{tool_name}")
            result = contract.handler(payload)
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
    # Canonical SSE mounted ADDITIVELY at ``/a2a/events/sse`` via
    # ``create_a2a_events_router`` for PS-72-conforming consumers.
    broadcaster = _ImapMcpServiceBackedBroadcaster(
        store_path=admin_state.event_path,
        service="imap-mcp-server",
    )

    @app.websocket(join_base_path(a2a_base_path, "/events"))
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
        # First replay any existing JSONL content so admin-SPA clients
        # that reconnect after a restart see the unseen history.
        offset = 0
        lines, offset = admin_state.read_event_lines_from(offset)
        for line in lines:
            try:
                await websocket.send_json(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                continue
        try:
            async for payload in broadcaster.subscribe_legacy():
                await websocket.send_json(payload)
        except WebSocketDisconnect:
            return

    # Canonical PS-72 §A2A-change-events SSE surface (additive).
    app.include_router(
        create_a2a_events_router(
            broadcaster,
            base_path=join_base_path(a2a_base_path, "/events/sse"),
        )
    )

    # --- A2A skill handlers that call IMAP tool registry functions ---
    def _parse_a2a_input(text: str) -> dict[str, Any]:
        """Parse JSON input text or return a minimal dict from plain text."""
        text = text.strip()
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        return {"query": text} if text else {}

    def _handle_mail_search(text: str) -> Any:
        """Search emails via the IMAP tool registry."""
        payload = _parse_a2a_input(text)
        # Ensure required fields have defaults for a minimal search
        payload.setdefault("profile_id", "default")
        payload.setdefault("mode", "live")
        return tool_registry.call("mail_search", payload)

    def _handle_mail_get_message(text: str) -> Any:
        """Retrieve a specific email message via the IMAP tool registry."""
        payload = _parse_a2a_input(text)
        payload.setdefault("profile_id", "default")
        return tool_registry.call("mail_get_message", payload)

    def _handle_mail_probe(text: str) -> Any:
        """Probe mailbox connectivity via the IMAP tool registry."""
        payload = _parse_a2a_input(text)
        payload.setdefault("profile_id", "default")
        return tool_registry.call("mail_probe", payload)

    # A2A agent card and task submission router
    _a2a_skills = [
        A2ASkill(id="mail_search", name="Mail Search", description="Search emails across configured mailboxes", handler=_handle_mail_search),
        A2ASkill(id="mail_get_message", name="Mail Get Message", description="Retrieve a specific email message by ID", handler=_handle_mail_get_message),
        A2ASkill(id="mail_probe", name="Mail Probe", description="Probe mailbox connectivity and status", handler=_handle_mail_probe),
    ]
    _a2a_card_router = create_a2a_card_router(
        name="imap-mcp",
        description="IMAP MCP A2A server for email operations and tool execution",
        skills=_a2a_skills,
    )
    app.include_router(_a2a_card_router)
    if a2a_base_path:
        app.include_router(_a2a_card_router, prefix=a2a_base_path)

    app.state.config = config
    app.state.profile_store = profile_store
    app.state.tool_registry = tool_registry
    app.state.auth_runtime = auth_runtime
    app.state.audit_writer = audit_writer
    app.state.admin_state = admin_state
    app.state.seed_api_key = seed_api_key
    app.state.server_id = config.server.server_id
    app.state.environment = environment
    app.state.a2a_events_broadcaster = broadcaster

    # Register lifecycle hooks via the platform factory's lifespan context.
    # NOTE: @app.on_event("startup"/"shutdown") is silently ignored when a
    # lifespan context is set (which platform_create_app does).
    hooks = app.state.lifecycle_hooks
    _prev_post_router = hooks.on_post_router
    _prev_shutdown = hooks.on_shutdown

    async def _start_broadcaster(app_ref: object) -> None:
        if _prev_post_router is not None:
            await _prev_post_router(app_ref)
        broadcaster.start_watcher(rewind=True)

    async def _shutdown_runtime(app_ref: object) -> None:
        if _prev_shutdown is not None:
            await _prev_shutdown(app_ref)
        await broadcaster.stop_watcher()
        audit_writer.close()

    hooks.on_post_router = _start_broadcaster
    hooks.on_shutdown = _shutdown_runtime

    return app


def run_a2a(env_files: list[str] | None = None) -> None:
    """Run the dedicated A2A server."""
    resolved_env_files = resolve_env_files(env_files)
    config = load_global_config(env_files=resolved_env_files)
    getattr(uvicorn, "run")(
        create_a2a_app(env_files=resolved_env_files),
        host=config.a2a_server.host,
        port=config.a2a_server.port,
        log_level="info",
    )


if __name__ == "__main__":
    run_a2a()
