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
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("CS-014")


def test_qt11_secrets_never_logged(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    writer = AuditWriter(str(path))
    writer.emit(
        AuditRecord(
            operation="token_write",
            status="success",
            correlation_id="qt11",
            actor=AuditActor(actor_id="tester"),
            params={"api_key": "<api-key>", "password": "<password>"},
        )
    )
    writer.close()

    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines
    payload = json.loads(lines[-1])
    serialised = json.dumps(payload)
    assert "very-secret" not in serialised
    assert "hidden" not in serialised
