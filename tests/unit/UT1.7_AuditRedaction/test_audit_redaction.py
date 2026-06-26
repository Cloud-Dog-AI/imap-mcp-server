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

from imap_hub_core.audit.events import AuditActor, AuditRecord
import pytest
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-09")


def test_audit_redacts_secret_fields() -> None:
    event = AuditRecord(
        operation="credential_rotate",
        status="ok",
        correlation_id="corr-2",
        actor=AuditActor(actor_id="admin"),
        params={"api_key": "secret", "folder": "INBOX"},
    )
    redacted = event.redacted_params()
    assert redacted["api_key"] == "***REDACTED***"
    assert redacted["folder"] == "INBOX"
