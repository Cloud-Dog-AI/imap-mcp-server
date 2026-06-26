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

# Covers: FR-04

import httpx
import pytest
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("CS-005")


def test_it12_api_auth_reject(integration_server) -> None:
    with httpx.Client(base_url=integration_server.api_base_url, timeout=30.0) as client:
        response = client.get(integration_server.api_path("/tools"))
    assert response.status_code == 401
