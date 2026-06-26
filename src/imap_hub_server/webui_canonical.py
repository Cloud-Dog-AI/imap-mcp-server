"""PS-WEBUI-URL-CANONICAL v1.0 — canonical WebUI route map + 308 legacy-alias redirects.

Single source of truth for the imap-mcp-server WebUI URL surface (W28E-1803C).

- Canonical routes serve the SPA shell (HTTP 200; the SPA self-gates auth).
- Legacy aliases — including the historical ``/ui/*`` prefix and the flat
  ``/idam/*`` / ``/api-docs`` / ``/jobs`` / ``/settings`` paths — return an HTTP
  **308** permanent redirect to their canonical path, preserving query + fragment
  (WURL-002 / WURL-010). The named offender ``/ui/login`` → ``/login`` is covered.
- API / MCP / A2A / health / assets / runtime-config surfaces are NEVER touched
  by the redirect middleware (WURL-008).
- Unknown WebUI paths are not registered as shell routes, so they fall through to
  a route-level 404 (WURL-007) instead of a silent SPA rewrite.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

from imap_hub_core.config.base_paths import join_base_path, strip_base_path

# WURL-008: non-WebUI surface prefixes the canonical redirect MUST never touch.
API_SURFACE_PREFIXES: tuple[str, ...] = (
    "/api",
    "/app",
    "/webapi",
    "/webdocs",
    "/mcp",
    "/webmcp",
    "/a2a",
    "/weba2a",
    "/v1",
    "/events",
    "/tasks",
    "/health",
    "/ready",
    "/live",
    "/status",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/assets",
    "/runtime-config.js",
    "/favicon.ico",
    "/auth",
)

# Canonical WebUI routes (serve the SPA shell, HTTP 200). The home route ``/`` is
# the Dashboard. These are the ONLY paths that serve the shell; anything else is a
# 404 (WURL-007).
CANONICAL_WEBUI_ROUTES: tuple[str, ...] = (
    "/",
    "/login",
    "/profiles",
    "/mailbox-workspace",
    "/search-retrieve",
    "/audit-log",
    "/admin/users",
    "/admin/groups",
    "/admin/api-keys",
    "/admin/roles",
    "/admin/rbac",
    "/developer/api-docs",
    "/developer/mcp-console",
    "/developer/a2a-console",
    "/system/jobs",
    "/system/settings",
    "/system/gmail-settings",
    "/system/about",
)

# Flat legacy alias -> canonical path (308). The ``/ui/*`` historical prefix is
# handled generically by ``canonical_redirect_target`` so it does not need an
# entry per route here.
LEGACY_WEBUI_REDIRECTS: dict[str, str] = {
    "/dashboard": "/",
    "/diagnostics-audit": "/audit-log",
    "/idam/users": "/admin/users",
    "/idam/groups": "/admin/groups",
    "/idam/api-keys": "/admin/api-keys",
    "/idam/roles": "/admin/roles",
    "/idam/rbac": "/admin/rbac",
    "/admin-control": "/admin/users",
    "/api-docs": "/developer/api-docs",
    "/mcp-console": "/developer/mcp-console",
    "/a2a-console": "/developer/a2a-console",
    "/jobs": "/system/jobs",
    "/settings": "/system/settings",
    "/gmail-settings": "/system/gmail-settings",
    "/about": "/system/about",
    "/mutation-gating": "/",
    "/legacy-diagnostics": "/audit-log",
}


def is_api_surface_path(path: str) -> bool:
    """Return True for any non-WebUI surface that must never be redirected."""
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in API_SURFACE_PREFIXES)


def is_canonical_webui_route(path: str) -> bool:
    """Return True when ``path`` is a canonical WebUI shell route (serves 200)."""
    return path in CANONICAL_WEBUI_ROUTES


def canonical_redirect_target(path: str) -> str | None:
    """Return the canonical 308 target for a legacy WebUI alias, else ``None``.

    Handles the flat alias map plus the historical ``/ui`` prefix generically:
    ``/ui/login`` -> ``/login``, ``/ui/jobs`` -> ``/system/jobs`` (chaining the
    stripped path through the flat alias map), ``/ui`` / ``/ui/`` -> ``/``.
    """
    if path in LEGACY_WEBUI_REDIRECTS:
        return LEGACY_WEBUI_REDIRECTS[path]
    if path in ("/ui", "/ui/"):
        return "/"
    if path.startswith("/ui/"):
        stripped = path[3:]  # keep the leading slash: "/ui/login"[3:] == "/login"
        if stripped in LEGACY_WEBUI_REDIRECTS:
            return LEGACY_WEBUI_REDIRECTS[stripped]
        if stripped in CANONICAL_WEBUI_ROUTES:
            return stripped
        # Unknown /ui/* target: send it to the stripped path so the canonical
        # layer can 404 it consistently rather than serving a stale /ui shell.
        return stripped
    return None


def _redirect_preserving(request: Request, target: str) -> RedirectResponse:
    """Build a 308 redirect to ``target`` preserving query string + fragment."""
    query = request.url.query
    fragment = request.url.fragment
    destination = target
    if query:
        destination = f"{destination}?{query}"
    if fragment:
        destination = f"{destination}#{fragment}"
    return RedirectResponse(destination, status_code=308)


def install_canonical_webui_redirects(app: FastAPI, *, base_path: str = "") -> None:
    """Register the 308 legacy-alias → canonical WebUI redirect middleware.

    Only GET/HEAD browser navigations are redirected; non-WebUI surfaces
    (``is_api_surface_path``) are never touched. ``base_path`` is the surface
    base prefix (empty for the canonical Web origin) and is stripped before
    matching, then re-applied to the redirect target.
    """

    @app.middleware("http")
    async def canonical_webui_redirects(request: Request, call_next):
        if request.method in ("GET", "HEAD"):
            relative = strip_base_path(request.url.path, base_path) if base_path else request.url.path
            if not is_api_surface_path(relative):
                target = canonical_redirect_target(relative)
                if target is not None and target != relative:
                    full_target = join_base_path(base_path, target) if base_path else target
                    return _redirect_preserving(request, full_target)
        return await call_next(request)


def canonical_shell_route_paths(base_path: str = "") -> list[str]:
    """Return the de-duplicated, sorted list of canonical shell route paths."""
    return sorted({join_base_path(base_path, route) for route in CANONICAL_WEBUI_ROUTES})
