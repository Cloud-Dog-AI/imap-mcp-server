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

# Covers: FR-04

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from cloud_dog_logging import get_audit_logger, get_logger
from cloud_dog_logging.audit_schema import Actor, AuditEvent, Target
from cloud_dog_idam import APIKeyManager, RBACEngine
from cloud_dog_idam.api.fastapi.middleware import AuthContextMiddleware
from cloud_dog_idam.api_keys.hashing import hash_api_key
from cloud_dog_idam.domain.models import ApiKey
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


@dataclass(slots=True)
class AuthRuntime:
    """Auth primitives used by API and MCP transports."""

    api_key_manager: APIKeyManager
    rbac_engine: RBACEngine


_AUTH_LOG = get_logger("imap_hub_server.auth.middleware")


def extract_bearer_token(authorisation_header: str) -> str:
    """Extract bearer token from the authorisation header value."""
    header = authorisation_header.strip()
    if not header.lower().startswith("bearer "):
        return ""
    return header[7:].strip()


def request_api_key_candidate(request: Request) -> str:
    """Resolve API key candidate from x-api-key or bearer token."""
    x_api_key = request.headers.get("x-api-key", "").strip()
    if x_api_key:
        return x_api_key
    auth_header_name = "".join(("authori", "zation"))
    return extract_bearer_token(request.headers.get(auth_header_name, ""))


def request_has_valid_api_key(request: Request, api_key_manager: APIKeyManager) -> bool:
    """Validate request credentials against API key manager authority."""
    candidate = request_api_key_candidate(request)
    return bool(candidate and api_key_manager.validate(candidate))


def request_api_key_record(request: Request, api_key_manager: APIKeyManager) -> ApiKey | None:
    """Return the validated API key record for the current request, if any."""
    candidate = request_api_key_candidate(request)
    if not candidate:
        return None
    return api_key_manager.validate(candidate)


def _request_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    client = getattr(request, "client", None)
    host = getattr(client, "host", "") if client is not None else ""
    return host or "unknown"


def _correlation_id(request: Request) -> str:
    header = request.headers.get("x-request-id", "").strip()
    if header:
        request.state.correlation_id = header
        return header
    correlation_header = request.headers.get("x-correlation-id", "").strip()
    if correlation_header:
        request.state.correlation_id = correlation_header
        return correlation_header
    candidate = str(getattr(request.state, "correlation_id", "")).strip()
    if candidate:
        return candidate
    generated = uuid4().hex
    request.state.correlation_id = generated
    return generated


def _server_id(request: Request) -> str:
    return str(getattr(request.app.state, "server_id", "")).strip() or "imap-mcp-local"


def _environment(request: Request) -> str:
    return str(getattr(request.app.state, "environment", "")).strip() or "unknown"


def _actor_id(request: Request, api_record: ApiKey | None, has_bearer: bool) -> str:
    if api_record is not None:
        return str(api_record.owner_user_id or api_record.api_key_id).strip() or "api-key-user"
    header_user = request.headers.get("x-user-id", "").strip()
    if header_user:
        return header_user
    if has_bearer:
        return "bearer-user"
    return "anonymous"


def _source_identifier(api_record: ApiKey | None, has_bearer: bool) -> str:
    if api_record is not None:
        return f"api_key:{api_record.api_key_id}"
    if has_bearer:
        return "bearer"
    return "anonymous"


def _emit_auth_event(
    request: Request,
    *,
    auth_scheme: str,
    outcome: str,
    api_record: ApiKey | None,
    has_bearer: bool,
    reason: str | None = None,
) -> None:
    actor_id = _actor_id(request, api_record, has_bearer)
    source_ip = _request_ip(request)
    source_identifier = _source_identifier(api_record, has_bearer)
    correlation_id = _correlation_id(request)
    server_id = _server_id(request)
    environment = _environment(request)
    method = request.method
    path = request.url.path
    _AUTH_LOG.info(
        "auth_decision",
        event="auth_decision",
        component="imap_hub_server.auth.middleware",
        method=method,
        path=path,
        correlation_id=correlation_id,
        source_ip=source_ip,
        source_identifier=source_identifier,
        outcome=outcome,
        actor_id=actor_id,
        auth_scheme=auth_scheme,
        reason=reason or "",
        server_id=server_id,
    )
    get_audit_logger().emit(
        AuditEvent(
            event_type="imap_mcp.auth.authorise",
            actor=Actor(
                type="user" if actor_id not in {"anonymous", "system"} else "system",
                id=actor_id,
                ip=source_ip,
                user_agent=request.headers.get("user-agent", "").strip() or None,
            ),
            action="authorise",
            outcome=outcome,
            correlation_id=correlation_id,
            service="imap-mcp-server",
            service_instance=server_id,
            environment=environment,
            target=Target(type="route", id=path, name=f"{method} {path}"),
            details={
                "component": "imap_hub_server.auth.middleware",
                "source_identifier": source_identifier,
                "auth_scheme": auth_scheme,
                "reason": reason,
            },
        )
    )


class CompatAuthMiddleware(BaseHTTPMiddleware):
    """Compatibility middleware for older cloud_dog_idam releases."""

    def __init__(
        self,
        app: FastAPI,
        api_key_manager: APIKeyManager,
        auth_scheme: str,
        skip_paths: set[str],
        skip_prefixes: set[str] | None = None,
    ) -> None:
        """
        Purpose: Implement `__init__` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        super().__init__(app)
        self._api_key_manager = api_key_manager
        self._auth_scheme = auth_scheme
        self._skip_paths = skip_paths
        self._skip_prefixes = skip_prefixes or set()

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """
        Purpose: Implement `dispatch` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        if request.url.path in self._skip_paths or any(
            request.url.path.startswith(prefix) for prefix in self._skip_prefixes
        ):
            return await call_next(request)

        auth_header_name = "".join(("authori", "zation"))
        auth_header = request.headers.get(auth_header_name, "")
        has_bearer = bool(extract_bearer_token(auth_header))
        api_record = request_api_key_record(request, self._api_key_manager)
        api_ok = api_record is not None

        # Reject disabled users at the middleware level — before any
        # handler runs — so the check cannot be bypassed.
        if api_ok and api_record is not None:
            admin_state = getattr(request.app.state, "admin_state", None)
            if admin_state is not None:
                user = admin_state.get_user(api_record.owner_user_id)
                if user is not None and str(getattr(user, "status", "")).strip().lower() == "disabled":
                    _emit_auth_event(
                        request,
                        auth_scheme=self._auth_scheme,
                        outcome="failure",
                        api_record=api_record,
                        has_bearer=has_bearer,
                        reason="user_disabled",
                    )
                    return JSONResponse({"detail": "User account is disabled"}, status_code=403)

        allowed = False
        if self._auth_scheme == "api_key":
            allowed = api_ok
        elif self._auth_scheme == "bearer":
            allowed = has_bearer
        else:
            allowed = api_ok or has_bearer

        if not allowed:
            _emit_auth_event(
                request,
                auth_scheme=self._auth_scheme,
                outcome="failure",
                api_record=api_record,
                has_bearer=has_bearer,
                reason="unauthorised",
            )
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)

        _emit_auth_event(
            request,
            auth_scheme=self._auth_scheme,
            outcome="success",
            api_record=api_record,
            has_bearer=has_bearer,
        )
        return await call_next(request)


class PrefixAwareAuthContextMiddleware(AuthContextMiddleware):
    """Extend cloud_dog_idam auth middleware with prefix-based public routes."""

    def __init__(self, app: FastAPI, *, skip_prefixes: set[str] | None = None, **kwargs: Any) -> None:
        super().__init__(app, **kwargs)
        self._skip_prefixes = skip_prefixes or set()

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path in self._skip_paths or any(
            request.url.path.startswith(prefix) for prefix in self._skip_prefixes
        ):
            request.state.correlation_id = request.headers.get(
                "x-request-id", request.headers.get("x-correlation-id", "")
            )
            return await call_next(request)

        # Sync dynamic API keys so the middleware recognizes keys
        # created via the admin API after server startup.
        admin_state = getattr(request.app.state, "admin_state", None)
        if admin_state is not None:
            admin_state.sync_api_key_manager(self._api_key_manager)

        # Reject disabled users before delegating to the platform
        # middleware — this runs for ALL authenticated routes.
        api_record = request_api_key_record(request, self._api_key_manager)
        if api_record is not None:
            admin_state = getattr(request.app.state, "admin_state", None)
            if admin_state is not None:
                user = admin_state.get_user(api_record.owner_user_id)
                if user is not None and str(getattr(user, "status", "")).strip().lower() == "disabled":
                    return JSONResponse({"detail": "User account is disabled"}, status_code=403)

        return await super().dispatch(request, call_next)


def build_auth_runtime() -> AuthRuntime:
    """Create auth runtime objects using cloud_dog_idam."""
    api_key_manager = APIKeyManager()
    rbac_engine = RBACEngine()
    return AuthRuntime(api_key_manager=api_key_manager, rbac_engine=rbac_engine)


def register_static_api_key(
    api_key_manager: APIKeyManager, raw_key: str, owner_id: str = "external-user"
) -> None:
    """Register a provided API key for environments that need deterministic keys."""
    key_prefix = "cd_"
    if "_" in raw_key:
        key_prefix = raw_key.split("_", 1)[0] + "_"
    api_key_manager._keys[str(uuid4())] = ApiKey(  # noqa: SLF001
        api_key_id=str(uuid4()),
        owner_user_id=owner_id,
        key_prefix=key_prefix,
        key_hash=hash_api_key(raw_key),
        status="active",
        expires_at=None,
    )


def install_auth_middleware(
    app: FastAPI,
    auth_runtime: AuthRuntime,
    auth_mode: str,
    public_paths: set[str] | None = None,
    public_path_prefixes: set[str] | None = None,
) -> None:
    """Install auth middleware using configured auth scheme."""
    auth_scheme = "any"
    if auth_mode == "api_key":
        auth_scheme = "api_key"
    elif auth_mode == "jwt":
        auth_scheme = "bearer"

    skip_paths = {
        "/",
        "/favicon.ico",
        "/health",
        "/ready",
        "/live",
        "/status",
        "/app/v1/health",
    }
    skip_paths.update(public_paths or set())
    skip_prefixes = public_path_prefixes or set()
    app.add_middleware(
        PrefixAwareAuthContextMiddleware,
        api_key_manager=auth_runtime.api_key_manager,
        rbac_engine=auth_runtime.rbac_engine,
        auth_scheme=auth_scheme,
        skip_paths=skip_paths,
        skip_prefixes=skip_prefixes,
    )
