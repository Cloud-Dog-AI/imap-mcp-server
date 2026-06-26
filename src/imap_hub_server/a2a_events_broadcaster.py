"""imap-mcp-server A2A events broadcaster (CFG-06 → platform primitive).

Covers: CFG-06
Related: PS-72 §A2A-change-events, W28A-1002-CONV-IMAP-MCP.

Wraps the existing cross-process JSONL file-queue written by
``FileBackedAdminState.emit_event()`` (authoritative source-of-truth) as
an ``EventBroadcaster`` (Protocol per cloud_dog_api_kit.a2a.events).

Publishers (admin REST routes and MCP tool handlers) continue to call
``admin_state.emit_event(...)`` which appends a legacy-envelope JSON
line (``event_id/timestamp/entity_type/action/entity_id/actor_id/source/
outcome/details``) to ``{data_dir}/config_events.jsonl``.

This broadcaster runs a background tail-task that polls the file for
new lines at ~poll_interval seconds (default 0.25s, matching the
pre-CONV implementation cadence) and fans out through platform
subscriber primitives:

* **legacy-dict** — raw JSON-decoded dicts wrapped in platform
  ConfigChangeEvents, consumed by the inline legacy WS ``/a2a/events``
  handler so the wire shape visible to the admin-SPA client remains
  byte-for-byte unchanged.
* **canonical ConfigChangeEvent** — synthesised on-the-fly so the
  platform SSE router (``create_a2a_events_router``) mounted additively
  at ``/a2a/events/sse`` emits PS-72 11-field envelopes.

The broadcaster also implements ``history(after_id, limit)`` for
canonical consumers by reading the tail of the JSONL file and
synthesising the newest events.
"""

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

import asyncio
import json
import os
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from cloud_dog_api_kit.a2a.events import (
    ConfigChangeEvent,
    EventBroadcaster,
    InMemoryEventBroadcaster,
)

# Canonical PS-72 §A2A-change-events resource names. ConfigEvent.entity_type
# on the wire is already singular (``user``/``group``/``api_key``/``profile``)
# so the canonical mapping is identity — kept explicit so unknown entity_type
# values are still emitted verbatim.
_ENTITY_TO_RESOURCE = {
    "user": "user",
    "group": "group",
    "api_key": "api_key",
    "profile": "profile",
}

# Actions whose details payload describes the prior state (``before``).
_DELETE_LIKE_ACTIONS = {"delete", "remove_member", "revoke"}


def _parse_iso8601(value: Any) -> datetime:
    """Best-effort parse of a legacy ConfigEvent.timestamp ("...Z") string."""
    if isinstance(value, datetime):
        ts = value
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    if isinstance(value, str) and value:
        try:
            normalised = value.replace("Z", "+00:00") if value.endswith("Z") else value
            ts = datetime.fromisoformat(normalised)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return ts
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _legacy_payload_to_canonical_event(
    payload: dict[str, Any],
    *,
    service: str,
    event_id: int = 0,
) -> ConfigChangeEvent:
    """Translate one legacy ConfigEvent dict to a PS-72 ConfigChangeEvent.

    See the CONV-2 sql-agent pattern (W28A-1002-CONV-SQL-AGENT) — this is
    the imap-mcp equivalent for the legacy 9-field envelope
    ``{event_id, timestamp, entity_type, action, entity_id, actor_id,
    source, outcome, details}``.
    """
    action = str(payload.get("action") or "").strip() or "update"
    entity_type_raw = str(payload.get("entity_type") or "").strip()
    resource = _ENTITY_TO_RESOURCE.get(entity_type_raw, entity_type_raw or "unknown")
    identifier = str(payload.get("entity_id") or "")
    actor = payload.get("actor_id")
    actor_str = str(actor).strip() if actor is not None else None
    if actor_str == "":
        actor_str = None
    details = payload.get("details") or {}
    if not isinstance(details, dict):
        details = {}
    # Delete-like verbs: the legacy ``details`` describes the state being
    # removed; treat as ``before``. Otherwise treat as ``after``.
    if action.lower() in _DELETE_LIKE_ACTIONS:
        before: dict[str, Any] | None = details or None
        after: dict[str, Any] | None = None
    else:
        before = None
        after = details or None
    outcome = str(payload.get("outcome") or "success").strip() or "success"
    ts = _parse_iso8601(payload.get("timestamp"))
    return ConfigChangeEvent(
        service=service,
        resource=resource,
        action=action,
        identifier=identifier,
        actor=actor_str,
        correlation_id=None,
        before=before,
        after=after,
        outcome=outcome,
        timestamp=ts,
        event_id=event_id,
    )


class _ImapMcpServiceBackedBroadcaster:
    """Tail the ``config_events.jsonl`` file-queue and fan out.

    Implements the ``cloud_dog_api_kit.a2a.events.EventBroadcaster``
    Protocol (``publish``, ``subscribe``, ``history``). ``publish`` is
    a NO-OP writer for incoming canonical events — publishers of the
    imap-mcp service continue to go through ``admin_state.emit_event``
    which is the authoritative durable channel. ``publish`` still
    accepts a ConfigChangeEvent (for Protocol conformance and to allow
    the canonical SSE router to forward events it might receive from
    future callers) and fans it out in-process without touching the
    file.

    Args:
        store_path: absolute path to the JSONL file-queue.
        service: canonical service identifier (PS-72 ``service`` field).
        poll_interval_seconds: tail-poll cadence. Default 0.25s — matches
            the pre-CONV inline WS handler.
        history_size: in-memory retained canonical-event window for
            the SSE ``history()`` endpoint.
        subscriber_queue_size: per-subscriber fan-out queue depth.
    """

    def __init__(
        self,
        store_path: str,
        *,
        service: str = "imap-mcp-server",
        poll_interval_seconds: float = 0.25,
        history_size: int = 1000,
        subscriber_queue_size: int = 256,
    ) -> None:
        if history_size <= 0:
            raise ValueError("history_size must be positive")
        if subscriber_queue_size <= 0:
            raise ValueError("subscriber_queue_size must be positive")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        self._store_path = store_path
        self._service = service
        self._poll_interval = float(poll_interval_seconds)
        self._offset = 0
        self._canonical_broadcaster: EventBroadcaster = InMemoryEventBroadcaster(
            history_size=int(history_size),
            subscriber_queue_size=int(subscriber_queue_size),
        )
        self._legacy_broadcaster: EventBroadcaster = InMemoryEventBroadcaster(
            history_size=int(history_size),
            subscriber_queue_size=int(subscriber_queue_size),
        )
        self._watcher_task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()

    # ------------------------------------------------------------------ properties
    @property
    def store_path(self) -> str:
        """Path to the tailed JSONL file-queue."""
        return self._store_path

    @property
    def service(self) -> str:
        """Canonical ``service`` identifier emitted in ConfigChangeEvent."""
        return self._service

    @property
    def subscriber_count(self) -> int:
        """Number of active canonical subscribers (for observability/tests)."""
        return int(getattr(self._canonical_broadcaster, "subscriber_count", 0))

    @property
    def legacy_subscriber_count(self) -> int:
        """Number of active legacy-dict subscribers (inline WS clients)."""
        return int(getattr(self._legacy_broadcaster, "subscriber_count", 0))

    # ------------------------------------------------------------------ lifecycle
    def start_watcher(self, *, rewind: bool = True) -> None:
        """Kick off the background tail-task.

        Args:
            rewind: when True (default), seed in-memory history with all
                existing JSONL lines before entering the polling loop,
                so canonical SSE ``history()`` returns cross-restart
                durable content.
        """
        if self._watcher_task is not None and not self._watcher_task.done():
            return
        self._stopped.clear()
        self._watcher_task = asyncio.create_task(self._watcher_loop(rewind=rewind))

    async def stop_watcher(self) -> None:
        """Stop the background tail-task (idempotent)."""
        self._stopped.set()
        task = self._watcher_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._watcher_task = None

    # ------------------------------------------------------------------ protocol
    async def publish(self, event: ConfigChangeEvent) -> ConfigChangeEvent:
        """Stamp a canonical event id and fan out in-process only.

        NOT a durable writer — the file-queue is written exclusively by
        ``FileBackedAdminState.emit_event()``. Callers that route
        canonical events through ``publish`` (e.g. a future platform
        service mesh ingest) will reach SSE subscribers but will NOT
        reach the legacy WS handler unless also persisted via
        ``admin_state.emit_event``. This matches PS-72 behaviour where
        the canonical envelope is authoritative and legacy surfaces are
        a presentation transform over the durable log.
        """
        return await self._canonical_broadcaster.publish(event)

    async def subscribe(self) -> AsyncIterator[ConfigChangeEvent]:
        """Async iterator of live canonical ConfigChangeEvents."""
        async for event in self._canonical_broadcaster.subscribe():
            yield event

    def history(self, after_id: int = 0, limit: int = 100) -> list[ConfigChangeEvent]:
        """Return recent canonical events with ``event_id > after_id``."""
        return self._canonical_broadcaster.history(after_id=after_id, limit=limit)

    # ------------------------------------------------------------------ legacy surface
    async def subscribe_legacy(self) -> AsyncIterator[dict[str, Any]]:
        """Yield raw legacy-dict events for the inline WS handler.

        The iterator is backed by the platform A2A broadcaster and
        receives a JSON-decoded dict per appended JSONL line, preserving
        the 9-field legacy envelope.
        """
        async for event in self._legacy_broadcaster.subscribe():
            payload = event.after if isinstance(event.after, dict) else {}
            yield dict(payload)

    # ------------------------------------------------------------------ internals
    def _current_size(self) -> int:
        try:
            return os.path.getsize(self._store_path)
        except FileNotFoundError:
            return 0
        except OSError:
            return 0

    async def _rewind_history(self) -> None:
        """Seed in-memory canonical history from existing JSONL content."""
        if not os.path.isfile(self._store_path):
            self._offset = 0
            return
        try:
            with open(self._store_path, "rb") as fh:
                data = fh.read()
        except OSError:
            self._offset = 0
            return
        self._offset = len(data)
        text = data.decode("utf-8", errors="replace")
        for line in text.splitlines():
            payload = self._decode_line(line)
            if payload is None:
                continue
            canonical = _legacy_payload_to_canonical_event(payload, service=self._service)
            await self._canonical_broadcaster.publish(canonical)

    @staticmethod
    def _decode_line(line: str) -> dict[str, Any] | None:
        line = line.strip()
        if not line:
            return None
        try:
            data = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    async def _watcher_loop(self, *, rewind: bool) -> None:
        """Poll the JSONL file for new lines and dispatch."""
        if rewind:
            await self._rewind_history()
        else:
            self._offset = self._current_size()
        while not self._stopped.is_set():
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Never let the watcher die — next tick tries again.
                pass
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self._poll_interval)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                raise

    async def _poll_once(self) -> None:
        """Read any newly-appended lines from the JSONL file and dispatch."""
        try:
            stat_size = os.path.getsize(self._store_path)
        except FileNotFoundError:
            return
        except OSError:
            return
        if stat_size < self._offset:
            # File rotated / truncated externally — restart from the top.
            self._offset = 0
        if stat_size == self._offset:
            return
        try:
            with open(self._store_path, "rb") as fh:
                fh.seek(self._offset)
                chunk = fh.read(stat_size - self._offset)
        except OSError:
            return
        self._offset = stat_size
        text = chunk.decode("utf-8", errors="replace")
        for line in text.splitlines():
            payload = self._decode_line(line)
            if payload is None:
                continue
            await self._dispatch_payload(payload)

    async def _dispatch_payload(self, payload: dict[str, Any]) -> None:
        """Fan out one legacy payload through platform subscriber primitives."""
        canonical = _legacy_payload_to_canonical_event(payload, service=self._service)
        await self._canonical_broadcaster.publish(canonical)
        await self._legacy_broadcaster.publish(
            ConfigChangeEvent(
                service=self._service,
                resource="legacy_config_event",
                action=str(payload.get("action") or "update"),
                identifier=str(payload.get("event_id") or ""),
                after=dict(payload),
                outcome=str(payload.get("outcome") or "success"),
                timestamp=_parse_iso8601(payload.get("timestamp")),
            )
        )


__all__ = [
    "_ImapMcpServiceBackedBroadcaster",
    "_legacy_payload_to_canonical_event",
]
