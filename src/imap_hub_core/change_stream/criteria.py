# imap-mcp-server change-stream criteria.

# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# imap-mcp-server mail-change criteria adapter.
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

"""Mail-profile change-watch criteria matching (PS-102 CSTREAM-IMAP-001).

The criteria matcher is a *pure* function over a proposed
:class:`MailChangeCandidate` (folder + message identity + envelope headers +
flags + attachment presence + body/header text + action) and a watch's
declarative ``criteria`` mapping. It decides whether an observed mail change
matches a watch and, when it does, returns the ``criteria_match`` provenance the
common :class:`cloud_dog_api_kit.change_stream.ChangeEvent` envelope requires so
a consumer can prove the event is not a false positive (PS-102 §4).

Supported criteria fields (CSTREAM-IMAP-001):

* ``folder`` — exact folder/mailbox name (or list of names).
* ``sender`` / ``from`` — glob or ``re:`` regex over the ``From`` header.
* ``recipient`` / ``to`` — glob or ``re:`` regex over the ``To``/``Cc`` recipients.
* ``subject`` — glob or ``re:`` regex over the message subject.
* ``header`` — mapping of header-name -> required value (exact or ``re:``).
* ``body`` / ``text`` — glob or ``re:`` regex over the extracted body text.
* ``attachment`` — bool (has-attachment) or a glob/``re:`` over an attachment name.
* ``flags`` — one flag (e.g. ``\\Seen``) or a list; ALL listed flags must be set.
* ``action`` — one action verb or a list of verbs from the canonical set.

No criterion means "match everything" (an unfiltered watch). This module owns NO
journal / cursor / queue logic — that all lives in the common foundation
(``cloud_dog_api_kit.change_stream``), consumed by the adapter (RULES §1.4).
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from cloud_dog_api_kit.change_stream import ACTIONS
from cloud_dog_api_kit.change_stream.errors import InvalidCriteria

_REGEX_PREFIX = "re:"

# Criteria keys this service understands (CSTREAM-IMAP-001). Unknown keys are a
# hard InvalidCriteria at watch-create time rather than a silent no-op.
# ``from``/``to``/``text`` are convenience aliases for sender/recipient/body.
_KNOWN_CRITERIA = frozenset(
    {
        "folder",
        "sender",
        "from",
        "recipient",
        "to",
        "subject",
        "header",
        "body",
        "text",
        "attachment",
        "flags",
        "action",
    }
)


@dataclass(frozen=True)
class MailChangeCandidate:
    """A proposed mail change evaluated against a watch's criteria.

    ``flags`` is the set of IMAP flags on the message (e.g. ``\\Seen``,
    ``\\Flagged``). ``body`` is extracted plain text (optional; present for
    arrival events when the body was fetched). ``attachment_names`` lists any
    attachment filenames. The candidate carries no secrets — the coordinator
    redacts metadata before it rests in the journal.
    """

    folder: str
    action: str
    object_ref: str  # message UID (as string)
    object_version: str = ""  # UID+UIDVALIDITY composite
    sender: str = ""
    recipients: str = ""
    subject: str = ""
    body: str = ""
    message_id: str = ""
    has_attachment: bool = False
    attachment_names: Sequence[str] = field(default_factory=tuple)
    flags: Sequence[str] = field(default_factory=tuple)
    headers: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _compile_regex(raw: str) -> re.Pattern[str]:
    pattern = raw[len(_REGEX_PREFIX):]
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise InvalidCriteria(f"invalid regex {pattern!r}: {exc}") from exc


def _text_match(pattern: str, value: str) -> str | None:
    """Return the matched value/substring when ``pattern`` matches ``value``.

    ``re:`` prefix -> case-insensitive regex ``search``; otherwise a
    case-insensitive ``fnmatch`` glob. Returns ``None`` on no match. Header/body
    matching is case-insensitive because mail headers are not case-normalised.
    """
    if pattern.startswith(_REGEX_PREFIX):
        compiled = _compile_regex(pattern)
        m = compiled.search(value or "")
        return m.group(0) if m is not None else None
    if fnmatch.fnmatchcase((value or "").lower(), pattern.lower()):
        return value
    return None


def _normalise_flag(flag: str) -> str:
    """Normalise an IMAP flag for comparison (case-insensitive, keep backslash)."""
    return str(flag).strip().lower()


def validate_criteria(criteria: Mapping[str, Any]) -> None:
    """Validate a watch's criteria mapping, raising ``InvalidCriteria`` on error.

    Called at watch-create time so an unsupported field / bad regex / unknown
    action verb is rejected *before* the watch starts (PS-102 §5.1).
    """
    if not isinstance(criteria, Mapping):
        raise InvalidCriteria("criteria must be a mapping")
    unknown = set(criteria) - _KNOWN_CRITERIA
    if unknown:
        raise InvalidCriteria(
            f"unsupported criteria field(s): {', '.join(sorted(unknown))}; "
            f"supported: {', '.join(sorted(_KNOWN_CRITERIA))}"
        )
    # action verbs must be from the canonical set
    actions = criteria.get("action")
    if actions is not None:
        for verb in _as_list(actions):
            if verb not in ACTIONS:
                raise InvalidCriteria(
                    f"unknown action verb {verb!r}; valid: {', '.join(sorted(ACTIONS))}"
                )
    # header must be a mapping
    header = criteria.get("header")
    if header is not None and not isinstance(header, Mapping):
        raise InvalidCriteria("header criterion must be a mapping of name -> value")
    # eagerly compile regex patterns to surface bad patterns now (PS-102 §5.1)
    for pattern_field in ("sender", "from", "recipient", "to", "subject", "body", "text"):
        raw = criteria.get(pattern_field)
        if isinstance(raw, str) and raw.startswith(_REGEX_PREFIX):
            _compile_regex(raw)
    attachment = criteria.get("attachment")
    if isinstance(attachment, str) and attachment.startswith(_REGEX_PREFIX):
        _compile_regex(attachment)
    if isinstance(header, Mapping):
        for value in header.values():
            if isinstance(value, str) and value.startswith(_REGEX_PREFIX):
                _compile_regex(value)


def match(criteria: Mapping[str, Any], candidate: MailChangeCandidate) -> dict[str, Any] | None:
    """Return a ``criteria_match`` mapping if the candidate matches, else ``None``.

    An empty ``criteria`` mapping matches everything and returns ``{"all": True}``
    so the envelope's ``criteria_match`` is never empty (CSTREAM-004). When any
    criterion fails, the whole watch does NOT match and ``None`` is returned
    (all listed criteria are ANDed together).
    """
    if not criteria:
        return {"all": True}

    matched: dict[str, Any] = {}

    # folder — exact (single or list)
    if "folder" in criteria:
        wanted = {str(f) for f in _as_list(criteria["folder"])}
        if candidate.folder not in wanted:
            return None
        matched["folder"] = candidate.folder

    # action verb — single or list
    if "action" in criteria:
        wanted_actions = _as_list(criteria["action"])
        if candidate.action not in wanted_actions:
            return None
        matched["action"] = candidate.action

    # sender / from — glob or regex over the From header
    for key in ("sender", "from"):
        if key in criteria:
            hit = _text_match(str(criteria[key]), candidate.sender)
            if hit is None:
                return None
            matched["sender"] = candidate.sender

    # recipient / to — glob or regex over To/Cc recipients
    for key in ("recipient", "to"):
        if key in criteria:
            hit = _text_match(str(criteria[key]), candidate.recipients)
            if hit is None:
                return None
            matched["recipient"] = candidate.recipients

    # subject — glob or regex
    if "subject" in criteria:
        hit = _text_match(str(criteria["subject"]), candidate.subject)
        if hit is None:
            return None
        matched["subject"] = candidate.subject

    # body / text — glob or regex over the extracted body text
    for key in ("body", "text"):
        if key in criteria:
            hit = _text_match(str(criteria[key]), candidate.body or "")
            if hit is None:
                return None
            matched["body"] = hit

    # header — name -> value (exact or regex), case-insensitive header lookup
    if "header" in criteria:
        wanted_headers = criteria["header"]
        matched_headers: dict[str, Any] = {}
        lowered = {str(k).lower(): v for k, v in candidate.headers.items()}
        for name, expected in wanted_headers.items():
            actual = lowered.get(str(name).lower())
            if actual is None:
                return None
            if isinstance(expected, str) and expected.startswith(_REGEX_PREFIX):
                if _text_match(expected, str(actual)) is None:
                    return None
            elif str(actual).strip().lower() != str(expected).strip().lower():
                return None
            matched_headers[str(name)] = actual
        matched["header"] = matched_headers

    # attachment — bool (has-attachment) or glob/regex over an attachment name
    if "attachment" in criteria:
        spec = criteria["attachment"]
        if isinstance(spec, str) and (spec.startswith(_REGEX_PREFIX) or any(ch in spec for ch in "*?[")):
            names = list(candidate.attachment_names)
            hit = next((n for n in names if _text_match(spec, n) is not None), None)
            if hit is None:
                return None
            matched["attachment"] = hit
        else:
            want = _truthy(spec)
            if candidate.has_attachment != want:
                return None
            matched["attachment"] = candidate.has_attachment

    # flags — ALL listed flags must be present on the message
    if "flags" in criteria:
        required = [_normalise_flag(f) for f in _as_list(criteria["flags"])]
        present = {_normalise_flag(f) for f in candidate.flags}
        missing = [f for f in required if f not in present]
        if missing:
            return None
        matched["flags"] = required

    return matched


__all__ = ["MailChangeCandidate", "match", "validate_criteria"]
