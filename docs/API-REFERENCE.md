---
template-id: T-API
template-version: 1.0
applies-to: docs/API-REFERENCE.md
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

# API Reference — imap-mcp-server

## 1. Overview

Canonical interface contract:
- REST base: `/api/v1`
- MCP base: `/mcp`
- A2A base: `/a2a`
- Legacy REST alias (compat only): `/app/v1`

Common REST envelope:
```json
{
  "ok": true,
  "result": {},
  "warnings": [],
  "errors": [],
  "meta": {
    "request_id": "...",
    "correlation_id": "..."
  }
}
```

## 2. Authentication

### REST/MCP tool APIs
- API key header: `x-api-key: <key>`

### Admin APIs
- API key + admin role header:
  - `x-api-key: <key>`
  - `x-role: admin`
  - optional bearer-token HTTP auth header for parity in test flows

### A2A APIs
- Bearer-token HTTP auth header required for `/a2a/*`

Common auth errors:
- `401 Unauthorised`
- `403 {"code":"admin_required"...}` (admin endpoints)

## 3. REST Endpoints

### 3.1 System and Web

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | none | Base health endpoint |
| GET | `/api/v1/health` | none | Canonical API health endpoint |
| GET | `/` | none | Redirect to `/ui/` |
| GET | `/ui/` | none | SPA shell entrypoint |
| GET | `/ui/{route}` | none | SPA shell for BrowserRouter routes |
| GET | `/runtime-config.js` | none | Runtime configuration for the SPA shell |
| GET | `/assets/{asset_path}` | none | Vendored SPA asset bundle |
| GET | `/favicon.ico` | none | Empty favicon response |

### 3.2 Tool catalogue and execution

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/tools` | `x-api-key` | List tool contracts |
| POST | `/api/v1/tools/{tool_name}` | `x-api-key` | Execute named tool |

### 3.3 Admin API

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/admin/profiles` | admin | List profile IDs |
| GET | `/api/v1/admin/profiles/{profile_id}` | admin | Fetch profile payload |
| PUT | `/api/v1/admin/profiles/{profile_id}` | admin | Upsert profile payload |
| DELETE | `/api/v1/admin/profiles/{profile_id}` | admin | Delete profile |
| POST | `/api/v1/admin/index/reconcile` | admin | Reconcile index documents |
| POST | `/api/v1/admin/archive/export` | admin | Export message payload to archive |
| GET | `/api/v1/admin/rbac/policies` | admin | List in-memory RBAC roles |
| PUT | `/api/v1/admin/rbac/policies` | admin | Replace RBAC role mappings |
| GET | `/api/v1/admin/audit/events` | admin | Query audit records (`limit`, `contains`) |

A compatibility alias remains available during transition, but `/api/v1` is the documented contract.

## 4. MCP HTTP Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/mcp/tools` | `x-api-key` | List MCP tool catalogue |
| POST | `/mcp/tools/{tool_name}` | `x-api-key` | Execute MCP tool |

Note: MCP app runtime currently uses API-kit router registration with internal tool registry handlers.

## 5. A2A Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/a2a/health` | bearer API key | A2A health parity endpoint |
| GET | `/a2a/tools` | bearer API key | A2A tool catalogue |
| POST | `/a2a/tools/{tool_name}` | bearer API key | A2A tool execution |

## 6. MCP Tool Reference

### 6.1 Tool list

| Tool | Description |
|---|---|
| `profile_list` | List configured profile IDs |
| `mail_probe` | Probe IMAP connectivity for a profile/folder |
| `mail_search` | Search messages |
| `mail_search_since_last` | Delta search since prior baseline |
| `mail_headlines` | Headline-only search summary |
| `mail_move_duplicates_since_last_search` | Duplicate sweep/move workflow |
| `mail_get_message` | Fetch raw message |
| `mail_list_attachments` | List attachment metadata |
| `mail_download_attachment` | Download attachment payload |
| `mail_extract_message` | Extract message to JSON/Markdown |
| `mail_set_seen` | Set/unset `\\Seen` |
| `mail_move_messages` | Move messages to folder |
| `mail_delete_messages` | Delete messages (flag + expunge) |

### 6.2 Parameters and outputs

| Tool | Required fields | Optional fields | Result summary |
|---|---|---|---|
| `profile_list` | none | `include_disabled` | `profiles[]` |
| `mail_probe` | `profile_id` | `folder` | IMAP connection status |
| `mail_search` | `profile_id`, `query` | `mode`, `filters`, `similarity_pins` | `messages[]`, canonical metadata |
| `mail_search_since_last` | `profile_id`, `query` | `mode`, `filters` | delta message set + watermark metadata |
| `mail_headlines` | `profile_id` | `mode`, `query`, `filters`, `limit` | `items[]` headline rows |
| `mail_move_duplicates_since_last_search` | `profile_id`, `query`, `destination_folder` | `strategy`, `policy`, `dry_run` | duplicate analysis/move summary |
| `mail_get_message` | `profile_id`, `uid` | `folder` | raw EML payload |
| `mail_list_attachments` | `profile_id`, `uid` | `folder` | attachment list with part metadata |
| `mail_download_attachment` | `profile_id`, `uid`, `part_id` | `folder`, `filename` | attachment bytes/encoding/path metadata |
| `mail_extract_message` | `profile_id`, `uid` | `folder`, `format` | JSON/Markdown extraction |
| `mail_set_seen` | `profile_id`, `uids`, `seen` | `folder` | updated/failed UID lists |
| `mail_move_messages` | `profile_id`, `uids`, `destination_folder` | `folder` | moved/failed UID lists |
| `mail_delete_messages` | `profile_id`, `uids` | `folder` | deleted/failed UID lists |

### 6.3 Example tool execution

Request:
```http
POST /api/v1/tools/mail_search
x-api-key: 12345678
Content-Type: application/json

{
  "profile_id": "operations_cloud_dog",
  "mode": "imap",
  "query": "ALL",
  "filters": {"folder": "INBOX"}
}
```

Response (shape):
```json
{
  "ok": true,
  "result": {
    "ok": true,
    "result": {
      "messages": []
    },
    "warnings": [],
    "errors": [],
    "meta": {}
  },
  "warnings": [],
  "errors": [],
  "meta": {
    "request_id": "...",
    "correlation_id": "..."
  }
}
```

## 7. Error Contract Summary

| Status | Typical cause |
|---|---|
| 400 | Invalid payload, model validation failure, runtime operation error |
| 401 | Missing/invalid auth for protected endpoints |
| 403 | Admin role missing for admin endpoints |
| 404 | Unknown tool or missing resource |
| 504 | Upstream IMAP timeout surfaced by handlers |

## 8. OpenAPI

- Runtime OpenAPI URL: `/openapi.json`
- Canonical local URL: `http://127.0.0.1:28983/openapi.json`

Generate and save static spec example:

```bash
curl -fsS http://127.0.0.1:28983/openapi.json > docs/openapi.json
```



<!-- W28C-1710a recovery: full content from archive/2026-06-12/API_DOCUMENTATION.md (archived sha256=250a92c3b792, 85 lines) -->

## Recovered domain content — `archive/2026-06-12/API_DOCUMENTATION.md` (85 lines)

_This section carries forward the full content of the archived predecessor doc verbatim. Topic checklist + SHA256 chain in `cloud-dog-ai-platform-standards/working/evidence/W28C-1710a/per-doc/imap-mcp-server/API_DOCUMENTATION.md.topics.tsv`. Archive contents are unchanged (sha256 stable)._

# API Documentation

## Base URLs

- Local API: `http://127.0.0.1:28983`
- Local WebUI: `http://127.0.0.1:28980/ui/`
- Local MCP HTTP: `http://127.0.0.1:28981/mcp`
- Local A2A HTTP: `http://127.0.0.1:28982/a2a`
- Preprod: `https://imapmcpserver0.example.com`

## Canonical Paths

- REST base: `/api/v1`
- Legacy REST compatibility alias: `/app/v1`
- MCP base: `/mcp`
- A2A base: `/a2a`
- WebUI shell: `/ui/`

## Authentication

- REST and MCP HTTP: `x-api-key: <key>`
- Admin REST: `x-api-key: <key>` plus `x-role: admin`
- A2A HTTP: bearer-token HTTP auth header
- WebUI: API-key sign-in via `/ui/login?auth=api_key`

## Route Surfaces

Primary route inventories live in:

- [API-REFERENCE.md](API-REFERENCE.md)
- [openapi.json](openapi.json)

Key runtime surfaces:

| Surface | Paths |
|---|---|
| Health | `/health`, `/api/v1/health`, `/a2a/health`, `/mcp/health` |
| WebUI shell | `/`, `/ui/`, `/ui/{route}`, `/runtime-config.js`, `/assets/{asset_path}` |
| Tool REST | `/api/v1/tools`, `/api/v1/tools/{tool_name}` |
| MCP HTTP | `/mcp/tools`, `/mcp/tools/{tool_name}` |
| A2A HTTP | `/a2a/tools`, `/a2a/tools/{tool_name}` |
| Admin REST | `/api/v1/admin/*` for profiles, logs, jobs, audit, RBAC, users, groups, API keys, settings |

## Example Requests

Health:

```bash
curl -fsS http://127.0.0.1:28983/api/v1/health | python3 -m json.tool
```

Tool execution:

```bash
curl -fsS \
  -H 'x-api-key: 12345678' \
  -H 'Content-Type: application/json' \
  http://127.0.0.1:28983/api/v1/tools/mail_search \
  -d '{"profile_id":"operations","mode":"imap","query":"ALL","filters":{"folder":"INBOX"}}' \
  | python3 -m json.tool
```

## Response Envelope

REST responses use the Cloud-Dog envelope:

```json
{
  "ok": true,
  "result": {},
  "warnings": [],
  "errors": [],
  "meta": {
    "request_id": "...",
    "correlation_id": "..."
  }
}
```

## Verification Basis

- Reviewed runtime entrypoints: `src/imap_hub_server/api_server.py`, `web_server.py`, `mcp_server.py`, `a2a_server.py`
- Reviewed admin routes: `src/imap_hub_server/admin/endpoints.py`
- Verified canonical REST path remains `/api/v1`
- Verified local health on `28983` and preprod health on `https://imapmcpserver0.example.com/health` during W28A-962
