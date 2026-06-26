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

from pydantic import BaseModel, ConfigDict, Field


class AuditActor(BaseModel):
    """Actor details attached to each audit record."""

    model_config = ConfigDict(extra="forbid")

    actor_type: str = "user"
    actor_id: str
    roles: list[str] = Field(default_factory=list)
    ip: str | None = None
    user_agent: str | None = None


class AuditRecord(BaseModel):
    """Append-only audit payload emitted by core operations."""

    model_config = ConfigDict(extra="forbid")

    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )
    operation: str
    status: str
    correlation_id: str
    actor: AuditActor
    profile_id: str | None = None
    component: str | None = None
    source_identifier: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    target_name: str | None = None
    server_id: str | None = None
    environment: str = "unknown"
    params: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    def redacted_params(self) -> dict[str, Any]:
        """Return parameters with sensitive values redacted."""
        redacted: dict[str, Any] = {}
        for key, value in self.params.items():
            lowered = key.lower()
            if any(token in lowered for token in ("token", "password", "secret", "api_key", "key")):
                redacted[key] = "***REDACTED***"
            else:
                redacted[key] = value
        return redacted
