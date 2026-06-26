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

# Covers: FR-09

from imap_hub_core.audit.events import AuditActor, AuditRecord
import pytest
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-09")


def test_audit_event_has_required_fields() -> None:
    event = AuditRecord(
        operation="sync_start",
        status="ok",
        correlation_id="corr-1",
        actor=AuditActor(actor_id="user-1"),
    )
    assert event.timestamp
    assert event.operation == "sync_start"
    assert event.actor.actor_id == "user-1"
