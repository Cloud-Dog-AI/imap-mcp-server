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

from contextvars import ContextVar, Token
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AuditRequestContext:
    """Request-scoped audit metadata propagated into core handlers."""

    correlation_id: str
    actor_id: str
    actor_type: str = "user"
    roles: list[str] = field(default_factory=list)
    source_identifier: str | None = None
    source_ip: str | None = None
    user_agent: str | None = None
    component: str = "unknown"
    server_id: str = "unknown"
    environment: str = "unknown"


_AUDIT_CONTEXT: ContextVar[AuditRequestContext | None] = ContextVar("imap_audit_context", default=None)


def set_audit_request_context(context: AuditRequestContext) -> Token[AuditRequestContext | None]:
    """Set the current audit request context and return the reset token."""
    return _AUDIT_CONTEXT.set(context)


def reset_audit_request_context(token: Token[AuditRequestContext | None]) -> None:
    """Restore the previous audit request context."""
    _AUDIT_CONTEXT.reset(token)


def get_audit_request_context() -> AuditRequestContext | None:
    """Return the current request-scoped audit context when present."""
    return _AUDIT_CONTEXT.get()
