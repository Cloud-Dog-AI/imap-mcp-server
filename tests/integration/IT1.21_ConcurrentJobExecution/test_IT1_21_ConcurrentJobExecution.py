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
from threading import Event, Thread
import time

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


def _config(tmp_path: Path, server_id: str) -> GlobalConfigModel:
    return GlobalConfigModel(
        server=ServerConfig(
            server_id=server_id,
            auth=ServerAuthConfig(mode="api_key"),
            audit=AuditConfig(log_path=str(tmp_path / f"{server_id}-audit.jsonl")),
            storage=StorageConfig(
                data_dir=str(tmp_path / "shared-data"),
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
            backend=JobsBackendConfig(preferred="sql", sql_url=f"sqlite:///{tmp_path / 'jobs.db'}"),
            retry=JobsRetryConfig(max_attempts=1, initial_delay_seconds=0.0, max_delay_seconds=0.0),
            maintenance=JobsMaintenanceConfig(claim_timeout_seconds=1, max_age_seconds=60),
            payload_max_bytes=16384,
        ),
        profiles={},
    )
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-19")


def test_it121_two_workers_claim_and_complete_distinct_jobs(tmp_path: Path) -> None:
    runtime_a = build_jobs_runtime(_config(tmp_path, "imap-it-a"), worker_suffix="it-a")
    runtime_b = build_jobs_runtime(_config(tmp_path, "imap-it-b"), worker_suffix="it-b")
    release = Event()
    claims: list[str] = []

    def _handler(envelope: JobEnvelope) -> dict[str, str]:
        claims.append(envelope.profile_id or "missing")
        release.wait(timeout=2.0)
        return {"profile_id": envelope.profile_id or ""}

    try:
        runtime_a.register_handler("sync", _handler)
        runtime_b.register_handler("sync", _handler)
        job_a = runtime_a.submit(JobEnvelope(job_type="sync", profile_id="profile-a", payload={}))
        job_b = runtime_a.submit(JobEnvelope(job_type="sync", profile_id="profile-b", payload={}))

        thread_a = Thread(target=runtime_a.run_once)
        thread_b = Thread(target=runtime_b.run_once)
        thread_a.start()
        thread_b.start()
        release.set()
        thread_a.join(timeout=5.0)
        thread_b.join(timeout=5.0)

        deadline = time.monotonic() + 5.0
        state_a = runtime_a.get_state(job_a)
        state_b = runtime_a.get_state(job_b)
        while time.monotonic() < deadline:
            if (
                state_a is not None
                and state_b is not None
                and state_a.status == "succeeded"
                and state_b.status == "succeeded"
                and sorted(claims) == ["profile-a", "profile-b"]
            ):
                break
            time.sleep(0.05)
            state_a = runtime_a.get_state(job_a)
            state_b = runtime_a.get_state(job_b)
        assert state_a is not None and state_a.status == "succeeded"
        assert state_b is not None and state_b.status == "succeeded"
        assert sorted(claims) == ["profile-a", "profile-b"]
        assert len({state_a.claimed_by, state_b.claimed_by}) == 2
    finally:
        runtime_a.close()
        runtime_b.close()
