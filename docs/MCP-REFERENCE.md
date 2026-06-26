---
template-id: T-MCP
template-version: 1.0
applies-to: docs/MCP-REFERENCE.md
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

# imap-mcp-server — MCP-REFERENCE

> **Template version:** T-MCP v1.0 — MCP tool surface (JSON-RPC 2.0 at `/mcp`).

## 1. Auth model

Auth mode: `api_key` (HTTP bearer or `x-api-key` header).  
Transport gate: `install_auth_middleware` rejects unauthenticated callers with HTTP 401 before any
tool execution (W28A-735-R5 / D-IMAP-IDENTITY-COLLAPSE-1). Anonymous MCP clients never reach
the tool layer.  
RBAC: the API key is resolved to a user record; the user's flat role (`admin`, `read-write`,
`read-only`) is looked up from the admin state and maps to the flat role permission set defined
in `web_flat_roles.py`. Per-tool RBAC is enforced by `tool_rbac.py` using a
`resource:action` permission map (PS-70 UM3).

Admin tools (prefixed `user_`, `group_`, `api_key_`) require the `admin` flat role AND a valid
API key checked via `_require_admin_tool_access`. Mail/folder/index tools are resource-bearing and
additionally scoped per `mailbox_profile` via the RBACBinding cascade (W28A-750).

## 2. Tools

Tool count: 29. All names below exist as string literals in
`src/imap_hub_core/tools/handlers.py` (`ToolContract(name=...)`) and are dynamically
registered into the MCP router at startup.

---

### 2.1 `profile_list`

- **Description:** List all configured mailbox profiles visible to the caller.
- **RBAC:** `admin`, `read-write`, `read-only` (all authenticated roles)
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "include_disabled": { "type": "boolean", "default": false }
    },
    "additionalProperties": false
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "ok": { "type": "boolean" },
      "result": { "type": "object", "description": "Map of profile_id → profile dict" },
      "warnings": { "type": "array" },
      "errors": { "type": "array" },
      "meta": { "type": "object" }
    }
  }
  ```
- **Errors:** `403 Forbidden` if caller lacks role; `401 Unauthorized` if no valid API key.
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp/tools/profile_list \
    -H "x-api-key: ${API_KEY}" \
    -H "Content-Type: application/json" \
    -d '{"include_disabled": false}'
  ```

---

### 2.2 `mail_probe`

- **Description:** Probe IMAP connectivity for a named profile (login + INBOX select).
- **RBAC:** `admin`, `read-write`, `read-only`
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "profile_id": { "type": "string" },
      "folder":     { "type": "string", "default": "INBOX" }
    },
    "required": ["profile_id"],
    "additionalProperties": false
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "ok": { "type": "boolean" },
      "result": {
        "type": "object",
        "properties": {
          "connected": { "type": "boolean" },
          "profile_id": { "type": "string" },
          "folder": { "type": "string" },
          "message_count": { "type": "integer" }
        }
      }
    }
  }
  ```
- **Errors:** `404` profile not found; `502` IMAP connection failed.
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp/tools/mail_probe \
    -H "x-api-key: ${API_KEY}" \
    -H "Content-Type: application/json" \
    -d '{"profile_id": "operations_cloud_dog", "folder": "INBOX"}'
  ```

---

### 2.3 `mail_search`

- **Description:** Search for messages using the configured mode (cache / imap / vector / hybrid). Supports async submission via `run_async`.
- **RBAC:** `admin`, `read-write`, `read-only` — requires `imap:mail:read`
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "profile_id":      { "type": "string" },
      "mode":            { "type": "string", "enum": ["cache","imap","vector","hybrid"], "default": "cache" },
      "query":           { "type": "string" },
      "filters":         { "type": "object", "default": {} },
      "similarity_pins": { "type": "array",  "items": { "type": "string" }, "default": [] },
      "limit":           { "type": ["integer","null"] },
      "run_async":       { "type": "boolean", "default": false }
    },
    "required": ["profile_id", "query"],
    "additionalProperties": false
  }
  ```
- **Output schema:** Standard envelope; `result` contains `messages[]` (sync) or `job_id` + `status` (async).
- **Errors:** `403` insufficient permission; `404` profile not found; `408` timeout.
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp/tools/mail_search \
    -H "x-api-key: ${API_KEY}" \
    -H "Content-Type: application/json" \
    -d '{"profile_id":"operations_cloud_dog","mode":"imap","query":"invoice","limit":20}'
  ```

---

### 2.4 `mail_search_since_last`

- **Description:** Return only messages that are new/changed since the last equivalent search (delta via the Search Ledger).
- **RBAC:** `admin`, `read-write`, `read-only` — requires `imap:mail:read`
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "profile_id": { "type": "string" },
      "mode":       { "type": "string", "enum": ["cache","imap","vector","hybrid"], "default": "cache" },
      "query":      { "type": "string" },
      "filters":    { "type": "object", "default": {} },
      "limit":      { "type": ["integer","null"] }
    },
    "required": ["profile_id", "query"],
    "additionalProperties": false
  }
  ```
- **Output schema:** Standard envelope; `result.messages[]` contains only delta messages.
- **Errors:** `404` profile or ledger entry not found; `403` insufficient permission.
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp/tools/mail_search_since_last \
    -H "x-api-key: ${API_KEY}" \
    -H "Content-Type: application/json" \
    -d '{"profile_id":"operations_cloud_dog","query":"invoice"}'
  ```

---

### 2.5 `mail_headlines`

- **Description:** Return concise subject/from/date headlines for search results without fetching full message bodies.
- **RBAC:** `admin`, `read-write`, `read-only` — requires `imap:mail:read`
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "profile_id": { "type": "string" },
      "mode":       { "type": "string", "enum": ["cache","imap","vector","hybrid"], "default": "imap" },
      "query":      { "type": "string", "default": "" },
      "filters":    { "type": "object", "default": {} },
      "limit":      { "type": ["integer","null"] }
    },
    "required": ["profile_id"],
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.headlines[]` — each item: `{ uid, subject, from, date }`.
- **Errors:** `403` insufficient permission; `404` profile not found.
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp/tools/mail_headlines \
    -H "x-api-key: ${API_KEY}" \
    -H "Content-Type: application/json" \
    -d '{"profile_id":"operations_cloud_dog","query":"invoice","limit":10}'
  ```

---

### 2.6 `mail_move_duplicates_since_last_search`

- **Description:** Plan or execute duplicate message moves since the last similar search, using configurable dedup strategy and keeper policy. Defaults to `dry_run=true`.
- **RBAC:** `admin`, `read-write` — requires `imap:mail:write`
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "profile_id":          { "type": "string" },
      "query":               { "type": "string" },
      "destination_folder":  { "type": "string" },
      "strategy":            { "type": "string", "enum": ["message_id","content_hash","heuristic"], "default": "message_id" },
      "policy":              { "type": "string", "enum": ["newest","oldest","flagged","first_seen"], "default": "newest" },
      "dry_run":             { "type": "boolean", "default": true }
    },
    "required": ["profile_id", "query", "destination_folder"],
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.plan[]` (dry_run) or `result.moved[]` (executed).
- **Errors:** `403` insufficient permission; `404` profile or destination folder not found.

---

### 2.7 `mail_get_message`

- **Description:** Fetch the full message payload (headers + body + parts) for a given UID.
- **RBAC:** `admin`, `read-write`, `read-only` — requires `imap:mail:read`
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "profile_id": { "type": "string" },
      "uid":        { "type": "string" },
      "folder":     { "type": "string", "default": "INBOX" }
    },
    "required": ["profile_id", "uid"],
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.message` — full message dict with headers, body, parts.
- **Errors:** `404` UID or profile not found; `403` insufficient permission.

---

### 2.8 `mail_list_folders`

- **Description:** List all live IMAP folders available for a profile.
- **RBAC:** `admin`, `read-write`, `read-only` — requires `imap:folder:read`
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "profile_id": { "type": "string" }
    },
    "required": ["profile_id"],
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.folders[]` — list of folder name strings.
- **Errors:** `404` profile not found; `502` IMAP connection error.

---

### 2.9 `mail_list_attachments`

- **Description:** List attachment metadata (filename, size, content-type, part_id) for a specific message without downloading.
- **RBAC:** `admin`, `read-write`, `read-only` — requires `imap:mail:read`
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "profile_id": { "type": "string" },
      "uid":        { "type": "string" },
      "folder":     { "type": "string", "default": "INBOX" }
    },
    "required": ["profile_id", "uid"],
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.attachments[]` — list of `{ part_id, filename, content_type, size }`.
- **Errors:** `404` UID or profile not found.

---

### 2.10 `mail_download_attachment`

- **Description:** Download a specific message attachment to local storage (downloads_dir) and return the saved path.
- **RBAC:** `admin`, `read-write` — requires `imap:mail:read`
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "profile_id": { "type": "string" },
      "uid":        { "type": "string" },
      "part_id":    { "type": "string" },
      "folder":     { "type": "string", "default": "INBOX" },
      "filename":   { "type": ["string","null"] }
    },
    "required": ["profile_id", "uid", "part_id"],
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.path` — local filesystem path of downloaded file.
- **Errors:** `404` part_id, UID, or profile not found; `507` storage full.

---

### 2.11 `mail_extract_message`

- **Description:** Extract message content to JSON and/or Markdown formats (text, subject, from, date, attachments summary).
- **RBAC:** `admin`, `read-write`, `read-only` — requires `imap:mail:read`
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "profile_id": { "type": "string" },
      "uid":        { "type": "string" },
      "folder":     { "type": "string", "default": "INBOX" },
      "format":     { "type": "string", "enum": ["json","markdown","both"], "default": "both" }
    },
    "required": ["profile_id", "uid"],
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.json` (object) and/or `result.markdown` (string) depending on format.
- **Errors:** `404` UID or profile not found; `400` unsupported format.

---

### 2.12 `mail_set_seen`

- **Description:** Set or clear the `\Seen` IMAP flag on a list of message UIDs.
- **RBAC:** `admin`, `read-write` — requires `imap:mail:write`
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "profile_id": { "type": "string" },
      "uids":       { "type": "array", "items": { "type": "string" } },
      "seen":       { "type": "boolean" },
      "folder":     { "type": "string", "default": "INBOX" }
    },
    "required": ["profile_id", "uids", "seen"],
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.updated` — count of UIDs successfully updated.
- **Errors:** `403` insufficient permission; `404` profile not found.

---

### 2.13 `mail_move_messages`

- **Description:** Move a list of messages by UID from the source folder to a destination folder.
- **RBAC:** `admin`, `read-write` — requires `imap:mail:write`
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "profile_id":         { "type": "string" },
      "uids":               { "type": "array", "items": { "type": "string" } },
      "destination_folder": { "type": "string" },
      "folder":             { "type": "string", "default": "INBOX" }
    },
    "required": ["profile_id", "uids", "destination_folder"],
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.moved` — count of messages successfully moved.
- **Errors:** `403` insufficient permission; `404` profile or destination folder not found.

---

### 2.14 `mail_delete_messages`

- **Description:** Delete (expunge) a list of messages by UID from a folder.
- **RBAC:** `admin`, `read-write` — requires `imap:mail:delete`
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "profile_id": { "type": "string" },
      "uids":       { "type": "array", "items": { "type": "string" } },
      "folder":     { "type": "string", "default": "INBOX" }
    },
    "required": ["profile_id", "uids"],
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.deleted` — count of messages successfully deleted.
- **Errors:** `403` insufficient permission; `404` profile not found.

---

### 2.15 `user_list`

- **Description:** List all configured users in the admin state.
- **RBAC:** `admin` only — requires valid API key + admin role
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "include_disabled": { "type": "boolean", "default": false }
    },
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.users[]` — list of user record objects.
- **Errors:** `401` no API key; `403` non-admin role.

---

### 2.16 `user_get`

- **Description:** Get a single user record by `user_id`.
- **RBAC:** `admin` only
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "user_id": { "type": "string" }
    },
    "required": ["user_id"],
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.user` — single user record object.
- **Errors:** `401` no API key; `403` non-admin; `404` user not found.

---

### 2.17 `user_create`

- **Description:** Create a new user in the admin state.
- **RBAC:** `admin` only
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "user_id":        { "type": ["string","null"] },
      "username":       { "type": "string" },
      "email":          { "type": "string" },
      "display_name":   { "type": "string", "default": "" },
      "role":           { "type": "string", "default": "viewer" },
      "status":         { "type": "string", "default": "active" },
      "is_system_user": { "type": "boolean", "default": false },
      "tenant_id":      { "type": ["string","null"] }
    },
    "required": ["username", "email"],
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.user` — created user record with assigned `user_id`.
- **Errors:** `401`/`403` auth; `409` username or email conflict.

---

### 2.18 `user_update`

- **Description:** Update fields on an existing user record.
- **RBAC:** `admin` only
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "user_id":        { "type": "string" },
      "username":       { "type": ["string","null"] },
      "email":          { "type": ["string","null"] },
      "display_name":   { "type": ["string","null"] },
      "role":           { "type": ["string","null"] },
      "status":         { "type": ["string","null"] },
      "is_system_user": { "type": ["boolean","null"] },
      "tenant_id":      { "type": ["string","null"] }
    },
    "required": ["user_id"],
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.user` — updated user record.
- **Errors:** `401`/`403` auth; `404` user not found.

---

### 2.19 `user_delete`

- **Description:** Delete a user record from the admin state.
- **RBAC:** `admin` only
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "user_id": { "type": "string" }
    },
    "required": ["user_id"],
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.deleted` — boolean confirming deletion.
- **Errors:** `401`/`403` auth; `404` user not found.

---

### 2.20 `group_list`

- **Description:** List all configured groups in the admin state.
- **RBAC:** `admin` only
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "include_disabled": { "type": "boolean", "default": false }
    },
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.groups[]` — list of group record objects.
- **Errors:** `401`/`403` auth.

---

### 2.21 `group_get`

- **Description:** Get a single group record by `group_id`.
- **RBAC:** `admin` only
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "group_id": { "type": "string" }
    },
    "required": ["group_id"],
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.group` — single group record.
- **Errors:** `401`/`403` auth; `404` group not found.

---

### 2.22 `group_create`

- **Description:** Create a new group in the admin state.
- **RBAC:** `admin` only
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "group_id":   { "type": ["string","null"] },
      "name":       { "type": "string" },
      "description":{ "type": "string", "default": "" },
      "roles":      { "type": "array", "items": { "type": "string" }, "default": [] },
      "members":    { "type": "array", "items": { "type": "string" }, "default": [] },
      "tenant_id":  { "type": ["string","null"] }
    },
    "required": ["name"],
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.group` — created group with assigned `group_id`.
- **Errors:** `401`/`403` auth; `409` name conflict.

---

### 2.23 `group_update`

- **Description:** Update fields on an existing group.
- **RBAC:** `admin` only
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "group_id":    { "type": "string" },
      "name":        { "type": ["string","null"] },
      "description": { "type": ["string","null"] },
      "roles":       { "type": ["array","null"] },
      "tenant_id":   { "type": ["string","null"] }
    },
    "required": ["group_id"],
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.group` — updated group record.
- **Errors:** `401`/`403` auth; `404` group not found.

---

### 2.24 `group_delete`

- **Description:** Delete a group from the admin state.
- **RBAC:** `admin` only
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "group_id": { "type": "string" }
    },
    "required": ["group_id"],
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.deleted` — boolean.
- **Errors:** `401`/`403` auth; `404` group not found.

---

### 2.25 `group_add_member`

- **Description:** Add a user to a group (by `user_id`).
- **RBAC:** `admin` only
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "group_id": { "type": "string" },
      "user_id":  { "type": "string" }
    },
    "required": ["group_id", "user_id"],
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.group` — updated group with new member.
- **Errors:** `401`/`403` auth; `404` group or user not found.

---

### 2.26 `group_remove_member`

- **Description:** Remove a user from a group.
- **RBAC:** `admin` only
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "group_id": { "type": "string" },
      "user_id":  { "type": "string" }
    },
    "required": ["group_id", "user_id"],
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.group` — updated group without the removed member.
- **Errors:** `401`/`403` auth; `404` group or user not found.

---

### 2.27 `api_key_list`

- **Description:** List managed API keys, optionally filtered by owner user.
- **RBAC:** `admin` only
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "owner_user_id": { "type": ["string","null"] }
    },
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.api_keys[]` — list of API key records (no secret values).
- **Errors:** `401`/`403` auth.

---

### 2.28 `api_key_create`

- **Description:** Create a scoped API key for a user, optionally with a TTL and prefix.
- **RBAC:** `admin` only
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "owner_user_id": { "type": "string" },
      "scopes":        { "type": "array", "items": { "type": "string" }, "default": [] },
      "description":   { "type": "string", "default": "" },
      "ttl_days":      { "type": ["integer","null"] },
      "key_prefix":    { "type": ["string","null"] }
    },
    "required": ["owner_user_id"],
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.api_key` — the raw key value (returned once only) and metadata.
- **Errors:** `401`/`403` auth; `404` owner user not found.

---

### 2.29 `api_key_revoke`

- **Description:** Revoke (permanently disable) a managed API key by its `api_key_id`.
- **RBAC:** `admin` only
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "api_key_id": { "type": "string" }
    },
    "required": ["api_key_id"],
    "additionalProperties": false
  }
  ```
- **Output schema:** `result.revoked` — boolean.
- **Errors:** `401`/`403` auth; `404` key not found.

---

## 3. Cross-references
- [API-REFERENCE.md](API-REFERENCE.md)
- [A2A-REFERENCE.md](A2A-REFERENCE.md)
- [ROLES-AND-USECASES.md](ROLES-AND-USECASES.md)
- PS-72-mcp-a2a-webui.md

## 4. Project-specific notes

- MCP tools path: `/mcp/tools` (alias: `/tools`). JSON-RPC 2.0 at `/mcp`.
- Async search: `mail_search` accepts `run_async: true`; the job is submitted to the
  `JobsRuntime` and returns a `job_id` for polling.
- Tool source: `src/imap_hub_core/tools/handlers.py` — `build_default_tool_registry()`.
- Admin tool gate: any tool whose name starts with `user_`, `group_`, or `api_key_` requires
  `_require_admin_tool_access` (admin role + valid API key) regardless of the caller's role headers.
