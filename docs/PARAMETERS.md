---
template-id: T-PAR
template-version: 1.0
applies-to: docs/PARAMETERS.md
registry: service
required: must-have
when-applicable: ""
template-last-updated: 2026-06-12
template-owner: platform-standards

project: imap-mcp-server
doc-last-updated: 2026-06-18
doc-git-commit: 7683f39
doc-git-branch: main
doc-source-shas: []
doc-age-policy: 90d
doc-conformance-stamp: 2026-06-18T00:00:00Z
---

# Parameters

This reference is generated from `defaults.yaml`. Each key can be overridden by the corresponding environment variable.

## `a2a_server`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `a2a_server.host` | `0.0.0.0` | `CLOUD_DOG__A2A_SERVER__HOST` | Host binding or upstream host for a2a server. |
| `a2a_server.port` | `8073` | `CLOUD_DOG__A2A_SERVER__PORT` | Port for a2a server connections. |

## `api_server`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `api_server.host` | `0.0.0.0` | `CLOUD_DOG__API_SERVER__HOST` | Host binding or upstream host for api server. |
| `api_server.port` | `8070` | `CLOUD_DOG__API_SERVER__PORT` | Port for api server connections. |

## `index`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `index.schedule_sec` | `300` | `CLOUD_DOG__INDEX__SCHEDULE_SEC` | Configuration value for index schedule sec. |
| `index.enabled` | `false` | `CLOUD_DOG__INDEX__ENABLED` | Toggle for index. |
| `index.managed` | `true` | `CLOUD_DOG__INDEX__MANAGED` | Configuration value for index managed. |
| `index.backend.type` | `chroma` | `CLOUD_DOG__INDEX__BACKEND__TYPE` | Configuration value for index backend type. |
| `index.backend.path` | `./data/chroma` | `CLOUD_DOG__INDEX__BACKEND__PATH` | Configuration value for index backend path. |
| `index.chunking.max_chars` | `2000` | `CLOUD_DOG__INDEX__CHUNKING__MAX_CHARS` | Configuration value for index chunking max chars. |
| `index.chunking.overlap_chars` | `200` | `CLOUD_DOG__INDEX__CHUNKING__OVERLAP_CHARS` | Configuration value for index chunking overlap chars. |

## `jobs`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `jobs.backend.preferred` | `sql` | `CLOUD_DOG__JOBS__BACKEND__PREFERRED` | Configuration value for jobs backend preferred. |
| `jobs.backend.sql_url` | `sqlite:///./data/imap_jobs.db` | `CLOUD_DOG__JOBS__BACKEND__SQL_URL` | Endpoint or connection URL for jobs backend sql. |
| `jobs.retry.max_attempts` | `3` | `CLOUD_DOG__JOBS__RETRY__MAX_ATTEMPTS` | Configuration value for jobs retry max attempts. |
| `jobs.retry.initial_delay_seconds` | `1.0` | `CLOUD_DOG__JOBS__RETRY__INITIAL_DELAY_SECONDS` | Timeout or duration control for jobs retry initial delay. |
| `jobs.retry.max_delay_seconds` | `30.0` | `CLOUD_DOG__JOBS__RETRY__MAX_DELAY_SECONDS` | Timeout or duration control for jobs retry max delay. |
| `jobs.maintenance.claim_timeout_seconds` | `60` | `CLOUD_DOG__JOBS__MAINTENANCE__CLAIM_TIMEOUT_SECONDS` | Timeout or duration control for jobs maintenance claim timeout. |
| `jobs.maintenance.max_age_seconds` | `86400` | `CLOUD_DOG__JOBS__MAINTENANCE__MAX_AGE_SECONDS` | Timeout or duration control for jobs maintenance max age. |
| `jobs.payload_max_bytes` | `16384` | `CLOUD_DOG__JOBS__PAYLOAD_MAX_BYTES` | Configuration value for jobs payload max bytes. |

## `log`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `log.service_instance` | `${HOSTNAME:imap-mcp-local}` | `CLOUD_DOG__LOG__SERVICE_INSTANCE` | Configuration value for log service instance. |
| `log.environment` | `${CLOUD_DOG_ENVIRONMENT:dev}` | `CLOUD_DOG__LOG__ENVIRONMENT` | Configuration value for log environment. |
| `log.retention.hot_days` | `14` | `CLOUD_DOG__LOG__RETENTION__HOT_DAYS` | Configuration value for log retention hot days. |
| `log.retention.cold_days` | `60` | `CLOUD_DOG__LOG__RETENTION__COLD_DAYS` | Configuration value for log retention cold days. |
| `log.retention.archive_format` | `gz` | `CLOUD_DOG__LOG__RETENTION__ARCHIVE_FORMAT` | Configuration value for log retention archive format. |
| `log.integrity.enabled` | `true` | `CLOUD_DOG__LOG__INTEGRITY__ENABLED` | Toggle for log integrity. |
| `log.integrity.interval_seconds` | `300` | `CLOUD_DOG__LOG__INTEGRITY__INTERVAL_SECONDS` | Timeout or duration control for log integrity interval. |
| `log.integrity.log_file` | `logs/audit-integrity.log` | `CLOUD_DOG__LOG__INTEGRITY__LOG_FILE` | Configuration value for log integrity log file. |
| `log.integrity.hash_algorithm` | `sha256` | `CLOUD_DOG__LOG__INTEGRITY__HASH_ALGORITHM` | Configuration value for log integrity hash algorithm. |
| `log.rotation.mode` | `size` | `CLOUD_DOG__LOG__ROTATION__MODE` | Configuration value for log rotation mode. |
| `log.rotation.max_bytes` | `104857600` | `CLOUD_DOG__LOG__ROTATION__MAX_BYTES` | Configuration value for log rotation max bytes. |
| `log.rotation.backup_count` | `10` | `CLOUD_DOG__LOG__ROTATION__BACKUP_COUNT` | Configuration value for log rotation backup count. |
| `log.rotation.when` | `midnight` | `CLOUD_DOG__LOG__ROTATION__WHEN` | Configuration value for log rotation when. |
| `log.rotation.interval` | `1` | `CLOUD_DOG__LOG__ROTATION__INTERVAL` | Configuration value for log rotation interval. |
| `log.rotation.compress` | `true` | `CLOUD_DOG__LOG__ROTATION__COMPRESS` | Configuration value for log rotation compress. |

## `mcp_server`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `mcp_server.host` | `0.0.0.0` | `CLOUD_DOG__MCP_SERVER__HOST` | Host binding or upstream host for mcp server. |
| `mcp_server.port` | `8072` | `CLOUD_DOG__MCP_SERVER__PORT` | Port for mcp server connections. |
| `mcp_server.transport` | `streamable-http` | `CLOUD_DOG__MCP_SERVER__TRANSPORT` | Configuration value for mcp server transport. |

## `rbac`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `rbac.enabled` | `true` | `CLOUD_DOG__RBAC__ENABLED` | Toggle for rbac. |
| `rbac.roles.admin` | `["*"]` | `CLOUD_DOG__RBAC__ROLES__ADMIN` | Configuration value for rbac roles admin. |
| `rbac.roles.operator` | `["health_status", "profile_list", "profile_get", "sync_*", "index_*", "archive_*", "search_log_*"]` | `CLOUD_DOG__RBAC__ROLES__OPERATOR` | Configuration value for rbac roles operator. |
| `rbac.roles.reader` | `["mail_search", "mail_search_since_last", "mail_get_message", "mail_list_attachments", "mail_download_attachment", "sear...` | `CLOUD_DOG__RBAC__ROLES__READER` | Configuration value for rbac roles reader. |
| `rbac.roles.writer` | `["mail_move_messages", "mail_delete_messages", "mail_set_flags", "mail_mark_read", "mail_mark_unread", "mail_move_duplic...` | `CLOUD_DOG__RBAC__ROLES__WRITER` | Configuration value for rbac roles writer. |

## `server`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `server.server_id` | `${HOSTNAME:imap-mcp-local}` | `CLOUD_DOG__SERVER__SERVER_ID` | Configuration value for server server id. |
| `server.base_path` | `-` | `CLOUD_DOG__SERVER__BASE_PATH` | Configuration value for server base path. |
| `server.auth.mode` | `api_key` | `CLOUD_DOG__SERVER__AUTH__MODE` | Configuration value for server auth mode. |
| `server.audit.log_path` | `./data/audit/audit.jsonl` | `CLOUD_DOG__SERVER__AUDIT__LOG_PATH` | Configuration value for server audit log path. |
| `server.storage.data_dir` | `./data` | `CLOUD_DOG__SERVER__STORAGE__DATA_DIR` | Configuration value for server storage data dir. |
| `server.storage.downloads_dir` | `./data/downloads` | `CLOUD_DOG__SERVER__STORAGE__DOWNLOADS_DIR` | Configuration value for server storage downloads dir. |
| `server.storage.archive_dir` | `./data/archive` | `CLOUD_DOG__SERVER__STORAGE__ARCHIVE_DIR` | Configuration value for server storage archive dir. |
| `server.limits.max_search_results` | `200` | `CLOUD_DOG__SERVER__LIMITS__MAX_SEARCH_RESULTS` | Configuration value for server limits max search results. |
| `server.limits.max_message_bytes` | `5000000` | `CLOUD_DOG__SERVER__LIMITS__MAX_MESSAGE_BYTES` | Configuration value for server limits max message bytes. |
| `server.limits.max_attachment_bytes` | `25000000` | `CLOUD_DOG__SERVER__LIMITS__MAX_ATTACHMENT_BYTES` | Configuration value for server limits max attachment bytes. |
| `server.limits.extractor_timeout_sec` | `30` | `CLOUD_DOG__SERVER__LIMITS__EXTRACTOR_TIMEOUT_SEC` | Configuration value for server limits extractor timeout sec. |

## `sync`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `sync.schedule_sec` | `120` | `CLOUD_DOG__SYNC__SCHEDULE_SEC` | Configuration value for sync schedule sec. |
| `sync.retention_enforce_sec` | `600` | `CLOUD_DOG__SYNC__RETENTION_ENFORCE_SEC` | Configuration value for sync retention enforce sec. |

## `web_server`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `web_server.host` | `0.0.0.0` | `CLOUD_DOG__WEB_SERVER__HOST` | Host binding or upstream host for web server. |
| `web_server.port` | `8071` | `CLOUD_DOG__WEB_SERVER__PORT` | Port for web server connections. |
