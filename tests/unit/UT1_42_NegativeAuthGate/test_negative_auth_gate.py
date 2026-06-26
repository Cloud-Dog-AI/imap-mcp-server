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

"""W28A-889-A-R2 — unauthenticated negative-auth gate (COMMON-FINAL-EVIDENCE §0C pt5).

Guards the index-retriever bypass class against the FULL IMAP-MCP API app (real
auth middleware): an unauthenticated caller (no api-key, no cookie, no bearer) must
be DENIED (401) on the admin/IDAM surface and never handed a populated/admin
principal. CI catches a regression locally, not only in preprod.
"""


from __future__ import annotations
import pytest

from fastapi.testclient import TestClient

from imap_hub_server.api_server import create_api_app
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-04")
@pytest.mark.req("CS-001")
@pytest.mark.req("CS-005")
@pytest.mark.req("CS-006")
@pytest.mark.req("CS-007")


def test_unauth_admin_surface_denied_no_principal_leak() -> None:
    app = create_api_app(env_files=["tests/env-UT"])
    client = TestClient(app)

    for path in ("/api/v1/admin/users", "/api/v1/admin/roles", "/api/v1/admin/profiles"):
        resp = client.get(path)
        assert resp.status_code == 401, f"{path} must be 401 unauthenticated, got {resp.status_code}"
        body = resp.text
        # an anonymous caller must NEVER receive a populated/admin principal
        assert '"*"' not in body and '"permissions"' not in body
