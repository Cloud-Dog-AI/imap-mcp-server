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

from pathlib import Path
import pytest

BANNED_SPELLINGS = {
    "color": "colour",
    "behavior": "behaviour",
    "authorization": "authorisation",
    "organization": "organisation",
}
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("NF-004")


def test_qt14_uk_english_compliance() -> None:
    root = Path("src")
    offenders: list[str] = []

    for path in root.rglob("*.py"):
        content = path.read_text(encoding="utf-8").lower()
        for us_word in BANNED_SPELLINGS:
            if us_word in content:
                offenders.append(f"{path}:{us_word}")

    assert offenders == []
