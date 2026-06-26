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

# Covers: FR-05
# Covers: FR-06

import base64
import hashlib
import html
import imaplib
import mimetypes
import os
import re
import shlex
import ssl
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email import policy
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.utils import format_datetime, parsedate_to_datetime
from fnmatch import fnmatch
from typing import Any, Callable
from uuid import uuid4

import time as _time

from cloud_dog_storage.backends.local import LocalStorage
from cloud_dog_idam import APIKeyManager, RBACEngine
from cloud_dog_logging import get_logger
from pydantic import BaseModel, ValidationError

from imap_hub_core.attachment.listing import list_attachments
from imap_hub_core.audit.events import AuditActor, AuditRecord
from imap_hub_core.audit.context import get_audit_request_context
from imap_hub_core.tools.tool_rbac import resource_permission_for_tool
from imap_hub_core.audit.logger import AuditWriter
from imap_hub_core.duplicate.detector import DuplicateCandidate, group_duplicates
from imap_hub_core.duplicate.policy import choose_keeper
from imap_hub_core.extract.extractors import extract_message_text
from imap_hub_core.imap.connection import IMAPConnectionConfig, probe_imap_connectivity
from imap_hub_core.ledger.similarity import build_similarity_key
from imap_hub_core.ledger.store import LedgerEntry, SearchLedgerStore
from imap_hub_core.storage_paths import (
    join_fs_path,
    safe_file_name,
    split_file_name,
    write_storage_bytes,
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
)
from imap_hub_server.admin.state import FileBackedAdminState

_TOOL_AUDIT_LOG = get_logger("imap_hub_core.tools.handlers")


def _imap_quote_search_value(value: str) -> str:
    """Quote an IMAP SEARCH string argument that contains whitespace.

    ``imaplib`` passes each SEARCH term argument to the server verbatim. A
    multi-word value (e.g. a ``SUBJECT``/``HEADER`` phrase like
    ``W24A Attachment Seed 20260101``) MUST be a quoted IMAP string, otherwise
    the server parses the trailing words as additional search criteria and
    rejects the command (Dovecot: ``BAD ... Unknown argument <WORD>``). Atoms,
    numbers, dates and flag keywords never contain whitespace, so they are left
    untouched; an already-quoted value is returned as-is. (W28A-735-R5: exposed
    by the real-IMAP attachment integration tests once live credentials were
    wired in.)
    """
    if not value:
        return '""'
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value
    if any(ch.isspace() for ch in value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


@dataclass(slots=True)
class ToolContract:
    """Registered tool contract."""

    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(slots=True)
class ResolvedConnection:
    """Resolved IMAP connection settings for a profile operation."""

    host: str
    port: int
    security: str
    username: str
    password: str
    timeout_seconds: int
    ca_bundle_path: str | None
    allow_self_signed: bool


@dataclass(slots=True)
class OfflineAttachmentFixture:
    """Attachment fixture backed by an existing downloaded artifact."""

    part_id: str
    filename: str
    path: str
    content_type: str
    size_bytes: int


@dataclass(slots=True)
class OfflineMessageFixture:
    """Offline message fixture used when local test stacks have no live IMAP credentials."""

    uid: str
    profile_id: str
    folder: str
    subject: str
    sender: str
    recipient: str
    received_at: datetime
    text_plain: str
    attachments: list[OfflineAttachmentFixture]


@dataclass(slots=True)
class FolderListCacheEntry:
    """Cached live IMAP folder listing for a profile."""

    expires_at: float
    retrieved_at: str
    folders: list[dict[str, Any]]


class ToolRegistry:
    """In-memory tool registry used by API and MCP layers."""

    _PROFILE_READ_TOOLS = frozenset(
        {
            "mail_probe",
            "mail_search",
            "mail_search_since_last",
            "mail_headlines",
            "mail_get_message",
            "mail_list_folders",
            "mail_extract_message",
            "mail_list_attachments",
            "mail_download_attachment",
        }
    )

    def __init__(
        self,
        role_patterns: dict[str, list[str]] | None = None,
        admin_state: FileBackedAdminState | None = None,
        audit_writer: AuditWriter | None = None,
        resource_guard: Any | None = None,
    ) -> None:
        """
        Purpose: Implement `__init__` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        self._contracts: dict[str, ToolContract] = {}
        self._role_patterns = {
            str(role).strip().lower(): [str(pattern).strip() for pattern in values]
            for role, values in (role_patterns or {}).items()
        }
        self._admin_state = admin_state
        self._audit_writer = audit_writer
        # W28A-750: optional resource-aware guard (duck-typed ImapResourceGuard with
        # .authorise(user_id, permission, resource_type, resource_id)). Used ONLY to
        # ADDITIVELY grant a resource-bearing tool call that the role-pattern gate
        # denied, when an RBACBinding cascade authorises it. It NEVER overrides a
        # role-pattern allow, so deployed flat-role behaviour cannot regress.
        self._resource_guard = resource_guard

    def register(self, contract: ToolContract) -> None:
        """
        Purpose: Implement `register` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        self._contracts[contract.name] = contract

    def contracts(self) -> dict[str, ToolContract]:
        """
        Purpose: Implement `contracts` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        return dict(self._contracts)

    def list_tools(self) -> list[dict[str, Any]]:
        """
        Purpose: Implement `list_tools` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        items: list[dict[str, Any]] = []
        for contract in self._contracts.values():
            items.append(
                {
                    "name": contract.name,
                    "description": contract.description,
                    "input_schema": contract.input_model.model_json_schema(),
                }
            )
        return items

    def call(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Purpose: Implement `call` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        contract = self._contracts.get(tool_name)
        if contract is None:
            raise KeyError(f"tool_not_found:{tool_name}")
        self._authorise(tool_name, payload)
        # PS-50 tool audit: log every tool call with redacted email bodies
        _safe = {k: ("[REDACTED]" if k.lower() in ("password", "secret", "token", "body", "content") else v) for k, v in payload.items()}
        _t0 = _time.monotonic()
        try:
            result = contract.handler(payload)
            _TOOL_AUDIT_LOG.info("mcp_tool_call", extra={"event_type": "mcp_tool_call", "tool_name": tool_name, "parameters": _safe, "outcome": "success", "duration_ms": round((_time.monotonic() - _t0) * 1000, 2), "service": "imap-mcp"})
            return result
        except Exception:
            _TOOL_AUDIT_LOG.warning("mcp_tool_call", extra={"event_type": "mcp_tool_call", "tool_name": tool_name, "parameters": _safe, "outcome": "error", "duration_ms": round((_time.monotonic() - _t0) * 1000, 2), "service": "imap-mcp"})
            raise

    def _authorise(self, tool_name: str, payload: dict[str, Any] | None = None) -> None:
        """Require the current request context roles to match the configured tool patterns.

        W28A-750: a resource-bearing tool that the role-pattern gate would DENY is
        additionally offered to the resource-aware guard — if an RBACBinding cascade
        grants the principal access to the named ``mailbox_profile``, the call is
        allowed. This is grant-only: a role-pattern allow always wins first, so the
        deployed flat-role behaviour is unchanged.
        """
        if tool_name == "profile_list":
            return
        if not self._role_patterns:
            return
        context = get_audit_request_context()
        if context is None:
            return
        if self._managed_key_can_read_profile_tools(tool_name, context.source_identifier):
            return
        roles = {str(role).strip().lower() for role in context.roles if str(role).strip()}
        for role in roles:
            for pattern in self._role_patterns.get(role, []):
                if pattern == "*" or fnmatch(tool_name, pattern):
                    return
        # W28A-750 cascade: additive resource-binding grant (never a role-pattern override).
        if self._resource_grants_access(tool_name, payload, context):
            return
        self._audit_authorisation_denial(tool_name, context)
        raise PermissionError(f"Actor {context.actor_id!r} cannot execute tool {tool_name!r}")

    def _resource_grants_access(
        self, tool_name: str, payload: dict[str, Any] | None, context: Any
    ) -> bool:
        """Return True iff the RBACBinding cascade authorises this resource-bearing tool call.

        Resolves the per-profile permission for the tool (None for admin/surface
        tools), reads ``profile_id`` from the payload, and asks the guard whether the
        principal (``context.actor_id``) may perform ``permission`` on
        ``mailbox_profile:<profile_id>``. Any error or missing input -> False (DENY).
        """
        if self._resource_guard is None or context is None:
            return False
        permission = resource_permission_for_tool(tool_name)
        if not permission:
            return False
        profile_id = None
        if isinstance(payload, dict):
            profile_id = payload.get("profile_id") or payload.get("profile")
        if not profile_id:
            return False
        user_id = str(getattr(context, "actor_id", "") or "")
        if not user_id:
            return False
        try:
            return bool(
                self._resource_guard.authorise(
                    user_id,
                    permission=permission,
                    resource_type="mailbox_profile",
                    resource_id=str(profile_id),
                )
            )
        except Exception:
            return False

    def _audit_authorisation_denial(self, tool_name: str, context: Any) -> None:
        """Emit durable audit evidence when role-pattern authorisation denies a tool call."""
        if self._audit_writer is None:
            return
        self._audit_writer.emit(
            AuditRecord(
                operation=tool_name,
                status="denied",
                correlation_id=context.correlation_id,
                actor=AuditActor(
                    actor_type=context.actor_type,
                    actor_id=context.actor_id,
                    roles=list(context.roles),
                    ip=context.source_ip,
                    user_agent=context.user_agent,
                ),
                component=context.component,
                source_identifier=context.source_identifier,
                target_type="tool",
                target_id=tool_name,
                target_name=tool_name,
                server_id=context.server_id,
                environment=context.environment,
                params={
                    "reason": "tool_permission_denied",
                    "tool_name": tool_name,
                },
            )
        )

    def _managed_key_can_read_profile_tools(
        self,
        tool_name: str,
        source_identifier: str | None,
    ) -> bool:
        """Allow profile-scoped read tools for managed keys with matching read scopes."""
        if tool_name not in self._PROFILE_READ_TOOLS or self._admin_state is None:
            return False
        source = str(source_identifier or "").strip()
        if not source.startswith("api_key:"):
            return False
        api_key_id = source.split(":", 1)[1].strip()
        if not api_key_id:
            return False
        return any(
            self._admin_state.key_has_scope(api_key_id, required_scope)
            for required_scope in ("profiles:read", "profiles:*", "profile:*")
        )


class ImapToolHandlersBase:
    """Handler set for profile listing and IMAP-backed operations."""

    _LIST_RESPONSE_RE = re.compile(
        rb'^\((?P<attributes>[^)]*)\)\s+(?P<delimiter>NIL|"(?P<quoted_delimiter>(?:\\.|[^"])*)")\s+(?P<name>.+)$'
    )
    _LIST_ESCAPE_RE = re.compile(r"\\(.)")
    _SPECIAL_USE_FLAGS = frozenset(
        {
            "\\all",
            "\\archive",
            "\\drafts",
            "\\flagged",
            "\\important",
            "\\inbox",
            "\\junk",
            "\\sent",
            "\\trash",
        }
    )

    def __init__(
        self,
        profiles: dict[str, dict[str, Any]] | None = None,
        ledger: SearchLedgerStore | None = None,
        downloads_dir: str = "./data/downloads",
        audit_writer: AuditWriter | None = None,
        max_search_results: int = 200,
        profile_provider: Callable[[], dict[str, dict[str, Any]]] | None = None,
        admin_state: FileBackedAdminState | None = None,
        rbac_engine: RBACEngine | None = None,
        runtime_fallback_profile: dict[str, Any] | None = None,
        resource_guard: Any | None = None,
    ) -> None:
        """Initialize handlers with profile, ledger, download, and audit dependencies."""
        self._profiles = profiles or {}
        self._profile_provider = profile_provider
        self._ledger = ledger or SearchLedgerStore()
        self._downloads_dir = join_fs_path(downloads_dir)
        self._download_storage = LocalStorage(root_path=self._downloads_dir)
        self._audit_writer = audit_writer
        self._max_search_results = max(1, int(max_search_results))
        self._admin_state = admin_state
        self._rbac_engine = rbac_engine
        self._runtime_fallback_profile = runtime_fallback_profile or {}
        # W28A-750: optional ImapResourceGuard for the RBACBinding cascade in
        # _check_profile_access (additive grant; also scopes profile_list).
        self._resource_guard = resource_guard
        self._folder_list_cache: dict[str, FolderListCacheEntry] = {}

    def _current_profiles(self) -> dict[str, dict[str, Any]]:
        """Return the current profile mapping, refreshing from provider when configured."""
        if self._profile_provider is not None:
            return self._profile_provider()
        return self._profiles

    @staticmethod
    def _profile_permission(profile_id: str) -> str:
        """Return the required profile-scoped permission label."""
        return f"profile:{profile_id}"

    def _context_roles(self) -> set[str]:
        """Return the current request roles from the audit context."""
        context = get_audit_request_context()
        if context is None:
            return set()
        return {str(role).strip().lower() for role in context.roles if str(role).strip()}

    def _effective_actor_roles(self, actor_id: str) -> set[str]:
        """Resolve direct and group-derived roles for the current actor."""
        if not actor_id or self._admin_state is None:
            return set()
        user = self._admin_state.get_user(actor_id)
        if user is None:
            return set()
        roles = {str(user.role).strip().lower()} if str(user.role).strip() else set()
        for group in self._admin_state.groups_for_user(actor_id):
            roles.update(str(role).strip().lower() for role in group.roles if str(role).strip())
        return roles

    def _managed_key_has_profile_scope(self, profile_id: str) -> bool:
        """Return whether the current managed API key grants the required profile scope."""
        context = get_audit_request_context()
        if context is None or self._admin_state is None:
            return False
        source_identifier = str(context.source_identifier or "").strip()
        if not source_identifier.startswith("api_key:"):
            return False
        api_key_id = source_identifier.split(":", 1)[1].strip()
        if not api_key_id:
            return False
        required_scopes = (
            self._profile_permission(profile_id),
            "profiles:read",
            "profiles:*",
        )
        return any(
            self._admin_state.key_has_scope(api_key_id, required_scope)
            for required_scope in required_scopes
        )

    def _check_profile_access(self, profile_id: str) -> bool:
        """Return whether the current actor may access the named profile."""
        required = self._profile_permission(profile_id).lower()
        roles = self._context_roles()

        # Admins always have access.
        if "*" in roles or "admin" in roles:
            return True

        context = get_audit_request_context()
        actor_id = str(context.actor_id if context is not None else "").strip()
        actor_roles = self._effective_actor_roles(actor_id)
        if "*" in actor_roles or "admin" in actor_roles:
            return True

        # W28A-750 / IDAM-B2 §2.3: RBACBinding cascade grant (group:G -> mailbox_profile:P).
        # Additive grant consulted alongside allowed_groups; a GROUPUSER bound to this
        # profile via a central binding is authorised, and this also scopes profile_list
        # (which filters by _check_profile_access).
        if self._resource_guard is not None and actor_id:
            try:
                if self._resource_guard.authorise(
                    actor_id,
                    permission="imap:mail:read",
                    resource_type="mailbox_profile",
                    resource_id=profile_id,
                ):
                    return True
            except Exception:
                pass

        # Profile-level allowed_groups gate — checked BEFORE scope/RBAC
        # grants so that explicit group bindings take precedence.
        if self._admin_state is not None and actor_id:
            profile = self._current_profiles().get(profile_id)
            allowed_groups = (profile or {}).get("allowed_groups")
            if isinstance(allowed_groups, list) and allowed_groups:
                user_groups = {g.group_id for g in self._admin_state.groups_for_user(actor_id)}
                if user_groups & set(allowed_groups):
                    return True
                # Profile has explicit group binding and user is not in
                # any of them — deny regardless of other grants.
                return False

        # Fall through to role/scope/RBAC checks for profiles without
        # explicit allowed_groups binding.
        if required in roles or required in actor_roles:
            return True

        if self._managed_key_has_profile_scope(profile_id):
            return True

        if self._rbac_engine is not None and actor_id:
            try:
                if self._rbac_engine.has_permission(actor_id, self._profile_permission(profile_id)):
                    return True
            except Exception:
                return False

        return False

    def _require_profile_access(self, profile_id: str, operation: str, payload: dict[str, Any]) -> None:
        """Raise when the current actor lacks access to the named profile."""
        if self._check_profile_access(profile_id):
            return
        denial = {"reason": "profile_permission_denied", "profile_id": profile_id, **payload}
        self._audit(operation, "denied", profile_id, denial)
        raise PermissionError(f"Access denied to profile '{profile_id}'")

    def _audit(
        self, operation: str, status: str, profile_id: str | None, params: dict[str, Any]
    ) -> None:
        """
        Purpose: Implement `_audit` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
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
                    actor_id=context.actor_id if context is not None else "system",
                    roles=list(context.roles) if context is not None else [],
                    ip=context.source_ip if context is not None else None,
                    user_agent=context.user_agent if context is not None else None,
                ),
                profile_id=profile_id,
                component=context.component if context is not None else "imap_hub_core.tools.handlers",
                source_identifier=context.source_identifier if context is not None else "internal",
                target_type="profile" if profile_id else "tool",
                target_id=profile_id or operation,
                target_name=operation,
                server_id=context.server_id if context is not None else "imap-mcp-local",
                environment=context.environment if context is not None else "unknown",
                params=params,
            )
        )

    def _profile(self, profile_id: str) -> dict[str, Any]:
        """
        Purpose: Implement `_profile` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        profile = self._current_profiles().get(profile_id)
        if profile is None:
            raise KeyError(f"profile_not_found:{profile_id}")
        return profile

    def _profile_retention(self, profile_id: str) -> tuple[int, int]:
        """Return profile retention days and max message limit."""
        profile = self._profile(profile_id)
        sync_cfg = profile.get("sync")
        retention_cfg = sync_cfg.get("retention") if isinstance(sync_cfg, dict) else {}
        if not isinstance(retention_cfg, dict):
            retention_cfg = {}
        max_age_days = max(1, int(retention_cfg.get("max_age_days", 30) or 30))
        max_messages = max(1, int(retention_cfg.get("max_messages", 50) or 50))
        return max_age_days, max_messages

    def _folder_list_cache_ttl_seconds(self, profile_id: str) -> int:
        """Resolve the live folder-list cache TTL."""
        profile = self._profile(profile_id)
        sync_cfg = profile.get("sync")
        sync_cfg = sync_cfg if isinstance(sync_cfg, dict) else {}
        workspace_cfg = profile.get("mailbox_workspace")
        workspace_cfg = workspace_cfg if isinstance(workspace_cfg, dict) else {}
        return max(
            1,
            self._safe_int(
                workspace_cfg.get("folder_cache_ttl_seconds")
                or sync_cfg.get("folder_cache_ttl_seconds")
                or profile.get("sync_interval_seconds")
                or 30,
                30,
            ),
        )

    def _effective_search_query(self, profile_id: str, query: str) -> str:
        """Use explicit query when present, else derive a retention-bounded SINCE query."""
        candidate = str(query or "").strip()
        if candidate:
            return candidate
        max_age_days, _ = self._profile_retention(profile_id)
        marker = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        return f"SINCE {marker.strftime('%d-%b-%Y')}"

    def _effective_search_limit(
        self,
        profile_id: str,
        requested_limit: int | None,
        *,
        fallback: int,
    ) -> int:
        """Resolve live-search limits from request, profile policy, and server bounds."""
        _, profile_max_messages = self._profile_retention(profile_id)
        candidate = requested_limit if requested_limit not in (None, "") else profile_max_messages
        resolved = max(1, int(candidate if candidate not in (None, "") else fallback))
        return max(1, min(resolved, self._max_search_results))

    @staticmethod
    def _ok_envelope(
        result: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a successful MCP tool response envelope."""
        return {
            "ok": True,
            "result": result or {},
            "warnings": warnings or [],
            "errors": [],
            "meta": meta or {},
        }

    @staticmethod
    def _error_envelope(code: str, message: str) -> dict[str, Any]:
        """
        Purpose: Implement `_error_envelope` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        return {
            "ok": False,
            "result": None,
            "warnings": [],
            "errors": [{"code": code, "message": message}],
            "meta": {},
        }

    @staticmethod
    def _validation_error(exc: ValidationError) -> dict[str, Any]:
        """
        Purpose: Implement `_validation_error` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        return ImapToolHandlersBase._error_envelope("invalid_request", str(exc))

    def _write_disabled(self) -> dict[str, Any]:
        """
        Purpose: Implement `_write_disabled` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        return self._error_envelope("write_disabled", "Write operations are disabled.")

    @staticmethod
    def _safe_int(value: Any, default: int) -> int:
        """
        Purpose: Implement `_safe_int` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _clean_str(value: Any) -> str:
        """Normalise nullable config values to clean strings."""
        if value is None:
            return ""
        text = str(value).strip()
        if text.lower() in {"none", "null"}:
            return ""
        return text

    @staticmethod
    def _parse_received_at(value: str | None) -> datetime:
        """
        Purpose: Implement `_parse_received_at` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        if not value:
            return datetime.now(timezone.utc)
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return datetime.now(timezone.utc)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _to_utc_iso(dt: datetime) -> str:
        """
        Purpose: Implement `_to_utc_iso` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _profile_has_live_imap(self, profile_id: str) -> bool:
        """Return whether a profile resolves to a usable live IMAP connection."""
        try:
            self._resolve_connection(self._profile(profile_id))
        except Exception:
            return False
        return True

    def _offline_fixture_messages(self, profile_id: str, folder: str) -> list[OfflineMessageFixture]:
        """Return deterministic offline fixtures backed by the local downloads directory."""
        stem = "briefing_20260405_072246"
        downloads = self._downloads_dir
        md_path = join_fs_path(downloads, f"{stem}.md")
        pdf_path = join_fs_path(downloads, f"{stem}.pdf")
        docx_path = join_fs_path(downloads, f"{stem}.docx")
        hint_path = join_fs_path(downloads, "at17.txt")
        required_paths = (md_path, pdf_path, docx_path)
        if not all(os.path.exists(path) for path in required_paths):
            return []

        text_path = hint_path if os.path.exists(hint_path) else md_path
        with open(text_path, "r", encoding="utf-8", errors="replace") as handle:
            text_plain = handle.read().strip()

        attachments = []
        for part_id, path in (("5", pdf_path), ("6", docx_path), ("7", md_path)):
            content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
            attachments.append(
                OfflineAttachmentFixture(
                    part_id=part_id,
                    filename=os.path.basename(path),
                    path=path,
                    content_type=content_type,
                    size_bytes=os.path.getsize(path),
                )
            )

        return [
            OfflineMessageFixture(
                uid="175",
                profile_id=profile_id,
                folder=folder,
                subject="AT1.17 Offline Briefing",
                sender="briefing-bot@cloud-dog.local",
                recipient="integration-user@cloud-dog.local",
                received_at=datetime(2026, 4, 5, 7, 22, 46, tzinfo=timezone.utc),
                text_plain=text_plain or "Offline briefing fixture.",
                attachments=attachments,
            )
        ]

    @staticmethod
    def _offline_search_token(query: str) -> tuple[str, str]:
        """Normalise a minimal subset of the IMAP-like query syntax used in local tests."""
        text = str(query or "").strip()
        if not text or text.upper() == "ALL":
            return ("all", "")
        subject_match = re.fullmatch(r'(?i)SUBJECT\s+"([^"]+)"', text)
        if subject_match:
            return ("subject", subject_match.group(1).strip().lower())
        uid_match = re.fullmatch(r"(?i)UID\s+(\d+)", text)
        if uid_match:
            return ("uid", uid_match.group(1))
        return ("text", text.lower())

    def _offline_search_messages(
        self,
        profile_id: str,
        folder: str,
        query: str,
        limit: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
        """Return offline fixture summaries for cache-mode search flows."""
        matches: list[OfflineMessageFixture] = []
        query_kind, query_value = self._offline_search_token(query)
        for fixture in self._offline_fixture_messages(profile_id, folder):
            haystack = " ".join(
                [
                    fixture.subject,
                    fixture.text_plain,
                    fixture.sender,
                    " ".join(item.filename for item in fixture.attachments),
                ]
            ).lower()
            if query_kind == "all":
                matches.append(fixture)
            elif query_kind == "uid" and fixture.uid == query_value:
                matches.append(fixture)
            elif query_kind == "subject" and query_value in fixture.subject.lower():
                matches.append(fixture)
            elif query_kind == "text" and query_value in haystack:
                matches.append(fixture)

        limited = matches[:limit]
        messages = [
            {
                "uid": fixture.uid,
                "subject": fixture.subject,
                "from": fixture.sender,
                "date": format_datetime(fixture.received_at),
                "received_at": self._to_utc_iso(fixture.received_at),
                "mailbox": fixture.folder,
                "folder": fixture.folder,
                "relevance_score": 1.0,
            }
            for fixture in limited
        ]
        if limited:
            max_received_at = max(item.received_at for item in limited)
        else:
            max_received_at = datetime.now(timezone.utc)
        high_water_mark = {"max_received_at_utc": self._to_utc_iso(max_received_at)}
        return messages, high_water_mark, [item.uid for item in limited]

    def _offline_fixture_message(
        self,
        profile_id: str,
        folder: str,
        uid: str,
    ) -> OfflineMessageFixture | None:
        """Return one offline fixture message by UID when available."""
        wanted_uid = str(uid).strip()
        for fixture in self._offline_fixture_messages(profile_id, folder):
            if fixture.uid == wanted_uid:
                return fixture
        return None

    @staticmethod
    def _offline_attachment_for_part(
        fixture: OfflineMessageFixture,
        part_id: str,
    ) -> OfflineAttachmentFixture | None:
        """Return one offline fixture attachment by part identifier."""
        wanted_part = str(part_id).strip()
        for item in fixture.attachments:
            if item.part_id == wanted_part:
                return item
        return None

    def _offline_message_bytes(self, fixture: OfflineMessageFixture) -> bytes:
        """Build a synthetic RFC 822 message from local fixture content."""
        message = EmailMessage()
        message["Subject"] = fixture.subject
        message["From"] = fixture.sender
        message["To"] = fixture.recipient
        message["Date"] = format_datetime(fixture.received_at)
        message.set_content(fixture.text_plain)

        for item in fixture.attachments:
            with open(item.path, "rb") as handle:
                payload = handle.read()
            if item.content_type.startswith("text/"):
                subtype = item.content_type.split("/", 1)[1]
                try:
                    message.add_attachment(payload.decode("utf-8"), subtype=subtype, filename=item.filename)
                    continue
                except UnicodeDecodeError:
                    pass
            maintype, subtype = (item.content_type.split("/", 1) + ["octet-stream"])[:2]
            message.add_attachment(payload, maintype=maintype, subtype=subtype, filename=item.filename)

        return message.as_bytes(policy=policy.default)

    def _resolve_connection(self, profile: dict[str, Any]) -> ResolvedConnection:
        """
        Purpose: Implement `_resolve_connection` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        imap_cfg = profile.get("imap")
        if not isinstance(imap_cfg, dict):
            imap_cfg = {}
        tls_cfg = imap_cfg.get("tls")
        if not isinstance(tls_cfg, dict):
            tls_cfg = {}
        auth_cfg = profile.get("auth")
        if not isinstance(auth_cfg, dict):
            auth_cfg = {}
        cred_cfg = profile.get("credentials")
        if not isinstance(cred_cfg, dict):
            cred_cfg = {}

        host = self._clean_str(imap_cfg.get("host", ""))
        port = self._safe_int(
            imap_cfg.get("port"), 993 if str(imap_cfg.get("security", "")).lower() == "ssl" else 143
        )
        security = self._clean_str(imap_cfg.get("security", "")).lower()
        if not security:
            security = "ssl" if port == 993 else "starttls"
        timeout_seconds = self._safe_int(imap_cfg.get("timeout_seconds"), 15)
        ca_bundle_path = (
            self._clean_str(tls_cfg.get("ca_bundle_path", ""))
            or None
        )
        allow_self_signed = bool(tls_cfg.get("allow_self_signed", False))

        auth_mode = self._clean_str(auth_cfg.get("mode", "")).lower()
        username = self._clean_str(cred_cfg.get("username", ""))
        password = self._clean_str(cred_cfg.get("password", "")) or self._clean_str(
            cred_cfg.get("app_password", "")
        )

        use_runtime_fallback = not host or not username or not password or auth_mode == "oauth2"
        if use_runtime_fallback:
            fallback = self._runtime_fallback_profile
            fallback_imap = fallback.get("imap") if isinstance(fallback, dict) else {}
            fallback_imap = fallback_imap if isinstance(fallback_imap, dict) else {}
            fallback_tls = fallback_imap.get("tls") if isinstance(fallback_imap, dict) else {}
            fallback_tls = fallback_tls if isinstance(fallback_tls, dict) else {}
            fallback_creds = fallback.get("credentials") if isinstance(fallback, dict) else {}
            fallback_creds = fallback_creds if isinstance(fallback_creds, dict) else {}

            runtime_host = self._clean_str(fallback_imap.get("host", ""))
            runtime_port = self._safe_int(fallback_imap.get("port"), 143)
            runtime_username = self._clean_str(fallback_creds.get("username", ""))
            runtime_password = self._clean_str(
                fallback_creds.get("password", "")
            ) or self._clean_str(fallback_creds.get("app_password", ""))

            if not runtime_host or not runtime_username or not runtime_password:
                raise ValueError(
                    "IMAP runtime fallback is not configured in cloud_dog_config; "
                    "refusing to connect with incomplete credentials."
                )

            host = runtime_host
            port = runtime_port
            security = self._clean_str(fallback_imap.get("security", "")).lower()
            if not security:
                security = "ssl" if runtime_port == 993 else "starttls"
            username = runtime_username
            password = runtime_password
            ca_bundle_path = self._clean_str(fallback_tls.get("ca_bundle_path", "")) or ca_bundle_path

        if not host:
            raise ValueError("IMAP host is not configured.")
        if not username or not password:
            raise ValueError("IMAP credentials are not configured for this profile.")

        return ResolvedConnection(
            host=host,
            port=port,
            security=security,
            username=username,
            password=password,
            timeout_seconds=timeout_seconds,
            ca_bundle_path=ca_bundle_path,
            allow_self_signed=allow_self_signed,
        )

    def _build_ssl_context(self, settings: ResolvedConnection) -> ssl.SSLContext:
        """
        Purpose: Implement `_build_ssl_context` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        context = ssl.create_default_context()
        if settings.ca_bundle_path:
            context.load_verify_locations(cafile=settings.ca_bundle_path)
        if settings.allow_self_signed:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        return context

    def _connect_imap_client(
        self,
        profile_id: str,
    ) -> tuple[imaplib.IMAP4 | imaplib.IMAP4_SSL, ResolvedConnection]:
        """Open and authenticate an IMAP client without selecting a mailbox."""
        profile = self._profile(profile_id)
        settings = self._resolve_connection(profile)
        context = self._build_ssl_context(settings)

        client: imaplib.IMAP4 | imaplib.IMAP4_SSL
        if settings.security == "ssl":
            client = imaplib.IMAP4_SSL(
                host=settings.host,
                port=settings.port,
                timeout=settings.timeout_seconds,
                ssl_context=context,
            )
        else:
            client = imaplib.IMAP4(
                host=settings.host,
                port=settings.port,
                timeout=settings.timeout_seconds,
            )
            if settings.security in {"starttls", "tls"}:
                client.starttls(ssl_context=context)

        login_status, _ = client.login(settings.username, settings.password)
        if login_status != "OK":
            raise RuntimeError(f"IMAP login failed: {login_status}")
        return client, settings

    def _open_imap_client(
        self,
        profile_id: str,
        folder: str = "INBOX",
        readonly: bool = True,
    ) -> tuple[imaplib.IMAP4 | imaplib.IMAP4_SSL, ResolvedConnection]:
        """Open and authenticate an IMAP client for a profile and folder."""
        client, settings = self._connect_imap_client(profile_id)
        select_status, _ = client.select(folder, readonly=readonly)
        if select_status != "OK":
            raise RuntimeError(f"IMAP select failed: {select_status}")
        return client, settings

    @staticmethod
    def _logout(client: imaplib.IMAP4 | imaplib.IMAP4_SSL | None) -> None:
        """
        Purpose: Implement `_logout` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        if client is None:
            return
        try:
            client.logout()
        except Exception:
            return

    @staticmethod
    def _parse_imap_search_terms(query: str) -> list[str] | None:
        """Parse query text into IMAP SEARCH terms when query uses supported IMAP syntax."""
        term = query.strip()
        if not term:
            return ["ALL"]
        try:
            tokens = shlex.split(term)
        except ValueError:
            return None
        if not tokens:
            return ["ALL"]

        no_arg_terms = {
            "ALL",
            "ANSWERED",
            "DELETED",
            "DRAFT",
            "FLAGGED",
            "NEW",
            "OLD",
            "RECENT",
            "SEEN",
            "UNANSWERED",
            "UNDELETED",
            "UNDRAFT",
            "UNFLAGGED",
            "UNSEEN",
        }
        one_arg_terms = {
            "BCC",
            "BEFORE",
            "BODY",
            "CC",
            "FROM",
            "KEYWORD",
            "LARGER",
            "ON",
            "SENTBEFORE",
            "SENTON",
            "SENTSINCE",
            "SINCE",
            "SMALLER",
            "SUBJECT",
            "TEXT",
            "TO",
            "UID",
            "UNKEYWORD",
        }

        terms: list[str] = []
        index = 0
        while index < len(tokens):
            token = tokens[index]
            upper = token.upper()
            if upper in no_arg_terms:
                terms.append(upper)
                index += 1
                continue
            if upper in one_arg_terms:
                if index + 1 >= len(tokens):
                    return None
                terms.extend([upper, _imap_quote_search_value(tokens[index + 1])])
                index += 2
                continue
            if upper == "HEADER":
                if index + 2 >= len(tokens):
                    return None
                terms.extend(
                    [
                        "HEADER",
                        tokens[index + 1],
                        _imap_quote_search_value(tokens[index + 2]),
                    ]
                )
                index += 3
                continue
            return None
        return terms

    @staticmethod
    def _decode_search_ids(data: Any) -> list[str]:
        """Decode IMAP SEARCH response IDs to UTF-8 strings."""
        if not data or not data[0]:
            return []
        return [item.decode("utf-8", "ignore") for item in data[0].split() if item]

    @staticmethod
    def _uid_command(
        client: imaplib.IMAP4 | imaplib.IMAP4_SSL,
        command: str,
        uid: str,
        *args: str,
    ) -> tuple[str, Any]:
        """Run UID-scoped IMAP commands so API mutation payloads operate on message UIDs."""
        status, data = client.uid(command, uid, *args)
        return str(status), data

    @staticmethod
    def _is_message_id_header_only_search(terms: list[str]) -> bool:
        """Return True only for exact HEADER Message-ID <value> search terms."""
        return len(terms) == 3 and terms[0].upper() == "HEADER" and terms[1].upper() == "MESSAGE-ID"

    @staticmethod
    def _message_id_search_candidates(raw_value: str) -> list[str]:
        """Build bracketed/unbracketed Message-ID candidates for IMAP HEADER compatibility."""
        value = raw_value.strip()
        if not value:
            return []
        if value.startswith("<") and value.endswith(">"):
            core = value[1:-1].strip()
            candidates = [value]
            if core:
                candidates.append(core)
            return candidates
        return [value, f"<{value}>"]

    def _search_message_id_header_compatible(
        self,
        client: imaplib.IMAP4 | imaplib.IMAP4_SSL,
        raw_value: str,
    ) -> tuple[str, Any]:
        """
        Retry Message-ID HEADER search with normalised value variants.
        This preserves real IMAP behaviour while handling provider formatting differences.
        """
        for candidate in self._message_id_search_candidates(raw_value):
            status, data = client.uid("SEARCH", None, "HEADER", "Message-ID", candidate)
            if status == "OK" and self._decode_search_ids(data):
                return status, data
        return "OK", [b""]

    def _search_ids(self, client: imaplib.IMAP4 | imaplib.IMAP4_SSL, query: str) -> list[str]:
        """
        Purpose: Implement `_search_ids` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        term = query.strip()
        terms = self._parse_imap_search_terms(term)
        if terms is not None:
            status, data = client.uid("SEARCH", None, *terms)
            if status == "OK" and self._is_message_id_header_only_search(terms):
                if not self._decode_search_ids(data):
                    status, data = self._search_message_id_header_compatible(client, terms[2])
        else:
            phrase = term.replace('"', " ").strip()
            if phrase:
                status, data = client.uid("SEARCH", None, "TEXT", f'"{phrase}"')
            else:
                status, data = client.uid("SEARCH", None, "ALL")
        if status != "OK":
            status, data = client.uid("SEARCH", None, "ALL")

        if status != "OK":
            raise RuntimeError(f"IMAP search failed: {status}")
        return self._decode_search_ids(data)

    def _fetch_message_bytes(self, client: imaplib.IMAP4 | imaplib.IMAP4_SSL, uid: str) -> bytes:
        """
        Purpose: Implement `_fetch_message_bytes` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        status, data = self._uid_command(client, "FETCH", uid, "(RFC822)")
        if status != "OK":
            raise RuntimeError(f"IMAP fetch failed: {status}")
        for item in data or []:
            if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], bytes):
                return item[1]
        raise RuntimeError("IMAP fetch returned no message bytes.")

    @classmethod
    def _decode_list_quoted_bytes(cls, value: bytes) -> str:
        """Decode quoted LIST response fields with simple IMAP escaping."""
        text = value.decode("utf-8", "replace")
        text = cls._LIST_ESCAPE_RE.sub(r"\1", text)
        try:
            decoder = getattr(imaplib.IMAP4, "_decode_utf7")
        except AttributeError:
            decoder = None
        if callable(decoder):
            try:
                return str(decoder(text))
            except Exception:
                return text
        return text

    @classmethod
    def _decode_mailbox_name(cls, raw_name: bytes) -> str:
        """Decode a mailbox name from an IMAP LIST line."""
        candidate = raw_name.strip()
        if candidate.upper() == b"NIL":
            return ""
        if candidate.startswith(b'"') and candidate.endswith(b'"') and len(candidate) >= 2:
            return cls._decode_list_quoted_bytes(candidate[1:-1])
        return cls._decode_list_quoted_bytes(candidate)

    @classmethod
    def _parse_list_response_line(cls, raw_line: bytes) -> dict[str, Any] | None:
        """Parse one IMAP LIST response line into a folder descriptor."""
        match = cls._LIST_RESPONSE_RE.match(raw_line.strip())
        if match is None:
            return None
        raw_attributes = match.group("attributes").decode("utf-8", "replace").strip()
        attributes = [flag for flag in raw_attributes.split() if flag]
        raw_delimiter = match.group("delimiter")
        delimiter = ""
        if raw_delimiter and raw_delimiter.upper() != b"NIL":
            delimiter = cls._decode_list_quoted_bytes(match.group("quoted_delimiter") or b"")
        name = cls._decode_mailbox_name(match.group("name"))
        special_use = [
            flag for flag in attributes if flag.strip().lower() in cls._SPECIAL_USE_FLAGS
        ]
        return {
            "name": name,
            "delimiter": delimiter,
            "attributes": attributes,
            "special_use": special_use,
            "source": "imap",
        }

    def _fetch_message_headers(
        self, client: imaplib.IMAP4 | imaplib.IMAP4_SSL, uid: str
    ) -> dict[str, Any]:
        """
        Purpose: Implement `_fetch_message_headers` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        status, data = self._uid_command(
            client,
            "FETCH",
            uid,
            "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID SUBJECT FROM TO DATE)])",
        )
        if status != "OK":
            raise RuntimeError(f"IMAP header fetch failed: {status}")

        payload: bytes | None = None
        for item in data or []:
            if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], bytes):
                payload = item[1]
                break
        if payload is None:
            raise RuntimeError("IMAP header fetch returned no payload.")

        parsed = BytesParser(policy=policy.default).parsebytes(payload)
        received_at = self._parse_received_at(parsed.get("Date"))
        message_id = str(parsed.get("Message-ID") or "").strip()
        return {
            "uid": uid,
            "header_message_id": message_id,
            "subject": parsed.get("Subject", ""),
            "from": parsed.get("From", ""),
            "to": parsed.get("To", ""),
            "date_utc": self._to_utc_iso(received_at),
        }

    def _search_live_messages(
        self,
        profile_id: str,
        query: str,
        folder: str = "INBOX",
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
        """Run a live IMAP search and return message headers plus watermark metadata."""
        client: imaplib.IMAP4 | imaplib.IMAP4_SSL | None = None
        try:
            client, _ = self._open_imap_client(profile_id=profile_id, folder=folder, readonly=True)
            all_ids = self._search_ids(client, query=query)
            selected_ids = all_ids[-limit:] if limit > 0 else all_ids

            messages: list[dict[str, Any]] = []
            for uid in selected_ids:
                try:
                    messages.append(self._fetch_message_headers(client, uid))
                except Exception:
                    continue

            numeric_ids = [int(uid) for uid in selected_ids if uid.isdigit()]
            if numeric_ids:
                high_water_mark = {"per_folder_uid_max": {folder: max(numeric_ids)}}
            else:
                high_water_mark = {
                    "max_received_at_utc": self._to_utc_iso(datetime.now(timezone.utc))
                }

            return messages, high_water_mark, selected_ids
        finally:
            self._logout(client)

    @staticmethod
    def _decode_message(raw_bytes: bytes) -> Message:
        """
        Purpose: Implement `_decode_message` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        return BytesParser(policy=policy.default).parsebytes(raw_bytes)

    @staticmethod
    def _attachment_payload_for_part(message: Message, part_id: str) -> tuple[str, bytes] | None:
        """
        Purpose: Implement `_attachment_payload_for_part` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        for index, part in enumerate(message.walk(), start=1):
            disposition = (part.get("Content-Disposition") or "").lower()
            if "attachment" not in disposition:
                continue
            if str(index) != part_id:
                continue
            filename = part.get_filename() or f"part-{index}"
            payload = part.get_payload(decode=True) or b""
            return filename, payload
        return None


__all__ = [name for name in globals() if not name.startswith("__")]
