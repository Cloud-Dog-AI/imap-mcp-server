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

from email.message import EmailMessage

import pytest

from imap_hub_core.attachment.listing import list_attachments
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-05")


def test_attachment_parser_enforces_max_size() -> None:
    message = EmailMessage()
    message.set_content("body")
    message.add_attachment(
        b"0123456789", maintype="application", subtype="octet-stream", filename="big.bin"
    )
    with pytest.raises(ValueError):
        list_attachments(message, max_attachment_bytes=5)
