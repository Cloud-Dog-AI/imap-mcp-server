"""imap-mcp-server RBAC bridge backed by cloud_dog_idam."""

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

from cloud_dog_idam.rbac import RBACEngine


class AccessDeniedError(PermissionError):
    """Raised when an actor cannot execute an operation."""


def build_rbac_engine(role_permissions: dict[str, list[str] | set[str]]) -> RBACEngine:
    """Build a cloud_dog_idam RBACEngine from configured permissions."""
    return RBACEngine(
        role_overlay={role: set(values) for role, values in role_permissions.items()}
    )


def can_execute_tool(engine: RBACEngine, actor_id: str, permission: str) -> bool:
    """Check access through cloud_dog_idam.RBACEngine exact permission semantics."""
    return engine.has_permission(actor_id, permission)


def require_tool_access(
    engine: RBACEngine,
    actor_id: str,
    permission: str,
) -> None:
    """Raise AccessDeniedError when cloud_dog_idam denies a permission."""
    if not can_execute_tool(engine, actor_id, permission):
        raise AccessDeniedError(f"Actor {actor_id!r} lacks permission {permission!r}")
