"""Per-tool RBAC enforcement for imap-mcp MCP tools (PS-70 UM3).

Provides a centralised TOOL_PERMISSION_MAP and enforcement helper
using cloud_dog_idam.RBACEngine.has_permission for per-tool checks.

Related: W28A-763, PS-70 UM3, PS-50
"""

from __future__ import annotations

from typing import Dict

from cloud_dog_idam import RBACEngine

# Per-tool permission map (PS-70 UM3 resource:action format)
_TOOL_PERMISSION_MAP: Dict[str, str] = {
    # Mail operations
    "mail_fetch": "imap:mail:read",
    "mail_search": "imap:mail:read",
    "mail_get": "imap:mail:read",
    "mail_get_message": "imap:mail:read",
    "mail_list_attachments": "imap:mail:read",
    "mail_download_attachment": "imap:mail:read",
    "mail_delete": "imap:mail:delete",
    "mail_delete_messages": "imap:mail:delete",
    "mail_move": "imap:mail:write",
    "mail_move_messages": "imap:mail:write",
    "mail_move_duplicates_since_last_search": "imap:mail:write",
    "mail_flag": "imap:mail:write",
    "mail_set_seen": "imap:mail:write",
    # Folder operations
    "folder_list": "imap:folder:read",
    "mail_list_folders": "imap:folder:read",
    "folder_create": "imap:folder:write",
    "folder_delete": "imap:folder:delete",
    "folder_rename": "imap:folder:write",
    # Index/sync operations
    "index_sync": "imap:index:write",
    "index_rebuild": "imap:index:write",
    "index_status": "imap:index:read",
    # W28E-1870-D mail-profile change-watch (PS-102 §7 RBAC): read verbs need the
    # profile read grant, mutating lifecycle verbs need the profile write grant.
    # Scoped to a mailbox_profile so the RBACBinding cascade applies.
    "imap_watch_list": "imap:mail:read",
    "imap_watch_status": "imap:mail:read",
    "imap_watch_get_batch": "imap:mail:read",
    "imap_watch_ack": "imap:mail:read",
    "imap_watch_recover": "imap:mail:read",
    "imap_watch_create": "imap:mail:write",
    "imap_watch_pause": "imap:mail:write",
    "imap_watch_resume": "imap:mail:write",
    "imap_watch_delete": "imap:mail:write",
    "imap_watch_test_event": "imap:mail:write",
    # Admin operations
    "admin_list_profiles": "imap:admin:*",
    "admin_create_profile": "imap:admin:*",
    "admin_delete_profile": "imap:admin:*",
    "admin_list_users": "imap:admin:*",
    "admin_create_user": "imap:admin:*",
    "admin_create_api_key": "imap:admin:*",
    "admin_revoke_api_key": "imap:admin:*",
}


def has_permission_for_tool(engine: RBACEngine, user_id: str, tool_name: str) -> bool:
    """Check per-tool RBAC via cloud_dog_idam.RBACEngine.has_permission."""
    required = _TOOL_PERMISSION_MAP.get(tool_name, "imap:tool:execute")
    return engine.has_permission(user_id, required)


def require_permission_for_tool(engine: RBACEngine, user_id: str, tool_name: str) -> None:
    """Raise PermissionError if per-tool RBAC check fails."""
    if not has_permission_for_tool(engine, user_id, tool_name):
        raise PermissionError(f"User {user_id!r} lacks permission for tool {tool_name!r}")


# W28A-750 / IDAM-B2 §2.3 — resource-bearing tools are scoped to a mailbox_profile.
# A tool keyed on profile_id (mail/folder/index ops) is gated against the
# RBACBinding cascade; imap:admin:* and imap:tool:execute are surface gates, not
# resource-bearing, so they are NOT cascade-scoped.
_RESOURCE_BEARING_PREFIXES = ("imap:mail:", "imap:folder:", "imap:index:")


def resource_permission_for_tool(tool_name: str) -> str | None:
    """Return the mailbox_profile-scoped permission for a resource-bearing tool, else None.

    Used by the additive resource-aware authorisation in ``ToolRegistry`` (W28A-750):
    only tools whose permission is one of the per-profile prefixes participate in the
    group->resource cascade; admin/surface tools do not.
    """
    perm = _TOOL_PERMISSION_MAP.get(tool_name)
    if perm and any(perm.startswith(prefix) for prefix in _RESOURCE_BEARING_PREFIXES):
        return perm
    return None
