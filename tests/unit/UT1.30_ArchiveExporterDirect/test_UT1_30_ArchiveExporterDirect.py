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

from datetime import datetime
from pathlib import Path

from imap_hub_core.archive.exporter import ArchiveExporter
import pytest
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-21")


def test_ut130_archive_exporter_direct(tmp_path) -> None:
    exporter = ArchiveExporter(str(tmp_path))
    path = exporter.export_message(
        profile_id="gmail_personal",
        received_at=datetime(2026, 2, 19, 12, 0, 0),
        message_id="message-1",
        raw_eml=b"Subject: test\n\nbody",
        metadata_json='{"subject": "test"}',
    )
    target = Path(path)
    assert target.exists()
    assert (target / "message.eml").exists()
    assert (target / "message.json").exists()
