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

from typing import Any, Callable

from cloud_dog_idam import APIKeyManager, RBACEngine

from imap_hub_core.audit.logger import AuditWriter
from imap_hub_core.ledger.store import SearchLedgerStore
from imap_hub_core.tools.admin_handler import AdminToolHandlers
from imap_hub_core.tools.base_handler import (
    OfflineAttachmentFixture,
    OfflineMessageFixture,
    ResolvedConnection,
    ToolContract,
    ToolRegistry,
)
from imap_hub_core.tools.definitions import (
    APIKeyCreateInput,
    APIKeyListInput,
    APIKeyRevokeInput,
    GroupCreateInput,
    GroupDeleteInput,
    GroupGetInput,
    GroupMemberInput,
    GroupUpdateInput,
    MailDeleteMessagesInput,
    MailDownloadAttachmentInput,
    MailExtractMessageInput,
    MailGetMessageInput,
    MailHeadlinesInput,
    MailListAttachmentsInput,
    MailListFoldersInput,
    MailMoveDuplicatesInput,
    MailMoveMessagesInput,
    MailProbeInput,
    MailSearchInput,
    MailSearchSinceLastInput,
    MailSetSeenInput,
    ProfileListInput,
    UserCreateInput,
    UserDeleteInput,
    UserGetInput,
    UserUpdateInput,
    WatchAckInput,
    WatchCreateInput,
    WatchGetBatchInput,
    WatchIdInput,
    WatchListInput,
    WatchRecoverInput,
    WatchTestEventInput,
)
from imap_hub_core.tools.read_handler import ReadToolHandlers
from imap_hub_core.tools.search_handler import SearchToolHandlers
from imap_hub_core.tools.watch_handler import WatchToolHandlers
from imap_hub_core.tools.write_handler import WriteToolHandlers
from imap_hub_server.admin.state import FileBackedAdminState


class ImapToolHandlers(SearchToolHandlers, ReadToolHandlers, WriteToolHandlers):
    """Composed IMAP tool handlers split by operation category."""


def build_default_tool_registry(
    profiles: dict[str, dict[str, Any]],
    downloads_dir: str,
    audit_writer: AuditWriter | None = None,
    admin_state: FileBackedAdminState | None = None,
    api_key_manager: APIKeyManager | None = None,
    rbac_engine: RBACEngine | None = None,
    rbac_roles: dict[str, list[str]] | None = None,
    max_search_results: int = 200,
    profile_provider: Callable[[], dict[str, dict[str, Any]]] | None = None,
    runtime_fallback_profile: dict[str, Any] | None = None,
    resource_guard: Any | None = None,
    watch_service: Any | None = None,
) -> ToolRegistry:
    """Build the default tool registry with IMAP handlers.

    ``resource_guard`` (W28A-750, duck-typed ``ImapResourceGuard``) is supplied by
    the imap_hub_server layer so the registry can additively authorise
    resource-bearing tools via the RBACBinding cascade. Optional: when ``None`` the
    registry behaves exactly as before (role-pattern gate only).

    ``watch_service`` (W28E-1870-D, duck-typed ``WatchService``) is supplied by the
    imap_hub_server layer so the registry can expose the mail-profile change-watch
    tool family (PS-102 §5.3 / CSTREAM-IMAP-001/002). When ``None`` an isolated
    in-memory ``WatchService`` is built so the tools register and work in the unit
    tier without a live DB — the durable journal only activates when a real
    ``cloud_dog_db`` engine is wired in by the server surface.
    """
    handlers = ImapToolHandlers(
        profiles=profiles,
        ledger=SearchLedgerStore(),
        downloads_dir=downloads_dir,
        audit_writer=audit_writer,
        max_search_results=max_search_results,
        profile_provider=profile_provider,
        admin_state=admin_state,
        rbac_engine=rbac_engine,
        runtime_fallback_profile=runtime_fallback_profile,
        resource_guard=resource_guard,
    )
    if admin_state is None:
        admin_state = FileBackedAdminState("./data")
    if api_key_manager is None:
        api_key_manager = APIKeyManager()
    admin_handlers = AdminToolHandlers(
        admin_state=admin_state,
        api_key_manager=api_key_manager,
        rbac_engine=rbac_engine,
        audit_writer=audit_writer,
    )
    registry = ToolRegistry(
        role_patterns=rbac_roles,
        admin_state=admin_state,
        audit_writer=audit_writer,
        resource_guard=resource_guard,
    )
    registry.register(
        ToolContract(
            name="profile_list",
            description="List configured profiles.",
            input_model=ProfileListInput,
            handler=handlers.profile_list,
        )
    )
    registry.register(
        ToolContract(
            name="user_list",
            description="List configured users.",
            input_model=ProfileListInput,
            handler=admin_handlers.user_list,
        )
    )
    registry.register(
        ToolContract(
            name="user_get",
            description="Get one configured user.",
            input_model=UserGetInput,
            handler=admin_handlers.user_get,
        )
    )
    registry.register(
        ToolContract(
            name="user_create",
            description="Create one configured user.",
            input_model=UserCreateInput,
            handler=admin_handlers.user_create,
        )
    )
    registry.register(
        ToolContract(
            name="user_update",
            description="Update one configured user.",
            input_model=UserUpdateInput,
            handler=admin_handlers.user_update,
        )
    )
    registry.register(
        ToolContract(
            name="user_delete",
            description="Delete one configured user.",
            input_model=UserDeleteInput,
            handler=admin_handlers.user_delete,
        )
    )
    registry.register(
        ToolContract(
            name="group_list",
            description="List configured groups.",
            input_model=ProfileListInput,
            handler=admin_handlers.group_list,
        )
    )
    registry.register(
        ToolContract(
            name="group_get",
            description="Get one configured group.",
            input_model=GroupGetInput,
            handler=admin_handlers.group_get,
        )
    )
    registry.register(
        ToolContract(
            name="group_create",
            description="Create one configured group.",
            input_model=GroupCreateInput,
            handler=admin_handlers.group_create,
        )
    )
    registry.register(
        ToolContract(
            name="group_update",
            description="Update one configured group.",
            input_model=GroupUpdateInput,
            handler=admin_handlers.group_update,
        )
    )
    registry.register(
        ToolContract(
            name="group_delete",
            description="Delete one configured group.",
            input_model=GroupDeleteInput,
            handler=admin_handlers.group_delete,
        )
    )
    registry.register(
        ToolContract(
            name="group_add_member",
            description="Add one user to a configured group.",
            input_model=GroupMemberInput,
            handler=admin_handlers.group_add_member,
        )
    )
    registry.register(
        ToolContract(
            name="group_remove_member",
            description="Remove one user from a configured group.",
            input_model=GroupMemberInput,
            handler=admin_handlers.group_remove_member,
        )
    )
    registry.register(
        ToolContract(
            name="api_key_list",
            description="List managed API keys.",
            input_model=APIKeyListInput,
            handler=admin_handlers.api_key_list,
        )
    )
    registry.register(
        ToolContract(
            name="api_key_create",
            description="Create one scoped API key.",
            input_model=APIKeyCreateInput,
            handler=admin_handlers.api_key_create,
        )
    )
    registry.register(
        ToolContract(
            name="api_key_revoke",
            description="Revoke one managed API key.",
            input_model=APIKeyRevokeInput,
            handler=admin_handlers.api_key_revoke,
        )
    )
    registry.register(
        ToolContract(
            name="mail_probe",
            description="Probe IMAP connectivity for a profile.",
            input_model=MailProbeInput,
            handler=handlers.mail_probe,
        )
    )
    registry.register(
        ToolContract(
            name="mail_search",
            description="Search for messages using configured mode.",
            input_model=MailSearchInput,
            handler=handlers.mail_search,
        )
    )
    registry.register(
        ToolContract(
            name="mail_search_since_last",
            description="Resolve delta results since the last similar search.",
            input_model=MailSearchSinceLastInput,
            handler=handlers.mail_search_since_last,
        )
    )
    registry.register(
        ToolContract(
            name="mail_headlines",
            description="Return concise subject/from/date headlines for search results.",
            input_model=MailHeadlinesInput,
            handler=handlers.mail_headlines,
        )
    )
    registry.register(
        ToolContract(
            name="mail_move_duplicates_since_last_search",
            description="Plan or execute duplicate message moves.",
            input_model=MailMoveDuplicatesInput,
            handler=handlers.mail_move_duplicates_since_last_search,
        )
    )
    registry.register(
        ToolContract(
            name="mail_get_message",
            description="Fetch a message payload.",
            input_model=MailGetMessageInput,
            handler=handlers.mail_get_message,
        )
    )
    registry.register(
        ToolContract(
            name="mail_list_folders",
            description="List live IMAP folders for a profile.",
            input_model=MailListFoldersInput,
            handler=handlers.mail_list_folders,
        )
    )
    registry.register(
        ToolContract(
            name="mail_list_attachments",
            description="List attachment metadata for a message.",
            input_model=MailListAttachmentsInput,
            handler=handlers.mail_list_attachments,
        )
    )
    registry.register(
        ToolContract(
            name="mail_download_attachment",
            description="Download a message attachment to local storage.",
            input_model=MailDownloadAttachmentInput,
            handler=handlers.mail_download_attachment,
        )
    )
    registry.register(
        ToolContract(
            name="mail_extract_message",
            description="Extract message content to JSON and/or Markdown.",
            input_model=MailExtractMessageInput,
            handler=handlers.mail_extract_message,
        )
    )
    registry.register(
        ToolContract(
            name="mail_set_seen",
            description="Set seen state on message UIDs.",
            input_model=MailSetSeenInput,
            handler=handlers.mail_set_seen,
        )
    )
    registry.register(
        ToolContract(
            name="mail_move_messages",
            description="Move messages between folders.",
            input_model=MailMoveMessagesInput,
            handler=handlers.mail_move_messages,
        )
    )
    registry.register(
        ToolContract(
            name="mail_delete_messages",
            description="Delete messages from a folder.",
            input_model=MailDeleteMessagesInput,
            handler=handlers.mail_delete_messages,
        )
    )
    # -- W28E-1870-D mail-profile change-watch tools (PS-102 §5.3 / CSTREAM-IMAP) --
    # A thin adapter over the common ``cloud_dog_api_kit.change_stream`` foundation.
    # When no durable ``watch_service`` is supplied by the server surface, build an
    # isolated in-memory one so the tools register and function in the unit tier.
    if watch_service is None:
        from imap_hub_core.change_stream import WatchService as _WatchService

        watch_service = _WatchService()
    watch_handlers = WatchToolHandlers(watch_service)
    registry.register(
        ToolContract(
            name="imap_watch_create",
            description="Create a mail-profile change-watch with criteria (folder, sender, "
            "recipient, subject, header/body, attachment, flags, glob/regex). Returns the "
            "watch id and status.",
            input_model=WatchCreateInput,
            handler=watch_handlers.watch_create,
        )
    )
    registry.register(
        ToolContract(
            name="imap_watch_list",
            description="List the caller's mail-profile change-watches for the current profile.",
            input_model=WatchListInput,
            handler=watch_handlers.watch_list,
        )
    )
    registry.register(
        ToolContract(
            name="imap_watch_status",
            description="Return a change-watch status (state, journal depth, cursors, in-flight, throttle).",
            input_model=WatchIdInput,
            handler=watch_handlers.watch_status,
        )
    )
    registry.register(
        ToolContract(
            name="imap_watch_get_batch",
            description="Retrieve a bounded batch of mail change events for a watch since a "
            "cursor, with the next cursor. Respects max_batch and backpressure.",
            input_model=WatchGetBatchInput,
            handler=watch_handlers.watch_get_batch,
        )
    )
    registry.register(
        ToolContract(
            name="imap_watch_ack",
            description="Acknowledge progress on a change-watch up to a cursor, releasing an in-flight batch slot.",
            input_model=WatchAckInput,
            handler=watch_handlers.watch_ack,
        )
    )
    registry.register(
        ToolContract(
            name="imap_watch_recover",
            description="Re-enquire a safe resume cursor for a change-watch without a replay storm.",
            input_model=WatchRecoverInput,
            handler=watch_handlers.watch_recover,
        )
    )
    registry.register(
        ToolContract(
            name="imap_watch_pause",
            description="Pause a change-watch; it retains its cursor and journal within retention.",
            input_model=WatchIdInput,
            handler=watch_handlers.watch_pause,
        )
    )
    registry.register(
        ToolContract(
            name="imap_watch_resume",
            description="Resume a paused change-watch.",
            input_model=WatchIdInput,
            handler=watch_handlers.watch_resume,
        )
    )
    registry.register(
        ToolContract(
            name="imap_watch_delete",
            description="Delete a change-watch and its journal.",
            input_model=WatchIdInput,
            handler=watch_handlers.watch_delete,
        )
    )
    registry.register(
        ToolContract(
            name="imap_watch_test_event",
            description="Inject a deterministic synthetic mail change event into a watch's "
            "journal (test-mode, no external IMAP mutation).",
            input_model=WatchTestEventInput,
            handler=watch_handlers.watch_test_event,
        )
    )
    return registry


__all__ = [
    "AdminToolHandlers",
    "ImapToolHandlers",
    "OfflineAttachmentFixture",
    "OfflineMessageFixture",
    "ResolvedConnection",
    "ToolContract",
    "ToolRegistry",
    "build_default_tool_registry",
]
