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

from imap_hub_core.message.normalise import normalise_message_metadata
import pytest
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-05")


def test_message_metadata_normalises_dates_and_whitespace() -> None:
    output = normalise_message_metadata(
        {
            "date": "2026-02-19T12:00:00+01:00",
            "from": "  user@example.com  ",
            "subject": "  Hello ",
        }
    )
    assert output["date_utc"] == "2026-02-19T11:00:00Z"
    assert output["from"] == "user@example.com"
    assert output["subject"] == "Hello"
