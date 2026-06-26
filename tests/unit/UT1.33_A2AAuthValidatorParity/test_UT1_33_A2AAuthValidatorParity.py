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

from cloud_dog_idam import APIKeyManager
from starlette.requests import Request

from imap_hub_server.auth.middleware import (
    register_static_api_key,
    request_api_key_candidate,
    request_has_valid_api_key,
)
import pytest


def _request(headers: dict[str, str]) -> Request:
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1")) for key, value in headers.items()
    ]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/a2a/health",
        "headers": raw_headers,
    }
    return Request(scope)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-04")
@pytest.mark.req("CS-010")


def test_ut133_auth_candidate_prefers_x_api_key() -> None:
    request = _request({"x-api-key": "from-x-api-key", "Authorization": "Bearer from-bearer"})
    assert request_api_key_candidate(request) == "from-x-api-key"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-04")
@pytest.mark.req("CS-010")


def test_ut133_a2a_bearer_and_x_api_key_validate_against_same_manager() -> None:
    manager = APIKeyManager()
    register_static_api_key(manager, "12345678", owner_id="test-a2a")

    assert request_has_valid_api_key(_request({"x-api-key": "12345678"}), manager) is True
    assert (
        request_has_valid_api_key(_request({"Authorization": "Bearer 12345678"}), manager) is True
    )
    assert (
        request_has_valid_api_key(_request({"Authorization": "Bearer wrong-key"}), manager) is False
    )
    assert request_has_valid_api_key(_request({}), manager) is False
