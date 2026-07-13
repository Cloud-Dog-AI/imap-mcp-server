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

"""Mail change-watch tool handlers (PS-102 §5.3 / CSTREAM-IMAP-001/002).

Thin MCP/A2A/REST tool glue over the :class:`WatchService` adapter. Each handler
resolves the tenant scope (the mail profile) and the acting principal from the
shared audit request context, calls the adapter, and maps common change-stream
errors to the service's error envelope. No journal/cursor/queue/broadcaster logic
lives here — it is all consumed from the common foundation via ``WatchService``.
"""

from __future__ import annotations

from typing import Any

from cloud_dog_api_kit.change_stream.errors import ChangeStreamError

from imap_hub_core.audit.context import get_audit_request_context
from imap_hub_core.change_stream import WatchService

# Read verbs need the profile-read scope; mutating lifecycle verbs need write.
WATCH_READ_TOOLS = frozenset(
    {"imap_watch_list", "imap_watch_status", "imap_watch_get_batch", "imap_watch_ack",
     "imap_watch_recover"}
)
WATCH_WRITE_TOOLS = frozenset(
    {"imap_watch_create", "imap_watch_pause", "imap_watch_resume", "imap_watch_delete",
     "imap_watch_test_event"}
)
WATCH_TOOLS = WATCH_READ_TOOLS | WATCH_WRITE_TOOLS


def watch_permission_for_tool(tool_name: str) -> str | None:
    """Return the required RBAC permission label for a watch tool (or None).

    PS-102 §7: read verbs require the profile read grant, mutating lifecycle
    verbs require the profile write grant. The resolved permission is per-profile
    (``profile:<id>``) and enforced by the registry role-pattern / resource guard.
    """
    if tool_name in WATCH_READ_TOOLS:
        return "read"
    if tool_name in WATCH_WRITE_TOOLS:
        return "write"
    return None


class WatchToolHandlers:
    """Dispatch the ``imap_watch_*`` tool family onto a :class:`WatchService`."""

    def __init__(self, watch_service: WatchService) -> None:
        self._ws = watch_service

    # -- helpers ------------------------------------------------------
    @staticmethod
    def _tenant(payload: dict[str, Any]) -> str:
        """Resolve the change-watch tenant scope from the payload (mail profile)."""
        return str(payload.get("profile_id") or payload.get("profile") or "default")

    @staticmethod
    def _actor() -> str:
        context = get_audit_request_context()
        if context is not None and str(getattr(context, "actor_id", "")).strip():
            return str(context.actor_id).strip()
        return "mcp"

    @staticmethod
    def _correlation_id() -> str | None:
        context = get_audit_request_context()
        if context is not None:
            cid = str(getattr(context, "correlation_id", "")).strip()
            return cid or None
        return None

    @staticmethod
    def _ok(result: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "result": result, "warnings": [], "errors": [], "meta": {}}

    @staticmethod
    def _error(exc: ChangeStreamError) -> dict[str, Any]:
        detail = exc.to_dict() if hasattr(exc, "to_dict") else {"code": "error", "message": str(exc)}
        return {"ok": False, "result": None, "warnings": [], "errors": [detail], "meta": {}}

    # -- tool handlers ------------------------------------------------
    def watch_create(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._ok(
                self._ws.create_watch(
                    profile_id=self._tenant(payload),
                    tenant_id=self._tenant(payload),
                    actor=self._actor(),
                    criteria=payload.get("criteria") if isinstance(payload.get("criteria"), dict) else None,
                    max_batch=int(payload.get("max_batch", 100)),
                    max_inflight=int(payload.get("max_inflight", 4)),
                    journal_max=int(payload.get("journal_max", 1000)),
                    journal_ttl_seconds=(
                        float(payload["journal_ttl_seconds"])
                        if payload.get("journal_ttl_seconds") not in (None, "")
                        else None
                    ),
                )
            )
        except ChangeStreamError as exc:
            return self._error(exc)

    def watch_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._ok({"watches": self._ws.list_watches(tenant_id=self._tenant(payload))})

    def watch_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._ok(self._ws.get_status(str(payload["watch_id"]), tenant_id=self._tenant(payload)))
        except ChangeStreamError as exc:
            return self._error(exc)

    def watch_get_batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._ok(
                self._ws.get_batch(
                    str(payload["watch_id"]),
                    tenant_id=self._tenant(payload),
                    since_cursor=payload.get("since_cursor") or None,
                    max_batch=int(payload["max_batch"]) if payload.get("max_batch") else None,
                )
            )
        except ChangeStreamError as exc:
            return self._error(exc)

    def watch_ack(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._ok(
                self._ws.ack(
                    str(payload["watch_id"]),
                    tenant_id=self._tenant(payload),
                    ack_cursor=str(payload["ack_cursor"]),
                )
            )
        except ChangeStreamError as exc:
            return self._error(exc)

    def watch_recover(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._ok(
                self._ws.recover(
                    str(payload["watch_id"]),
                    tenant_id=self._tenant(payload),
                    since_cursor=payload.get("since_cursor") or None,
                )
            )
        except ChangeStreamError as exc:
            return self._error(exc)

    def watch_pause(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._ok(self._ws.pause(str(payload["watch_id"]), tenant_id=self._tenant(payload)))
        except ChangeStreamError as exc:
            return self._error(exc)

    def watch_resume(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._ok(self._ws.resume(str(payload["watch_id"]), tenant_id=self._tenant(payload)))
        except ChangeStreamError as exc:
            return self._error(exc)

    def watch_delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._ok(self._ws.delete(str(payload["watch_id"]), tenant_id=self._tenant(payload)))
        except ChangeStreamError as exc:
            return self._error(exc)

    def watch_test_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        extra = {
            k: v
            for k, v in payload.items()
            if k not in {"watch_id", "tenant_id", "profile", "profile_id", "actor",
                         "action", "object_ref"}
        }
        try:
            return self._ok(
                self._ws.test_event(
                    str(payload["watch_id"]),
                    tenant_id=self._tenant(payload),
                    action=str(payload.get("action", "created")),
                    object_ref=str(payload.get("object_ref", "test")),
                    **extra,
                )
            )
        except ChangeStreamError as exc:
            return self._error(exc)


__all__ = [
    "WatchToolHandlers",
    "watch_permission_for_tool",
    "WATCH_TOOLS",
    "WATCH_READ_TOOLS",
    "WATCH_WRITE_TOOLS",
]
