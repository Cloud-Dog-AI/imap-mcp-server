"""Persistent admin state records."""

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

from collections.abc import Mapping
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def _ts(value: datetime | None = None) -> str:
    """Serialise UTC timestamps in a stable ISO-8601 form."""
    current = value or _utcnow()
    return current.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _json_safe(value: Any) -> Any:
    """Normalise runtime values into JSON-safe data structures."""
    if isinstance(value, BaseModel):
        return _json_safe(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "__fspath__"):
        return str(value)
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


class UserRecord(BaseModel):
    """Persistent user payload stored in the shared admin state file."""

    model_config = ConfigDict(extra="forbid")

    user_id: str
    username: str
    email: str
    display_name: str = ""
    status: str = "active"
    role: str = "viewer"
    is_system_user: bool = False
    tenant_id: str | None = None
    created_at: str = Field(default_factory=_ts)
    updated_at: str = Field(default_factory=_ts)


class GroupRecord(BaseModel):
    """Persistent group payload with role assignments and members."""

    model_config = ConfigDict(extra="forbid")

    group_id: str
    name: str
    description: str = ""
    roles: list[str] = Field(default_factory=list)
    members: list[str] = Field(default_factory=list)
    group_admins: list[str] = Field(default_factory=list)
    tenant_id: str | None = None
    created_at: str = Field(default_factory=_ts)
    updated_at: str = Field(default_factory=_ts)


class APIKeyRecord(BaseModel):
    """Persistent API key metadata with capability scopes."""

    model_config = ConfigDict(extra="forbid")

    api_key_id: str
    owner_user_id: str
    key_prefix: str
    key_hash: str
    status: str = "active"
    scopes: list[str] = Field(default_factory=list)
    description: str = ""
    expires_at: str | None = None
    created_at: str = Field(default_factory=_ts)
    updated_at: str = Field(default_factory=_ts)


class RBACBindingRecord(BaseModel):
    """Persistent resource-scoped RBAC binding (W28A-750 / IDAM-B2 §2.1).

    The group->resource edge that gives the cascade a data path: a row binds a
    subject (``user`` or ``group``) to a permission on a domain resource
    (``mailbox_profile:P``). Mirrors ``cloud_dog_idam.domain.models.RBACBinding``
    but persists in the imap JSON snapshot (imap has no SQLAlchemy bindings
    table). Consumed at authorisation time by ``ImapBindingRepository.by_subject``
    feeding ``cloud_dog_idam.rbac.grants.authorise`` (idam 0.5.0, W28A-741).
    """

    model_config = ConfigDict(extra="forbid")

    binding_id: str = Field(default_factory=lambda: str(uuid4()))
    subject_type: str  # "user" | "group"
    subject_id: str
    project: str = "imap-mcp"
    resource_type: str  # e.g. "mailbox_profile"
    resource_id: str = "*"
    permission: str  # e.g. "imap:mail:read"
    granted_by: str = ""
    created_at: str = Field(default_factory=_ts)


class ConfigEvent(BaseModel):
    """One append-only config change event for A2A broadcast consumers."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: str = Field(default_factory=_ts)
    entity_type: str
    action: str
    entity_id: str
    actor_id: str
    source: str
    outcome: str = "success"
    details: dict[str, Any] = Field(default_factory=dict)


class AdminStateSnapshot(BaseModel):
    """Top-level serialised admin state shared by API and MCP processes."""

    model_config = ConfigDict(extra="forbid")

    users: dict[str, UserRecord] = Field(default_factory=dict)
    groups: dict[str, GroupRecord] = Field(default_factory=dict)
    api_keys: dict[str, APIKeyRecord] = Field(default_factory=dict)
    profiles: dict[str, dict[str, Any]] = Field(default_factory=dict)
    deleted_profiles: list[str] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)
    bindings: dict[str, RBACBindingRecord] = Field(default_factory=dict)


__all__ = [
    "APIKeyRecord",
    "AdminStateSnapshot",
    "ConfigEvent",
    "GroupRecord",
    "RBACBindingRecord",
    "UserRecord",
]
