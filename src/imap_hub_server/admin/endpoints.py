"""Admin router composition."""

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

# Covers: FR-03
# Covers: FR-10
# Covers: FR-11
# Covers: FR-12
# Covers: FR-13

from typing import Any

from cloud_dog_idam import APIKeyManager, RBACEngine
from fastapi import APIRouter

from imap_hub_core.audit.logger import AuditWriter
from imap_hub_server.admin.endpoint_common import (
    actor_id as _actor_id,
    authorise_read as _authorise_read,
    emit_admin_audit as _emit_admin_audit,
    emit_config_event as _emit_config_event,
    normalise_log_entry as _normalise_log_entry,
    request_roles as _request_roles,
    require_admin_role as _require_admin_role,
)
from imap_hub_server.admin.endpoint_identity import register_identity_routes
from imap_hub_server.admin.endpoint_observability import register_observability_routes
from imap_hub_server.admin.endpoint_profiles import register_profile_routes
from imap_hub_server.admin.endpoint_roles import register_roles_routes
from imap_hub_server.admin.state import FileBackedAdminState
from imap_hub_server.admin.state_roles import RoleStoreState


def build_admin_router(
    profile_store: dict[str, dict[str, Any]],
    archive_root: str,
    admin_state: FileBackedAdminState,
    api_key_manager: APIKeyManager,
    rbac_engine: RBACEngine,
    audit_writer: AuditWriter | None = None,
    audit_path: str | None = None,
    log_paths: dict[str, str] | None = None,
    rbac_store: dict[str, list[str]] | None = None,
    session_manager: Any | None = None,
    api_base_path: str = "/api/v1",
    legacy_api_base_path: str = "/app/v1",
) -> APIRouter:
    """Create the composed admin router."""
    router = APIRouter(tags=["admin"])
    if rbac_store is None:
        rbac_store = {}
    resolved_log_paths = {
        "api": "logs/api_server.log",
        "web": "logs/web_server.log",
        "mcp": "logs/mcp_server.log",
        "a2a": "logs/a2a_server.log",
        "audit": audit_path or "logs/audit.log.jsonl",
    }
    if log_paths:
        resolved_log_paths.update({key: value for key, value in log_paths.items() if value})

    register_profile_routes(
        router,
        profile_store=profile_store,
        archive_root=archive_root,
        admin_state=admin_state,
        audit_writer=audit_writer,
        rbac_store=rbac_store,
        api_base_path=api_base_path,
        legacy_api_base_path=legacy_api_base_path,
    )
    register_identity_routes(
        router,
        admin_state=admin_state,
        api_key_manager=api_key_manager,
        rbac_engine=rbac_engine,
        audit_writer=audit_writer,
        api_base_path=api_base_path,
        legacy_api_base_path=legacy_api_base_path,
    )
    register_observability_routes(
        router,
        admin_state=admin_state,
        audit_writer=audit_writer,
        audit_path=audit_path,
        resolved_log_paths=resolved_log_paths,
        api_base_path=api_base_path,
        legacy_api_base_path=legacy_api_base_path,
    )
    if session_manager is not None:
        # W28A-876 Gate 4b: canonical PS-71 §IW3A roles endpoint backed by the
        # shared cloud_dog_idam SqlAlchemyRoleStore (not the bespoke role-policy).
        role_state = RoleStoreState(session_manager=session_manager)
        role_state.ensure_roles_seed()
        register_roles_routes(
            router,
            admin_state=admin_state,
            role_state=role_state,
            audit_writer=audit_writer,
            api_base_path=api_base_path,
            legacy_api_base_path=legacy_api_base_path,
        )
    return router


__all__ = [
    "_actor_id",
    "_authorise_read",
    "_emit_admin_audit",
    "_emit_config_event",
    "_normalise_log_entry",
    "_request_roles",
    "_require_admin_role",
    "build_admin_router",
]
