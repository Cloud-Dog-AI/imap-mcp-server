"""T3-IMAP-CASCADE (resolver level) + T2-SECRET-MASK smoke — W28A-750 / IDAM-B2 §4.3.

Proves the group->resource cascade RESOLVES against a real ``FileBackedAdminState``
JSON store + the real ``cloud_dog_idam`` 0.5.0 resolver via ``ImapResourceGuard``:

    restricted user U (no flat imap:mail:read)  ->  add to group G
    (bound RBACBinding group:G -> mailbox_profile:P = imap:mail:read)  ->  U reads P (allow),
    sees ONLY P (not Q), cannot WRITE P, cannot read Q  ->  remove U from G  ->  revoked.

The cascade is provable (not vacuous) precisely because U is ``restricted`` — its
access to P comes ONLY through the group binding, never a flat role grant. This is
the resolver-level proof; the live API/MCP/A2A/WebUI proof is the e2e T3-IMAP-CASCADE.

Run: PYTHONPATH=<worktree>/src:<platform-standards>/packages/backend/platform-idam \\
     .venv/bin/python -m pytest tests/smoke/test_cascade_resolves.py -v
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

import pytest

from pydantic import BaseModel

from cloud_dog_idam import RBACEngine, mask_secrets

from imap_hub_core.audit.context import (
    AuditRequestContext,
    reset_audit_request_context,
    set_audit_request_context,
)
from imap_hub_core.tools.base_handler import ToolContract, ToolRegistry
from imap_hub_server.admin.state import FileBackedAdminState
from imap_hub_server.rbac_seam import ImapResourceGuard


class _MailSearchInput(BaseModel):
    """Minimal input model for the cascade tool-gate test."""

    profile_id: str

MAILBOX_PROFILE = "mailbox_profile"
READ = "imap:mail:read"
WRITE = "imap:mail:write"


def _build_state(tmp_path) -> FileBackedAdminState:
    """Seed the PS-82 §1 canonical cascade fixture into a fresh JSON store."""
    state = FileBackedAdminState(str(tmp_path))
    # ADMIN + restricted GROUPUSER U + the group G + two profiles P (bound) / Q (unbound).
    state.create_user({"user_id": "admin", "username": "admin", "email": "admin@example.com", "role": "admin"})
    state.create_user({"user_id": "u-cascade", "username": "cascade", "email": "u@example.com", "role": "restricted"})
    state.create_group({"group_id": "g-cascade", "name": "cascade-group", "roles": []})
    # Profiles P and Q live in the snapshot profiles map (domain resources).
    snap = state._load()
    snap.profiles["P"] = {"name": "P", "credentials": {"username": "ops@example.com", "password": "s3cr3t-P"}}
    snap.profiles["Q"] = {"name": "Q", "credentials": {"username": "ops2@example.com", "password": "s3cr3t-Q"}}
    state._save(snap)
    # The group->resource binding: G may READ mailbox_profile P (NOT Q, NOT write).
    state.create_binding({
        "subject_type": "group", "subject_id": "g-cascade",
        "resource_type": MAILBOX_PROFILE, "resource_id": "P",
        "permission": READ, "granted_by": "admin",
    })
    return state


def _build_guard(state: FileBackedAdminState) -> ImapResourceGuard:
    """Hydrate the shared RBACEngine from the snapshot and wrap it in the guard."""
    engine = RBACEngine()
    state.sync_rbac_engine(engine)
    return ImapResourceGuard(engine, state)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("FR-13")
@pytest.mark.req("FR-04")


def test_cascade_resolves_add_then_revoke(tmp_path):
    """T3-IMAP-CASCADE: add-to-group grants P-read; remove revokes; scoped + graded."""
    state = _build_state(tmp_path)
    guard = _build_guard(state)

    # STEP 1 — baseline: U not in G -> default-DENY on P.
    assert guard.authorise("u-cascade", permission=READ, resource_type=MAILBOX_PROFILE, resource_id="P") is False

    # STEP 2 — group-admin adds U to G (the grant).
    state.add_group_member("g-cascade", "u-cascade")
    guard.invalidate("u-cascade")

    # STEP 3 — CASCADE ON: U reads P, sees ONLY P, cannot write P, cannot read Q.
    assert guard.authorise("u-cascade", permission=READ, resource_type=MAILBOX_PROFILE, resource_id="P") is True
    assert guard.allowed_resource_ids("u-cascade", MAILBOX_PROFILE, READ) == {"P"}
    assert guard.authorise("u-cascade", permission=WRITE, resource_type=MAILBOX_PROFILE, resource_id="P") is False
    assert guard.authorise("u-cascade", permission=READ, resource_type=MAILBOX_PROFILE, resource_id="Q") is False

    # STEP 4 — group-admin removes U from G (the revoke).
    state.remove_group_member("g-cascade", "u-cascade")
    guard.invalidate("u-cascade")

    # STEP 5 — CASCADE OFF (live, no restart): P-read denied again.
    assert guard.authorise("u-cascade", permission=READ, resource_type=MAILBOX_PROFILE, resource_id="P") is False
    assert guard.allowed_resource_ids("u-cascade", MAILBOX_PROFILE, READ) == set()
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("FR-13")
@pytest.mark.req("FR-04")


def test_admin_wildcard_sees_all_profiles(tmp_path):
    """Admin (flat '*') is authorised for any profile and lists all (allowed = {'*'})."""
    state = _build_state(tmp_path)
    guard = _build_guard(state)
    assert guard.is_admin("admin") is True
    assert guard.authorise("admin", permission=READ, resource_type=MAILBOX_PROFILE, resource_id="Q") is True
    assert guard.allowed_resource_ids("admin", MAILBOX_PROFILE, READ) == {"*"}
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("FR-13")
@pytest.mark.req("FR-04")


def test_secret_masking_non_admin_vs_admin(tmp_path):
    """T2-SECRET-MASK: profile credentials masked for non-admin, cleartext for admin."""
    state = _build_state(tmp_path)
    guard = _build_guard(state)
    profile_payload = state._load().profiles["P"]

    # Non-admin (restricted U) -> password redacted on the egress path.
    masked = mask_secrets(profile_payload, is_admin=guard.is_admin("u-cascade"))
    assert masked["credentials"]["password"] == "***REDACTED***"
    assert masked["credentials"]["username"] == "ops@example.com"  # non-secret preserved

    # Admin -> cleartext (reveal path).
    revealed = mask_secrets(profile_payload, is_admin=guard.is_admin("admin"))
    assert revealed["credentials"]["password"] == "s3cr3t-P"


def _build_registry(state: FileBackedAdminState, guard: ImapResourceGuard) -> ToolRegistry:
    """A registry whose role-patterns grant mail_* to read-only/admin only (NOT restricted)."""
    registry = ToolRegistry(
        role_patterns={"admin": ["*"], "read-only": ["mail_*"], "read-write": ["mail_*"]},
        admin_state=state,
        resource_guard=guard,
    )
    registry.register(
        ToolContract(
            name="mail_search",
            description="search",
            input_model=_MailSearchInput,
            handler=lambda payload: {"ok": True, "profile_id": payload.get("profile_id")},
        )
    )
    return registry
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("FR-13")
@pytest.mark.req("FR-04")


def test_cascade_through_tool_gate(tmp_path):
    """T3-IMAP-CASCADE at the live tool gate: restricted user denied -> add to G -> allowed -> revoked.

    The role-pattern gate never grants ``restricted`` the ``mail_*`` tools, so access to
    profile P comes ONLY through the additive RBACBinding cascade (grant-only; a
    role-pattern allow always wins first and is never overridden).
    """
    state = _build_state(tmp_path)
    guard = _build_guard(state)
    registry = _build_registry(state, guard)

    token = set_audit_request_context(
        AuditRequestContext(correlation_id="c1", actor_id="u-cascade", roles=["restricted"])
    )
    try:
        # STEP 1 — restricted U, not in G -> role-pattern deny, no binding -> PermissionError.
        with pytest.raises(PermissionError):
            registry.call("mail_search", {"profile_id": "P"})

        # STEP 2/3 — add U to G -> cascade grants P (NOT Q).
        state.add_group_member("g-cascade", "u-cascade")
        guard.invalidate("u-cascade")
        assert registry.call("mail_search", {"profile_id": "P"}) == {"ok": True, "profile_id": "P"}
        with pytest.raises(PermissionError):
            registry.call("mail_search", {"profile_id": "Q"})  # scoped: Q not bound

        # STEP 4/5 — remove U from G -> revoked live.
        state.remove_group_member("g-cascade", "u-cascade")
        guard.invalidate("u-cascade")
        with pytest.raises(PermissionError):
            registry.call("mail_search", {"profile_id": "P"})
    finally:
        reset_audit_request_context(token)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("FR-13")
@pytest.mark.req("FR-04")


def test_tool_gate_flat_role_unaffected(tmp_path):
    """Regression guard: a flat read-only role still passes mail_* via role-patterns (no cascade needed)."""
    state = _build_state(tmp_path)
    guard = _build_guard(state)
    registry = _build_registry(state, guard)
    token = set_audit_request_context(
        AuditRequestContext(correlation_id="c2", actor_id="someone", roles=["read-only"])
    )
    try:
        # read-only has the mail_* role-pattern -> allowed for ANY profile, no binding required.
        assert registry.call("mail_search", {"profile_id": "Q"}) == {"ok": True, "profile_id": "Q"}
    finally:
        reset_audit_request_context(token)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("FR-13")
@pytest.mark.req("FR-04")


def test_profile_list_scoped_by_cascade(tmp_path):
    """T3-IMAP-CASCADE list-filter: profile_list returns ONLY the bound profile for a GROUPUSER.

    Proves IDAM-B2 §2.3 'GROUPUSER sees ONLY G's data' is provable, not vacuous —
    the handler's _check_profile_access (which profile_list filters by) honours the
    RBACBinding cascade via the injected ImapResourceGuard.
    """
    from imap_hub_core.tools.handlers import ImapToolHandlers

    state = _build_state(tmp_path)
    guard = _build_guard(state)
    handlers = ImapToolHandlers(
        profiles={"P": {"name": "P", "enabled": True}, "Q": {"name": "Q", "enabled": True}},
        downloads_dir=str(tmp_path / "dl"),
        admin_state=state,
        rbac_engine=guard._engine,  # same hydrated engine
        resource_guard=guard,
    )
    # restricted GROUPUSER, member of G (bound to P): sees ONLY P.
    state.add_group_member("g-cascade", "u-cascade")
    guard.invalidate("u-cascade")
    token = set_audit_request_context(
        AuditRequestContext(correlation_id="c3", actor_id="u-cascade", roles=["restricted"])
    )
    try:
        result = handlers.profile_list({})
        assert result["result"]["profiles"] == ["P"], result
    finally:
        reset_audit_request_context(token)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
