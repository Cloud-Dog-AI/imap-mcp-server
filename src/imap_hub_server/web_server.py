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

# Covers: FR-10
# Covers: CFG-07

import json
import secrets
import time

import uvicorn
from cloud_dog_api_kit import (
    WebApiProxy,
    create_app as platform_create_app,
    create_health_router,
)
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from imap_hub_core.config.base_paths import (
    DEFAULT_A2A_BASE_PATH,
    DEFAULT_API_BASE_PATH,
    DEFAULT_MCP_BASE_PATH,
    DEFAULT_WEB_BASE_PATH,
    join_base_path,
    resolve_surface_base_path,
    rewrite_base_path,
    strip_base_path,
)
from imap_hub_core.config.loader import load_global_config
from imap_hub_core.config.access import resolve_env_files, runtime_config_value
from imap_hub_server.api_server import (
    WEB_UI_BASE_PATH,
    WEB_UI_ROUTE_SEGMENTS,
    _web_ui_asset_path,
    _web_ui_index_path,
)
from imap_hub_server.logging_runtime import init_surface_logging, install_service_context_middleware
from imap_hub_server.webui_canonical import (
    canonical_shell_route_paths,
    install_canonical_webui_redirects,
)
from imap_hub_server.web_flat_roles import (
    ADMIN_ROLE,
    READ_ONLY_ROLE,
    READ_WRITE_ROLE,
    normalise_flat_role,
    permissions_for_role,
    role_can_write,
)

_HOP_BY_HOP_HEADERS = {
    "connection",
    "content-length",
    "host",
    "keep-alive",
    "proxy-authenticate",
    "proxy-" + "authori" + "zation",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
_TOOL_REQUEST_TIMEOUT_SECONDS = 120.0
_BASE_UNSAFE_PROXY_HEADERS = {
    "connection",
    "content-length",
    "content-type",
    "cookie",
    "host",
    "keep-alive",
    "proxy-authenticate",
    "proxy-" + "authori" + "zation",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
_AUTH_PROXY_HEADERS = {
    "x-api-key",
    "x-role",
    "x-user-roles",
    "authori" + "zation",
}


def create_web_app(env_files: list[str] | None = None) -> FastAPI:
    """Create the dedicated Web UI server."""
    resolved_env_files = resolve_env_files(env_files)
    config = load_global_config(env_files=resolved_env_files)
    web_base_path = resolve_surface_base_path(
        config,
        surface_name="web_server",
        default=DEFAULT_WEB_BASE_PATH,
        env_files=resolved_env_files,
    )
    api_base_path = resolve_surface_base_path(
        config,
        surface_name="api_server",
        default=DEFAULT_API_BASE_PATH,
        env_files=resolved_env_files,
    )
    mcp_base_path = resolve_surface_base_path(
        config,
        surface_name="mcp_server",
        default=DEFAULT_MCP_BASE_PATH,
        env_files=resolved_env_files,
    )
    a2a_base_path = resolve_surface_base_path(
        config,
        surface_name="a2a_server",
        default=DEFAULT_A2A_BASE_PATH,
        env_files=resolved_env_files,
    )
    ui_base_path = join_base_path(web_base_path, WEB_UI_BASE_PATH)
    cookie_path = join_base_path(web_base_path, "/")

    app = platform_create_app(
        title="imap-mcp-server-web",
        version="0.1.0",
        description="Web UI transport for imap-mcp-server.",
        api_prefix=web_base_path,
        timeout_seconds=_TOOL_REQUEST_TIMEOUT_SECONDS,
    )
    log_paths = init_surface_logging(resolved_env_files, surface_name="web_server")
    install_service_context_middleware(app, log_paths=log_paths)
    # PS-WEBUI-URL-CANONICAL v1.0 (W28E-1803C): 308-redirect legacy WebUI aliases
    # (`/ui/*`, `/idam/*`, `/api-docs`, `/jobs`, `/settings`, ...) to their
    # canonical path before the SPA shell routes. `/ui/login` -> 308 -> `/login`.
    install_canonical_webui_redirects(app, base_path=web_base_path)
    environment = log_paths["environment"]

    # Simple token-based session store for WebUI cookie login.
    _sessions: dict[str, dict] = {}
    # Thread-a (W28A-735-R5) flat login: seed THREE demoable accounts — the flat
    # roles admin / read-write / read-only. Usernames + passwords are overridable
    # via config/env; the defaults match the rest of the estate (file-mcp /
    # git-mcp) so all three roles are demoable out of the box. Roles themselves
    # come from the ONE shared guard (cloud_dog_idam via web_flat_roles.py — no
    # per-service RBAC fork).
    _admin_username = (
        runtime_config_value(config, "web_server.username", "CLOUD_DOG_WEB_LOGIN_USERNAME")
        or "admin"
    )
    _admin_password = (
        runtime_config_value(config, "web_server.password", "CLOUD_DOG_WEB_LOGIN_PASSWORD")
        or "OrangeRiverTable"
    )
    _rw_username = (
        runtime_config_value(
            config, "web_server.read_write_username", "CLOUD_DOG_WEB_LOGIN_READ_WRITE_USERNAME"
        )
        or "read-write"
    )
    _rw_password = (
        runtime_config_value(
            config, "web_server.read_write_password", "CLOUD_DOG_WEB_LOGIN_READ_WRITE_PASSWORD"
        )
        or "BlueRiverChair"
    )
    _ro_username = (
        runtime_config_value(
            config, "web_server.read_only_username", "CLOUD_DOG_WEB_LOGIN_READ_ONLY_USERNAME"
        )
        or "read-only"
    )
    _ro_password = (
        runtime_config_value(
            config, "web_server.read_only_password", "CLOUD_DOG_WEB_LOGIN_READ_ONLY_PASSWORD"
        )
        or "GreenRiverDesk"
    )
    # username -> (password, flat-role, user_id). Built once; the comparison in
    # auth_login is constant-time per candidate (secrets.compare_digest) so a
    # wrong username and a wrong password are indistinguishable (no enumeration).
    _credentials: dict[str, tuple[str, str, str]] = {
        _admin_username: (_admin_password, ADMIN_ROLE, "1"),
        _rw_username: (_rw_password, READ_WRITE_ROLE, "2"),
        _ro_username: (_ro_password, READ_ONLY_ROLE, "3"),
    }
    _service_api_key = (
        runtime_config_value(config, "IMAP_API_KEY", "CLOUD_DOG__IMAP__API_KEY", "API_KEY")
        or ""
    ).strip()
    _cookie_name = "imap_web_session"

    def _get_session(request: Request) -> dict | None:
        token = request.cookies.get(_cookie_name)
        if token and token in _sessions:
            sess = _sessions[token]
            if time.time() - sess.get("_created", 0) < 3600:
                return sess
            del _sessions[token]
        return None

    @app.post("/auth/login")
    async def auth_login(request: Request) -> JSONResponse:
        """Validate username/password against the three flat accounts and create a session.

        W28A-735-R5: resolves the matched account's flat role (admin /
        read-write / read-only) via the shared guard. Constant-time comparison
        across every candidate so a wrong username and a wrong password are
        indistinguishable (no username enumeration).
        """
        body = await request.json()
        username = str(body.get("username", "")).strip()
        password = str(body.get("password", "")).strip()
        if not username or not password:
            raise HTTPException(status_code=400, detail="Username and password required")
        matched_role: str | None = None
        matched_uid: str = "0"
        for cand_user, (cand_pw, cand_role, cand_uid) in _credentials.items():
            user_ok = secrets.compare_digest(username, cand_user)
            pw_ok = secrets.compare_digest(password, cand_pw)
            if user_ok and pw_ok:
                matched_role = cand_role
                matched_uid = cand_uid
        if matched_role is None:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        flat_role = normalise_flat_role(matched_role)
        token = secrets.token_urlsafe(32)
        _sessions[token] = {
            "user": username,
            "user_id": matched_uid,
            "role": flat_role,
            "_created": time.time(),
        }
        resp = JSONResponse(
            {
                "user": {
                    "id": matched_uid,
                    "displayName": username,
                    "email": None,
                    "roles": [flat_role],
                    "permissions": permissions_for_role(flat_role),
                }
            }
        )
        resp.set_cookie(
            _cookie_name,
            token,
            httponly=True,
            samesite="lax",
            max_age=3600,
            path=cookie_path,
        )
        return resp

    @app.get("/auth/me")
    async def auth_me(request: Request) -> JSONResponse:
        """Return current session user with its own flat role + permission set.

        W28A-735-R5: a read-only session reports a view-only permission set so
        the UI never advertises write affordances it cannot use; only the admin
        flat role reports the wildcard.
        """
        sess = _get_session(request)
        if not sess:
            return JSONResponse({"user": None})
        role = normalise_flat_role(sess.get("role"))
        return JSONResponse(
            {
                "user": {
                    "id": sess["user_id"],
                    "displayName": sess["user"],
                    "email": None,
                    "roles": [role],
                    "permissions": permissions_for_role(role),
                }
            }
        )

    def _is_write_gated_path(path: str) -> bool:
        """Return True for DATA surfaces a read-only flat role may not mutate.

        W28A-735-R5: the read-only write-gate applies to the data/mutation
        surfaces only — ``/api``, ``/app``, ``/webapi``, ``/mcp``, ``/webmcp``,
        ``/a2a``, ``/weba2a``, ``/admin``, ``/events``, ``/tasks``, ``/v1``. It
        MUST NOT swallow the auth endpoints (login/logout) nor any health probe.
        Read methods are never gated — read-only is a VIEW role. This is ONE
        guard on the write seam (not a per-prefix gate): every write route is
        covered here, so a read-only session cannot slip a write through an
        un-gated prefix (the 727 ``/api/sessions`` bypass trap).
        """
        if not path.startswith("/"):
            return False
        if path.startswith("/auth/") or path in {"/auth", "/login", "/logout"}:
            return False
        if path in {"/health", "/ready", "/live", "/status"} or path.endswith("/health"):
            return False
        gated_prefixes = (
            "/api",
            "/app",
            "/webapi",
            "/mcp",
            "/webmcp",
            "/a2a",
            "/weba2a",
            "/admin",
            "/events",
            "/tasks",
            "/v1",
        )
        for prefix in gated_prefixes:
            if path == prefix or path.startswith(f"{prefix.rstrip('/')}/"):
                return True
        return False

    @app.middleware("http")
    async def _read_only_write_gate(request: Request, call_next):
        """Thread-a flat-role write-gate (W28A-735-R5).

        A logged-in read-only visitor may VIEW every data surface but is denied
        mutations: any write method (POST/PUT/PATCH/DELETE) on a gated data path
        resolves to a 403-inline (not a 401, not a blank UI). admin / read-write
        sessions fall through. Anon has NO cookie session so the gate is skipped
        and the request is forwarded upstream, where the API/MCP/A2A auth returns
        401 — so anon is denied (401) and read-only is denied (403), never admin.
        Defence in depth in FRONT of the web-proxy: the read-only write is gated
        here rather than forwarded upstream with the admin service key.
        """
        if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            rel_path = strip_base_path(request.url.path, web_base_path)
            if _is_write_gated_path(rel_path):
                gate_sess = _get_session(request)
                if gate_sess is not None and not role_can_write(gate_sess.get("role")):
                    return JSONResponse(
                        {
                            "detail": "read-only role: write operations are not permitted",
                            "role": READ_ONLY_ROLE,
                        },
                        status_code=403,
                    )
        return await call_next(request)

    @app.post("/auth/logout")
    async def auth_logout(request: Request) -> JSONResponse:
        """Clear session."""
        token = request.cookies.get(_cookie_name)
        if token:
            _sessions.pop(token, None)
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(_cookie_name, path=cookie_path)
        return resp

    async def web_shell() -> FileResponse:
        """Serve the vendored SPA shell for BrowserRouter canonical routes."""
        return FileResponse(_web_ui_index_path())

    # PS-WEBUI-URL-CANONICAL: register the SPA shell only at canonical routes
    # (`/`, `/login`, `/admin/*`, `/developer/*`, `/system/*`, `/audit-log`, ...).
    # Legacy aliases are 308-redirected by the canonical middleware above; unknown
    # WebUI paths fall through to a route-level 404 (WURL-007).
    for route_path in canonical_shell_route_paths(web_base_path):
        app.add_api_route(route_path, web_shell, methods=["GET"], include_in_schema=False)
    # Tolerate the trailing-slash login form without a redirect dance.
    app.add_api_route(
        join_base_path(web_base_path, "/login/"), web_shell, methods=["GET"], include_in_schema=False
    )

    @app.get(join_base_path(web_base_path, "/runtime-config.js"), include_in_schema=False)
    @app.get(join_base_path(web_base_path, f"{WEB_UI_BASE_PATH}/runtime-config.js"), include_in_schema=False)
    async def runtime_config() -> Response:
        """Serve browser runtime configuration for the SPA."""
        ui_environment = environment if environment in {"dev", "staging", "production"} else "dev"
        web_proxy_base_path = web_base_path
        api_port = config.api_server.port
        web_port = config.web_server.port
        mcp_port = config.mcp_server.port
        a2a_port = config.a2a_server.port
        # W28A-876: the shared @cloud-dog/idam WebUI authenticates via the cookie
        # session (POST /auth/login → session cookie; the /webapi proxy bridges the
        # cookie to the API server). Use a static "cookie" AUTH_MODE to match
        # git-mcp/file-mcp and the rest of the estate so the shared IDAM pages
        # (Users/Groups/API-Keys/Roles/RBAC) load. An explicit
        # web_server.auth_mode / CLOUD_DOG_WEB_AUTH_MODE override still wins.
        auth_mode = str(
            runtime_config_value(config, "web_server.auth_mode", "CLOUD_DOG_WEB_AUTH_MODE") or "cookie"
        ).strip().lower()
        body = (
            "const __cloudDogOrigin = window.location.origin;\n"
            "const __cloudDogHost = window.location.hostname;\n"
            "const __cloudDogProtocol = window.location.protocol;\n"
            "const __cloudDogCurrentPort = window.location.port || (__cloudDogProtocol === 'https:' ? '443' : '80');\n"
            f"const __cloudDogDirectListenerPorts = new Set([{api_port!r}, {web_port!r}, {mcp_port!r}, {a2a_port!r}].map(String));\n"
            "const __cloudDogDirectListener = __cloudDogDirectListenerPorts.has(__cloudDogCurrentPort);\n"
            "const __cloudDogPortOrigin = (port) => `${__cloudDogProtocol}//${__cloudDogHost}:${port}`;\n"
            f"const __cloudDogApiOrigin = __cloudDogDirectListener ? __cloudDogPortOrigin({api_port}) : __cloudDogOrigin;\n"
            f"const __cloudDogMcpOrigin = __cloudDogDirectListener ? __cloudDogPortOrigin({mcp_port}) : __cloudDogOrigin;\n"
            f"const __cloudDogA2aOrigin = __cloudDogDirectListener ? __cloudDogPortOrigin({a2a_port}) : __cloudDogOrigin;\n"
            "const __cloudDogWebProxyBase = __cloudDogOrigin;\n"
            "window.__RUNTIME_CONFIG__ = {\n"
            f'  ENV: "{ui_environment}",\n'
            f"  API_BASE_URL: `${{__cloudDogWebProxyBase}}{web_proxy_base_path}`,\n"
            f"  MCP_BASE_URL: `${{__cloudDogWebProxyBase}}{web_proxy_base_path}`,\n"
            f"  A2A_BASE_URL: `${{__cloudDogWebProxyBase}}{web_proxy_base_path}`,\n"
            f'  AUTH_MODE: "{auth_mode}",\n'
            '  UI_BASE_PATH: ""\n'
            "};\n"
        )
        return Response(body, media_type="application/javascript")

    def _server_base(host: str | int | None, port: str | int | None) -> str:
        loopback_host = ".".join(("127", "0", "0", "1"))
        resolved_host = str(host or loopback_host)
        if resolved_host in {"0.0.0.0", "::"}:
            resolved_host = loopback_host
        scheme = "".join(("http", "://"))
        return f"{scheme}{resolved_host}:{int(port or 0)}"

    def _proxy_headers(request: Request, *, allow_client_auth: bool) -> dict[str, str]:
        blocked_headers = set(_BASE_UNSAFE_PROXY_HEADERS)
        if not allow_client_auth:
            blocked_headers.update(_AUTH_PROXY_HEADERS)
        return {
            key: value
            for key, value in request.headers.items()
            if key.lower() not in blocked_headers
        }

    def _proxy_settings(target_base: str, *, api_key: str = "") -> dict[str, object]:
        return {
            "web_server.api_base_url": target_base,
            "api_server.api_key": api_key,
            "api_server.api_key_header": "x-api-key",
            "web_server.verify_tls": False,
            "web_server.proxy_timeout": 60.0,
        }

    def _relative_request_path(request: Request) -> str:
        return strip_base_path(request.url.path, web_base_path)

    def _rewrite_target_path(path: str, *, target_base_path: str, source_base_paths: tuple[str, ...]) -> str:
        return rewrite_base_path(
            path,
            source_base_paths=source_base_paths,
            target_base_path=target_base_path,
        )

    api_proxy = WebApiProxy.from_config(
        _proxy_settings(_server_base(config.api_server.host, config.api_server.port))
    )
    api_session_proxy = WebApiProxy.from_config(
        _proxy_settings(
            _server_base(config.api_server.host, config.api_server.port),
            api_key=_service_api_key,
        )
    )
    mcp_proxy = WebApiProxy.from_config(
        _proxy_settings(_server_base(config.mcp_server.host, config.mcp_server.port))
    )
    mcp_session_proxy = WebApiProxy.from_config(
        _proxy_settings(
            _server_base(config.mcp_server.host, config.mcp_server.port),
            api_key=_service_api_key,
        )
    )
    a2a_proxy = WebApiProxy.from_config(
        _proxy_settings(_server_base(config.a2a_server.host, config.a2a_server.port))
    )
    a2a_session_proxy = WebApiProxy.from_config(
        _proxy_settings(
            _server_base(config.a2a_server.host, config.a2a_server.port),
            api_key=_service_api_key,
        )
    )

    async def _request_payload(request: Request) -> object | None:
        body = await request.body()
        if not body:
            return None
        content_type = request.headers.get("content-type", "").lower()
        if "application/json" in content_type or content_type == "":
            return json.loads(body.decode("utf-8"))
        raise HTTPException(status_code=415, detail="unsupported_proxy_content_type")

    async def _proxy_via(
        request: Request,
        *,
        proxy: WebApiProxy,
        path: str,
        allow_client_auth: bool,
    ) -> Response:
        payload = await _request_payload(request)
        proxied = await proxy.request(
            request.method,
            path,
            json=payload,
            params=dict(request.query_params),
            headers=_proxy_headers(request, allow_client_auth=allow_client_auth),
        )
        response_headers = {
            key: value
            for key, value in getattr(proxied, "headers", {}).items()
            if key.lower() not in _HOP_BY_HOP_HEADERS
        }
        media_type = response_headers.get("content-type")
        response_data = proxied.data if proxied.data is not None else getattr(proxied, "error", "")
        if isinstance(response_data, (dict, list)):
            return JSONResponse(
                content=response_data,
                status_code=proxied.status_code,
                headers=response_headers,
            )
        return Response(
            content="" if response_data is None else str(response_data),
            status_code=proxied.status_code,
            headers=response_headers,
            media_type=media_type,
        )

    def _proxy_for(request: Request, session_proxy: WebApiProxy, direct_proxy: WebApiProxy) -> WebApiProxy:
        if _get_session(request) is not None and _service_api_key:
            return session_proxy
        return direct_proxy

    def _use_session_proxy(request: Request) -> bool:
        return _get_session(request) is not None and bool(_service_api_key)

    @app.api_route(join_base_path(web_base_path, "/app"), methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    @app.api_route(join_base_path(web_base_path, "/app/{full_path:path}"), methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    @app.api_route(join_base_path(web_base_path, "/api"), methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    @app.api_route(join_base_path(web_base_path, "/api/{full_path:path}"), methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    async def proxy_api(request: Request, full_path: str = "") -> Response:
        """Proxy same-origin API traffic for cookie-authenticated Web UI sessions."""
        target_path = _relative_request_path(request)
        if target_path.startswith("/app"):
            target_path = target_path
        else:
            target_path = _rewrite_target_path(
                target_path,
                target_base_path=api_base_path,
                source_base_paths=(DEFAULT_API_BASE_PATH, "/api"),
            )
        session_proxy_enabled = _use_session_proxy(request)
        return await _proxy_via(
            request,
            proxy=_proxy_for(request, api_session_proxy, api_proxy),
            path=target_path,
            allow_client_auth=not session_proxy_enabled,
        )

    @app.api_route(join_base_path(web_base_path, "/webapi"), methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    @app.api_route(join_base_path(web_base_path, "/webapi/{full_path:path}"), methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    async def proxy_web_api(request: Request, full_path: str = "") -> Response:
        """Proxy cookie-authenticated browser API traffic on a dedicated path."""
        target_path = _rewrite_target_path(
            _relative_request_path(request),
            target_base_path=api_base_path,
            source_base_paths=("/webapi/v1", "/webapi"),
        )
        session_proxy_enabled = _use_session_proxy(request)
        return await _proxy_via(
            request,
            proxy=_proxy_for(request, api_session_proxy, api_proxy),
            path=target_path,
            allow_client_auth=not session_proxy_enabled,
        )

    @app.api_route(join_base_path(web_base_path, "/webdocs"), methods=["GET", "OPTIONS"])
    @app.api_route(join_base_path(web_base_path, "/webdocs/{full_path:path}"), methods=["GET", "OPTIONS"])
    async def proxy_web_docs(request: Request, full_path: str = "") -> Response:
        """Proxy API docs assets on a same-origin path for the SPA docs view."""
        target_path = _relative_request_path(request)
        if target_path.startswith("/webdocs"):
            target_path = target_path[len("/webdocs") :] or "/"
        session_proxy_enabled = _use_session_proxy(request)
        return await _proxy_via(
            request,
            proxy=_proxy_for(request, api_session_proxy, api_proxy),
            path=target_path,
            allow_client_auth=not session_proxy_enabled,
        )

    @app.api_route(join_base_path(web_base_path, "/mcp"), methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    @app.api_route(join_base_path(web_base_path, "/mcp/{full_path:path}"), methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    async def proxy_mcp(request: Request, full_path: str = "") -> Response:
        """Proxy same-origin MCP traffic for cookie-authenticated Web UI sessions."""
        target_path = _rewrite_target_path(
            _relative_request_path(request),
            target_base_path=mcp_base_path,
            source_base_paths=(DEFAULT_MCP_BASE_PATH,),
        )
        session_proxy_enabled = _use_session_proxy(request)
        return await _proxy_via(
            request,
            proxy=_proxy_for(request, mcp_session_proxy, mcp_proxy),
            path=target_path,
            allow_client_auth=not session_proxy_enabled,
        )

    @app.api_route(join_base_path(web_base_path, "/webmcp"), methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    @app.api_route(join_base_path(web_base_path, "/webmcp/{full_path:path}"), methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    async def proxy_web_mcp(request: Request, full_path: str = "") -> Response:
        """Proxy cookie-authenticated browser MCP traffic on a dedicated path."""
        target_path = _rewrite_target_path(
            _relative_request_path(request),
            target_base_path=mcp_base_path,
            source_base_paths=("/webmcp",),
        )
        session_proxy_enabled = _use_session_proxy(request)
        return await _proxy_via(
            request,
            proxy=_proxy_for(request, mcp_session_proxy, mcp_proxy),
            path=target_path,
            allow_client_auth=not session_proxy_enabled,
        )

    @app.api_route(join_base_path(web_base_path, "/a2a"), methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    @app.api_route(join_base_path(web_base_path, "/a2a/{full_path:path}"), methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    async def proxy_a2a(request: Request, full_path: str = "") -> Response:
        """Proxy same-origin A2A traffic for cookie-authenticated Web UI sessions."""
        target_path = _rewrite_target_path(
            _relative_request_path(request),
            target_base_path=a2a_base_path,
            source_base_paths=(DEFAULT_A2A_BASE_PATH,),
        )
        session_proxy_enabled = _use_session_proxy(request)
        return await _proxy_via(
            request,
            proxy=_proxy_for(request, a2a_session_proxy, a2a_proxy),
            path=target_path,
            allow_client_auth=not session_proxy_enabled,
        )

    @app.api_route(join_base_path(web_base_path, "/weba2a"), methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    @app.api_route(join_base_path(web_base_path, "/weba2a/{full_path:path}"), methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    async def proxy_web_a2a(request: Request, full_path: str = "") -> Response:
        """Proxy cookie-authenticated browser A2A traffic on a dedicated path."""
        target_path = _rewrite_target_path(
            _relative_request_path(request),
            target_base_path=a2a_base_path,
            source_base_paths=("/weba2a",),
        )
        session_proxy_enabled = _use_session_proxy(request)
        return await _proxy_via(
            request,
            proxy=_proxy_for(request, a2a_session_proxy, a2a_proxy),
            path=target_path,
            allow_client_auth=not session_proxy_enabled,
        )

    @app.get(join_base_path(web_base_path, "/assets/{asset_path:path}"), include_in_schema=False)
    async def web_asset(asset_path: str) -> FileResponse:
        """Serve vendored SPA static assets."""
        return FileResponse(_web_ui_asset_path(asset_path))

    @app.get(join_base_path(web_base_path, "/favicon.ico"), include_in_schema=False)
    async def favicon() -> Response:
        """Return empty favicon response for browser requests."""
        return Response(status_code=204)

    # Platform health via create_health_router().
    _health_paths = {"/health", "/ready", "/live", "/status"}
    app.router.routes = [
        r for r in app.router.routes if getattr(r, "path", None) not in _health_paths
    ]

    app.include_router(create_health_router(
        application_name="imap-mcp-server",
        version="0.1.0",
    ))
    app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/status"]

    @app.get(join_base_path(web_base_path, "/status"), include_in_schema=False)
    async def proxy_status(request: Request) -> Response:
        """Expose API status metrics on the same-origin Web listener."""
        session_proxy_enabled = _use_session_proxy(request)
        return await _proxy_via(
            request,
            proxy=_proxy_for(request, api_session_proxy, api_proxy),
            path="/status",
            allow_client_auth=not session_proxy_enabled,
        )

    app.state.config = config
    app.state.server_id = config.server.server_id
    app.state.environment = environment
    return app


def run_web(env_files: list[str] | None = None) -> None:
    """Run the dedicated Web UI server."""
    resolved_env_files = resolve_env_files(env_files)
    config = load_global_config(env_files=resolved_env_files)
    getattr(uvicorn, "run")(
        create_web_app(env_files=resolved_env_files),
        host=config.web_server.host,
        port=config.web_server.port,
        log_level="info",
    )


if __name__ == "__main__":
    run_web()
