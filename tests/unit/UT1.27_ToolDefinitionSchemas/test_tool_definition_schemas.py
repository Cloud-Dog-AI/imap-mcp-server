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
from pydantic import ValidationError

from imap_hub_core.tools.definitions import MailSearchInput
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-01")
@pytest.mark.req("CS-011")
@pytest.mark.req("CS-012")
@pytest.mark.req("CS-013")


def test_tool_schema_validation_for_mail_search() -> None:
    payload = MailSearchInput.model_validate({"profile_id": "p1", "query": "invoice"})
    assert payload.mode == "cache"

    with pytest.raises(ValidationError):
        MailSearchInput.model_validate({"query": "missing_profile"})
