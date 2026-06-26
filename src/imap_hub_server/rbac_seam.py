"""imap-mcp resource-aware RBAC seam (W28A-750 / IDAM-B2 §4.2).

Adapts imap's JSON-snapshot identity store to the W28A-741 ``cloud_dog_idam``
0.5.0 resolver so the cascade RESOLVES live:

    user U --(GroupRecord.members: U in G)--> group G
           --(RBACBindingRecord: group:G -> mailbox_profile:P = imap:mail:read)--> profile P

Three adapters, all framework-free (imap_hub_server layer; no FastAPI import here):

- ``ImapMembershipResolver``  : the ``cloud_dog_idam.rbac.membership.MembershipResolver``
  Protocol over the live snapshot (``admin_state.groups_for_user``).
- ``ImapBindingRepository``   : the ``by_subject(subject_type, subject_id)`` data path
  the resolver needs, over ``admin_state.list_bindings_by_subject``.
- ``ImapResourceGuard``       : composes the shared ``RBACEngine`` + the two adapters and
  exposes ``authorise`` / ``allowed_resource_ids`` / ``is_admin`` / ``invalidate``.

The pure decision logic lives in ``cloud_dog_idam.rbac.grants`` (the keystone); this
module only supplies the imap-specific membership + binding data and a thin facade.
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

from typing import TYPE_CHECKING, Any

from cloud_dog_idam.rbac.grants import allowed_resource_ids, authorise

if TYPE_CHECKING:
    from cloud_dog_idam import RBACEngine

    from imap_hub_server.admin.state import FileBackedAdminState


class ImapMembershipResolver:
    """``MembershipResolver`` Protocol over the imap JSON snapshot.

    ``groups_of(user_id)`` reads the live snapshot each call (``groups_for_user``
    already exists at ``state_idam.py``); the idam engine cache (``grants:{uid}``)
    handles caching, and ``ImapResourceGuard.invalidate`` drops it on
    add/remove-member so revocation lands within one request (cascade STEP 5).
    """

    def __init__(self, admin_state: "FileBackedAdminState") -> None:
        """Store the admin-state facade (queries are lazy/live)."""
        self._admin_state = admin_state

    def groups_of(self, user_id: str) -> set[str]:
        """Return the set of ``group_id`` values ``user_id`` is currently a member of."""
        return {g.group_id for g in self._admin_state.groups_for_user(user_id)}


class ImapBindingRepository:
    """``by_subject`` data path over imap's JSON-snapshot RBAC bindings.

    The idam resolver calls ``by_subject("user", uid)`` and ``by_subject("group", gid)``
    and reads ``.resource_type`` / ``.resource_id`` / ``.permission`` from each row.
    ``RBACBindingRecord`` carries exactly those attributes.
    """

    def __init__(self, admin_state: "FileBackedAdminState") -> None:
        """Store the admin-state facade."""
        self._admin_state = admin_state

    def by_subject(self, subject_type: str, subject_id: str) -> list[Any]:
        """Return binding rows for one subject (resolver data path)."""
        return self._admin_state.list_bindings_by_subject(subject_type, subject_id)


class ImapResourceGuard:
    """Resource-aware authorisation facade for imap (IDAM-B2 §3.1).

    Wraps the shared ``RBACEngine`` + the imap membership/binding adapters and
    routes decisions through the idam 0.5.0 resolver. Default-DENY for
    resource-bearing checks; admin wildcard short-circuits; role-level flat
    permissions remain a fallback for surface gates (so the deployed flat
    ``admin``/``read-write``/``read-only`` roles keep working).
    """

    def __init__(
        self, engine: "RBACEngine", admin_state: "FileBackedAdminState"
    ) -> None:
        """Compose the engine with the imap membership + binding adapters."""
        self._engine = engine
        self._membership = ImapMembershipResolver(admin_state)
        self._binding_repo = ImapBindingRepository(admin_state)

    def authorise(
        self,
        user_id: str,
        *,
        permission: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> bool:
        """Return whether ``user_id`` is authorised for ``(permission, resource_type, resource_id)``."""
        return authorise(
            user_id,
            permission=permission,
            resource_type=resource_type,
            resource_id=resource_id,
            engine=self._engine,
            binding_repo=self._binding_repo,
            membership=self._membership,
        )

    def allowed_resource_ids(
        self, user_id: str, resource_type: str, permission: str
    ) -> set[str]:
        """Return the resource_id set the user may access (LIST filter; "*" = all)."""
        return allowed_resource_ids(
            user_id,
            resource_type,
            permission,
            engine=self._engine,
            binding_repo=self._binding_repo,
            membership=self._membership,
        )

    def is_admin(self, user_id: str) -> bool:
        """Return whether the principal holds the admin wildcard (for secret-masking)."""
        try:
            return "*" in set(self._engine.get_effective_permissions(user_id))
        except Exception:
            return False

    def invalidate(self, *user_ids: str) -> None:
        """Drop cached grants for the given user(s) so cascade changes land live.

        Calls the engine's ``_invalidate_user`` (drops ``roles:``/``perms:``/``grants:``
        keys per W28A-741) when present; otherwise clears the whole engine cache.
        Call after add/remove-member or binding create/delete (live revoke, no restart).
        """
        invalidator = getattr(self._engine, "_invalidate_user", None)
        for uid in user_ids:
            if callable(invalidator):
                try:
                    invalidator(uid)
                    continue
                except Exception:
                    pass
            cache = getattr(self._engine, "_cache", None)
            data = getattr(cache, "_data", None)
            if isinstance(data, dict):
                data.clear()


__all__ = [
    "ImapBindingRepository",
    "ImapMembershipResolver",
    "ImapResourceGuard",
]
