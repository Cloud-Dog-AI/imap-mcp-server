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

from fastapi.testclient import TestClient

from imap_hub_core.jobs.models import JobEnvelope
from imap_hub_server.api_server import create_api_app
import pytest


def _build_app(tmp_path, monkeypatch):
    env_file = tmp_path / "ut-jobs-admin.env"
    data_dir = tmp_path / "data"
    env_file.write_text(
        "\n".join(
            [
                "CLOUD_DOG__SERVER__AUTH__MODE=api_key",
                f"CLOUD_DOG__SERVER__STORAGE__DATA_DIR={data_dir.as_posix()}",
                "CLOUD_DOG__API_SERVER__PORT=18170",
                "CLOUD_DOG__WEB_SERVER__PORT=18171",
                "CLOUD_DOG__MCP_SERVER__PORT=18172",
                "CLOUD_DOG__A2A_SERVER__PORT=18173",
                "CLOUD_DOG__PROFILES__OPERATIONS__IMAP__HOST=127.0.0.1",
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("TEST_ENV_TIER", "UT")
    monkeypatch.setenv("API_KEY", "unit-admin-key")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "unit-google-secret")
    monkeypatch.setenv("MS_CLIENT_SECRET", "unit-ms-secret")
    monkeypatch.setenv("IMAP_OPERATIONS_HOST", "127.0.0.1")
    monkeypatch.setenv("IMAP_OPERATIONS_PORT", "993")
    monkeypatch.setenv("IMAP_OPERATIONS_USERNAME", "unit-operations")
    monkeypatch.setenv("IMAP_OPERATIONS_PASSWORD", "unit-password")
    monkeypatch.setenv("CLOUD_DOG__PROFILES__OPERATIONS__IMAP__PORT", "993")
    monkeypatch.setenv("CLOUD_DOG__PROFILES__OPERATIONS_CLOUD_DOG__IMAP__PORT", "993")
    return create_api_app(env_files=[str(env_file)])


def _create_managed_key(
    client: TestClient,
    admin_headers: dict[str, str],
    *,
    user_id: str,
    role: str,
) -> str:
    created_user = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "user_id": user_id,
            "username": user_id,
            "email": f"{user_id}@example.test",
            "role": role,
        },
    )
    assert created_user.status_code == 200, created_user.text

    created_key = client.post(
        "/api/v1/admin/api-keys",
        headers=admin_headers,
        json={
            "owner_user_id": user_id,
            "scopes": ["*"],
            "description": f"{role} key",
        },
    )
    assert created_key.status_code == 200, created_key.text
    return created_key.json()["result"]["raw_key"]
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-19")


def test_jobs_admin_routes_enforce_permissions_and_return_enriched_records(tmp_path, monkeypatch) -> None:
    app = _build_app(tmp_path, monkeypatch)
    runtime = app.state.jobs_runtime

    queued_job_id = runtime.submit(
        JobEnvelope(
            job_type="sync",
            profile_id="ops",
            payload={"mailbox": "INBOX", "request_auth_identity": "queue-reader"},
        )
    )
    retry_job_id = runtime.submit(
        JobEnvelope(
            job_type="sync",
            profile_id="ops",
            payload={"mailbox": "Archive", "request_auth_identity": "queue-writer"},
        )
    )
    archived_job_id = runtime.submit(
        JobEnvelope(
            job_type="archive",
            profile_id="ops",
            payload={"mailbox": "Sent"},
        )
    )
    assert runtime.backend.update_status(retry_job_id, "failed") is True
    assert runtime.backend.update_status(archived_job_id, "succeeded") is True

    with TestClient(app) as client:
        admin_headers = {"x-api-key": str(app.state.seed_api_key), "x-role": "admin"}

        rbac_before = client.get("/api/v1/admin/rbac/policies", headers=admin_headers)
        assert rbac_before.status_code == 200, rbac_before.text
        roles = dict(rbac_before.json()["result"]["roles"])
        roles["job-reader"] = ["read_jobs"]
        roles["job-writer"] = ["write_jobs"]
        updated_rbac = client.put(
            "/api/v1/admin/rbac/policies",
            headers=admin_headers,
            json={"roles": roles},
        )
        assert updated_rbac.status_code == 200, updated_rbac.text

        reader_key = _create_managed_key(client, admin_headers, user_id="jobs-reader", role="job-reader")
        writer_key = _create_managed_key(client, admin_headers, user_id="jobs-writer", role="job-writer")
        viewer_key = _create_managed_key(client, admin_headers, user_id="jobs-viewer", role="viewer")

        reader_headers = {"x-api-key": reader_key}
        writer_headers = {"x-api-key": writer_key}
        viewer_headers = {"x-api-key": viewer_key}

        list_response = client.get("/api/v1/admin/jobs", headers=reader_headers)
        assert list_response.status_code == 200, list_response.text
        items = list_response.json()["result"]["items"]
        queued_record = next(item for item in items if item["job_id"] == queued_job_id)
        assert queued_record["profile_id"] == "ops"
        assert queued_record["mailbox"] == "INBOX"
        assert queued_record["request_auth_identity"] == "queue-reader"
        assert "payload" in queued_record

        queue_status = client.get("/api/v1/admin/jobs/queue/status", headers=writer_headers)
        assert queue_status.status_code == 200, queue_status.text
        assert queue_status.json()["result"]["counts"]["queued"] >= 1

        detail_response = client.get(f"/api/v1/admin/jobs/{retry_job_id}", headers=reader_headers)
        assert detail_response.status_code == 200, detail_response.text
        assert detail_response.json()["result"]["status"] == "failed"

        denied_list = client.get("/api/v1/admin/jobs", headers=viewer_headers)
        assert denied_list.status_code == 403, denied_list.text

        denied_cancel = client.post(f"/api/v1/admin/jobs/{queued_job_id}/cancel", headers=reader_headers)
        assert denied_cancel.status_code == 403, denied_cancel.text

        cancel_response = client.post(f"/api/v1/admin/jobs/{queued_job_id}/cancel", headers=writer_headers)
        assert cancel_response.status_code == 200, cancel_response.text
        assert cancel_response.json()["result"]["job"]["status"] == "cancelled"

        retry_response = client.post(f"/api/v1/admin/jobs/{retry_job_id}/retry", headers=writer_headers)
        assert retry_response.status_code == 200, retry_response.text
        assert retry_response.json()["result"]["job"]["status"] == "queued"

        denied_delete = client.delete(f"/api/v1/admin/jobs/{archived_job_id}", headers=writer_headers)
        assert denied_delete.status_code == 403, denied_delete.text

        delete_response = client.delete(f"/api/v1/admin/jobs/{archived_job_id}", headers=admin_headers)
        assert delete_response.status_code == 200, delete_response.text
        assert delete_response.json()["result"]["job"]["status"] == "archived"
