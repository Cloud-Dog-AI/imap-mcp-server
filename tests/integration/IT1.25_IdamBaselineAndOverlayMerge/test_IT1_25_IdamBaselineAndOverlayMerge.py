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

"""IT1.25 — IDAM uplift: six undeletable baseline roles + role_overlay baseline merge.

PS-IDAM-ROLE-CASCADE v1.0 (W28E-1803B Stream-B D5) requires the service to prove,
against the real ``cloud_dog_idam`` engine, that:

  * the six undeletable baseline role entries are present and stable, and
  * the service's flat-role catalogue is layered via ``role_overlay=`` so that it is
    MERGED on top of the baseline (per-role union) rather than replacing it.

The scoped ``RBACBinding`` cascade and live-revoke-without-restart proofs live in
``tests/smoke/test_cascade_resolves.py`` (T3-IMAP-CASCADE). This module closes the
two remaining PS-IDAM-ROLE-CASCADE obligations (baseline-presence + overlay-merge)
and the fail-closed flat-role posture.
"""

from __future__ import annotations

import pytest

from cloud_dog_idam import BASELINE_ROLE_NAMES, BASELINE_ROLE_PERMISSIONS

from imap_hub_server.web_flat_roles import (
    build_flat_rbac_engine,
    normalise_flat_role,
    permissions_for_role,
    role_can_write,
    role_is_admin,
)

#: The six undeletable baseline role identifiers shared across every cloud-dog
#: service (cloud_dog_idam BASELINE_ROLE_NAMES). Hard-pinned here so a silent
#: baseline drift in a future idam release fails this lane's contract.
EXPECTED_BASELINE_ROLES = {
    "admin",
    "audit-log",
    "group-admin",
    "job-control",
    "restricted",
    "user",
}


@pytest.mark.IT
@pytest.mark.internal
@pytest.mark.req("FR-04")
def test_it25_six_undeletable_baseline_roles_present() -> None:
    """The shared idam baseline exposes exactly the six canonical role entries."""
    assert set(BASELINE_ROLE_NAMES) == EXPECTED_BASELINE_ROLES
    # Each baseline role carries a defined (non-None) permission set in the catalogue.
    for role in EXPECTED_BASELINE_ROLES:
        assert role in BASELINE_ROLE_PERMISSIONS
        assert isinstance(BASELINE_ROLE_PERMISSIONS[role], (set, frozenset))


@pytest.mark.IT
@pytest.mark.internal
@pytest.mark.req("FR-04")
@pytest.mark.req("FR-13")
def test_it25_role_overlay_merges_with_baseline() -> None:
    """The flat catalogue is overlaid (merged), not substituted, onto the baseline.

    Proven by assigning a synthetic user to a BASELINE-ONLY role (``audit-log``)
    that the imap flat overlay does not redefine: the engine still resolves its
    baseline permissions, which is only possible if ``role_overlay=`` performed a
    per-role union with ``BASELINE_ROLE_PERMISSIONS`` rather than a full replace.
    """
    engine = build_flat_rbac_engine()

    # Baseline-only role survives the overlay (merge proof).
    engine.assign_role_to_user("u-audit", "audit-log")
    audit_perms = set(engine.get_effective_permissions("u-audit"))
    assert audit_perms, "audit-log baseline role resolved to no permissions"
    assert set(BASELINE_ROLE_PERMISSIONS["audit-log"]).issubset(audit_perms)

    engine.assign_role_to_user("u-job", "job-control")
    job_perms = set(engine.get_effective_permissions("u-job"))
    assert set(BASELINE_ROLE_PERMISSIONS["job-control"]).issubset(job_perms)

    # The flat overlay roles are also resolvable with their imap use-permissions.
    rw_perms = set(permissions_for_role("read-write"))
    assert "imap:mail:read" in rw_perms and "imap:mail:write" in rw_perms
    ro_perms = set(permissions_for_role("read-only"))
    assert "imap:mail:write" not in ro_perms  # read-only never gains write via overlay


@pytest.mark.IT
@pytest.mark.internal
@pytest.mark.req("FR-04")
def test_it25_flat_role_semantics_fail_closed() -> None:
    """Flat-role privilege mapping is correct and unknown roles fail closed."""
    assert role_is_admin("admin") is True
    assert role_can_write("admin") is True
    assert role_can_write("read-write") is True

    # read-only and any unrecognised role normalise to read-only (no write).
    assert role_can_write("read-only") is False
    assert role_is_admin("read-only") is False
    assert normalise_flat_role("totally-unknown-role") == "read-only"
    assert role_can_write("totally-unknown-role") is False
