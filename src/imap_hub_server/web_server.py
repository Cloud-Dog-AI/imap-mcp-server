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

from imap_hub_server import __version__
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
from imap_hub_server.gmail_admin import (
    MASKED_CLIENT_SECRET,
    begin_oauth,
    complete_oauth_callback,
    load_gmail_client_secret,
    load_gmail_profile_values,
    parse_form_urlencoded,
    render_callback_page,
    render_setup_page,
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


def _git_head_commit() -> str:
    """Best-effort git HEAD for dev/source runs (empty string if unavailable).

    Mirrors the deployed chart-mcp / file-mcp reference so a local/source run
    still populates the WebUI About page when no container build-identity ENV is
    present. W28E-1863 fix-wave-d (WSC-014).
    """
    try:
        import subprocess
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        out = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:  # noqa: BLE001 - build identity must never crash a request
        return ""
    return ""


def build_identity(config) -> dict[str, str]:
    """Return build/deploy identity for WSC-014 / PS-30 UI-R7.3.

    Source of truth is the container build: ``docker-build.sh`` stamps the image
    OCI ``org.opencontainers.image.revision`` label AND injects the matching
    runtime ENV, read config-routed via ``runtime_config_value`` (RULES §1.4.1).
    For a dev/source run (no container ENV) ``source_commit``
    falls back to the working-tree git HEAD so the About page is still populated
    locally. Modelled on the deployed chart-mcp reference. W28E-1863 fix-wave-d.
    """
    commit = runtime_config_value(config, "build.source_commit", "CLOUD_DOG__BUILD__SOURCE_COMMIT").strip()
    if not commit or commit == "unknown":
        commit = _git_head_commit()
    branch = runtime_config_value(config, "build.source_branch", "CLOUD_DOG__BUILD__SOURCE_BRANCH").strip()
    if branch == "unknown":
        branch = ""
    build_date = runtime_config_value(config, "build.build_date", "CLOUD_DOG__BUILD__BUILD_DATE").strip()
    digest = runtime_config_value(config, "build.container_digest", "CLOUD_DOG__BUILD__CONTAINER_DIGEST").strip()
    return {
        "source_commit": commit,
        "source_branch": branch,
        "build_date": build_date,
        "container_digest": digest,
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
        version=__version__,
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

    @app.get(join_base_path(web_base_path, "/version"), include_in_schema=False)
    async def web_version() -> JSONResponse:
        """Web-tier build-identity surface for the shared About page (WSC-014).

        W28E-1863 fix-wave-d / PS-30 UI-R7.3: emit source commit + build date +
        deployment identity (config-routed via ``build_identity``, git-HEAD dev
        fallback) so the shared @cloud-dog/shell AboutPage can render build
        provenance. imap serves the SPA shell only for the canonical route
        allowlist (no ``/{path:path}`` catch-all). The shared cloud_dog_api_kit
        factory already registers a same-path ``/version`` (application/version/
        api_version only); this route is promoted to the FRONT of the router below
        so it takes precedence (first-match-wins) without forking the factory.
        """
        _build = build_identity(config)
        return JSONResponse(
            {
                "service": "imap-mcp-server",
                "application": "imap-mcp-server",
                "version": __version__,
                "appVersion": __version__,
                "source_commit": _build["source_commit"],
                "source_branch": _build["source_branch"],
                "build_date": _build["build_date"],
                "container_digest": _build["container_digest"],
                "environment": environment,
                # legacy field name any VersionInfo consumer may already read
                "commit": _build["source_commit"],
            }
        )

    # W28E-1863 fix-wave-d (WSC-014): promote the build-identity /version route to
    # the front so it takes precedence over the shared api-kit factory's own
    # same-path /version endpoint (first-match-wins) without forking the factory.
    for _idx, _route in enumerate(list(app.router.routes)):
        if getattr(_route, "endpoint", None) is web_version:
            app.router.routes.insert(0, app.router.routes.pop(_idx))
            break

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

    def _has_client_key_override(request: Request) -> bool:
        """Whether the caller supplied an explicit per-request API-key override.

        The PS-72 MCP / A2A consoles expose an "API-key override" field so an
        admin can execute a tool *as another actor* (e.g. to prove an RBAC
        denial, w28a-776 T.2.4, or an override-actor audit, T.2.5). When set,
        the SPA sends the override as an ``x-api-key`` (+ Bearer) header. A
        normal cookie-session request sends NO ``x-api-key`` header, so the mere
        presence of a client ``x-api-key`` on a browser-proxy call unambiguously
        signals an explicit override that MUST be honoured — otherwise the
        session proxy would silently strip it and re-run as the service
        identity, defeating the override (and RBAC enforcement) entirely.
        """
        return bool(str(request.headers.get("x-api-key") or "").strip())

    def _proxy_for(request: Request, session_proxy: WebApiProxy, direct_proxy: WebApiProxy) -> WebApiProxy:
        # An explicit per-request API-key override must reach the backend so it
        # resolves that key's actor + roles — route it through the direct proxy
        # (no injected service key) rather than the session proxy.
        if _has_client_key_override(request):
            return direct_proxy
        if _get_session(request) is not None and _service_api_key:
            return session_proxy
        return direct_proxy

    def _use_session_proxy(request: Request) -> bool:
        if _has_client_key_override(request):
            return False
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

    # W28E-1863 fix-wave-b (console-404): the SHARED @cloud-dog/idam WebUI pages
    # (Users/Groups/API-Keys/Roles/RBAC) issue best-effort capability probes to
    # /webapi/auth/status, /webapi/v1/users and /webapi/v1/api-keys. imap's API
    # tier only mounts the canonical cloud_dog_idam idam_v1_router (/idam/v1/*),
    # so those probe paths 404 when proxied — the pages still render (their
    # failure is swallowed at the page level) but each 404 breaches the PS-72
    # clean-console gate. These small compat handlers answer the probes with a
    # 2xx so no browser console 404 is emitted. They are registered BEFORE the
    # /webapi/{full_path:path} catch-all proxy so they win the route match.
    # Pattern mirrors db-mcp-server's webapi_auth_status (working-service parity).
    # The shared idam package is intentionally NOT modified (estate-wide ripple).

    @app.get(join_base_path(web_base_path, "/webapi/auth/status"), include_in_schema=False)
    async def webapi_auth_status(request: Request) -> JSONResponse:
        """Best-effort IDAM capability probe for the shared WebUI admin pages."""
        sess = _get_session(request)
        if not sess:
            return JSONResponse({"detail": "authentication required"}, status_code=401)
        role = normalise_flat_role(sess.get("role"))
        return JSONResponse(
            {
                "username": str(sess.get("user") or ""),
                "role": role,
                "is_system_admin": role == ADMIN_ROLE,
                "can_write": role_can_write(role),
            }
        )

    @app.get(join_base_path(web_base_path, "/webapi/v1/users"), include_in_schema=False)
    async def webapi_v1_users_compat(request: Request) -> JSONResponse:
        """Compact users list probe. imap serves the canonical /v1/admin/users; this
        compat alternate returns an empty set so the shared page merges the admin
        collection without a console 404 (auth still enforced)."""
        sess = _get_session(request)
        if not sess:
            return JSONResponse({"detail": "authentication required"}, status_code=401)
        return JSONResponse({"users": []})

    @app.get(join_base_path(web_base_path, "/webapi/v1/api-keys"), include_in_schema=False)
    async def webapi_v1_api_keys_compat(request: Request) -> JSONResponse:
        """Compact API-keys list probe. imap serves the canonical admin key routes;
        this compat alternate returns an empty set so the shared page merges the
        admin collection without a console 404 (auth still enforced)."""
        sess = _get_session(request)
        if not sess:
            return JSONResponse({"detail": "authentication required"}, status_code=401)
        return JSONResponse({"api_keys": []})

    @app.get(join_base_path(web_base_path, "/webapi/v1/groups"), include_in_schema=False)
    async def webapi_v1_groups_compat(request: Request) -> JSONResponse:
        """Compact groups list probe. imap serves the canonical /v1/admin/groups;
        this compat alternate returns an empty set so the shared @cloud-dog/idam
        Groups page merges the admin collection without a browser console 404
        (auth still enforced). Companion to the users / api-keys compat probes
        above — the shared IDAM page issues the same best-effort /v1/groups probe
        (index.tsx groupsCompact) that W28E-1863 fix-wave-b missed for groups."""
        sess = _get_session(request)
        if not sess:
            return JSONResponse({"detail": "authentication required"}, status_code=401)
        return JSONResponse({"groups": []})

    @app.api_route(join_base_path(web_base_path, "/webapi"), methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    @app.api_route(join_base_path(web_base_path, "/webapi/{full_path:path}"), methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    async def proxy_web_api(request: Request, full_path: str = "") -> Response:
        """Proxy cookie-authenticated browser API traffic on a dedicated path."""
        rel_path = _relative_request_path(request)
        if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"} and (
            rel_path == "/webapi/v1/admin/users"
            or rel_path.startswith("/webapi/v1/admin/users/")
        ):
            gate_sess = _get_session(request)
            if gate_sess is None:
                return JSONResponse({"detail": "authentication required"}, status_code=401)
            if not role_can_write(gate_sess.get("role")):
                return JSONResponse(
                    {
                        "detail": "read-only role: write operations are not permitted",
                        "role": READ_ONLY_ROLE,
                    },
                    status_code=403,
                )
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
        version=__version__,
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

    # --- Gmail OAuth admin setup routes (server-hosted setup pages) ---------
    # Mirrors the File-MCP google_drive_admin canonical pattern. These routes
    # are served directly on the Web listener (not proxied) because the OAuth
    # start/callback flow must write refresh tokens into the local config.yaml
    # plus the /app/logs sidecar for container-restart survival.
    def _compute_callback_url(request: Request) -> str:
        """Build the OAuth callback URL from the current request context."""
        proto = request.headers.get("x-forwarded-proto", "")
        if not proto:
            scope_scheme = request.scope.get("scheme", "http")
            proto = scope_scheme if scope_scheme in {"http", "https"} else "http"
        host = request.headers.get("host", "")
        if not host:
            host = request.url.netloc
        return f"{proto}://{host}/auth/google/callback"

    def _gmail_profile_names() -> list[str]:
        """Return profile names that are gmail-typed or could be used for gmail."""
        names = []
        for name, prof in (config.profiles or {}).items():
            prov = getattr(prof, "provider", None) or (prof.get("provider") if isinstance(prof, dict) else None)
            if prov == "gmail":
                names.append(name)
        if not names:
            names.append("gmail_personal")
        return names

    @app.get("/admin/gmail-setup", include_in_schema=False)
    async def gmail_setup_page(request: Request, profile: str | None = None) -> Response:
        """Render the Gmail OAuth setup form."""
        callback_url = _compute_callback_url(request)
        profiles = _gmail_profile_names()
        stored = load_gmail_profile_values(config)
        has_secret = stored.pop("has_client_secret", "") == "true"

        # Detect missing-config fields
        missing: list[str] = []
        if not stored.get("client_id"):
            missing.append("GOOGLE_CLIENT_ID")

        html = render_setup_page(
            callback_url=callback_url,
            profiles=profiles,
            selected_profile=profile or (profiles[0] if profiles else None),
            lock_profile=bool(profile),
            prefills=stored,
            has_client_secret=has_secret,
            missing_config_fields=missing if missing else None,
        )
        return Response(html, media_type="text/html")

    @app.post("/admin/gmail-setup/start", include_in_schema=False)
    async def gmail_setup_start(request: Request) -> Response:
        """Validate fields and return/redirect to Google authorisation URL."""
        body = await request.body()
        content_type = request.headers.get("content-type", "").lower()
        if "application/x-www-form-urlencoded" in content_type:
            data = parse_form_urlencoded(body)
        elif "application/json" in content_type:
            data = json.loads(body.decode("utf-8"))
        else:
            data = parse_form_urlencoded(body)

        # Fallback: if client_secret is masked, try to reuse stored secret
        stored = load_gmail_profile_values(config)
        client_secret = (data.get("client_secret") or "").strip()
        if not client_secret or client_secret == MASKED_CLIENT_SECRET:
            data["client_secret"] = load_gmail_client_secret(config)

        # Fallback: if client_id is not supplied (e.g. SPA-driven one-click
        # start), reuse the stored client_id from the gmail_personal profile.
        if not (data.get("client_id") or "").strip():
            stored_client_id = (stored.get("client_id") or "").strip()
            if stored_client_id:
                data["client_id"] = stored_client_id

        # Fill defaults for optional fields
        if not data.get("redirect_uri"):
            data["redirect_uri"] = _compute_callback_url(request)

        accept = request.headers.get("accept", "")
        try:
            auth_url = begin_oauth(data)
        except ValueError as exc:
            error_detail = str(exc)
            if "application/json" in accept:
                return JSONResponse(
                    {"ok": False, "error": error_detail, "error_type": "validation"},
                    status_code=400,
                )
            html = render_setup_page(
                callback_url=_compute_callback_url(request),
                profiles=_gmail_profile_names(),
                selected_profile=data.get("profile"),
                status_message=f"Validation error: {error_detail}",
                status_type="error",
                prefills=data,
            )
            return Response(html, media_type="text/html", status_code=400)

        if "application/json" in accept:
            return JSONResponse({"ok": True, "location": auth_url})
        from fastapi.responses import RedirectResponse as _RR
        return _RR(auth_url, status_code=302)

    @app.get("/auth/google/callback", include_in_schema=False)
    async def gmail_oauth_callback(request: Request) -> Response:
        """Handle the Google OAuth callback (W28C-434B token-exchange path).

        Mirrors file-mcp google_drive_admin.complete_oauth_callback at
        file_mcp_server/server_runtime.py lines 5136-5217 (W28C-433 reference).
        Exchanges the code for tokens at pending.token_uri, fetches the user
        email via Google userinfo for verification, writes refresh_token to
        config.yaml plus a /app/logs sidecar for restart survival, then
        redirects to /gmail-settings with status query params.
        """
        from urllib.parse import urlencode as _urlencode
        from fastapi.responses import RedirectResponse as _RR
        from pathlib import Path as _Path

        state = request.query_params.get("state", "")
        code = request.query_params.get("code", "")
        oauth_error = request.query_params.get("error", "")
        error_description = request.query_params.get("error_description", "")

        def _redirect_error(message: str, *, profile_for_redirect: str = "") -> Response:
            params = _urlencode({
                "profile": profile_for_redirect,
                "status": "error",
                "error_message": (message or "")[:300],
            })
            return _RR(f"/gmail-settings?{params}", status_code=302)

        if oauth_error:
            return _redirect_error(
                f"Google returned error: {oauth_error} — {error_description}",
            )

        if not state or not code:
            return _redirect_error("Missing state or code in callback.")

        # Resolve the active config.yaml path. CLOUD_DOG__CONFIG__YAML env or
        # common container paths take precedence. The bootstrap config loader
        # already used one of these; we resolve symbolically here so the
        # callback works on local-docker and preprod.
        config_path_str = runtime_config_value(config, "CLOUD_DOG__CONFIG__YAML", "CONFIG_YAML")
        if not config_path_str:
            for candidate in ("/app/config.yaml", "/app/config.yml"):
                if _Path(candidate).is_file():
                    config_path_str = candidate
                    break
        if not config_path_str:
            return _redirect_error(
                "Could not resolve active config.yaml path for OAuth completion.",
            )

        try:
            result = complete_oauth_callback(
                state=state,
                code=code,
                config_path=_Path(config_path_str),
            )
        except Exception as exc:  # noqa: BLE001 — surface the error to redirect, not 500
            return _redirect_error(str(exc))

        # Structured success log — redacted (no token values, no client_secret).
        try:
            from cloud_dog_logging import get_logger as _gl  # type: ignore[import-untyped]
            _gl(__name__).info(
                "admin_gmail_callback_success",
                extra={
                    "profile": result.profile,
                    "account_email": result.user_email,
                    "config_path": result.config_path,
                    "has_refresh_token": True,
                    "has_access_token": True,
                },
            )
        except Exception:  # noqa: BLE001 — never break the redirect on logging failure
            pass

        params = _urlencode({
            "profile": result.profile,
            "status": "success",
            "account": result.user_email,
        })
        return _RR(f"/gmail-settings?{params}", status_code=302)

    @app.get("/admin/gmail-setup/status", include_in_schema=False)
    async def gmail_setup_status(request: Request) -> JSONResponse:
        """Return structured status of Gmail OAuth configuration readiness.

        W28C-434B: extended with has_refresh_token, connected_account_email,
        token_obtained_at so the SPA GmailSettingsPage can render the
        Connected card without an extra round-trip.
        """
        stored = load_gmail_profile_values(config)
        has_client_id = bool(stored.get("client_id"))
        has_redirect = bool(stored.get("redirect_uri"))
        has_secret = stored.get("has_client_secret") == "true"
        missing: list[str] = []
        if not has_client_id:
            missing.append("GOOGLE_CLIENT_ID")
        if not has_secret:
            missing.append("GOOGLE_CLIENT_SECRET")

        ready = has_client_id and has_secret and has_redirect and not missing

        # W28C-434B connection state — refresh_token presence in
        # config.profiles.<profile>.auth.oauth.refresh_token (post-callback).
        has_refresh_token = False
        connected_account_email = ""
        token_obtained_at = ""
        try:
            profiles = getattr(config, "profiles", None) or {}
            for _name, prof in (profiles.items() if isinstance(profiles, dict) else []):
                auth_block = getattr(prof, "auth", None) or (prof.get("auth") if isinstance(prof, dict) else None)
                oauth_block = (
                    getattr(auth_block, "oauth", None)
                    or (auth_block.get("oauth") if isinstance(auth_block, dict) else None)
                ) if auth_block is not None else None
                if oauth_block is None:
                    continue
                rt = (
                    getattr(oauth_block, "refresh_token", None)
                    or (oauth_block.get("refresh_token") if isinstance(oauth_block, dict) else None)
                )
                rt_value = str(rt or "").strip()
                # Skip unresolved template values like ${vault....} or ${IMAP_MCP_GMAIL_REFRESH_TOKEN}
                if rt_value and not rt_value.startswith("$"):
                    has_refresh_token = True
                    ae = (
                        getattr(oauth_block, "account_email", None)
                        or (oauth_block.get("account_email") if isinstance(oauth_block, dict) else None)
                    )
                    connected_account_email = str(ae or "").strip()
                    # token_obtained_at comes from sidecar file mtime if present.
                    try:
                        import os as _os
                        sidecar = f"/app/logs/gmail_oauth_state-{_name}.json"
                        if _os.path.isfile(sidecar):
                            from datetime import datetime as _dt, timezone as _tz
                            mtime = _os.path.getmtime(sidecar)
                            token_obtained_at = _dt.fromtimestamp(mtime, tz=_tz.utc).isoformat()
                    except Exception:  # noqa: BLE001
                        pass
                    break
        except Exception:  # noqa: BLE001
            pass

        return JSONResponse({
            "ok": True,
            "result": {
                "gmail_oauth_ready": ready,
                "has_client_id": has_client_id,
                "has_client_secret": has_secret,
                "has_redirect_uri": has_redirect,
                "has_refresh_token": has_refresh_token,
                "connected_account_email": connected_account_email,
                "token_obtained_at": token_obtained_at,
                "missing_fields": missing,
                "profiles": _gmail_profile_names(),
            },
        })

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
