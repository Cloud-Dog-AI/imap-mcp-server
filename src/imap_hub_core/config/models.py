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

from pydantic import BaseModel, ConfigDict, Field, field_validator

from imap_hub_core.config.base_paths import normalise_base_path


class TLSConfig(BaseModel):
    """TLS policy configuration for a profile."""

    model_config = ConfigDict(extra="forbid")

    ca_bundle_path: str | None = None
    allow_self_signed: bool = False


class OAuthConfig(BaseModel):
    """Mailbox-provider OAuth metadata for XOAUTH2-capable IMAP profiles."""

    model_config = ConfigDict(extra="forbid")

    client_id: str | None = None
    client_secret: str | None = None
    redirect_url: str | None = None
    redirect_uri: str | None = None
    scopes: list[str] = Field(default_factory=list)
    oauth_scope: str | None = None
    token_uri: str | None = None
    token_store_key: str | None = None
    refresh_token: str | None = None
    access_token: str | None = None
    account_email: str | None = None
    state_dir: str | None = None


class AuthProfileConfig(BaseModel):
    """IMAP profile authentication mode and optional mailbox OAuth settings."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["oauth2", "app_password", "basic"]
    oauth: OAuthConfig = Field(default_factory=OAuthConfig)


class CredentialsConfig(BaseModel):
    """Non-OAuth credential fields for app-password/basic profiles."""

    model_config = ConfigDict(extra="forbid")

    username: str | None = None
    app_password: str | None = None
    password: str | None = None


class IMAPProfileConfig(BaseModel):
    """IMAP endpoint and connection policy."""

    model_config = ConfigDict(extra="forbid")

    host: str
    port: int
    security: Literal["ssl", "starttls", "tls", "none"]
    tls: TLSConfig = Field(default_factory=TLSConfig)
    timeout_seconds: int = 30
    retry_limit: int = 3


class RetentionConfig(BaseModel):
    """Retention and cache size constraints."""

    model_config = ConfigDict(extra="forbid")

    max_age_days: int
    max_total_bytes: int
    max_messages: int


class FolderPolicyConfig(BaseModel):
    """Include/exclude rules for synced folders."""

    model_config = ConfigDict(extra="forbid")

    include_globs: list[str] = Field(default_factory=list)
    exclude_globs: list[str] = Field(default_factory=list)


class PartsPolicyConfig(BaseModel):
    """Message-part caching policy."""

    model_config = ConfigDict(extra="forbid")

    cache_headers: bool = True
    cache_bodies: bool = True
    max_body_bytes: int = 200000
    cache_raw_rfc822: bool = False
    max_raw_bytes: int = 5000000
    cache_attachments: bool = False
    max_attachment_bytes: int = 25000000
    max_total_attachments_bytes: int = 25000000


class SyncProfileConfig(BaseModel):
    """Per-profile sync and content policies."""

    model_config = ConfigDict(extra="forbid")

    retention: RetentionConfig
    folder_policy: FolderPolicyConfig
    parts_policy: PartsPolicyConfig


class WriteConfig(BaseModel):
    """Write capability gate."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False


class IndexBackendConfig(BaseModel):
    """Vector index backend settings."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    path: str | None = None


class IndexConfig(BaseModel):
    """Managed index configuration."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    managed: bool = True
    backend: IndexBackendConfig = Field(default_factory=IndexBackendConfig)


class ArchiveConfig(BaseModel):
    """Archive export configuration."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    root: str | None = None
    rules: list[dict[str, Any]] = Field(default_factory=list)


class SearchLedgerConfig(BaseModel):
    """Search ledger runtime policy."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    retention_days: int = 90


class ProfileConfig(BaseModel):
    """Complete IMAP profile configuration."""

    model_config = ConfigDict(extra="allow")

    provider: Literal["gmail", "o365", "imap_generic"]
    description: str = Field(
        default="",
        description="Human-readable description of this mailbox profile (what it is used for).  "
        "Optional; existing profiles without one keep working.  Settable via config/env "
        "(e.g. CLOUD_DOG__PROFILES__<name>__DESCRIPTION) or the admin/WebUI profile payload.",
    )
    imap: IMAPProfileConfig
    auth: AuthProfileConfig
    credentials: CredentialsConfig = Field(default_factory=CredentialsConfig)
    sync: SyncProfileConfig
    write: WriteConfig = Field(default_factory=WriteConfig)
    index: IndexConfig = Field(default_factory=IndexConfig)
    archive: ArchiveConfig = Field(default_factory=ArchiveConfig)
    search_ledger: SearchLedgerConfig = Field(default_factory=SearchLedgerConfig)
    allowed_groups: list[str] = Field(
        default_factory=list,
        description="Group IDs permitted to access this profile.  Empty means no group restriction (admin-only or role-based access).",
    )


class AuditConfig(BaseModel):
    """Audit logging settings."""

    model_config = ConfigDict(extra="forbid")

    log_path: str


class StorageConfig(BaseModel):
    """Filesystem storage configuration."""

    model_config = ConfigDict(extra="forbid")

    data_dir: str
    downloads_dir: str
    archive_dir: str


class LimitsConfig(BaseModel):
    """Server request and payload limits."""

    model_config = ConfigDict(extra="forbid")

    max_search_results: int
    max_message_bytes: int
    max_attachment_bytes: int
    extractor_timeout_sec: int


class ServerAuthConfig(BaseModel):
    """Server auth mode."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["api_key", "jwt", "api_key+jwt"]


class ServerConfig(BaseModel):
    """Shared server runtime configuration."""

    model_config = ConfigDict(extra="forbid")

    server_id: str = "imap-mcp-local"
    auth: ServerAuthConfig
    audit: AuditConfig
    storage: StorageConfig
    limits: LimitsConfig


class ListenerConfig(BaseModel):
    """HTTP listener host and port configuration."""

    model_config = ConfigDict(extra="forbid")

    host: str
    port: int
    base_path: str = ""

    @field_validator("base_path", mode="before")
    @classmethod
    def _normalise_base_path(cls, value: object) -> str:
        """Coerce listener base paths into a stable route-prefix form."""
        return normalise_base_path("" if value is None else str(value))


class WebServerConfig(ListenerConfig):
    """Web server listener with optional cookie-auth credentials."""

    model_config = ConfigDict(extra="forbid")

    username: str | None = None
    password: str | None = None
    # W28A-806 (ported W28A-750): declare the auth_mode the web server already
    # reads via runtime_config_value so it is settable via
    # CLOUD_DOG__WEB_SERVER__AUTH_MODE (SPA enum: api_key|cookie|oidc). Default "cookie"
    # preserves the prior runtime fallback (web_server.py `or "cookie"`) so the deployed
    # flat username/password login is unchanged; an explicit env override still wins.
    auth_mode: Literal["api_key", "cookie", "oidc"] = "cookie"


class MCPServerConfig(ListenerConfig):
    """MCP server listener configuration."""

    model_config = ConfigDict(extra="forbid")

    transport: Literal["stdio", "http_sse", "streamable-http"] = "streamable-http"


class SchedulerConfig(BaseModel):
    """Generic scheduler cadence configuration."""

    model_config = ConfigDict(extra="allow")

    schedule_sec: int


class RBACConfig(BaseModel):
    """Role-to-tool permission patterns."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    roles: dict[str, list[str]] = Field(default_factory=dict)


class JobsBackendConfig(BaseModel):
    """Queue backend selection and connection settings."""

    model_config = ConfigDict(extra="forbid")

    preferred: Literal["memory", "sql", "redis"] = "sql"
    sql_url: str | None = None
    redis_url: str | None = None


class JobsRetryConfig(BaseModel):
    """Retry policy for failed or timed-out jobs."""

    model_config = ConfigDict(extra="forbid")

    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0


class JobsMaintenanceConfig(BaseModel):
    """Maintenance thresholds for stale-claim recovery and retention."""

    model_config = ConfigDict(extra="forbid")

    claim_timeout_seconds: int = 60
    max_age_seconds: int = 86400


class JobsConfig(BaseModel):
    """Job queue runtime configuration."""

    model_config = ConfigDict(extra="forbid")

    backend: JobsBackendConfig = Field(default_factory=JobsBackendConfig)
    retry: JobsRetryConfig = Field(default_factory=JobsRetryConfig)
    maintenance: JobsMaintenanceConfig = Field(default_factory=JobsMaintenanceConfig)
    dead_letter_queue: str = "imap_dead_letter"
    payload_max_bytes: int = 16384


class GlobalConfigModel(BaseModel):
    """Root validated runtime configuration model."""

    model_config = ConfigDict(extra="allow")

    server: ServerConfig
    api_server: ListenerConfig
    web_server: WebServerConfig
    mcp_server: MCPServerConfig
    a2a_server: ListenerConfig
    sync: SchedulerConfig
    index: SchedulerConfig
    rbac: RBACConfig
    jobs: JobsConfig = Field(default_factory=JobsConfig)
    profiles: dict[str, ProfileConfig] = Field(default_factory=dict)

    @field_validator("web_server", mode="before")
    @classmethod
    def _coerce_web_server(cls, value: object) -> object:
        """Accept plain listener configs where cookie-auth fields are omitted."""
        if isinstance(value, ListenerConfig):
            return {"host": value.host, "port": value.port, "base_path": value.base_path}
        return value
