# imap-mcp-server mailbox change watcher.

# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# imap-mcp-server bounded mailbox watcher.
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

"""IMAP mailbox change watcher (PS-102 §6 native-first, CSTREAM-IMAP-001/002).

The watcher observes a mail folder and turns raw IMAP state deltas into calls to
:meth:`WatchService.observe_change`. It captures four kinds of change, keyed by
mailbox/folder/UID+UIDVALIDITY:

* ``created`` — a new message arrival (a UID above the folder high-water mark).
* ``flag_changed`` — a flag delta on an existing UID (e.g. ``\\Seen`` set).
* ``moved`` / ``deleted`` — a UID that disappeared from the folder (EXPUNGE).
* recovery of UIDVALIDITY reset, folder rename/delete, and duplicates.

Native-first mechanism (PS-102 §6 imap-mcp row): **IMAP IDLE + UID / UIDVALIDITY**
where the server advertises it, with a **bounded incremental-UID-range polling
fallback** (capped frequency, bounded folder select, mailbox-size safeguards)
otherwise. The transport is abstracted behind :class:`MailboxSource` so:

* the live adapter (:class:`ImapMailboxSource`) talks to a real ``imaplib`` client
  supplied by the caller (RULES §6.45: the caller MUST resolve verified
  credentials via ``cloud_dog_config`` — this module never connects with blank
  creds and never selects a mailbox with unverified credentials);
* the unit tier drives a deterministic in-memory :class:`FakeMailbox` so the
  alert scenarios can be proven WITHOUT any live IMAP (RULES §6.45).

The watcher holds NO journal/cursor/queue — it delegates every observed change to
the :class:`WatchService` adapter, which consumes the common foundation.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
from typing import Any, Protocol

from cloud_dog_logging import get_logger

from imap_hub_core.change_stream.service import WatchService

_LOG = get_logger("imap_hub_core.change_stream.mailbox_watcher")

# Safeguards (PS-102 §6 / CSTREAM-006): a single scan pass never fetches more than
# this many *new* messages, and never selects a folder whose message count exceeds
# the size guard unless the caller raises it. These bound IO/CPU per scan pass.
_DEFAULT_MAX_NEW_PER_SCAN = 200
_DEFAULT_MAILBOX_SIZE_GUARD = 100_000


@dataclass(frozen=True)
class ObservedMessage:
    """A message as observed by a mailbox source during a scan/IDLE pass."""

    uid: int
    flags: tuple[str, ...] = ()
    sender: str = ""
    recipients: str = ""
    subject: str = ""
    body: str = ""
    message_id: str = ""
    has_attachment: bool = False
    attachment_names: tuple[str, ...] = ()
    headers: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class FolderCheckpoint:
    """Per-folder recovery checkpoint keyed by UIDVALIDITY (CSTREAM-IMAP-002).

    ``uid_high_water`` is the largest UID seen so far; on the next pass any UID
    above it is a new arrival. ``known`` maps UID -> observed flag set so a flag
    delta or an expunge (missing UID) can be detected. A change in
    ``uidvalidity`` means the server reset UIDs: the watcher rebases without
    replaying the whole folder as new arrivals.
    """

    uidvalidity: str = ""
    uid_high_water: int = 0
    known: dict[int, tuple[str, ...]] = field(default_factory=dict)


class MailboxSource(Protocol):
    """Abstract IMAP folder view the watcher scans (native-first, testable).

    Implementations MUST NOT connect with blank/unverified credentials
    (RULES §6.45). ``supports_idle`` advertises whether the server offers IMAP
    IDLE so the watcher can prefer it over polling.
    """

    supports_idle: bool

    def list_folders(self) -> list[str]:
        """Return the current folder names (for rename/delete detection)."""

    def uidvalidity(self, folder: str) -> str:
        """Return the folder's current UIDVALIDITY (empty when unavailable)."""

    def message_count(self, folder: str) -> int:
        """Return the number of messages currently in the folder."""

    def scan(self, folder: str, since_uid: int, limit: int) -> list[ObservedMessage]:
        """Return observed messages with UID > ``since_uid`` (bounded by ``limit``).

        The implementation MUST bound its own IO to ``limit`` messages so a single
        pass never floods (CSTREAM-006). Flag state for existing UIDs at/below the
        high-water mark is returned via :meth:`flag_snapshot`.
        """

    def flag_snapshot(self, folder: str, uids: Sequence[int]) -> dict[int, tuple[str, ...]]:
        """Return the current flags for a bounded set of already-known UIDs."""

    def live_uids(self, folder: str) -> set[int]:
        """Return the UIDs currently present (to detect expunged/moved messages)."""


class MailboxWatcher:
    """Scan a folder for arrival/flags/move/expunge and fan changes to WatchService.

    A ``scan_once`` pass is the bounded background unit of work (PS-102 §6): it
    selects the folder once, computes the delta against the recovery checkpoint,
    and delegates each observed change to :meth:`WatchService.observe_change`. It
    is idempotent — a change already reflected in the checkpoint is not re-emitted
    (dedup, CSTREAM-IMAP-002).
    """

    def __init__(
        self,
        *,
        watch_service: WatchService,
        source: MailboxSource,
        tenant_id: str,
        profile_id: str,
        actor: str = "imap-watcher",
        max_new_per_scan: int = _DEFAULT_MAX_NEW_PER_SCAN,
        mailbox_size_guard: int = _DEFAULT_MAILBOX_SIZE_GUARD,
    ) -> None:
        self._ws = watch_service
        self._source = source
        self._tenant_id = tenant_id
        self._profile_id = profile_id
        self._actor = actor
        self._max_new = max(1, int(max_new_per_scan))
        self._size_guard = max(1, int(mailbox_size_guard))
        self._checkpoints: dict[str, FolderCheckpoint] = {}
        self._known_folders: set[str] = set()

    @property
    def uses_idle(self) -> bool:
        """Whether this watcher can use IMAP IDLE (native) vs the polling fallback."""
        return bool(getattr(self._source, "supports_idle", False))

    def checkpoint(self, folder: str) -> FolderCheckpoint:
        """Return (creating if needed) the recovery checkpoint for a folder."""
        cp = self._checkpoints.get(folder)
        if cp is None:
            cp = FolderCheckpoint(uidvalidity=self._source.uidvalidity(folder))
            self._checkpoints[folder] = cp
        return cp

    def prime(self, folder: str) -> None:
        """Prime the checkpoint from the CURRENT folder state without emitting.

        Called once at watch start so pre-existing messages are the baseline and
        are NOT replayed as ``created`` arrivals (avoids a startup flood,
        CSTREAM-IMAP-002).
        """
        cp = self.checkpoint(folder)
        cp.uidvalidity = self._source.uidvalidity(folder)
        for uid in sorted(self._source.live_uids(folder)):
            cp.known[uid] = ()
            cp.uid_high_water = max(cp.uid_high_water, uid)
        snapshot = self._source.flag_snapshot(folder, list(cp.known))
        for uid, flags in snapshot.items():
            cp.known[uid] = tuple(flags)
        self._known_folders = set(self._source.list_folders())

    def scan_once(self, folder: str, *, correlation_id: str | None = None) -> list[str]:
        """Run one bounded scan pass; return the list of observed action verbs.

        Handles folder rename/delete, UIDVALIDITY reset, new arrivals, flag
        deltas, and expunge/move — each without flooding (bounded fetch + dedup).
        """
        actions: list[str] = []

        # 1. Folder rename/delete: a watched folder that vanished is a folder-level
        # change (deleted); do not scan a folder that is no longer present.
        current_folders = set(self._source.list_folders())
        if folder not in current_folders:
            if folder in self._known_folders:
                self._emit(
                    folder=folder,
                    action="deleted",
                    object_ref=f"folder:{folder}",
                    summary=f"folder {folder} renamed or deleted",
                    correlation_id=correlation_id,
                )
                actions.append("deleted")
                self._known_folders = current_folders
                self._checkpoints.pop(folder, None)
            return actions
        self._known_folders = current_folders

        # 2. Mailbox-size safeguard: refuse to scan an over-large folder (bounded
        # select). This prevents an unbounded fetch on a huge mailbox.
        count = self._source.message_count(folder)
        if count > self._size_guard:
            _LOG.warning(
                "mailbox_watcher_size_guard",
                extra={"folder": folder, "count": count, "guard": self._size_guard},
            )
            return actions

        cp = self.checkpoint(folder)

        # 3. UIDVALIDITY reset (CSTREAM-IMAP-002): the server reassigned UIDs.
        # Rebase the checkpoint from the current state WITHOUT replaying the whole
        # folder as new arrivals, and emit one bounded ``metadata_changed`` marker.
        current_validity = self._source.uidvalidity(folder)
        if cp.uidvalidity and current_validity and current_validity != cp.uidvalidity:
            _LOG.info(
                "mailbox_watcher_uidvalidity_reset",
                extra={"folder": folder, "old": cp.uidvalidity, "new": current_validity},
            )
            self._emit(
                folder=folder,
                action="metadata_changed",
                object_ref=f"folder:{folder}",
                uidvalidity=current_validity,
                summary=f"UIDVALIDITY reset {cp.uidvalidity}->{current_validity}",
                correlation_id=correlation_id,
            )
            actions.append("metadata_changed")
            cp.uidvalidity = current_validity
            cp.uid_high_water = 0
            cp.known.clear()
            self.prime(folder)
            return actions
        if not cp.uidvalidity:
            cp.uidvalidity = current_validity

        # 4. New arrivals: UID above the high-water mark (bounded to _max_new).
        new_messages = self._source.scan(folder, cp.uid_high_water, self._max_new)
        for msg in new_messages:
            if msg.uid in cp.known:
                continue  # dedup: already observed this UID
            self._emit_message(folder, "created", msg, cp, correlation_id)
            cp.known[msg.uid] = tuple(msg.flags)
            cp.uid_high_water = max(cp.uid_high_water, msg.uid)
            actions.append("created")

        # 5. Flag deltas on already-known UIDs (bounded snapshot).
        snapshot = self._source.flag_snapshot(folder, list(cp.known))
        for uid, new_flags in snapshot.items():
            old = cp.known.get(uid)
            new_tuple = tuple(new_flags)
            if old is not None and set(old) != set(new_tuple):
                self._emit(
                    folder=folder,
                    action="flag_changed",
                    object_ref=str(uid),
                    uid=str(uid),
                    uidvalidity=cp.uidvalidity,
                    flags=new_tuple,
                    summary=f"flags changed on uid {uid}",
                    correlation_id=correlation_id,
                )
                actions.append("flag_changed")
            cp.known[uid] = new_tuple

        # 6. Expunge / move: a previously-known UID that is no longer live.
        live = self._source.live_uids(folder)
        vanished = [uid for uid in list(cp.known) if uid not in live]
        for uid in vanished:
            self._emit(
                folder=folder,
                action="moved",
                object_ref=str(uid),
                uid=str(uid),
                uidvalidity=cp.uidvalidity,
                moved_from=folder,
                summary=f"uid {uid} expunged/moved out of {folder}",
                correlation_id=correlation_id,
            )
            cp.known.pop(uid, None)
            actions.append("moved")

        return actions

    # ------------------------------------------------------------------
    def _emit_message(
        self,
        folder: str,
        action: str,
        msg: ObservedMessage,
        cp: FolderCheckpoint,
        correlation_id: str | None,
    ) -> None:
        self._ws.observe_change(
            tenant_id=self._tenant_id,
            folder=folder,
            action=action,
            object_ref=str(msg.uid),
            uid=str(msg.uid),
            uidvalidity=cp.uidvalidity,
            sender=msg.sender,
            recipients=msg.recipients,
            subject=msg.subject,
            body=msg.body,
            message_id=msg.message_id,
            has_attachment=msg.has_attachment,
            attachment_names=msg.attachment_names,
            flags=msg.flags,
            headers=msg.headers,
            actor=self._actor,
            correlation_id=correlation_id,
            summary=f"{action} uid {msg.uid} in {folder}",
        )

    def _emit(
        self,
        *,
        folder: str,
        action: str,
        object_ref: str,
        uid: str = "",
        uidvalidity: str = "",
        flags: Sequence[str] | None = None,
        moved_from: str = "",
        summary: str = "",
        correlation_id: str | None = None,
    ) -> None:
        self._ws.observe_change(
            tenant_id=self._tenant_id,
            folder=folder,
            action=action,
            object_ref=object_ref,
            uid=uid,
            uidvalidity=uidvalidity,
            flags=flags,
            moved_from=moved_from,
            actor=self._actor,
            correlation_id=correlation_id,
            summary=summary,
        )


# ---------------------------------------------------------------------------
# Live IMAP source (bounded UID poll over an existing authenticated client).
# ---------------------------------------------------------------------------
class ImapMailboxSource:
    """A :class:`MailboxSource` backed by a real, already-authenticated ``imaplib`` client.

    The caller (the mailbox-watch runtime) MUST resolve verified credentials via
    ``cloud_dog_config`` and open the client (RULES §6.45); this class never
    connects and never logs in — it only issues bounded, read-only UID commands
    against the supplied client. IMAP IDLE is advertised via ``supports_idle`` but
    the delta computation is UID-scan based so it works whether the wake-up came
    from IDLE or from the capped-frequency polling fallback (PS-102 §6).
    """

    _UIDVALIDITY_RE = re.compile(rb"UIDVALIDITY\s+(\d+)")

    def __init__(self, client: Any, *, supports_idle: bool = False) -> None:
        self._client = client
        self.supports_idle = bool(supports_idle)

    def list_folders(self) -> list[str]:
        status, data = self._client.list()
        if status != "OK" or not data:
            return []
        names: list[str] = []
        for line in data:
            if not isinstance(line, (bytes, bytearray)):
                continue
            # name is the trailing token of the LIST response line
            token = line.rsplit(b" ", 1)[-1].strip().strip(b'"')
            if token and token.upper() != b"NIL":
                names.append(token.decode("utf-8", "replace"))
        return names

    def _select(self, folder: str) -> None:
        status, _ = self._client.select(folder, readonly=True)
        if status != "OK":
            raise RuntimeError(f"IMAP select failed for {folder!r}: {status}")

    def uidvalidity(self, folder: str) -> str:
        status, data = self._client.status(folder, "(UIDVALIDITY)")
        if status != "OK" or not data:
            return ""
        blob = data[0] if isinstance(data[0], (bytes, bytearray)) else str(data[0]).encode()
        m = self._UIDVALIDITY_RE.search(blob)
        return m.group(1).decode() if m else ""

    def message_count(self, folder: str) -> int:
        status, data = self._client.status(folder, "(MESSAGES)")
        if status != "OK" or not data:
            return 0
        blob = data[0] if isinstance(data[0], (bytes, bytearray)) else str(data[0]).encode()
        m = re.search(rb"MESSAGES\s+(\d+)", blob)
        return int(m.group(1)) if m else 0

    def live_uids(self, folder: str) -> set[int]:
        self._select(folder)
        status, data = self._client.uid("SEARCH", None, "ALL")
        if status != "OK" or not data or not data[0]:
            return set()
        return {int(tok) for tok in data[0].split() if tok.isdigit()}

    def scan(self, folder: str, since_uid: int, limit: int) -> list[ObservedMessage]:
        self._select(folder)
        low = since_uid + 1
        status, data = self._client.uid("SEARCH", None, f"UID {low}:*")
        if status != "OK" or not data or not data[0]:
            return []
        uids = sorted(int(tok) for tok in data[0].split() if tok.isdigit() and int(tok) >= low)
        uids = uids[: max(1, int(limit))]  # bounded fetch (CSTREAM-006)
        out: list[ObservedMessage] = []
        for uid in uids:
            out.append(self._fetch(folder, uid))
        return out

    def flag_snapshot(self, folder: str, uids: Sequence[int]) -> dict[int, tuple[str, ...]]:
        if not uids:
            return {}
        self._select(folder)
        # bound the snapshot: never fetch flags for an unbounded set in one command
        wanted = sorted(uids)[-self._flag_snapshot_limit():] if len(uids) > self._flag_snapshot_limit() else sorted(uids)
        seq = ",".join(str(u) for u in wanted)
        status, data = self._client.uid("FETCH", seq, "(FLAGS)")
        result: dict[int, tuple[str, ...]] = {}
        if status != "OK" or not data:
            return result
        for item in data:
            blob = item[0] if isinstance(item, tuple) else item
            if not isinstance(blob, (bytes, bytearray)):
                continue
            uid_m = re.search(rb"UID\s+(\d+)", blob)
            flags_m = re.search(rb"FLAGS\s+\(([^)]*)\)", blob)
            if not uid_m:
                continue
            flags = tuple(
                f.decode("utf-8", "replace")
                for f in (flags_m.group(1).split() if flags_m else [])
            )
            result[int(uid_m.group(1))] = flags
        return result

    @staticmethod
    def _flag_snapshot_limit() -> int:
        return 500

    def _fetch(self, folder: str, uid: int) -> ObservedMessage:
        status, data = self._client.uid(
            "FETCH", str(uid),
            "(FLAGS BODY.PEEK[HEADER.FIELDS (FROM TO CC SUBJECT MESSAGE-ID CONTENT-TYPE)])",
        )
        flags: tuple[str, ...] = ()
        headers: dict[str, Any] = {}
        if status == "OK":
            for item in data or []:
                if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], (bytes, bytearray)):
                    meta = item[0] if isinstance(item[0], (bytes, bytearray)) else b""
                    fm = re.search(rb"FLAGS\s+\(([^)]*)\)", meta)
                    if fm:
                        flags = tuple(f.decode("utf-8", "replace") for f in fm.group(1).split())
                    parsed = BytesParser(policy=policy.default).parsebytes(item[1])
                    headers = {
                        k.lower(): str(v) for k, v in parsed.items()
                    }
        content_type = str(headers.get("content-type", ""))
        has_attachment = "multipart/mixed" in content_type.lower()
        recipients = " ".join(
            v for v in (str(headers.get("to", "")), str(headers.get("cc", ""))) if v
        ).strip()
        return ObservedMessage(
            uid=uid,
            flags=flags,
            sender=str(headers.get("from", "")),
            recipients=recipients,
            subject=str(headers.get("subject", "")),
            message_id=str(headers.get("message-id", "")),
            has_attachment=has_attachment,
            headers=headers,
        )


# ---------------------------------------------------------------------------
# Deterministic in-memory source for the UT tier (NO live IMAP — RULES §6.45).
# ---------------------------------------------------------------------------
class FakeMailbox:
    """An in-memory :class:`MailboxSource` for deterministic UT-level proofs.

    Lets the alert scenarios (sender match, message-content term/regex match) and
    the arrival/flags/move/expunge + UIDVALIDITY-reset/rename recovery paths be
    proven WITHOUT any live IMAP connection (RULES §6.45). ``add`` inserts a
    message; ``set_flags`` mutates flags; ``expunge`` removes a UID; ``rename``
    drops a folder; ``reset_uidvalidity`` simulates a server UID reset.
    """

    supports_idle = True

    def __init__(self, folders: Sequence[str] = ("INBOX",)) -> None:
        self._folders: dict[str, dict[int, ObservedMessage]] = {f: {} for f in folders}
        self._uidvalidity: dict[str, str] = {f: "1000" for f in folders}

    # -- test-authoring helpers --------------------------------------
    def add(self, folder: str, message: ObservedMessage) -> None:
        self._folders.setdefault(folder, {})[message.uid] = message
        self._uidvalidity.setdefault(folder, "1000")

    def set_flags(self, folder: str, uid: int, flags: Sequence[str]) -> None:
        msg = self._folders[folder][uid]
        self._folders[folder][uid] = ObservedMessage(
            uid=msg.uid, flags=tuple(flags), sender=msg.sender, recipients=msg.recipients,
            subject=msg.subject, body=msg.body, message_id=msg.message_id,
            has_attachment=msg.has_attachment, attachment_names=msg.attachment_names,
            headers=msg.headers,
        )

    def expunge(self, folder: str, uid: int) -> None:
        self._folders.get(folder, {}).pop(uid, None)

    def rename(self, old: str, new: str | None = None) -> None:
        msgs = self._folders.pop(old, None)
        self._uidvalidity.pop(old, None)
        if new is not None and msgs is not None:
            self._folders[new] = msgs
            self._uidvalidity[new] = "1000"

    def reset_uidvalidity(self, folder: str, value: str) -> None:
        self._uidvalidity[folder] = value

    # -- MailboxSource protocol ---------------------------------------
    def list_folders(self) -> list[str]:
        return list(self._folders)

    def uidvalidity(self, folder: str) -> str:
        return self._uidvalidity.get(folder, "")

    def message_count(self, folder: str) -> int:
        return len(self._folders.get(folder, {}))

    def scan(self, folder: str, since_uid: int, limit: int) -> list[ObservedMessage]:
        msgs = self._folders.get(folder, {})
        uids = sorted(uid for uid in msgs if uid > since_uid)[: max(1, int(limit))]
        return [msgs[uid] for uid in uids]

    def flag_snapshot(self, folder: str, uids: Sequence[int]) -> dict[int, tuple[str, ...]]:
        msgs = self._folders.get(folder, {})
        return {uid: tuple(msgs[uid].flags) for uid in uids if uid in msgs}

    def live_uids(self, folder: str) -> set[int]:
        return set(self._folders.get(folder, {}))


__all__ = [
    "ObservedMessage",
    "FolderCheckpoint",
    "MailboxSource",
    "MailboxWatcher",
    "ImapMailboxSource",
    "FakeMailbox",
]
