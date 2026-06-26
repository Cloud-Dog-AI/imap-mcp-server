---
doc-id: RELEASE-1.0RC01
project: imap-mcp-server
lane: W28E-1803C
updated: 2026-06-24
---

# imap-mcp-server 1.0RC01

## Stream-C WebUI/E2E Closeout

- Consumes accepted W28E-1803A requirements/test-binding and accepted
  W28E-1803B functional/preprod backend proof.
- Enforces the W28E canonical WebUI routes: `/admin/*`, `/developer/*`,
  `/system/*`, `/audit-log`, and `/login` (PS-WEBUI-URL-CANONICAL v1.0).
  Canonical login `/login` serves 200.
- Preserves every legacy WebUI alias with a server-side HTTP 308 redirect to its
  canonical path (query + fragment preserved) and returns 404 for unknown WebUI
  paths (WURL-007). Legacy aliases redirected include: `/ui/login`->`/login`,
  `/idam/*`->`/admin/*`, `/api-docs`->`/developer/api-docs`,
  `/mcp-console`->`/developer/mcp-console`, `/a2a-console`->`/developer/a2a-console`,
  `/jobs`->`/system/jobs`, `/settings`->`/system/settings`,
  `/gmail-settings`->`/system/gmail-settings`, `/about`->`/system/about`,
  `/diagnostics-audit`->`/audit-log`.
- Keeps API, MCP, A2A, `/health`, and static assets OUTSIDE the WebUI alias
  redirects (WURL-008): those surfaces are never redirected. Implemented in
  `src/imap_hub_server/webui_canonical.py` with middleware wired into
  `web_server.py` and `api_server.py`.
- Common operator taxonomy delivered (PS-WEBUI-STYLE-COMPONENTS v1.0): Login,
  Top/Left menu, Footer, Audit-Log, Admin Users/Groups/API-Keys/Roles/RBAC,
  Developer API-Docs/MCP/A2A, System Jobs/Settings/Gmail-Settings/About, plus
  imap domain pages (Dashboard, Channels, Mailbox, Mailbox-Workspace). Shared
  `@cloud-dog/shell` + `@cloud-dog/ui` + `@cloud-dog/tokens`.
- Cookie-session auth; role matrix proven for admin / operator / read-only /
  anonymous; server-side RBAC enforced (AT_WEBUI T5 RbacEnforcement / FR-04).
- WCAG 2.1 AA: 0 axe violations on every taxonomy page (18/18 local and preprod,
  excluding the embedded Swagger `.swagger-ui` on the API-Docs page). A shared
  `@cloud-dog/ui` `MessageList.tsx` a11y defect was fixed this lane (imap is its
  sole consumer; monorepo origin/main `d03ab0c`).

## Stream-B credential-preservation fix

- A real service-repo fix landed during Stream-C in
  `src/imap_hub_server/admin/state_profiles.py::export_profiles`: it now
  preserves seed mailbox credentials when a persisted admin-state override blanks
  them (the WebUI never round-trips the mailbox secret). Bound to FR-03, covered
  by `tests/unit/UT1.36_AdminStateCRUD/test_admin_state_crud.py::test_ut136_export_preserves_seed_credentials_when_override_blanks_them`.
  This unblocked live mail-search (AT_WEBUI T7 / IMAP-084) on the deployed Vault
  container.

## Deployment

- Service `origin/main`: `b2864f7fd8d0098c0e30fb08bbb5b2aae375b594`.
- UI monorepo `origin/main`: `d03ab0c556f1e1a9db5ca262b6d18fd48d401b9d`
  (`apps/imap-mcp` canonical routes/nav + `@cloud-dog/ui` `MessageList.tsx` a11y).
- Image: `registry.cloud-dog.net:443/cloud-dog/imap-mcp-server:latest`
  manifest digest
  `sha256:f5a818cbcc50799b9a8abf65cd43d2e20b400daac1504ea44bc470414dffafb2`,
  built image_id
  `sha256:74f2adbbb2c88a1b12760baa069bb3e94ec714b7687b643f16759a410c4b2c67`.
- Deployed to preprod `imapmcpserver0.cloud-dog.net` (server0) via the operator
  canonical Terraform root `27 MLAgents`
  (`docker_image.imapmcpserver` + `docker_container.imapmcpserver0`); deployed
  container image == registry digest == built image == live (digest parity PASS).
  Health 200, version 0.1.0; live bundle `assets/index-wDjwBnJQ.js`.
- Estate no-regression: imap + 13 preprod siblings 200 before and after
  (socialmediamcpserver0 absent per W28E-1811B TEST-ONLY-NO-DEPLOY).

## Validation Summary

| Gate | Evidence | Verdict |
|---|---|---|
| Playwright WebUI (local) | `07-local-docker-playwright-junit.xml` (11/11) | PASS |
| Playwright WebUI (preprod) | `preprod-playwright-junit.xml` (11/11) | PASS |
| axe a11y (local + preprod) | `03-axe-a11y-evidence.tsv` + `03-preprod-axe-a11y-evidence.tsv` (18/18, 0 violations) | PASS |
| URL canonicalisation (local + preprod) | `04-url-canonical-audit.tsv` + `04-preprod-url-canonical-audit.tsv` (40/40 each) | PASS |
| Deployed digest parity | `preprod-deployed-identity.tsv` | PASS |
| Estate no-regression | `preprod-health-before-after.tsv` | PASS |
| 4-sentinel browser smoke | `preprod-sentinel-browser-smoke.tsv` (5/5) | PASS |
| Unauthenticated negative-auth | `preprod-unauth-negative-auth.tsv` | PASS |
| Stream-B credential-preservation fix | `01-stream-B-leakage.tsv` (FR-03) | PASS |

## Release Tag

`1.0RC01-imap-mcp-server` on `imap-mcp-server` `origin/main` (ancestor-proven),
plus lane tags `W28E-1803C-EVIDENCE` and `W28E-1803C-FINAL-PROOF`.
