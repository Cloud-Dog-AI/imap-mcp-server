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

from datetime import datetime, timezone

from cloud_dog_jobs import Job, JobStatus

from imap_hub_core.jobs.models import JobEnvelope
import pytest
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-19")


def test_job_envelope_builds_platform_request() -> None:
    envelope = JobEnvelope(
        job_type="sync",
        profile_id="gmail_personal",
        payload={"force": True},
        queue_name="sync",
        correlation_id="corr-123",
        max_attempts=4,
    )

    request = envelope.to_job_request(server_id="imap-node-a", default_max_attempts=3)

    assert request.job_type == "sync"
    assert request.queue_name == "sync"
    assert request.correlation_id == "corr-123"
    assert request.payload["profile_id"] == "gmail_personal"
    assert request.payload["payload"] == {"force": True}
    assert request.payload["server_id"] == "imap-node-a"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-19")


def test_job_envelope_rehydrates_from_persisted_job_payload() -> None:
    now = datetime.now(timezone.utc)
    job = Job(
        job_id="job-1",
        job_type="sync",
        queue_name="sync",
        payload={
            "job_type": "sync",
            "profile_id": "ops",
            "queue_name": "sync",
            "payload": {"force": False},
            "max_attempts": 2,
            "created_at_utc": "2026-01-01T00:00:00Z",
        },
        status=JobStatus.QUEUED,
        priority=0,
        created_at=now,
        updated_at=now,
    )

    envelope = JobEnvelope.from_job(job)

    assert envelope.profile_id == "ops"
    assert envelope.payload == {"force": False}
    assert envelope.max_attempts == 2
