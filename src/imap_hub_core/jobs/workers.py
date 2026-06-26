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

from collections.abc import Callable

from imap_hub_core.jobs.models import JobEnvelope
from imap_hub_core.jobs.runtime import JobsRuntime, build_jobs_runtime


class JobWorkers:
    """Dispatch job envelopes through the platform queue runtime."""

    def __init__(self, runtime: JobsRuntime) -> None:
        self._runtime = runtime
        self._handlers: dict[str, Callable[[JobEnvelope], dict[str, object] | None]] = {}

    def register(
        self, job_type: str, handler: Callable[[JobEnvelope], dict[str, object] | None]
    ) -> None:
        """Register a handler for a job type."""
        self._handlers[job_type] = handler
        self._runtime.register_handler(job_type, handler)

    def enqueue(self, envelope: JobEnvelope) -> str:
        """Queue one job through the configured backend."""
        return self._runtime.submit(envelope)

    def run_once(self) -> bool:
        """Process one queued job via the package worker engine."""
        return self._runtime.run_once()

    def run(self, envelope: JobEnvelope) -> dict[str, object]:
        """Preserve the legacy synchronous helper on top of the real queue."""
        if envelope.job_type not in self._handlers:
            raise KeyError(f"Unknown job type: {envelope.job_type}")
        job_id = self.enqueue(envelope)
        self.run_once()
        return self._runtime.last_result(job_id) or {}

    def list_jobs(self) -> list[object]:
        """Expose tracked jobs for system/integration assertions."""
        return self._runtime.list_jobs()

    def close(self) -> None:
        """Dispose runtime resources."""
        self._runtime.close()

    @classmethod
    def from_config(cls, config: object, *, worker_suffix: str = "main") -> "JobWorkers":
        """Create a workers facade from the typed global config."""
        return cls(build_jobs_runtime(config, worker_suffix=worker_suffix))
