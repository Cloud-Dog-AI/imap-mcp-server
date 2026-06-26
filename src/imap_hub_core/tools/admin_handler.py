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

from __future__ import annotations

from imap_hub_core.tools.base_handler import *  # noqa: F403

class AdminToolHandlers:
    """Handler set for shared user, group, and API-key admin operations."""

    def __init__(
        self,
        admin_state: FileBackedAdminState,
        api_key_manager: APIKeyManager,
        rbac_engine: RBACEngine | None = None,
        audit_writer: AuditWriter | None = None,
    ) -> None:
        """Initialise admin handlers with shared state and API-key authority."""
        self._admin_state = admin_state
        self._api_key_manager = api_key_manager
        self._rbac_engine = rbac_engine
        self._audit_writer = audit_writer

    def _audit(self, operation: str, status: str, params: dict[str, Any]) -> None:
        """Emit one audit record for an admin tool invocation."""
        if self._audit_writer is None:
            return
        now = datetime.now(timezone.utc)
        context = get_audit_request_context()
        self._audit_writer.emit(
            AuditRecord(
                operation=operation,
                status=status,
                correlation_id=(
                    context.correlation_id if context is not None else f"tool-{int(now.timestamp())}"
                ),
                actor=AuditActor(
                    actor_type=context.actor_type if context is not None else "system",
                    actor_id=context.actor_id if context is not None else "system-admin-tool",
                    roles=list(context.roles) if context is not None else ["admin"],
                    ip=context.source_ip if context is not None else None,
                    user_agent=context.user_agent if context is not None else None,
                ),
                profile_id=None,
                component=context.component if context is not None else "imap_hub_core.tools.handlers",
                source_identifier=context.source_identifier if context is not None else "internal",
                target_type="admin_tool",
                target_id=operation,
                target_name=operation,
                server_id=context.server_id if context is not None else "imap-mcp-local",
                environment=context.environment if context is not None else "unknown",
                params=params,
            )
        )

    def _sync_rbac(self) -> None:
        """Refresh the runtime RBAC engine after user/group mutations."""
        if self._rbac_engine is not None:
            self._admin_state.sync_rbac_engine(self._rbac_engine)

    @staticmethod
    def _ok(result: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return the standard success envelope for admin tools."""
        return ImapToolHandlersBase._ok_envelope(result=result)

    @staticmethod
    def _err(code: str, message: str) -> dict[str, Any]:
        """Return the standard error envelope for admin tools."""
        return ImapToolHandlersBase._error_envelope(code, message)

    def user_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        """List configured users."""
        try:
            request = ProfileListInput.model_validate(payload)
        except ValidationError as exc:
            return ImapToolHandlersBase._validation_error(exc)
        items = self._admin_state.list_users()
        if not request.include_disabled:
            items = [item for item in items if item.status != "disabled"]
        return self._ok(result={"items": [self._admin_state.export_user(item) for item in items]})

    def user_get(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return one configured user."""
        try:
            request = UserGetInput.model_validate(payload)
        except ValidationError as exc:
            return ImapToolHandlersBase._validation_error(exc)
        record = self._admin_state.get_user(request.user_id)
        if record is None:
            return self._err("user_not_found", request.user_id)
        return self._ok(result=self._admin_state.export_user(record))

    def user_create(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create one configured user."""
        try:
            request = UserCreateInput.model_validate(payload)
        except ValidationError as exc:
            return ImapToolHandlersBase._validation_error(exc)
        try:
            record = self._admin_state.create_user(request.model_dump(exclude_none=True))
        except ValueError as exc:
            return self._err("user_create_failed", str(exc))
        self._sync_rbac()
        self._audit("admin.user_create", "success", {"user_id": record.user_id})
        self._admin_state.emit_event(
            entity_type="user",
            action="create",
            entity_id=record.user_id,
            actor_id="system-admin-tool",
            source="tool",
            details={"username": record.username},
        )
        return self._ok(result=self._admin_state.export_user(record))

    def user_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Update one configured user."""
        try:
            request = UserUpdateInput.model_validate(payload)
        except ValidationError as exc:
            return ImapToolHandlersBase._validation_error(exc)
        try:
            record = self._admin_state.update_user(
                request.user_id,
                request.model_dump(exclude_none=True, exclude={"user_id"}),
            )
        except KeyError:
            return self._err("user_not_found", request.user_id)
        except ValueError as exc:
            return self._err("user_update_failed", str(exc))
        self._sync_rbac()
        self._audit("admin.user_update", "success", {"user_id": record.user_id})
        self._admin_state.emit_event(
            entity_type="user",
            action="update",
            entity_id=record.user_id,
            actor_id="system-admin-tool",
            source="tool",
            details={"username": record.username},
        )
        return self._ok(result=self._admin_state.export_user(record))

    def user_delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Delete one configured user."""
        try:
            request = UserDeleteInput.model_validate(payload)
        except ValidationError as exc:
            return ImapToolHandlersBase._validation_error(exc)
        if not self._admin_state.delete_user(request.user_id):
            return self._err("user_not_found", request.user_id)
        self._sync_rbac()
        self._audit("admin.user_delete", "success", {"user_id": request.user_id})
        self._admin_state.emit_event(
            entity_type="user",
            action="delete",
            entity_id=request.user_id,
            actor_id="system-admin-tool",
            source="tool",
        )
        return self._ok(result={"user_id": request.user_id})

    def group_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        """List configured groups."""
        try:
            ProfileListInput.model_validate(payload)
        except ValidationError as exc:
            return ImapToolHandlersBase._validation_error(exc)
        return self._ok(
            result={"items": [self._admin_state.export_group(item) for item in self._admin_state.list_groups()]}
        )

    def group_get(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return one configured group."""
        try:
            request = GroupGetInput.model_validate(payload)
        except ValidationError as exc:
            return ImapToolHandlersBase._validation_error(exc)
        record = self._admin_state.get_group(request.group_id)
        if record is None:
            return self._err("group_not_found", request.group_id)
        return self._ok(result=self._admin_state.export_group(record))

    def group_create(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create one configured group."""
        try:
            request = GroupCreateInput.model_validate(payload)
        except ValidationError as exc:
            return ImapToolHandlersBase._validation_error(exc)
        try:
            record = self._admin_state.create_group(request.model_dump(exclude_none=True))
        except (KeyError, ValueError) as exc:
            return self._err("group_create_failed", str(exc))
        self._sync_rbac()
        self._audit("admin.group_create", "success", {"group_id": record.group_id})
        self._admin_state.emit_event(
            entity_type="group",
            action="create",
            entity_id=record.group_id,
            actor_id="system-admin-tool",
            source="tool",
            details={"name": record.name, "roles": record.roles},
        )
        return self._ok(result=self._admin_state.export_group(record))

    def group_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Update one configured group."""
        try:
            request = GroupUpdateInput.model_validate(payload)
        except ValidationError as exc:
            return ImapToolHandlersBase._validation_error(exc)
        try:
            record = self._admin_state.update_group(
                request.group_id,
                request.model_dump(exclude_none=True, exclude={"group_id"}),
            )
        except KeyError:
            return self._err("group_not_found", request.group_id)
        except ValueError as exc:
            return self._err("group_update_failed", str(exc))
        self._sync_rbac()
        self._audit("admin.group_update", "success", {"group_id": record.group_id})
        self._admin_state.emit_event(
            entity_type="group",
            action="update",
            entity_id=record.group_id,
            actor_id="system-admin-tool",
            source="tool",
            details={"name": record.name, "roles": record.roles},
        )
        return self._ok(result=self._admin_state.export_group(record))

    def group_delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Delete one configured group."""
        try:
            request = GroupDeleteInput.model_validate(payload)
        except ValidationError as exc:
            return ImapToolHandlersBase._validation_error(exc)
        if not self._admin_state.delete_group(request.group_id):
            return self._err("group_not_found", request.group_id)
        self._sync_rbac()
        self._audit("admin.group_delete", "success", {"group_id": request.group_id})
        self._admin_state.emit_event(
            entity_type="group",
            action="delete",
            entity_id=request.group_id,
            actor_id="system-admin-tool",
            source="tool",
        )
        return self._ok(result={"group_id": request.group_id})

    def group_add_member(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Add one user to a configured group."""
        try:
            request = GroupMemberInput.model_validate(payload)
        except ValidationError as exc:
            return ImapToolHandlersBase._validation_error(exc)
        try:
            record = self._admin_state.add_group_member(request.group_id, request.user_id)
        except KeyError as exc:
            return self._err("group_member_add_failed", str(exc))
        self._sync_rbac()
        self._audit(
            "admin.group_add_member",
            "success",
            {"group_id": request.group_id, "user_id": request.user_id},
        )
        self._admin_state.emit_event(
            entity_type="group",
            action="add_member",
            entity_id=request.group_id,
            actor_id="system-admin-tool",
            source="tool",
            details={"user_id": request.user_id},
        )
        return self._ok(result=self._admin_state.export_group(record))

    def group_remove_member(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Remove one user from a configured group."""
        try:
            request = GroupMemberInput.model_validate(payload)
        except ValidationError as exc:
            return ImapToolHandlersBase._validation_error(exc)
        try:
            record = self._admin_state.remove_group_member(request.group_id, request.user_id)
        except KeyError as exc:
            return self._err("group_member_remove_failed", str(exc))
        self._sync_rbac()
        self._audit(
            "admin.group_remove_member",
            "success",
            {"group_id": request.group_id, "user_id": request.user_id},
        )
        self._admin_state.emit_event(
            entity_type="group",
            action="remove_member",
            entity_id=request.group_id,
            actor_id="system-admin-tool",
            source="tool",
            details={"user_id": request.user_id},
        )
        return self._ok(result=self._admin_state.export_group(record))

    def api_key_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        """List managed API keys without raw secret values."""
        try:
            request = APIKeyListInput.model_validate(payload)
        except ValidationError as exc:
            return ImapToolHandlersBase._validation_error(exc)
        items = self._admin_state.list_api_keys()
        if request.owner_user_id:
            items = [item for item in items if item.owner_user_id == request.owner_user_id]
        return self._ok(result={"items": [self._admin_state.export_api_key(item) for item in items]})

    def api_key_create(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create one scoped API key."""
        try:
            request = APIKeyCreateInput.model_validate(payload)
        except ValidationError as exc:
            return ImapToolHandlersBase._validation_error(exc)
        try:
            raw_key, record = self._admin_state.create_api_key(
                payload=request.model_dump(exclude_none=True),
                api_key_manager=self._api_key_manager,
            )
        except (KeyError, ValueError) as exc:
            return self._err("api_key_create_failed", str(exc))
        self._audit("admin.api_key_create", "success", {"api_key_id": record.api_key_id})
        self._admin_state.emit_event(
            entity_type="api_key",
            action="create",
            entity_id=record.api_key_id,
            actor_id="system-admin-tool",
            source="tool",
            details={"owner_user_id": record.owner_user_id, "scopes": record.scopes},
        )
        result = self._admin_state.export_api_key(record)
        result["raw_key"] = raw_key
        return self._ok(result=result)

    def api_key_revoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Revoke one managed API key."""
        try:
            request = APIKeyRevokeInput.model_validate(payload)
        except ValidationError as exc:
            return ImapToolHandlersBase._validation_error(exc)
        if not self._admin_state.revoke_api_key(request.api_key_id, self._api_key_manager):
            return self._err("api_key_not_found", request.api_key_id)
        self._audit("admin.api_key_revoke", "success", {"api_key_id": request.api_key_id})
        self._admin_state.emit_event(
            entity_type="api_key",
            action="revoke",
            entity_id=request.api_key_id,
            actor_id="system-admin-tool",
            source="tool",
        )
        return self._ok(result={"api_key_id": request.api_key_id})


