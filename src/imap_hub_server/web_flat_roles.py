"""imap-mcp-server — Thread-a flat WebUI roles (admin / read-write / read-only).

License: Apache 2.0
Ownership: Cloud-Dog, Viewdeck Engineering Limited
Description: Flat WebUI roles (admin / read-write / read-only) for the Thread-a
  login, derived from the shared ``cloud_dog_idam`` RBACEngine + role_catalog
  (no per-service fork). Names the three flat roles and resolves their
  permission sets from the shared canonical catalog.
Requirements: FR-04, CS1.1
Tasks: W28A-735-R5
Architecture: SE Authentication
Tests: tests/unit/UT_WebFlatRoles
Recent Change History:
- 2026-06-11: W28A-735-R5 flat-login surface re-proof + D-IMAP-IDENTITY-COLLAPSE-1.

Thread a is the *simple, flat* login that gets the demo back: three roles —
``admin`` (full), ``read-write`` (use it), ``read-only`` (view). No granularity
(that is Thread b). Roles are computed via the ONE shared guard
(``cloud_dog_idam.RBACEngine`` + the canonical PS-82 §7 permission catalog) —
there is no per-service RBAC fork here; this module only *names* the three flat
roles and derives their permission sets from the shared catalog.

The shared idam ships two baseline roles (``admin`` -> ``*`` and ``user`` ->
the PS-82 §7.2 default grant). The flat lane maps:

* ``admin``      -> the shared ``admin`` baseline (wildcard ``*``).
* ``read-write`` -> the shared ``user`` baseline PLUS the imap use-permissions a
  demo operator needs to actually *use* the mail service (read + search + move /
  flag / delete mail, manage folders, manage their storage profiles).
* ``read-only``  -> the shared ``user`` baseline only (view + self-service);
  every write resolves to a 403 at the enforcement point (never a blank UI).

This mirrors a1/chat-client and file-mcp's ``web_flat_roles.py`` exactly; only
the service-specific *use* permissions differ (imap:mail:* / imap:folder:* /
profile:write vs file:* / chat:*).
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

from cloud_dog_idam import RBACEngine  # type: ignore[import-untyped]
from cloud_dog_idam.rbac import role_catalog as _rc  # type: ignore[import-untyped]

# The shared idam wildcard ("*") is the one stable, always-present symbol.
WILDCARD_PERMISSION: str = getattr(_rc, "WILDCARD_PERMISSION", "*")


def _shared_user_baseline() -> set[str]:
    """Return the shared idam ``user`` baseline grant.

    Thread a anchors read-write/read-only on the SAME ``user`` baseline every
    other service inherits, so the flat roles stay consistent with the central
    catalog and there is no per-service fork. Resolve whichever symbol the
    installed idam provides so this builds against both the current AND the
    post-a0 idam — never crashing on an import of a symbol that has not landed
    yet.
    """
    explicit = getattr(_rc, "USER_BASELINE_PERMISSIONS", None)
    if explicit:
        return set(explicit)
    baseline = getattr(_rc, "BASELINE_ROLE_PERMISSIONS", {}) or {}
    user_grant = baseline.get("user")
    if user_grant:
        return set(user_grant)
    # Last-resort floor: a read-only view grant so a read-only session is never
    # empty (fail-safe, still view-only).
    return {"resources:read"}


def _shared_write_permissions() -> set[str]:
    """Named config/profiles WRITE grants from the shared catalog, if present.

    Uses the canonical strings when the richer a0 catalog is installed; absent
    those symbols, contributes nothing extra (the literal imap-use permissions
    below still let a read-write operator use the system).
    """
    out: set[str] = set()
    for name in ("CONFIG_WRITE", "PROFILES_WRITE"):
        value = getattr(_rc, name, None)
        if isinstance(value, str) and value:
            out.add(value)
    return out


#: The three flat roles, in descending privilege order.
ADMIN_ROLE = "admin"
READ_WRITE_ROLE = "read-write"
READ_ONLY_ROLE = "read-only"

FLAT_ROLES: tuple[str, ...] = (ADMIN_ROLE, READ_WRITE_ROLE, READ_ONLY_ROLE)

# imap-mcp use-permissions the read-write operator needs on top of the shared
# §7.2 user baseline. These are the strings the imap tool RBAC authorises on
# (see imap_hub_core/tools/tool_rbac.py — resource:action / PS-70 UM3). Kept
# minimal and flat; Thread b adds granularity. NOTE: ``imap:admin:*`` is
# deliberately EXCLUDED — admin CRUD stays with the admin flat role only.
_IMAP_USE_PERMISSIONS: set[str] = {
    "imap:mail:read",
    "imap:mail:write",
    "imap:mail:delete",
    "imap:folder:read",
    "imap:folder:write",
    "imap:index:read",
    "imap:index:write",
    "profile:write",
}


#: Flat role -> permission set, built from the shared canonical catalog.
#: ``admin`` is the shared wildcard; ``read-write`` and ``read-only`` are both
#: anchored on the shared ``user`` baseline so they stay consistent with every
#: other service that inherits the same idam.
FLAT_ROLE_PERMISSIONS: dict[str, set[str]] = {
    ADMIN_ROLE: {WILDCARD_PERMISSION},
    READ_WRITE_ROLE: (
        _shared_user_baseline()
        | _shared_write_permissions()
        | _IMAP_USE_PERMISSIONS
    ),
    READ_ONLY_ROLE: _shared_user_baseline(),
}


def normalise_flat_role(role: str | None) -> str:
    """Map an arbitrary role string onto one of the three flat roles.

    Anything that is not clearly admin / read-write resolves to the safest flat
    role (``read-only``) so an unknown role can never silently gain write access
    (fail-closed).
    """
    raw = str(role or "").strip().lower().replace("_", "-")
    if raw in {ADMIN_ROLE, "owner", "superuser", "super-admin"}:
        return ADMIN_ROLE
    if raw in {READ_WRITE_ROLE, "readwrite", "writer", "editor", "user", "member"}:
        return READ_WRITE_ROLE
    return READ_ONLY_ROLE


def build_flat_rbac_engine() -> RBACEngine:
    """Return the ONE shared RBACEngine loaded with the flat role catalog."""
    return RBACEngine(
        role_overlay={name: set(perms) for name, perms in FLAT_ROLE_PERMISSIONS.items()}
    )


def permissions_for_role(role: str) -> list[str]:
    """Return the sorted effective permissions for a flat role via the shared engine."""
    flat = normalise_flat_role(role)
    engine = build_flat_rbac_engine()
    uid = f"flat:{flat}"
    engine.assign_role_to_user(uid, flat)
    return sorted(engine.get_effective_permissions(uid))


def role_can_write(role: str) -> bool:
    """True when the flat role may perform write/mutation operations."""
    return normalise_flat_role(role) in {ADMIN_ROLE, READ_WRITE_ROLE}


def role_is_admin(role: str) -> bool:
    """True when the flat role is the full-admin flat role."""
    return normalise_flat_role(role) == ADMIN_ROLE
