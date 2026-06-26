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

import os
from uuid import uuid4

from fastapi.testclient import TestClient

from imap_hub_server.api_server import create_api_app
import pytest


def _headers(app) -> dict[str, str]:
    key = str(getattr(app.state, "seed_api_key", "") or "")
    assert key
    return {"x-api-key": key, "Authorization": f"Bearer {key}", "x-role": "admin"}


def _runtime_env_files() -> list[str] | None:
    raw = os.getenv("TEST_ENV_FILES", "").strip()
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]

    mode = os.getenv("TEST_RUNTIME_MODE", "").strip().lower()
    if mode == "local-docker":
        return ["tests/env-AT-local-docker"]
    if mode == "local-server":
        return ["tests/env-AT-local-server"]
    return ["tests/env-AT"]


def _api_base_path() -> str:
    value = (os.getenv("TEST_API_BASE_PATH", "") or "/api/v1").strip() or "/api/v1"
    if not value.startswith("/"):
        value = "/" + value
    if value != "/":
        value = value.rstrip("/")
    return value
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-23")


def test_at19_database_e2e_profile_workflow() -> None:
    os.environ["CA_BUNDLE_PATH"] = "/etc/ssl/certs/ca-certificates.crt"
    app = create_api_app(env_files=_runtime_env_files())
    api_base_path = _api_base_path()
    headers = _headers(app)
    profile_id = f"at19_profile_{uuid4().hex[:8]}"

    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200

        create = client.put(
            f"{api_base_path}/admin/profiles/{profile_id}",
            headers=headers,
            json={"provider": "imap_generic", "enabled": True},
        )
        assert create.status_code == 200

        listed = client.get(f"{api_base_path}/admin/profiles", headers=headers)
        assert listed.status_code == 200
        assert profile_id in set((listed.json().get("result") or {}).get("profiles") or [])

        reconcile = client.post(
            f"{api_base_path}/admin/index/reconcile",
            headers=headers,
            json={
                "documents": [
                    {
                        "profile_id": profile_id,
                        "message_id": f"<{profile_id}@example.com>",
                        "folder": "INBOX",
                        "uid": 1,
                        "uidvalidity": 1,
                        "date_utc": "2026-03-08T00:00:00Z",
                        "from": "operations@example.com",
                        "to": "operations@example.com",
                        "cc": "",
                        "subject": "AT1.9 index reconcile",
                        "source": "at19",
                        "content_type": "text/plain",
                        "chunk_id": "chunk-1",
                        "content_hash": "hash-at19-1",
                    }
                ]
            },
        )
        assert reconcile.status_code == 200
        assert int((reconcile.json().get("result") or {}).get("count") or 0) >= 1

        delete = client.delete(f"{api_base_path}/admin/profiles/{profile_id}", headers=headers)
        assert delete.status_code == 200
