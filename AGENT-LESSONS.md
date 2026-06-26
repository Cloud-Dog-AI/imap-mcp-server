---
template-id: T-AGL
template-version: 1.0
applies-to: AGENT-LESSONS.md
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
doc-age-policy: indefinite
doc-conformance-stamp: 2026-06-18T00:00:00Z
---

# AGENT LESSONS

## Central Programme Lesson Authority

The canonical programme lessons are in `/opt/iac/Development/cloud-dog-ai/cloud-dog-ai-platform-standards/AGENT-LESSONS.md`. This repository file is a service-specific overlay only. If this file conflicts with the central programme file, the central file wins.

Before project work, every agent must read the central `RULES.md`, central `AGENT-LESSONS.md`, `AGENT-BOOTSTRAP-DIRECTIVE.md`, the live `AGENT-DISPATCH-TABLE.md`, the exact lane instruction, and this overlay. Do not copy central rules here; add only service-specific deltas and feed reusable lessons back to the central file.


This file captures lessons from the IMAP MCP WebUI, native Playwright, deploy, and pre-E2E validation work. Read it before changing code, tests, docs, or deployment wiring in this repository.

## 1. Platform Alignment (BINDING)

This file extends — never overrides — the central platform doctrine. Before any work in
`imap-mcp-server`, the agent MUST read:

- `cloud-dog-ai-platform-standards/RULES.md` (latest version)
- `cloud-dog-ai-platform-standards/AGENT-LESSONS.md` (latest version)
- `cloud-dog-ai-platform-standards/AGENT-BOOTSTRAP-DIRECTIVE.md` (latest version)
- This file

Fix-what-you-find is the default (central `RULES.md §14.3` + central `AGENT-LESSONS.md §6.81`/§6.101).
"Not a fix lane" language is invalid unless the instruction is explicitly READ-ONLY/AUDIT-ONLY.

The lessons below capture `imap-mcp-server`-specific knowledge only. If you find yourself
re-stating a central rule, stop and link to central instead.

## Code

- The IMAP WebUI log/audit surfaces depend on the backend exposing normalized multi-source rows from `/api/v1/admin/logs`; the UI cannot meet AU-3 display requirements if the backend only returns message text.
- The diagnostics page and dashboard both work cleanly with the shared `@cloud-dog/ui` `DataTable` once column defaults are seeded into `localStorage` and the row payload already contains AU-3 fields.
- For IMAP create-user flows, the API log source contains the target user ID, but the WebUI log source usually needs method/path checks (`POST /webapi/v1/admin/users`) instead of target-ID checks because the proxy request path does not include the new ID.
- The delete flow is easier to prove across all sources because the WebUI proxy path includes the user ID (`DELETE /webapi/v1/admin/users/<id>`).
- `MailboxWorkspacePage` is a real page now, but its folder tree is still built from profile config include globs plus defaults. Do not mistake that for a real IMAP folder-list backend contract.
- The mailbox workspace currently loads mailbox content through `mail_search` in `cache` mode. A green workspace UI does not prove live IMAP browsing unless the backend call path and credentials are verified.
- `StorageProfilesPage.tsx` still renders CRUD affordances as if the user is an admin. If restricted-user or read-only behaviour matters, it needs explicit UI handling and direct tests; backend RBAC alone is not enough evidence.
- `AuditLogPage.tsx` is richer than the legacy diagnostics page, but the current routed `/diagnostics-audit` surface can still point at `LegacyDiagnosticsAuditPage`. Always inspect `App.tsx`, not just the page component you expect to be canonical.
- The current mailbox workspace supports attachment listing in the viewer tab, but not full attachment download actions from that workspace. Search-page attachment support and workspace attachment support are not equivalent.
- `McpToolsPage.tsx` still carries both legacy controls and the shared `McpConsole`. If console behaviour and legacy parity diverge, tests may pass against one surface while the other regresses.

## Test Environment

- `tests/env-AT-local-docker` is not directly usable by `docker compose` because it still contains literal Vault placeholder syntax like `${vault...}`. Local Docker smoke needs a resolved concrete env file.
- The repo-local `data/` and `logs/` mounts can become root-owned from prior container runs. When that happens, local Docker smoke is more reliable with isolated temporary bind mounts under `working/` than with the repo’s shared runtime folders.
- Existing IMAP WebUI regression coverage that is useful for this area is the local `webui_e2e_runner.mjs` block (`T1`, `T2`, `T3`, `T4`, `T8`, `T10`) plus a dedicated Playwright evidence runner for the required preprod screenshots.
- The current Playwright green bar (`20 passed`) proves the existing suite, not the full IMAP MCP spec. W28A-912 confirmed that mailbox workspace, A2A console, settings, split admin pages, richer audit page, and restricted-user RBAC are still uncovered directly.
- All current Playwright fixtures sign in as admin. If you need evidence for read-only or scoped access, add separate non-admin fixtures and tests; do not infer that from admin-only runs.
- `sync-search-retrieve.spec.ts` and `attachment-list-download.spec.ts` prove search/get/extract/download flows on the search page, but they do not prove the mailbox workspace route.
- The current suite does not directly prove live IMAP search. Because the UI and backend can fall back to `cache` mode, you need explicit evidence if the requirement is real IMAP SEARCH against a live mailbox.

## Infrastructure

- The live preprod hostname is `https://imapmcpserver0.cloud-dog.net`. The W28A-647 instruction text mentions `imapmcp0.cloud-dog.net`, but that hostname does not resolve.
- The active Terraform workspace for IMAP preprod deploys is `/opt/iac/cloud-dog-repo/terraform/server0.viewdeck.com/27 MLAgents`.
- The targeted deploy resources are `docker_image.imapmcpserver` and `docker_container.imapmcpserver0`.
- Current IMAP image push target is `registry.cloud-dog.net:443/cloud-dog/imap-mcp-server:latest`.
- The native local service ports used by the real IMAP stack are `8070` API, `8071` Web, `8072` MCP, and `8073` A2A. If an instruction mentions different IMAP ports, verify against `tests/env-ST` before acting.

## Architecture

- Preprod cookie-authenticated browser sessions talk to the Web proxy path `/webapi/v1/...`, not directly to `/api/v1/...`. Browser-side verification helpers must use `/webapi/v1` if they rely on the login session cookie.
- The deployed IMAP Web container is configured with `CLOUD_DOG_WEB_LOGIN_USERNAME` / `CLOUD_DOG_WEB_LOGIN_PASSWORD`; current preprod values are injected by Terraform rather than repo env files.
- The WebUI log source records proxy traffic and internal Web-surface activity, so “visible in WebUI logs” often means proving request method/path entries, not audit-target semantics.
- The service now has two competing UI realities: canonical richer pages exist in source, but legacy compatibility routes may still be the ones actually wired in `App.tsx`. Treat routing as part of the architecture, not just page implementation detail.
- There is still no real backend folder enumeration surface for the mailbox workspace. `tool_rbac.py` contains a `folder_list` permission string, but no matching live tool or API contract was found.
- Search-page read flows, mailbox-workspace read flows, and legacy mutation-gating flows are separate contracts. A fix in one does not prove the others.
- The richer diagnostics/audit architecture exists, but if `/diagnostics-audit` routes to the legacy compatibility page then the actual delivered operator surface is still the legacy one.
- A2A support is narrower than the full MCP tool surface. The current A2A skill set is limited and should not be assumed to cover every IMAP mail operation just because MCP tools exist for them.

## Related Projects

- IMAP UI changes live in the monorepo under `cloud-dog-ai-ui-monorepo/apps/imap-mcp`, but the deployed service serves the vendored bundle from `imap-mcp-server/ui/dist`. Any real UI fix needs both: rebuild in the monorepo and sync the built bundle into the service repo before Docker build/deploy.
- Shared `@cloud-dog/ui` `DataTable` behavior matters for evidence work: column picker labels are exposed as `Show <Column>`, bulk actions only appear once rows are selected, and sort state exposes `Sorted ascending` / `Sorted descending` labels that are useful in Playwright assertions.
- Shared `@cloud-dog/ui` patterns do not by themselves guarantee spec coverage. The presence of `FolderTree`, `MessageList`, `A2aConsole`, `JsonExplorer`, or `DataTable` only proves component adoption, not that the backend contract underneath is complete.
- If a UI report says a canonical route was adopted, verify the current route map in `apps/imap-mcp/src/routes/App.tsx` before repeating that claim. W28A-912 found route drift between earlier reports and current source.

## Deployment

- A green native Playwright run is not the same thing as full functional closure. For IMAP MCP, deployment confidence still needs route inspection and source-vs-report consistency checks because compatibility routes can remain active after a refactor.
- When a UI change affects canonical pages, verify both the page component and the actual active route after syncing the monorepo build into `ui/dist`. It is easy to rebuild the right page and still ship the wrong routed experience.

## Documentation

- `docs/REQUIREMENTS.md` is broader than the currently exercised Playwright suite. Treat it as the contract to validate against, not as proof that coverage already exists.
- `docs/API-REFERENCE.md` is weak on concrete route naming and still contains generic placeholders and `<dynamic>` entries. It is not sufficient as the sole source of truth for coverage decisions; inspect `api_server.py`, `web_server.py`, and `admin/endpoints.py` directly.
- When a report claims canonical route changes, compare that claim to the current source before relying on it. W28A-902 and current `App.tsx` were not fully aligned on `/diagnostics-audit` and `/mutation-gating`.

## Reporting

- The 12-step screenshot requirement must be checked with hash uniqueness, not visual inspection. For W28A-647 the correct check is `md5sum l-*.png | awk '{print $1}' | sort | uniq -d`.
- If a screenshot is captured after a redirect, it can silently duplicate the next step. Capture login-state evidence before submit if the next step is the authenticated dashboard.
- If a task begins after code changes are already underway, call out any missing “before state” evidence explicitly instead of pretending it exists.
- If a completion claim depends on E2E coverage, separate “the suite is green” from “the full spec is covered.” W28A-912 showed those are not the same statement for this service.

## W28A-662 — Job Control Adoption

### env-AT uses non-standard ports for imap-mcp
**What happened (W28A-662):** `tests/env-AT` sets `CLOUD_DOG__API_SERVER__PORT=28983` (not the allocated 8070). Server started successfully but health check on 8070 failed. Always read the env file for port values.

### JobsRuntime uses `slots=True` — use `object.__setattr__` for `__post_init__`
**What happened (W28A-662):** `@dataclass(slots=True)` prevents normal attribute assignment in `__post_init__`. Used `object.__setattr__(self, “_audit_logger”, ...)` to set the field.

## W28A-722 / W28A-743 Addendum

### IDAM COMPLIANCE (W28A-722)
Replaced requested_role == “admin” with RBACEngine escalation check in admin/endpoints.py.

### MCP TOOL AUDIT LOGGING (W28A-743)
MCP tool audit logging added to handlers.py call() method (W28A-743). Parameters body/content/password/secret/token redacted.

### SETTINGS PAGE — PS-73 SECTIONS
SettingsPage has all 7 PS-73 sections with health fetch from /health endpoint and Badge status display.

### UNIT TEST BASELINE
64 passed, 0 failed baseline. env-UT has Vault placeholder warnings but tests pass.

### TOOL DISPATCH ARCHITECTURE
Tool dispatch is in imap_hub_core/tools/handlers.py. ToolManager.call() handles authorization via _authorise() with fnmatch patterns, then delegates to contract handlers.

## W28A-846 — Native Playwright / WebApiProxy / Offline Read Path

### Code

- The current `cloud-dog-api-kit` pin for `imap-mcp-server` is `==0.12.1` (see `pyproject.toml`). The published package already exposes `WebApiProxy` and the MCP/A2A transport surfaces; do not edit `cloud_dog_api_kit/` locally to add proxy features; install the published package and use that. (Historical W28A-846 reference to `0.4.1` was correct at that time but is no longer the active pin.)
- `imap_hub_server/web_server.py` already supports the correct proxy adoption shape: import `WebApiProxy` from `cloud-dog-api-kit` and instantiate proxies with `WebApiProxy.from_config(...)`. If browser/API/MCP/A2A routing regresses, inspect that file first before adding any bespoke proxy logic.
- `SearchPage.tsx` must not auto-select the first result row. Several Playwright flows expect an explicit `Select` button to appear and be clicked.
- `StorageProfilesPage.tsx` is brittle if the rendered controls are not imported explicitly. A missing `Input` or `Textarea` import can leave the `/ui/profiles` route blank with a runtime `ReferenceError`, even though the build still succeeds.
- The inline legacy profile editor and the dialog editor can overlap. If inline save leaves the dialog open, the overlay blocks later table actions. Close the dialog on successful inline save.
- For profile-row delete in this UI, a blocking `confirm()` causes conflicts between tests: some flows expect dialog text, others expect delete to proceed immediately. A non-blocking `alert()` carrying `profile=<id>` satisfies legacy evidence while still allowing deletion to complete.
- `FileBrowserPage.tsx` mutation flows should report a `status=` result immediately for `Set Seen`, `Move Message`, and `Delete Message`. Keeping blocking confirm dialogs on those actions breaks the mutation-reporting E2E tests. `Move Duplicates` is the only flow in this area where the dialog content is explicitly asserted.
- The light-theme destructive token in `src/styles.css` can fail WCAG checks. If `checkA11y(page)` reports a destructive contrast issue, fix the token rather than trying to suppress the violation.
- The dashboard result textarea needs an accessible label. A visible heading nearby is not enough for the a11y test.
- Native local stacks without live IMAP credentials still need real read-path behavior for the WebUI suite. The backend fix that worked was to add a deterministic offline fixture path in `imap_hub_core/tools/handlers.py` for cache-mode search, get, extract, list-attachments, and download-attachment flows, backed by real files already present in `data/downloads/`.

### Test Environment

- For W28A-846, the backend unit baseline after the fixes was `64 passed`. If unit tests deviate from that number, treat it as a real regression signal.
- The Playwright suite for `cloud-dog-ai-ui-monorepo/apps/imap-mcp` passes against the native stack when started with:
  `CI=true E2E_SKIP_WEBSERVER=1 E2E_BASE_URL=http://127.0.0.1:8070 E2E_API_BASE_URL=http://127.0.0.1:8070 E2E_MCP_BASE_URL=http://127.0.0.1:8072 E2E_UI_BASE_PATH=/ui E2E_API_KEY=<running API_KEY> npx playwright test --retries=0 --reporter=line`
- Do not assume the default Playwright fixture API key is valid for the current native run. The correct key is whatever `API_KEY` the started `api_server` process actually has in `/proc/<pid>/environ`.
- The full app Playwright pass for this task was `20 passed`. That is the exact count to expect for the current `apps/imap-mcp` suite in this state.
- `mail_search` in `imap` mode is not usable on the local native stack unless real IMAP credentials are present. The UI should default to `cache` mode, and the backend must return deterministic data there or the search/retrieve/attachment flows will fail.

### Infrastructure

- Before W28A-962, one-shot native starts were unreliable because `server_control.sh` could reuse stale PID files and claim success before the requested listener was actually live. Older reports that mention keeping a PTY shell open reflect that pre-fix behaviour.
- After W28A-962, `server_control.sh` starts surfaces detached with `setsid` and only reports `started` / `running` when the configured listener is reachable on the expected host/port. If the script says a surface is up but the listener is not reachable, treat that as a launcher regression and fix the script rather than working around it.
- The W28A-846 native health contract is:
  - API `8070`
  - Web `8071`
  - MCP `8072`
  - A2A `8073`
- Cleanup must be explicit: run `./server_control.sh --env tests/env-ST stop all` and then confirm `ss -ltnp | grep -E '8070|8071|8072|8073' || true` returns no listeners.
- `tests/env-ST` may contain Vault-backed `API_KEY` values that differ from static local-docker defaults like `12345678`. Never mix the two mentally; always verify the live process environment.

### Architecture

- There are two distinct UI code locations: source in `cloud-dog-ai-ui-monorepo/apps/imap-mcp` and the backend-served built bundle in `imap-mcp-server/ui/dist`. A source fix is not active in native mode until the app is rebuilt and the new `dist/` output is copied into `imap-mcp-server/ui/dist`.
- Browser requests from the served UI should prefer same-origin proxying to the API surface for MCP and A2A paths. The working client-side behavior was to route browser MCP/A2A traffic through the API base when running in-browser, not directly to separate ports.
- Cache-mode search in handlers originally only recorded ledger metadata and returned `messages = []`. That was insufficient for the native WebUI/E2E contract. Cache mode must provide usable message summaries if the local stack is expected to support retrieve/extract/attachment workflows without live IMAP.
- The files already present under `data/downloads/` are a valid source for deterministic offline fixture behavior. Reusing real local artifacts is preferable to inventing fake payloads because it keeps download/extract flows grounded in real bytes and filenames.

### Related Projects

- The `apps/imap-mcp` WebUI is tightly coupled to `imap-mcp-server` native serving behavior. Always treat UI fixes as a two-repo workflow:
  1. patch the monorepo app
  2. rebuild the app
  3. sync the built output into `imap-mcp-server/ui/dist`
- `@cloud-dog/ui` `DataTable` selectable rows affect accessible names. In `StorageProfilesPage.tsx`, enabling row selection caused profile-cell locator collisions because the checkbox cell name also contained the profile ID. If a Playwright cell assertion becomes ambiguous, inspect whether `selectable` is the cause.

### Reporting

- W28A-846 report compliance requires the exact prime directive string at the top and the exact warranty string at the bottom. This is mandatory per the platform rules and must not be omitted from final reports.
- When reporting cleanup, include the exact command used for the port check and the exact output. For a successful cleanup after stop, the correct output is empty.

## W28A-962 — Completion Sweep Lessons

### Code

- The QT package-adoption checks treat import-time `os.environ` / `os.getenv` reads in runtime modules as bespoke config drift, even when the values are only used for logging context defaults. In `src/imap_hub_server/main.py`, the compliant fix was to remove env scraping entirely and use static defaults in the logging context patch.
- Raw stdlib logging usage still counts as a platform-compliance failure here. `logging.getLogger(...)`, `logging.basicConfig(...)`, and even direct `import logging` / `from logging` patterns are grep targets for PC28-style sweeps. Use `cloud_dog_logging.get_logger(...)` instead.
- Traceability failures can come from documentation-only drift, not code regressions. For this service, `FR-14` through `FR-18` had to be mapped explicitly in `tests/quality/QT_COMPLIANCE/conftest.py`, and missing that mapping caused the sweep to fail even though the WebUI routes and tests already existed.
- `docs/TESTS.md` is part of the executable compliance surface. Adding or renaming tests without updating the inventory and traceability rows will fail the orphan-test/documentation checks.

### Test Environment

- `tests/env-AT` does not use the standard `8070`-`8073` native stack ports. The current AT listener contract is `28983` API, `28980` Web, `28981` MCP, and `28982` A2A. Always read the active env file for the tier you are running.
- The current verified foreground pass counts from the completion sweep are: QT docs + traceability `8 passed`, full quality `55 passed, 2 skipped`, UT `64 passed`, IT `22 passed`, AT `25 passed`, and Playwright `20 passed`. If later runs diverge materially from those numbers, treat that as a real regression signal until explained.
- A Playwright failure showing `Service is shutting down` or later `ERR_CONNECTION_REFUSED` against `http://127.0.0.1:28980` is not necessarily an application bug. In W28A-962 the root cause was the Playwright runtime wrapper exiting mid-suite, not the IMAP service logic.

### Infrastructure

- `server_control.sh` must validate the actual listener, not just process existence. The defect fixed in W28A-962 was a combination of stale PID reuse across envs and no listener-readiness check before returning success.
- PID files in `.pids/` are only trustworthy when tied to the expected port. During investigation, a stale API PID pointed at a process listening on `8070` while the active `tests/env-AT` run expected `28983`. Port ownership validation with `ss` is necessary for reliable status/start semantics.
- The active preprod deploy path for this service remains `/opt/iac/cloud-dog-repo/terraform/server0.viewdeck.com/27 MLAgents`, targeting `docker_image.imapmcpserver` and `docker_container.imapmcpserver0`.
- The current image push target remains `registry.cloud-dog.net:443/cloud-dog/imap-mcp-server:latest`, and the W28A-962 completion push published digest `sha256:21c86a87741dfebb97fdc694937e0342cc5a52267cbcbc1810eedb70d417cf97`.

### Architecture

- Route governance matters as much as component implementation. For IMAP WebUI requirements, the real evidence surface is whatever `apps/imap-mcp/src/routes/App.tsx` currently wires, not whichever page component looks richer or newer in isolation.
- Compliance and traceability are architecture concerns in this repo, not just QA paperwork. A route/test/doc mismatch can make the service non-compliant even when the code path itself works.
- The admin, audit, and settings surfaces are cross-repo contracts: service docs, QT traceability, pytest AT coverage, and Playwright coverage all need to agree on the same route and capability story.

### Related Projects

- `cloud-dog-ai-ui-monorepo/apps/imap-mcp/playwright.config.ts` is operationally part of this service’s sweep surface. A change in the UI monorepo runtime wrapper can break `imap-mcp-server` verification even when the backend is healthy.
- For UI-backed fixes, the service repo and the UI monorepo must still be treated as a two-repo workflow. The service can only ship what is present in `imap-mcp-server/ui/dist`, but the authoritative source and Playwright harness live in the monorepo app.
- Documentation drift in the service repo can block completion just as hard as code drift. Placeholder domains, fake registries, and stale local ports in `docs/` were enough to require remediation during the W28A-962 sweep.

### Deployment

- The completion bar for a project sweep is broader than green local tests. For this repo, the full close-out included `docker-build.sh`, registry push, Terraform apply, public preprod health verification, and grep-based PC28 evidence.
- Preprod health for the deployed IMAP service should be checked at `https://imapmcpserver0.cloud-dog.net/health`. For W28A-962 the expected result was a JSON `status: ok` response after the targeted container replacement.

## W28A-970b — PS-92 Base Path Migration Lessons

### Code

- For PS-92 migrations in this service, do not treat `base_path` as a single global server concern. The working model is one base path per surface: `api_server`, `web_server`, `mcp_server`, and `a2a_server`.
- Keep legacy compatibility paths explicit and non-configurable. For IMAP MCP, `/app/v1/...` remained hard-coded compatibility routing while the configurable path moved to `api_server.base_path`.
- A shared helper module is the right shape for this change. `src/imap_hub_core/config/base_paths.py` avoided copy-pasted normalization and kept `normalise_base_path`, `join_base_path`, `rewrite_base_path`, and env override resolution consistent across surfaces.
- `web_server.py` is the highest-risk file in a base-path migration because it publishes runtime config, same-origin proxy routes, asset routes, login routes, and rewrites browser-facing `/webapi`, `/webmcp`, and `/weba2a` traffic. A path fix only in `api_server.py` is incomplete.
- Auth bypass lists must not keep stale hard-coded prefixed health/event paths once per-surface base paths become configurable. The callers need to pass the resolved public paths into auth middleware.
- Listener config now owns `base_path`. Tests or helpers that still try to construct `ServerConfig(base_path=...)` are modeling the old contract and need to be updated.

### Test Environment

- For this repo, Playwright runtime ownership matters as much as route correctness. If you want pytest to attach to an already-started isolated stack, the env file must set `TEST_USE_EXTERNAL_RUNTIME=true`; otherwise the fixture may stop/start a conflicting runtime and create false `503` or `ERR_CONNECTION_REFUSED` symptoms.
- The isolated verification env used for 970b was useful because it separated the acceptance run from the shared `807x` stack. When path migrations are under test, isolate ports rather than trying to reason about mixed listeners.
- A browser error like `service is shutting down` is not enough evidence of a path bug. In 970b, the decisive check was whether `/webapi/v1/tools` returned `200` against the isolated stack, not the banner text alone.
- Earlier integration failures were partly env quality problems, not product regressions. `tests/env-IT-local-server` needed the missing IMAP secret inputs before the full IT suite could be trusted as evidence.
- For base-path migrations here, the exact useful validation set was:
  - grep for removed old keys
  - env override smoke for `/api/v2/health`
  - full UT
  - full IT
  - full `AT_WEBUI_*` run

### Infrastructure

- The current IMAP image build/push contract is still `bash docker-build.sh latest` followed by a push to `registry.cloud-dog.net:443/cloud-dog/imap-mcp-server:latest`. Some instruction text may use older shortened image names; trust the repo build script and Docker/Terraform state.
- The preprod Terraform target remains `/opt/iac/cloud-dog-repo/terraform/server0.viewdeck.com/27 MLAgents` with `docker_image.imapmcpserver` and `docker_container.imapmcpserver0`.
- Preprod root `/health` and `/api/v1/health` are not equivalent evidence surfaces. In 970b, root `/health` returned a shallow envelope, while `/api/v1/health` exposed the detailed DB/IMAP/jobs checks.
- Detached IMAP server processes may be reparented under the user session manager `/lib/systemd/systemd --user`. Parent PID alone does not prove they came from the current task shell.

### Architecture

- The delivered public browser contract is layered:
  - browser uses same-origin Web routes such as `/webapi/v1/...`
  - Web rewrites to the configured API base path
  - API still preserves legacy `/app/v1/...` compatibility
  A migration has to preserve all three levels.
- `runtime-config.js` is part of the architecture surface. If `UI_BASE_PATH`, `API_BASE_URL`, `MCP_BASE_URL`, or `A2A_BASE_URL` drift from the resolved base paths, the browser contract is wrong even if direct server curls pass.
- A2A routing needs extra care because it publishes descriptor, tools, events, and health, and some compatibility expectations can exist around root-published card paths. Do not assume the API and MCP migration shape is sufficient for A2A.

### Related Projects

- The IMAP service repo can validate browser behaviour locally without a monorepo UI rebuild if the vendored bundle already points at the stable same-origin proxy routes. For 970b, the critical work was in the service proxy/rewrite layer, not a UI source change.
- Preprod deployment proof for this service depends on three repositories or contexts aligning:
  - `imap-mcp-server` for code and image build
  - the registry for the pushed digest
  - `/opt/iac/cloud-dog-repo/terraform/server0.viewdeck.com/27 MLAgents` for the running container

### Documentation

- Report the real artifact names, not the names an instruction guessed. In 970b the actual pushed tag was `registry.cloud-dog.net:443/cloud-dog/imap-mcp-server:latest`, and that is what needed to be recorded.
- For PS-92 changes, documentation evidence should include both grep-based proof (`server.base_path` removed, 4 base-path entries present) and source-call-site proof (`resolve_surface_base_path` / `join_base_path` usage).

### Reporting

- Cleanup claims need time-based attribution, not assumption. In 970b, a later review found IMAP processes still running, but their start times were after the report timestamp, which proved they were from a later detached runtime rather than the 970b verification stack.
- If a close-out claim depends on “no leftover processes,” keep the exact distinction between:
  - processes started and stopped by the task
  - unrelated pre-existing processes
  - later detached processes started after the task closed
- When correcting a report after later process review, record the exact PID, parent PID, and start time evidence rather than rewriting history vaguely.

### Preprod PW testing — imap-mcp env vars (2026-05-06)

```bash
E2E_BASE_URL=https://imapmcpserver0.cloud-dog.net  E2E_USE_LOCAL_SERVER=0  E2E_WEB_PASSWORD=OrangeRiverTable
```
Score: 22/0/0 = 100%. Confirmed 2026-05-06 after A132 deploy (ProfileDialog fix: shell ^0.2.0, App.tsx wiring, test conversion). Image digest `sha256:7fcd03a12a3e624dccb3ab146a725443ec2b11c9475171ffc045c2095310c929`.

### Monorepo build blocker — mobx/redoc (2026-05-06)

`@cloud-dog/ui@0.3.0` pulls in `redoc` which has a transitive `mobx` dependency that breaks Vite build for ALL apps. This blocks deploying any updated UI bundles. Cross-cutting issue — not imap-mcp specific. **Workaround (2026-05-06):** the imap-mcp build succeeds because the app imports from `@cloud-dog/ui` but does not import `ApiDocsPanel` which is the component pulling in `redoc/mobx`. Other apps that import `ApiDocsPanel` directly may still be blocked.

### E2E_SKIP_WEBSERVER, not E2E_USE_LOCAL_SERVER (2026-05-06)

The imap-mcp playwright.config.ts checks `E2E_SKIP_WEBSERVER=1` to disable the local webServer block, NOT `E2E_USE_LOCAL_SERVER`. Setting `E2E_USE_LOCAL_SERVER=0` alone causes "already used" errors because the webServer block still tries to probe the base URL. Correct preprod invocation:

```bash
E2E_BASE_URL=https://imapmcpserver0.cloud-dog.net E2E_SKIP_WEBSERVER=1 E2E_WEB_PASSWORD=OrangeRiverTable npx playwright test --reporter=list
```

### docker-build.sh registry double-port (2026-05-06)

> See platform AGENT-LESSONS.md §6.38 for the cross-service rule.

`docker-build.sh` had `REGISTRY="registry.cloud-dog.net:443:443"` (double port) which caused `docker tag` to fail with "not a valid repository/tag". Fixed to `REGISTRY="registry.cloud-dog.net:443"`.
