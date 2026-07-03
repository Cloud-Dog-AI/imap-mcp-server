---
template-id: T-WUI
template-version: 1.0
applies-to: docs/WEBUI-REFERENCE.md
registry: service
required: conditional
when-applicable: ""
template-last-updated: 2026-06-12
template-owner: public-standards

project: imap-mcp-server
doc-last-updated: 2026-06-18
doc-git-commit: 7683f39
doc-git-branch: main
doc-source-shas: []
doc-age-policy: 90d
doc-conformance-stamp: 2026-06-18T00:00:00Z
---

# imap-mcp-server — WEBUI-REFERENCE

> **Template version:** T-WUI v1.0 — conditional: service has a WebUI panel.

Sources consulted: `src/imap_hub_server/web_server.py`, `src/imap_hub_server/api_server.py`,
`src/imap_hub_server/web_flat_roles.py`, `cloud-dog-ai-ui-monorepo/apps/imap-mcp/src/routes/App.tsx`.

## 1. Panel structure

The WebUI is a React SPA (built from `cloud-dog-ai-ui-monorepo/apps/imap-mcp`) served at `/ui`
by the API server and proxied via the Web server (`web_server.py`). The SPA uses BrowserRouter;
all panel routes below resolve to `index.html` (served by the static file handler).

| Route | Panel | Roles | Backend route |
|---|---|---|---|
| `/ui/` | Dashboard | all authenticated | `GET /api/v1/...` health + status |
| `/ui/profiles` | Channels (Mailbox Profiles) | all authenticated | `GET /api/v1/profiles` |
| `/ui/mailbox-workspace` | Mailbox Workspace | all authenticated | `GET /api/v1/...` folder/message ops |
| `/ui/search-retrieve` | Mailbox (Search & Retrieve) | all authenticated | `POST /mcp/tools/mail_search` |
| `/ui/diagnostics-audit` | Audit & Log | all authenticated (write: admin) | `GET /api/v1/audit/...` |
| `/ui/jobs` | Jobs | all authenticated | `GET /api/v1/jobs/...` |
| `/ui/mcp-console` | MCP Console | all authenticated | `GET /mcp/tools`, `POST /mcp/tools/<name>` |
| `/ui/a2a-console` | A2A Console | all authenticated | `GET /a2a/...` |
| `/ui/api-docs` | API Docs (OpenAPI) | all authenticated | `GET /api/v1/openapi.json` |
| `/ui/idam/users` | Users (Admin) | admin | `GET /api/v1/admin/users` |
| `/ui/idam/groups` | Groups (Admin) | admin | `GET /api/v1/admin/groups` |
| `/ui/idam/api-keys` | API Keys (Admin) | admin | `GET /api/v1/admin/api-keys` |
| `/ui/idam/roles` | Roles (Admin) | admin | `GET /api/v1/admin/roles` |
| `/ui/idam/rbac` | RBAC (Admin) | admin | `GET /api/v1/admin/rbac` |
| `/ui/settings` | Settings | all authenticated | client-local only |
| `/ui/gmail-settings` | Gmail Settings | admin, read-write | `GET /api/v1/...` profile config |
| `/ui/about` | About (dialog) | all authenticated | client-local only |
| `/ui/login` | Login | unauthenticated | `POST /auth/login` |

## 2. Login

- **Flow:** Username + password form (`POST /auth/login`). On success, the server sets an
  HTTP-only session cookie (`imap_web_session`) and returns the flat role in the response body.
- **Session storage:** Server-side in-memory token store (`_sessions` dict). Cookie path is
  scoped to the Web server's `web_base_path` (default: `/`).
- **Session timeout:** Configurable via `CLOUD_DOG_SESSION_TIMEOUT_MINUTES` (default: 30 min).
- **Logout:** `POST /auth/logout` — cookie is deleted server-side.
- **Auth check:** `GET /auth/me` — returns the current session user, flat role, and permission set.
  Returns `401` if not authenticated.
- **Auth mode:** Always `"cookie"` for the WebUI (W28A-876 / `web_server.auth_mode`). The MCP/API
  transports use `api_key`.

Default demo accounts (overridable via env):

| Username | Password | Flat role |
|---|---|---|
| `admin` | `BlueRiverChair` | `admin` |
| `read-write` | `GreenRiverDesk` | `read-write` |
| `read-only` | configurable | `read-only` |

## 3. RBAC visibility matrix

Three flat roles (`admin`, `read-write`, `read-only`) derived from `web_flat_roles.py`.

| Panel | admin | read-write | read-only |
|---|---|---|---|
| Dashboard | Full view | Full view | Full view |
| Channels (Profiles) | View + manage | View + search/use | View only |
| Mailbox Workspace | Full (browse/move/delete) | Browse, move | Read-only browse |
| Search & Retrieve | Full + write ops | Search + download | Search + read |
| Audit & Log | Full view | View own entries | View own entries |
| Jobs | Full (submit/cancel) | Submit + view own | View only |
| MCP Console | All 29 tools | Mail/folder/index tools | Read tools only |
| A2A Console | Full | Full | Read |
| API Docs | Full | Full | Full |
| Users (Admin) | Full CRUD | No access (403) | No access (403) |
| Groups (Admin) | Full CRUD | No access (403) | No access (403) |
| API Keys (Admin) | Full CRUD | No access (403) | No access (403) |
| Roles / RBAC (Admin) | Full view + edit | No access (403) | No access (403) |
| Gmail Settings | Full | Limited (own profile) | No access |
| Settings | Personal prefs | Personal prefs | Personal prefs |

Write operations (move, delete, flag, create/update user/group/key) return `403` for
`read-only` callers via the flat-role write gate in `web_server.py`.

## 4. Static routes

Routes registered at the API server level (`api_server.py`, `WEB_UI_ROUTE_SEGMENTS`):

```
/ui
/ui/
/ui/dashboard
/ui/profiles
/ui/search-retrieve
/ui/mailbox-workspace
/ui/jobs
/ui/mcp-console
/ui/api-docs
/ui/admin/users
/ui/admin/groups
/ui/admin/api-keys
/ui/admin/rbac
/ui/diagnostics-audit
/ui/a2a-console
/ui/settings
/ui/about
/ui/login
/ui/admin-control
/ui/mutation-gating
```

Static assets served at `/ui/assets/` (CSS, JS bundles). Runtime config served at
`/ui/runtime-config.js` and `/runtime-config.js`.

Note: The IDAM admin pages (`/idam/users`, `/idam/groups`, etc.) are registered by the IDAM
shared component in the SPA and routed via the `/ui/idam/*` path in the browser. The backend
API uses `/api/v1/admin/...` for user/group/key operations.

## 5. Cross-references
- [API-REFERENCE.md](API-REFERENCE.md)
- [ROLES-AND-USECASES.md](ROLES-AND-USECASES.md)
- PS-77-webui-comprehensive.md
- PS-30-ui.md

## 6. Project-specific notes

- The WebUI SPA is built from `cloud-dog-ai-ui-monorepo/apps/imap-mcp` and vendored into
  `src/imap_hub_server/static/ui/` (also at `ui/dist/`).
- `web_server.py` installs a flat-role write gate as FastAPI middleware that returns `403` for
  `read-only` sessions attempting any HTTP mutation (PUT/POST/DELETE/PATCH) other than auth
  endpoints.
- The `auth_mode` is always `"cookie"` for the WebUI surface (overridden from any API auth mode
  setting via `runtime_config_value(...) or "cookie"`).
- AGENT-LESSONS (W28A-876): `_web_auth_mode` was previously derived from `config.auth.mode`,
  causing the WebUI to advertise `api_key` instead of `cookie`. Fixed to return `"cookie"` always.
