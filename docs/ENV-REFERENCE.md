---
template-id: T-ENV
template-version: 1.0
applies-to: docs/ENV-REFERENCE.md
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

# Environment Reference

This reference is generated from `defaults.yaml` and the standard Cloud-Dog environment override pattern.

## `a2a_server`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__A2A_SERVER__HOST` | `0.0.0.0` | Optional | `0.0.0.0` | Host binding or upstream host for a2a server. |
| `CLOUD_DOG__A2A_SERVER__PORT` | `8073` | Optional | `8073` | Port for a2a server connections. |

## `api_server`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__API_SERVER__HOST` | `0.0.0.0` | Optional | `0.0.0.0` | Host binding or upstream host for api server. |
| `CLOUD_DOG__API_SERVER__PORT` | `8070` | Optional | `8070` | Port for api server connections. |

## `index`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__INDEX__SCHEDULE_SEC` | `300` | Optional | `300` | Configuration value for index schedule sec. |
| `CLOUD_DOG__INDEX__ENABLED` | `false` | Optional | `false` | Toggle for index. |
| `CLOUD_DOG__INDEX__MANAGED` | `true` | Optional | `true` | Configuration value for index managed. |
| `CLOUD_DOG__INDEX__BACKEND__TYPE` | `chroma` | Optional | `chroma` | Configuration value for index backend type. |
| `CLOUD_DOG__INDEX__BACKEND__PATH` | `./data/chroma` | Optional | `./data/service.dat` | Configuration value for index backend path. |
| `CLOUD_DOG__INDEX__CHUNKING__MAX_CHARS` | `2000` | Optional | `2000` | Configuration value for index chunking max chars. |
| `CLOUD_DOG__INDEX__CHUNKING__OVERLAP_CHARS` | `200` | Optional | `200` | Configuration value for index chunking overlap chars. |

## `jobs`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__JOBS__BACKEND__PREFERRED` | `sql` | Optional | `sql` | Configuration value for jobs backend preferred. |
| `CLOUD_DOG__JOBS__BACKEND__SQL_URL` | `sqlite:///./data/imap_jobs.db` | Deployment dependent | `sqlite:///./data/imap_jobs.db` | Endpoint or connection URL for jobs backend sql. |
| `CLOUD_DOG__JOBS__RETRY__MAX_ATTEMPTS` | `3` | Optional | `3` | Configuration value for jobs retry max attempts. |
| `CLOUD_DOG__JOBS__RETRY__INITIAL_DELAY_SECONDS` | `1.0` | Optional | `1.0` | Timeout or duration control for jobs retry initial delay. |
| `CLOUD_DOG__JOBS__RETRY__MAX_DELAY_SECONDS` | `30.0` | Optional | `30.0` | Timeout or duration control for jobs retry max delay. |
| `CLOUD_DOG__JOBS__MAINTENANCE__CLAIM_TIMEOUT_SECONDS` | `60` | Optional | `60` | Timeout or duration control for jobs maintenance claim timeout. |
| `CLOUD_DOG__JOBS__MAINTENANCE__MAX_AGE_SECONDS` | `86400` | Optional | `86400` | Timeout or duration control for jobs maintenance max age. |
| `CLOUD_DOG__JOBS__PAYLOAD_MAX_BYTES` | `16384` | Optional | `16384` | Configuration value for jobs payload max bytes. |

## `log`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__LOG__SERVICE_INSTANCE` | `${HOSTNAME:imap-mcp-local}` | Optional | `${HOSTNAME:imap-mcp-local}` | Configuration value for log service instance. |
| `CLOUD_DOG__LOG__ENVIRONMENT` | `${CLOUD_DOG_ENVIRONMENT:dev}` | Optional | `${CLOUD_DOG_ENVIRONMENT:dev}` | Configuration value for log environment. |
| `CLOUD_DOG__LOG__RETENTION__HOT_DAYS` | `14` | Optional | `14` | Configuration value for log retention hot days. |
| `CLOUD_DOG__LOG__RETENTION__COLD_DAYS` | `60` | Optional | `60` | Configuration value for log retention cold days. |
| `CLOUD_DOG__LOG__RETENTION__ARCHIVE_FORMAT` | `gz` | Optional | `gz` | Configuration value for log retention archive format. |
| `CLOUD_DOG__LOG__INTEGRITY__ENABLED` | `true` | Optional | `true` | Toggle for log integrity. |
| `CLOUD_DOG__LOG__INTEGRITY__INTERVAL_SECONDS` | `300` | Optional | `300` | Timeout or duration control for log integrity interval. |
| `CLOUD_DOG__LOG__INTEGRITY__LOG_FILE` | `logs/audit-integrity.log` | Optional | `logs/audit-integrity.log` | Configuration value for log integrity log file. |
| `CLOUD_DOG__LOG__INTEGRITY__HASH_ALGORITHM` | `sha256` | Optional | `sha256` | Configuration value for log integrity hash algorithm. |
| `CLOUD_DOG__LOG__ROTATION__MODE` | `size` | Optional | `size` | Configuration value for log rotation mode. |
| `CLOUD_DOG__LOG__ROTATION__MAX_BYTES` | `104857600` | Optional | `104857600` | Configuration value for log rotation max bytes. |
| `CLOUD_DOG__LOG__ROTATION__BACKUP_COUNT` | `10` | Optional | `10` | Configuration value for log rotation backup count. |
| `CLOUD_DOG__LOG__ROTATION__WHEN` | `midnight` | Optional | `midnight` | Configuration value for log rotation when. |
| `CLOUD_DOG__LOG__ROTATION__INTERVAL` | `1` | Optional | `1` | Configuration value for log rotation interval. |
| `CLOUD_DOG__LOG__ROTATION__COMPRESS` | `true` | Optional | `true` | Configuration value for log rotation compress. |

## `mcp_server`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__MCP_SERVER__HOST` | `0.0.0.0` | Optional | `0.0.0.0` | Host binding or upstream host for mcp server. |
| `CLOUD_DOG__MCP_SERVER__PORT` | `8072` | Optional | `8072` | Port for mcp server connections. |
| `CLOUD_DOG__MCP_SERVER__TRANSPORT` | `streamable-http` | Optional | `streamable-http` | Configuration value for mcp server transport. |

## `rbac`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__RBAC__ENABLED` | `true` | Optional | `true` | Toggle for rbac. |
| `CLOUD_DOG__RBAC__ROLES__ADMIN` | `["*"]` | Optional | `<set as needed>` | Configuration value for rbac roles admin. |
| `CLOUD_DOG__RBAC__ROLES__OPERATOR` | `["health_status", "profile_list", "profile_get", "sync_*", "index_*", "archive_*", "search_log_*"]` | Optional | `<set as needed>` | Configuration value for rbac roles operator. |
| `CLOUD_DOG__RBAC__ROLES__READER` | `["mail_search", "mail_search_since_last", "mail_get_message", "mail_list_attachments", "mail_download_attachment", "sear...` | Optional | `<set as needed>` | Configuration value for rbac roles reader. |
| `CLOUD_DOG__RBAC__ROLES__WRITER` | `["mail_move_messages", "mail_delete_messages", "mail_set_flags", "mail_mark_read", "mail_mark_unread", "mail_move_duplic...` | Optional | `<set as needed>` | Configuration value for rbac roles writer. |

## `server`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__SERVER__SERVER_ID` | `${HOSTNAME:imap-mcp-local}` | Optional | `${HOSTNAME:imap-mcp-local}` | Configuration value for server server id. |
| `CLOUD_DOG__SERVER__BASE_PATH` | `-` | Optional | `<set as needed>` | Configuration value for server base path. |
| `CLOUD_DOG__SERVER__AUTH__MODE` | `api_key` | Optional | `api_key` | Configuration value for server auth mode. |
| `CLOUD_DOG__SERVER__AUDIT__LOG_PATH` | `./data/audit/audit.jsonl` | Optional | `./data/audit/audit.jsonl` | Configuration value for server audit log path. |
| `CLOUD_DOG__SERVER__STORAGE__DATA_DIR` | `./data` | Optional | `./data` | Configuration value for server storage data dir. |
| `CLOUD_DOG__SERVER__STORAGE__DOWNLOADS_DIR` | `./data/downloads` | Optional | `./data/downloads` | Configuration value for server storage downloads dir. |
| `CLOUD_DOG__SERVER__STORAGE__ARCHIVE_DIR` | `./data/archive` | Optional | `./data/archive` | Configuration value for server storage archive dir. |
| `CLOUD_DOG__SERVER__LIMITS__MAX_SEARCH_RESULTS` | `200` | Optional | `200` | Configuration value for server limits max search results. |
| `CLOUD_DOG__SERVER__LIMITS__MAX_MESSAGE_BYTES` | `5000000` | Optional | `5000000` | Configuration value for server limits max message bytes. |
| `CLOUD_DOG__SERVER__LIMITS__MAX_ATTACHMENT_BYTES` | `25000000` | Optional | `25000000` | Configuration value for server limits max attachment bytes. |
| `CLOUD_DOG__SERVER__LIMITS__EXTRACTOR_TIMEOUT_SEC` | `30` | Optional | `30` | Configuration value for server limits extractor timeout sec. |

## `sync`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__SYNC__SCHEDULE_SEC` | `120` | Optional | `120` | Configuration value for sync schedule sec. |
| `CLOUD_DOG__SYNC__RETENTION_ENFORCE_SEC` | `600` | Optional | `600` | Configuration value for sync retention enforce sec. |

## `web_server`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__WEB_SERVER__HOST` | `0.0.0.0` | Optional | `0.0.0.0` | Host binding or upstream host for web server. |
| `CLOUD_DOG__WEB_SERVER__PORT` | `8071` | Optional | `8071` | Port for web server connections. |

## Vault Support

| Variable | Purpose | Example |
|----------|---------|---------|
| `VAULT_ADDR` | Vault server URL when using secret-backed config resolution. | `https://your-vault-server` |
| `VAULT_TOKEN` | Token-based authentication for Vault when applicable. | `your-vault-token` |
| `VAULT_MOUNT_POINT` | Secret mount used by your Vault deployment. | `secret` |
| `VAULT_CONFIG_PATH` | Config path holding service settings. | `services/your-service` |
