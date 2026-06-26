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

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolEnvelope(BaseModel):
    """Standard tool response envelope."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    result: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class ProfileListInput(BaseModel):
    """Input schema for profile listing."""

    model_config = ConfigDict(extra="forbid")

    include_disabled: bool = False


class UserCreateInput(BaseModel):
    """Input schema for admin user creation."""

    model_config = ConfigDict(extra="forbid")

    user_id: str | None = None
    username: str
    email: str
    display_name: str = ""
    role: str = "viewer"
    status: str = "active"
    is_system_user: bool = False
    tenant_id: str | None = None


class UserGetInput(BaseModel):
    """Input schema for one-user lookup."""

    model_config = ConfigDict(extra="forbid")

    user_id: str


class UserUpdateInput(BaseModel):
    """Input schema for admin user updates."""

    model_config = ConfigDict(extra="forbid")

    user_id: str
    username: str | None = None
    email: str | None = None
    display_name: str | None = None
    role: str | None = None
    status: str | None = None
    is_system_user: bool | None = None
    tenant_id: str | None = None


class UserDeleteInput(BaseModel):
    """Input schema for admin user deletion."""

    model_config = ConfigDict(extra="forbid")

    user_id: str


class GroupCreateInput(BaseModel):
    """Input schema for admin group creation."""

    model_config = ConfigDict(extra="forbid")

    group_id: str | None = None
    name: str
    description: str = ""
    roles: list[str] = Field(default_factory=list)
    members: list[str] = Field(default_factory=list)
    tenant_id: str | None = None


class GroupGetInput(BaseModel):
    """Input schema for one-group lookup."""

    model_config = ConfigDict(extra="forbid")

    group_id: str


class GroupUpdateInput(BaseModel):
    """Input schema for admin group updates."""

    model_config = ConfigDict(extra="forbid")

    group_id: str
    name: str | None = None
    description: str | None = None
    roles: list[str] | None = None
    tenant_id: str | None = None


class GroupDeleteInput(BaseModel):
    """Input schema for admin group deletion."""

    model_config = ConfigDict(extra="forbid")

    group_id: str


class GroupMemberInput(BaseModel):
    """Input schema for group membership mutation."""

    model_config = ConfigDict(extra="forbid")

    group_id: str
    user_id: str


class APIKeyCreateInput(BaseModel):
    """Input schema for scoped API-key generation."""

    model_config = ConfigDict(extra="forbid")

    owner_user_id: str
    scopes: list[str] = Field(default_factory=list)
    description: str = ""
    ttl_days: int | None = None
    key_prefix: str | None = None


class APIKeyListInput(BaseModel):
    """Input schema for API-key listing."""

    model_config = ConfigDict(extra="forbid")

    owner_user_id: str | None = None


class APIKeyRevokeInput(BaseModel):
    """Input schema for API-key revocation."""

    model_config = ConfigDict(extra="forbid")

    api_key_id: str


class MailProbeInput(BaseModel):
    """Input schema for IMAP connectivity probe."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    folder: str = "INBOX"


class MailSearchInput(BaseModel):
    """Input schema for mail search."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    mode: Literal["cache", "imap", "vector", "hybrid"] = "cache"
    query: str
    filters: dict[str, Any] = Field(default_factory=dict)
    similarity_pins: list[str] = Field(default_factory=list)
    limit: int | None = None
    run_async: bool = False


class MailSearchSinceLastInput(BaseModel):
    """Input schema for delta search."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    mode: Literal["cache", "imap", "vector", "hybrid"] = "cache"
    query: str
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int | None = None


class MailHeadlinesInput(BaseModel):
    """Input schema for search headline summaries."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    mode: Literal["cache", "imap", "vector", "hybrid"] = "imap"
    query: str = ""
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int | None = None


class MailMoveDuplicatesInput(BaseModel):
    """Input schema for duplicate sweep operations."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    query: str
    destination_folder: str
    strategy: Literal["message_id", "content_hash", "heuristic"] = "message_id"
    policy: Literal["newest", "oldest", "flagged", "first_seen"] = "newest"
    dry_run: bool = True


class MailGetMessageInput(BaseModel):
    """Input schema for message retrieval."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    uid: str
    folder: str = "INBOX"


class MailListFoldersInput(BaseModel):
    """Input schema for live IMAP folder enumeration."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str


class MailListAttachmentsInput(BaseModel):
    """Input schema for attachment listing."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    uid: str
    folder: str = "INBOX"


class MailDownloadAttachmentInput(BaseModel):
    """Input schema for attachment download."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    uid: str
    part_id: str
    folder: str = "INBOX"
    filename: str | None = None


class MailExtractMessageInput(BaseModel):
    """Input schema for message text extraction output."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    uid: str
    folder: str = "INBOX"
    format: Literal["json", "markdown", "both"] = "both"


class MailSetSeenInput(BaseModel):
    """Input schema for seen/unseen flag updates."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    uids: list[str]
    seen: bool
    folder: str = "INBOX"


class MailMoveMessagesInput(BaseModel):
    """Input schema for message move operations."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    uids: list[str]
    destination_folder: str
    folder: str = "INBOX"


class MailDeleteMessagesInput(BaseModel):
    """Input schema for message delete operations."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    uids: list[str]
    folder: str = "INBOX"
