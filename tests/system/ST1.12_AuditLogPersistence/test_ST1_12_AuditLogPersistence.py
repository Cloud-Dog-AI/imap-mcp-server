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

import json

from imap_hub_core.audit.events import AuditActor, AuditRecord
from imap_hub_core.audit.logger import AuditWriter
import pytest
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-09")


def test_st112_audit_log_persistence(tmp_path) -> None:
    audit_file = tmp_path / "audit.jsonl"
    writer = AuditWriter(str(audit_file))
    writer.emit(
        AuditRecord(
            operation="sync_start",
            status="success",
            correlation_id="corr-1",
            actor=AuditActor(actor_id="tester"),
            params={"token": "secret"},
        )
    )
    writer.close()
    assert audit_file.exists()
    line = audit_file.read_text(encoding="utf-8").strip().splitlines()[-1]
    _ = json.loads(line)
    assert "sync_start" in line
