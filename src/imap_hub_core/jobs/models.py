"""imap-mcp-server module."""

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
from typing import Any

from cloud_dog_jobs import Job, JobRequest
from pydantic import BaseModel, ConfigDict, Field

_SERVICE_STATE_KEYS = ("_imap_mcp_job_state",)


class JobEnvelope(BaseModel):
    """Serialisable job envelope persisted through cloud_dog_jobs."""

    model_config = ConfigDict(extra="forbid")

    job_type: str
    profile_id: str | None = None
    queue_name: str = "default"
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
    server_id: str | None = None
    max_attempts: int | None = None
    created_at_utc: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    def to_job_request(self, *, server_id: str, default_max_attempts: int) -> JobRequest:
        """Convert the envelope into the platform job-request contract."""
        payload = self.model_dump(mode="python")
        payload["server_id"] = server_id
        payload["max_attempts"] = self.max_attempts if self.max_attempts is not None else default_max_attempts
        return JobRequest(
            job_type=self.job_type,
            queue_name=self.queue_name,
            payload=payload,
            correlation_id=self.correlation_id,
        )

    @classmethod
    def from_job(cls, job: Job) -> "JobEnvelope":
        """Rebuild the envelope from persisted job payload."""
        if isinstance(job.payload, dict) and job.payload.get("job_type") == job.job_type:
            payload = {
                key: value
                for key, value in job.payload.items()
                if key not in _SERVICE_STATE_KEYS
            }
            return cls.model_validate(payload)
        return cls(
            job_type=job.job_type,
            queue_name=job.queue_name,
            payload=dict(job.payload) if isinstance(job.payload, dict) else {},
            correlation_id=job.correlation_id,
        )


class JobStateRecord(BaseModel):
    """Persisted job-state projection shared across worker processes."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    job_type: str
    queue_name: str
    profile_id: str | None = None
    status: str
    claimed_by: str | None = None
    attempts: int = 0
    max_attempts: int = 3
    last_error: str | None = None
    progress_pct: float = 0.0
    progress_stage: str = ""
    server_id: str
    created_at_utc: str
    updated_at_utc: str
