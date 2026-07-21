# imap-mcp-server change-watch service.

# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# imap-mcp-server mail-change service adapter.
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

"""imap-mcp mail-profile change-watch adapter (PS-102 §4.2, CSTREAM-IMAP-001/002).

Requirements: FR-24, FR-25, CS-016.

``WatchService`` is a *thin adapter* over the common change-stream foundation
published in ``cloud_dog_api_kit.change_stream`` (PS-102 §9 / RULES §1.4). It:

* builds a :class:`~cloud_dog_api_kit.change_stream.WatchCoordinator` whose
  per-watch journal is the durable :class:`SqlJournal` (backed by the service's
  ``cloud_dog_db`` engine) so a watch backlog survives restart (CSTREAM-007);
* wires the coordinator's ``on_emit`` hook to the service's existing
  ``cloud_dog_api_kit.a2a.events`` broadcaster via ``make_broadcast_hook`` for
  live SSE fan-out (PS-102 §5.2) — no bespoke broadcaster;
* wires the coordinator's ``audit_sink`` to ``cloud_dog_logging`` /
  ``AuditWriter`` (CSTREAM-010);
* enforces RBAC/tenancy at the adapter boundary via ``cloud_dog_idam`` — a watch
  is scoped to a tenant + mail profile; cross-tenant reads are a hard failure
  (CSTREAM-009);
* translates observed IMAP mailbox mutations (message arrival / flag change /
  move / expunge) into the canonical :class:`ChangeEvent` envelope, keyed by
  mailbox/folder/UID+UIDVALIDITY, and emits them to every *live* watch whose
  criteria match (CSTREAM-IMAP-001/002).

This adapter re-implements NO journal, cursor, queue, broadcaster, RBAC, or error
model — all of that is consumed from the foundation.
"""

from __future__ import annotations

import contextlib
import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from cloud_dog_api_kit.change_stream import (
    ACTIONS,
    ChangeEvent,
    WatchCoordinator,
    WatchSpec,
    make_broadcast_hook,
)
from cloud_dog_api_kit.change_stream.db_journal import SqlJournal
from cloud_dog_api_kit.change_stream.errors import InvalidCriteria, WatchNotFound
from cloud_dog_api_kit.change_stream.journal import InMemoryJournal, Journal

from imap_hub_core.change_stream.criteria import (
    MailChangeCandidate,
    validate_criteria,
)
from imap_hub_core.change_stream.criteria import (
    match as criteria_match,
)

SERVICE_ID = "imap-mcp"
_SOURCE_TYPE = "imap_folder"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WatchService:
    """Per-service change-watch adapter binding the common coordinator to mail ops.

    Args:
        service_id: stable service identifier for the envelope (``imap-mcp``).
        engine: an optional SQLAlchemy ``Engine`` (from ``cloud_dog_db``). When
            supplied, watches journal durably via :class:`SqlJournal`; when
            ``None`` (unit tests / no DB), a bounded in-memory journal is used so
            the adapter still functions without a live database.
        broadcaster: an optional ``cloud_dog_api_kit.a2a.events`` broadcaster; when
            supplied, emitted events fan out live via ``make_broadcast_hook``.
        audit_sink: optional ``(kind, mapping)`` callable — the service wires
            ``cloud_dog_logging`` / ``AuditWriter`` here.
        broadcast_scheduler: optional scheduler for the (async) broadcast publish
            so the sync emit path never blocks a worker (CSTREAM-002).
    """

    def __init__(
        self,
        *,
        service_id: str = SERVICE_ID,
        engine: Any | None = None,
        broadcaster: Any | None = None,
        audit_sink: Callable[[str, Mapping[str, Any]], None] | None = None,
        broadcast_scheduler: Callable[[Any], None] | None = None,
    ) -> None:
        self._service_id = service_id
        self._engine = engine
        self._lock = threading.RLock()
        # watch_id -> declarative spec view (tenant/profile/criteria) kept for
        # criteria evaluation + RBAC scoping. The coordinator owns state/journal.
        self._specs: dict[str, WatchSpec] = {}
        self._criteria: dict[str, Mapping[str, Any]] = {}

        on_emit = None
        if broadcaster is not None:
            on_emit = make_broadcast_hook(broadcaster, scheduler=broadcast_scheduler)

        # Ensure the durable journal table exists once (idempotent).
        if engine is not None:
            with contextlib.suppress(Exception):  # pragma: no cover - schema may already exist
                SqlJournal.create_schema(engine)

        self._coordinator = WatchCoordinator(
            journal_factory=self._journal_factory,
            on_emit=on_emit,
            audit_sink=audit_sink,
        )

    # ------------------------------------------------------------------
    # journal factory (durable SqlJournal, else bounded in-memory)
    # ------------------------------------------------------------------
    def _journal_factory(self, spec: WatchSpec) -> Journal:
        if self._engine is not None:
            return SqlJournal(
                self._engine,
                spec.watch_id,
                max_size=spec.journal_max,
                ttl_seconds=spec.journal_ttl_seconds,
            )
        return InMemoryJournal(max_size=spec.journal_max, ttl_seconds=spec.journal_ttl_seconds)

    @property
    def coordinator(self) -> WatchCoordinator:
        return self._coordinator

    # ------------------------------------------------------------------
    # RBAC / tenancy boundary (CSTREAM-009)
    # ------------------------------------------------------------------
    def _require_owner(self, watch_id: str, tenant_id: str) -> WatchSpec:
        """Return the spec if the caller's tenant owns the watch, else raise.

        Cross-tenant / cross-profile access is a hard failure — the watch is
        scoped to the tenant it was created under (PS-102 §7). Existence is not
        leaked across tenants: a foreign watch reports ``WatchNotFound``.
        """
        spec = self._specs.get(watch_id)
        if spec is None:
            raise WatchNotFound(f"no watch {watch_id!r}")
        if tenant_id is not None and spec.tenant_id != tenant_id:
            raise WatchNotFound(f"no watch {watch_id!r}")
        return spec

    # ------------------------------------------------------------------
    # lifecycle (create/list/status/pause/resume/delete) — PS-102 §5.1
    # ------------------------------------------------------------------
    def create_watch(
        self,
        *,
        profile_id: str,
        tenant_id: str,
        actor: str,
        criteria: Mapping[str, Any] | None = None,
        max_batch: int = 100,
        max_inflight: int = 4,
        journal_max: int = 1000,
        journal_ttl_seconds: float | None = None,
        watch_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_criteria = dict(criteria or {})
        validate_criteria(resolved_criteria)
        if max_batch < 1 or max_inflight < 1 or journal_max < 1:
            raise InvalidCriteria("max_batch, max_inflight and journal_max must be >= 1")
        wid = watch_id or f"mailw-{uuid.uuid4().hex[:16]}"
        spec = WatchSpec(
            watch_id=wid,
            service_id=self._service_id,
            profile_id=profile_id,
            tenant_id=tenant_id,
            actor=actor,
            criteria=resolved_criteria,
            max_batch=max_batch,
            max_inflight=max_inflight,
            journal_max=journal_max,
            journal_ttl_seconds=journal_ttl_seconds,
        )
        with self._lock:
            status = self._coordinator.create_watch(spec)
            self._specs[wid] = spec
            self._criteria[wid] = resolved_criteria
        return self._watch_view(spec, status)

    def list_watches(self, *, tenant_id: str) -> list[dict[str, Any]]:
        with self._lock:
            out: list[dict[str, Any]] = []
            for wid, spec in self._specs.items():
                if spec.tenant_id != tenant_id:
                    continue
                out.append(self._watch_view(spec, self._coordinator.get_status(wid)))
            return out

    def get_watch(self, watch_id: str, *, tenant_id: str) -> dict[str, Any]:
        spec = self._require_owner(watch_id, tenant_id)
        return self._watch_view(spec, self._coordinator.get_status(watch_id))

    def get_status(self, watch_id: str, *, tenant_id: str) -> dict[str, Any]:
        self._require_owner(watch_id, tenant_id)
        return self._status_view(self._coordinator.get_status(watch_id))

    def pause(self, watch_id: str, *, tenant_id: str) -> dict[str, Any]:
        self._require_owner(watch_id, tenant_id)
        return self._status_view(self._coordinator.pause(watch_id))

    def resume(self, watch_id: str, *, tenant_id: str) -> dict[str, Any]:
        self._require_owner(watch_id, tenant_id)
        return self._status_view(self._coordinator.resume(watch_id))

    def delete(self, watch_id: str, *, tenant_id: str) -> dict[str, Any]:
        self._require_owner(watch_id, tenant_id)
        with self._lock:
            self._coordinator.delete(watch_id)
            self._specs.pop(watch_id, None)
            self._criteria.pop(watch_id, None)
        return {"watch_id": watch_id, "deleted": True}

    # ------------------------------------------------------------------
    # retrieval / ack / recover — PS-102 §5.2 (pull-batch base mode)
    # ------------------------------------------------------------------
    def get_batch(
        self,
        watch_id: str,
        *,
        tenant_id: str,
        since_cursor: str | None = None,
        max_batch: int | None = None,
    ) -> dict[str, Any]:
        self._require_owner(watch_id, tenant_id)
        result = self._coordinator.get_batch(
            watch_id, since_cursor=since_cursor, max_batch=max_batch
        )
        return WatchCoordinator.batch_to_dict(result, redact=True)

    def ack(self, watch_id: str, *, tenant_id: str, ack_cursor: str) -> dict[str, Any]:
        self._require_owner(watch_id, tenant_id)
        return self._status_view(self._coordinator.ack(watch_id, ack_cursor))

    def recover(
        self, watch_id: str, *, tenant_id: str, since_cursor: str | None = None
    ) -> dict[str, Any]:
        self._require_owner(watch_id, tenant_id)
        cursor = self._coordinator.recover(watch_id, since_cursor=since_cursor)
        return {"watch_id": watch_id, "resume_cursor": cursor}

    def test_event(
        self,
        watch_id: str,
        *,
        tenant_id: str,
        action: str = "created",
        object_ref: str = "test",
        **meta: Any,
    ) -> dict[str, Any]:
        """Inject a deterministic synthetic event (PS-102 §5.8), no IMAP mutation."""
        self._require_owner(watch_id, tenant_id)
        if action not in ACTIONS:
            raise InvalidCriteria(f"unknown action verb {action!r}")
        seq = self._coordinator.test_event(
            watch_id, action=action, object_ref=object_ref, **meta
        )
        return {
            "watch_id": watch_id,
            "emitted_seq": seq,
            "action": action,
            "object_ref": object_ref,
        }

    # ------------------------------------------------------------------
    # health (PS-102 §5.9) — aggregated for the service /health
    # ------------------------------------------------------------------
    def health(self) -> dict[str, int]:
        with self._lock:
            return self._coordinator.health()

    # ------------------------------------------------------------------
    # domain-event capture (CSTREAM-IMAP-001) — called by the mailbox watcher
    # ------------------------------------------------------------------
    def observe_change(
        self,
        *,
        tenant_id: str,
        folder: str,
        action: str,
        object_ref: str,
        object_version: str = "",
        uid: str = "",
        uidvalidity: str = "",
        sender: str = "",
        recipients: str = "",
        subject: str = "",
        body: str = "",
        message_id: str = "",
        has_attachment: bool = False,
        attachment_names: Sequence[str] | None = None,
        flags: Sequence[str] | None = None,
        headers: Mapping[str, Any] | None = None,
        moved_from: str = "",
        metadata: Mapping[str, Any] | None = None,
        actor: str | None = None,
        correlation_id: str | None = None,
        summary: str = "",
    ) -> list[str]:
        """Fan a single observed mail change into every matching *live* watch.

        Returns the list of watch ids the change was emitted to (may be empty).
        The change is captured at the point the mailbox watcher observes it (via
        IMAP IDLE / UID scan), keyed by mailbox/folder/UID+UIDVALIDITY, so there
        is no busy-wait on the emit path (PS-102 §6 native-first).
        """
        if action not in ACTIONS:
            # Defensive: an unknown verb is a contract error, but capture must
            # never crash the watcher — skip silently.
            return []
        att_names = tuple(attachment_names or ())
        flag_list = tuple(flags or ())
        hdrs = dict(headers or {})
        meta = dict(metadata or {})
        obj_version = object_version or (
            f"{uid}@{uidvalidity}" if uid and uidvalidity else object_ref
        )
        candidate = MailChangeCandidate(
            folder=folder,
            action=action,
            object_ref=object_ref,
            object_version=obj_version,
            sender=sender or str(hdrs.get("from", "")),
            recipients=recipients or str(hdrs.get("to", "")),
            subject=subject or str(hdrs.get("subject", "")),
            body=body,
            message_id=message_id or str(hdrs.get("message-id", "")),
            has_attachment=bool(has_attachment) or bool(att_names),
            attachment_names=att_names,
            flags=flag_list,
            headers=hdrs,
            metadata=meta,
        )
        emitted: list[str] = []
        # snapshot watch ids under lock; emit outside the lock (coordinator is
        # single-process and its own emit is cheap + bounded).
        with self._lock:
            targets = [
                (wid, spec, self._criteria.get(wid, {}))
                for wid, spec in self._specs.items()
                if spec.tenant_id == tenant_id
            ]
        for wid, spec, crit in targets:
            # only emit to live watches; a paused watch retains its cursor and is
            # not fed new events (PS-102 §5.1).
            status = self._coordinator.get_status(wid)
            if status.state != "live":
                continue
            matched = criteria_match(crit, candidate)
            if matched is None:
                continue
            event = self._build_event(
                spec=spec,
                candidate=candidate,
                criteria_match=matched,
                uid=uid,
                uidvalidity=uidvalidity,
                moved_from=moved_from,
                actor=actor,
                correlation_id=correlation_id,
                summary=summary,
            )
            try:
                self._coordinator.emit(wid, event)
                emitted.append(wid)
            except Exception:  # pragma: no cover - a paused/removed watch races
                continue
        return emitted

    # ------------------------------------------------------------------
    # envelope + view builders
    # ------------------------------------------------------------------
    def _build_event(
        self,
        *,
        spec: WatchSpec,
        candidate: MailChangeCandidate,
        criteria_match: Mapping[str, Any],
        uid: str,
        uidvalidity: str,
        moved_from: str,
        actor: str | None,
        correlation_id: str | None,
        summary: str,
    ) -> ChangeEvent:
        # per-service typed metadata extension (PS-102 §4.1 imap-mcp row).
        # subject is redacted-safe: only present as ``subject_redacted`` (a length
        # hint), never the raw subject, so the journal carries no message content.
        typed_metadata = {
            "folder": candidate.folder,
            "uid": uid or candidate.object_ref,
            "uidvalidity": uidvalidity,
            "message_id": candidate.message_id,
            "from": candidate.sender,
            "subject_redacted": _redact_subject(candidate.subject),
            "flags": list(candidate.flags),
            "has_attachment": candidate.has_attachment,
            "moved_from": moved_from,
        }
        return ChangeEvent(
            watch_id=spec.watch_id,
            service_id=self._service_id,
            profile_id=spec.profile_id,
            source_type=_SOURCE_TYPE,
            source_ref=f"{spec.profile_id}:{candidate.folder}",
            action=candidate.action,
            object_ref=candidate.object_ref,
            object_version=candidate.object_version,
            tenant_id=spec.tenant_id,
            event_time=_utc_now(),
            observed_time=_utc_now(),
            criteria_match=dict(criteria_match),
            summary=summary or _default_summary(candidate),
            metadata=typed_metadata,
            correlation_id=correlation_id,
            actor={"id": actor, "type": "user"} if actor else None,
            provenance={"capture": "imap_watcher", "folder": candidate.folder},
        )

    def _watch_view(self, spec: WatchSpec, status: Any) -> dict[str, Any]:
        return {
            "watch_id": spec.watch_id,
            "service_id": spec.service_id,
            "profile_id": spec.profile_id,
            "tenant_id": spec.tenant_id,
            "actor": spec.actor,
            "criteria": dict(spec.criteria),
            "max_batch": spec.max_batch,
            "max_inflight": spec.max_inflight,
            "journal_max": spec.journal_max,
            "journal_ttl_seconds": spec.journal_ttl_seconds,
            "status": self._status_view(status),
        }

    @staticmethod
    def _status_view(status: Any) -> dict[str, Any]:
        return {
            "watch_id": status.watch_id,
            "tenant_id": status.tenant_id,
            "state": status.state,
            "journal_depth": status.depth,
            "earliest_seq": status.earliest_seq,
            "latest_seq": status.latest_seq,
            "ack_seq": status.ack_seq,
            "inflight": status.inflight,
            "throttled": status.throttled,
            "trimmed_total": status.trimmed_total,
        }


def make_audit_sink(audit_writer: Any) -> Callable[[str, Mapping[str, Any]], None]:
    """Build a coordinator ``audit_sink`` that writes to the imap-mcp audit stream.

    The common :class:`WatchCoordinator` calls ``audit_sink(kind, row)`` for every
    lifecycle / emission / delivery / ack / recover / throttle / trim event
    (CSTREAM-010). This adapter maps each to the service's :class:`AuditWriter`
    (``emit(AuditRecord)``) so watch audit lands in the same privileged audit
    stream as the rest of the service — no bespoke audit writer (RULES §1.4).

    ``audit_writer`` is duck-typed: any object with ``emit(AuditRecord)`` works;
    when ``AuditRecord``/``AuditActor`` cannot be imported (isolated unit tier),
    the sink falls back to a plain ``log_admin_action(**kw)`` call so the
    reference-style capture-audit test double keeps working.
    """

    def _sink(kind: str, row: Mapping[str, Any]) -> None:
        watch_id = str(row.get("watch_id", ""))
        actor_id = str(row.get("actor") or "system")
        details = {k: v for k, v in row.items() if k not in {"watch_id", "actor"}}
        # Preferred: emit a real AuditRecord onto the AuditWriter.
        if hasattr(audit_writer, "emit"):
            with contextlib.suppress(Exception):  # pragma: no cover - audit never breaks flow
                from imap_hub_core.audit.events import AuditActor, AuditRecord

                audit_writer.emit(
                    AuditRecord(
                        operation=f"change_watch.{kind}",
                        status="success",
                        correlation_id=str(row.get("correlation_id") or f"cw-{watch_id or '-'}"),
                        actor=AuditActor(actor_type="system", actor_id=actor_id, roles=[]),
                        component="imap_hub_core.change_stream",
                        source_identifier=actor_id,
                        target_type="change_watch",
                        target_id=watch_id or "-",
                        target_name=watch_id or "-",
                        server_id="imap-mcp-local",
                        environment="unknown",
                        params=details or {},
                    )
                )
                return
        # Fallback for a minimal audit double (``log_admin_action(**kw)``).
        if hasattr(audit_writer, "log_admin_action"):
            with contextlib.suppress(Exception):  # pragma: no cover
                audit_writer.log_admin_action(
                    actor=actor_id,
                    roles=set(),
                    action=f"change_watch.{kind}",
                    target_type="change_watch",
                    target_id=watch_id or "-",
                    new_value=details or None,
                )

    return _sink


def _redact_subject(subject: str) -> str:
    """Return a redaction-safe subject hint (never the raw subject content)."""
    text = str(subject or "").strip()
    if not text:
        return ""
    return f"<subject len={len(text)}>"


def _default_summary(candidate: MailChangeCandidate) -> str:
    return f"{candidate.action} {candidate.folder}/uid={candidate.object_ref}".strip()


__all__ = ["WatchService", "SERVICE_ID", "make_audit_sink"]
