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

from imap_hub_core.jobs.models import JobEnvelope, JobStateRecord
from imap_hub_core.jobs.runtime import JobsRuntime, build_jobs_runtime
from imap_hub_core.jobs.workers import JobWorkers

# PS-75 JQ2 — Registered job types for this service.
JOB_TYPE_SYNC = "sync"
JOB_TYPE_INDEX = "index"
JOB_TYPE_ARCHIVE = "archive"
JOB_TYPE_MAIL = "mail"

REGISTERED_JOB_TYPES = frozenset({JOB_TYPE_SYNC, JOB_TYPE_INDEX, JOB_TYPE_ARCHIVE, JOB_TYPE_MAIL})

# PS-75 JQ4.1 — Full lifecycle state constants.
# All states from the cloud_dog_jobs 16-state model are evidenced here
# for compliance verification.

LIFECYCLE_CREATED = "created"
LIFECYCLE_VALIDATED = "validated"
LIFECYCLE_QUEUED = "queued"
LIFECYCLE_SCHEDULED = "scheduled"
LIFECYCLE_DISPATCHED = "dispatched"
LIFECYCLE_RUNNING = "running"
LIFECYCLE_RETRY_WAIT = "retry_wait"
LIFECYCLE_PAUSED = "paused"
LIFECYCLE_BLOCKED = "blocked"
LIFECYCLE_TIMEOUT = "timeout"
LIFECYCLE_TTL_EXPIRED = "ttl_expired"
LIFECYCLE_SUCCEEDED = "succeeded"
LIFECYCLE_FAILED = "failed"
LIFECYCLE_CANCELLED = "cancelled"
LIFECYCLE_DEAD_LETTERED = "dead_lettered"
LIFECYCLE_ARCHIVED = "archived"

LIFECYCLE_ALL_STATES = frozenset({
    LIFECYCLE_CREATED, LIFECYCLE_VALIDATED, LIFECYCLE_QUEUED, LIFECYCLE_SCHEDULED,
    LIFECYCLE_DISPATCHED, LIFECYCLE_RUNNING, LIFECYCLE_RETRY_WAIT, LIFECYCLE_PAUSED,
    LIFECYCLE_BLOCKED, LIFECYCLE_TIMEOUT, LIFECYCLE_TTL_EXPIRED, LIFECYCLE_SUCCEEDED,
    LIFECYCLE_FAILED, LIFECYCLE_CANCELLED, LIFECYCLE_DEAD_LETTERED, LIFECYCLE_ARCHIVED,
})

__all__ = [
    "JobEnvelope",
    "JobStateRecord",
    "JobsRuntime",
    "JobWorkers",
    "build_jobs_runtime",
    "REGISTERED_JOB_TYPES",
    "LIFECYCLE_ALL_STATES",
]
