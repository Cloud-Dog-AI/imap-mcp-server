# Covers: FR-07

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

from imap_hub_core.config.models import (
    AuditConfig,
    GlobalConfigModel,
    JobsBackendConfig,
    JobsConfig,
    JobsMaintenanceConfig,
    JobsRetryConfig,
    ListenerConfig,
    LimitsConfig,
    MCPServerConfig,
    RBACConfig,
    SchedulerConfig,
    ServerAuthConfig,
    ServerConfig,
    StorageConfig,
)
from imap_hub_core.jobs import JobEnvelope, build_jobs_runtime
from tests.helpers.ports import listener_host, listener_port
import pytest


def _config(tmp_path: Path) -> GlobalConfigModel:
    return GlobalConfigModel(
        server=ServerConfig(
            server_id="imap-ut-node",
            auth=ServerAuthConfig(mode="api_key"),
            audit=AuditConfig(log_path=str(tmp_path / "audit.jsonl")),
            storage=StorageConfig(
                data_dir=str(tmp_path / "data"),
                downloads_dir=str(tmp_path / "downloads"),
                archive_dir=str(tmp_path / "archive"),
            ),
            limits=LimitsConfig(
                max_search_results=200,
                max_message_bytes=5000000,
                max_attachment_bytes=25000000,
                extractor_timeout_sec=30,
            ),
        ),
        api_server=ListenerConfig(
            host=listener_host("CLOUD_DOG__API_SERVER__HOST"),
            port=listener_port("CLOUD_DOG__API_SERVER__PORT"),
            base_path="/api/v1",
        ),
        web_server=ListenerConfig(
            host=listener_host("CLOUD_DOG__WEB_SERVER__HOST"),
            port=listener_port("CLOUD_DOG__WEB_SERVER__PORT"),
            base_path="",
        ),
        mcp_server=MCPServerConfig(
            host=listener_host("CLOUD_DOG__MCP_SERVER__HOST"),
            port=listener_port("CLOUD_DOG__MCP_SERVER__PORT"),
            base_path="/mcp",
            transport="streamable-http",
        ),
        a2a_server=ListenerConfig(
            host=listener_host("CLOUD_DOG__A2A_SERVER__HOST"),
            port=listener_port("CLOUD_DOG__A2A_SERVER__PORT"),
            base_path="/a2a",
        ),
        sync=SchedulerConfig(schedule_sec=120),
        index=SchedulerConfig(schedule_sec=300, enabled=False, managed=True, backend={}),
        rbac=RBACConfig(enabled=True, roles={"admin": ["*"]}),
        jobs=JobsConfig(
            backend=JobsBackendConfig(
                preferred="sql",
                sql_url=f"sqlite:///{tmp_path / 'jobs.db'}",
            ),
            retry=JobsRetryConfig(max_attempts=2, initial_delay_seconds=0.0, max_delay_seconds=0.0),
            maintenance=JobsMaintenanceConfig(claim_timeout_seconds=1, max_age_seconds=60),
            payload_max_bytes=16384,
        ),
        profiles={},
    )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-19")


def test_ut_jobs_01_job_creation_and_persisted_state(tmp_path: Path) -> None:
    runtime = build_jobs_runtime(_config(tmp_path), worker_suffix="ut-submit")
    try:
        job_id = runtime.submit(
            JobEnvelope(job_type="sync", profile_id="ops", payload={"force": True}, queue_name="sync")
        )

        job = runtime.get_job(job_id)
        state = runtime.get_state(job_id)

        assert job is not None
        assert job.status.value == "queued"
        assert state is not None
        assert state.status == "queued"
        assert state.attempts == 0
        assert state.profile_id == "ops"
    finally:
        runtime.close()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-19")


def test_ut_jobs_02_claim_and_completion(tmp_path: Path) -> None:
    runtime = build_jobs_runtime(_config(tmp_path), worker_suffix="ut-success")
    try:
        runtime.register_handler("sync", lambda envelope: {"profile_id": envelope.profile_id, "ok": True})
        job_id = runtime.submit(JobEnvelope(job_type="sync", profile_id="ops", payload={"force": True}))

        assert runtime.run_once() is True

        job = runtime.get_job(job_id)
        state = runtime.get_state(job_id)
        assert job is not None
        assert job.status.value == "succeeded"
        assert state is not None
        assert state.status == "succeeded"
        assert state.attempts == 1
        assert runtime.last_result(job_id) == {"profile_id": "ops", "ok": True}
    finally:
        runtime.close()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-19")


def test_ut_jobs_03_failure_tracks_attempts_and_retries(tmp_path: Path) -> None:
    runtime = build_jobs_runtime(_config(tmp_path), worker_suffix="ut-retry")
    calls = {"count": 0}

    def _handler(_: JobEnvelope) -> None:
        calls["count"] += 1
        raise RuntimeError("boom")

    try:
        runtime.register_handler("sync", _handler)
        job_id = runtime.submit(JobEnvelope(job_type="sync", profile_id="ops", payload={"force": True}))

        assert runtime.run_once() is True
        first = runtime.get_job(job_id)
        first_state = runtime.get_state(job_id)
        assert first is not None and first.status.value == "queued"
        assert first_state is not None
        assert first_state.attempts == 1
        assert first_state.last_error == "boom"

        assert runtime.run_once() is True
        second = runtime.get_job(job_id)
        second_state = runtime.get_state(job_id)
        assert second is not None and second.status.value == "failed"
        assert second_state is not None
        assert second_state.attempts == 2
        assert calls["count"] == 2
    finally:
        runtime.close()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-19")


def test_ut_jobs_04_queue_status_reports_backend_and_tracking(tmp_path: Path) -> None:
    runtime = build_jobs_runtime(_config(tmp_path), worker_suffix="ut-status")
    try:
        runtime.submit(JobEnvelope(job_type="sync", profile_id="ops", payload={}))
        status = runtime.queue_status()
        assert status["backend"] == "sql"
        assert status["healthy"] is True
        assert status["counts"]["queued"] == 1
        assert status["tracked_jobs"] == 1
    finally:
        runtime.close()
