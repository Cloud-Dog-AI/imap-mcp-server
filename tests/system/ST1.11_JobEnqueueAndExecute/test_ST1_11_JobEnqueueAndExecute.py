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
from imap_hub_core.jobs import JobEnvelope, JobWorkers
from tests.helpers.ports import listener_host, listener_port
import pytest


def _config(tmp_path: Path) -> GlobalConfigModel:
    return GlobalConfigModel(
        server=ServerConfig(
            server_id="imap-st-node",
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
            backend=JobsBackendConfig(preferred="sql", sql_url=f"sqlite:///{tmp_path / 'jobs.db'}"),
            retry=JobsRetryConfig(max_attempts=2, initial_delay_seconds=0.0, max_delay_seconds=0.0),
            maintenance=JobsMaintenanceConfig(claim_timeout_seconds=1, max_age_seconds=60),
            payload_max_bytes=16384,
        ),
        profiles={},
    )
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-19")


def test_st111_job_enqueue_and_execute_via_platform_queue(tmp_path: Path) -> None:
    workers = JobWorkers.from_config(_config(tmp_path), worker_suffix="st")
    try:
        workers.register("sync", lambda envelope: {"ok": True, "profile_id": envelope.profile_id})
        result = workers.run(JobEnvelope(job_type="sync", profile_id="p1", payload={"force": True}))
        state = workers.list_jobs()

        assert result["ok"] is True
        assert result["profile_id"] == "p1"
        assert len(state) == 1
        assert state[0].status == "succeeded"
        assert state[0].attempts == 1
    finally:
        workers.close()
