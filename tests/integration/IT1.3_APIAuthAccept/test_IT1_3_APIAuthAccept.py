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

import httpx
import pytest
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-04")


def test_it13_api_auth_accept(integration_server) -> None:
    with httpx.Client(base_url=integration_server.api_base_url, timeout=30.0) as client:
        response = client.get(
            integration_server.api_path("/tools"), headers={"x-api-key": integration_server.api_key}
        )
    assert response.status_code == 200
    assert response.json()["ok"] is True
