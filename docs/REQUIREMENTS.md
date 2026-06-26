---
template-id: T-REQ
template-version: 1.1
applies-to: docs/REQUIREMENTS.md
project: imap-mcp-server
doc-last-updated: 2026-06-23T00:00:00Z
doc-git-commit: 17916ccd7ef96daa5140d4892c792a5ea14a44ad
doc-git-branch: main
doc-age-policy: indefinite
doc-conformance-stamp: 2026-06-23T00:00:00Z
req-trace-version: 1.0
req-id-prefixes-used: [SV, BO, BR, FR, UC, CS, NF, CFG, R, F]
surface-coverage: [api, mcp, a2a, webui]
---

# Requirements — imap-mcp-server

## W28A-421 Review Status
- Reviewed for external/shareable publication during W28A-421.
- Source basis: `defaults.yaml`, 4 server source files, 56 discovered routes/endpoints, and 29 MCP tools.
- Internal-only absolute paths, environment-specific hosts, and private registries have been removed from this shareable document set.

**Version:** 1.1  
**Date:** 2026-02-28  
**Standards:** PS-00, PS-10, PS-20, PS-30, PS-40, PS-70, PS-80, PS-90, PS-95  
**Platform packages:** `cloud_dog_config`, `cloud_dog_logging`, `cloud_dog_api_kit`, `cloud_dog_idam`

---

## 1. Purpose

`imap-mcp-server` is an **API-first** service that provides controlled email retrieval, extraction, and mailbox operations through:
- MCP-compatible **A2A tools**,
- an **HTTP API** (canonical interface), and
- an **Admin WebUI** that is a strict client of the HTTP API.

The service supports multi-profile IMAP connectivity (Gmail/O365/generic), message and attachment processing, optional mutation controls, and audit-safe operational management.

---

## 2. Core Concepts

- **Profile**: Named mailbox configuration (`operations`, `security`, `customer-support`) with host, auth mode, folder policies, retention, and RBAC policy.
- **Mailbox scope**: Allowed folder set and mutation policy per profile.
- **Search ledger**: Canonicalised query tracking and high-water-mark baseline for delta search.
- **Audit event**: Append-only operation record with actor, operation, mailbox scope, status, and correlation ID.

---

## 3. Stakeholders & Actors

- **Agent/Client**: Calls MCP tools and/or HTTP API for mail search/retrieval flows.
- **Admin**: Manages profiles, RBAC, credentials, retention, diagnostics, and operational controls.
- **Operator**: Runs the service, validates health, monitors logs/audit trail.

---

## 4. Functional Requirements (FR)

### FR-01 Interfaces: MCP A2A + HTTP API + Admin WebUI
- SHALL expose MCP-compatible A2A tool catalogue and execution.
- SHALL expose HTTP API endpoints (via `cloud_dog_api_kit`) for all supported capabilities.
- HTTP API SHALL include structured error contracts, correlation IDs, and health/readiness endpoints per PS-20.
- WebUI SHALL call HTTP API only; no privileged bypass.
- Interface route-prefix contract SHALL be:
  - API canonical base path: `/api/v1`
  - MCP canonical base path: `/mcp`
  - Web canonical base path: `/`
  - A2A canonical base path: `/a2a`
- A legacy API prefix MAY be exposed only as a compatibility alias and MUST NOT be treated as canonical.

### FR-02 Configuration precedence and no hard-coded values
- SHALL use `cloud_dog_config` for all runtime configuration.
- Precedence SHALL be `os.environ -> .env -> config.yaml -> defaults.yaml -> Vault`.
- SHALL support secure secret loading via Vault and environment override.
- SHALL NOT hard-code credentials, endpoints, folder names, policies, or API keys.

### FR-03 Multi-profile mailbox management
- SHALL support runtime profile create/read/update/delete through admin APIs.
- Per-profile settings SHALL include host/port/TLS mode, auth mode, folder include/exclude, retention, and mutation policy.
- Profile changes SHALL be applied without code changes.

### FR-04 Authentication and authorisation
- SHALL use `cloud_dog_idam` for authentication (API key/JWT/enterprise providers).
- SHALL enforce RBAC over profile access and mutating operations.
- Roles SHALL include `reader`, `writer`, `maintainer`, `admin`.
- Admin-only operations SHALL be denied to non-admin roles with explicit error code.
- A2A health endpoint `/a2a/health` SHALL enforce authentication with the same API-key authority used by API auth.
- In strict local test mode, `/a2a/health` SHALL return `401` with no auth or wrong key, and `200` for `Authorisation: Bearer 12345678`.

### FR-05 Mail retrieval and extraction
- SHALL provide core operations: search, get message, extract content, list attachments, download attachments.
- SHALL support extraction outputs in JSON and Markdown forms.
- SHALL support stable output envelope with `ok`, `result`, `warnings`, `errors`, `meta`.

### FR-06 Optional mutation controls
- SHALL support optional move/delete/flag operations where enabled by profile policy.
- Mutation tools SHALL be disabled by default unless explicitly enabled.
- All mutation attempts SHALL be audit logged.

### FR-07 Search ledger and delta semantics
- SHALL canonicalise search input into deterministic ledger keys.
- SHALL support delta queries using high-water-mark baseline.
- SHALL store and return query metadata for traceability.

### FR-08 TLS and connection policy
- SHALL support SSL and STARTTLS modes.
- SHALL support custom CA bundle configuration and explicit opt-in self-signed mode.
- SHALL fail closed for invalid TLS policy.

### FR-09 Audit logging
- SHALL use `cloud_dog_logging` for structured operational and audit logs.
- SHALL emit audit events for all mutating operations and admin actions.
- Audit entries SHALL include timestamp UTC, actor, profile/folder scope, operation, status, and correlation ID.

### FR-10 WebUI operational scope
- WebUI SHALL expose controlled admin/operator screens for:
  - profile CRUD,
  - folder and retention policy configuration,
  - RBAC management,
  - diagnostics and connectivity checks,
  - audit and structured log viewing.
- WebUI SHALL expose controlled user flows for read/search/get/extract/download operations.
- WebUI SHALL not implement any UI-only business logic that bypasses API validation.

### FR-11 WebUI/API parity and CRUD completeness
- Every WebUI action SHALL map to a documented API endpoint and machine-readable error contract.
- Every mutating capability exposed in API/MCP SHALL have equivalent WebUI workflow (or explicit role-denied behaviour).
- Destructive actions SHALL require explicit confirmation and show affected scope before submit.

### FR-12 Index Reconciliation
- The server SHALL provide an `index_reconcile` tool that compares the local search ledger with remote IMAP mailbox state and reports discrepancies (new messages, deleted messages, modified flags).
- This capability SHALL enable clients to detect and repair ledger drift.
- Reference: `ARCHITECTURE.md` § Search Ledger.

### FR-13 Group Admin Delegation
- The system SHALL support a `group admin` role that can be assigned to any user within a group.
- A group admin SHALL be able to:
  - add and remove users within their group,
  - create API keys for users within their group,
  - modify profile access permissions for their group,
  - disable and enable users within their group.
- A group admin SHALL NOT be able to:
  - modify users or groups outside their own group,
  - access system-level admin functions,
  - promote other users to system admin.
- Traceability: E2E W28A-500 Steps 9-10.

### FR to Platform Standard Mapping
| Requirement | Primary standard(s) |
|---|---|
| `FR-01` | PS-20, PS-80 |
| `FR-02` | PS-10 |
| `FR-03` | PS-10, PS-80 |
| `FR-04` | PS-30 |
| `FR-05` | PS-20 |
| `FR-06` | PS-30, PS-40 |
| `FR-07` | PS-20, PS-95 |
| `FR-08` | PS-30 |
| `FR-09` | PS-40 |
| `FR-10` | PS-90 |
| `FR-11` | PS-20, PS-90 |
| `FR-12` | PS-20, PS-40 |
| `FR-13` | PS-30 |

### Database Abstraction Requirements (R-DB)
- R-DB-01: All database access MUST use `cloud_dog_db` engine/session/CRUD abstractions.
- R-DB-02: Engine creation MUST use `cloud_dog_db` engine factories.
- R-DB-03: Session management MUST use `cloud_dog_db.session.SyncSessionManager`/`AsyncSessionManager`.
- R-DB-04: Schema migrations MUST use `cloud_dog_db` migration runner.
- R-DB-05: Direct `sqlite3`/`create_engine()`/`sessionmaker()`/raw `Session()` are FORBIDDEN in application code.
- R-DB-06: DB health MUST use `cloud_dog_db.health.probe_database()`.
- R-DB-07: DB connection config MUST come from `cloud_dog_config`/Vault-backed env hierarchy.
- R-DB-08: Schema versioning MUST be tested across SQLite, MySQL, and PostgreSQL.
- R-DB-09: Schema upgrade/downgrade MUST be validated with at least two migrations per dialect.
- R-DB-10: CRUD outcomes MUST be consistent across SQLite, MySQL, and PostgreSQL.

---

## 5. Non-Functional Requirements (NFR)

- **Security**: secrets never logged; default-deny role posture; mailbox scope enforcement.
- **Reliability**: deterministic query normalisation; predictable delta behaviour; explicit timeout handling.
- **Observability**: structured logs and append-only audit logs with correlation IDs.
- **Usability**: WebUI provides explicit success/failure feedback and predictable operational workflows.
- **Accessibility**: WebUI targets WCAG 2.2 AA for keyboard usage, labels, focus order, and contrast.
- **Testing**: full UT/ST/IT/AT/QT coverage with mandatory `--env`; no silent fallback masking.

---

## 6. Tool Catalogue (minimum)

| Tool | Input model | Required fields | Output shape (result payload) |
|------|-------------|-----------------|-------------------------------|
| `mail_search` | `MailSearchInput` | `profile_id`, `mode`, `query`, `filters` | `search_id`, `similarity_key`, `canonical`, `high_water_mark`, `messages[]` |
| `mail_get_message` | `MailGetMessageInput` | `profile_id`, `uid`, `folder` | `profile_id`, `folder`, `uid`, `raw_eml` |
| `mail_extract_message` | `MailExtractMessageInput` | `profile_id`, `uid`, `folder`, `format` | `json` and/or `markdown` extracted content |
| `mail_list_attachments` | `MailListAttachmentsInput` | `profile_id`, `uid`, `folder` | `attachments[]` with `part_id`, `filename`, `content_type`, `size`, `size_bytes` |
| `mail_download_attachment` | `MailDownloadAttachmentInput` | `profile_id`, `uid`, `part_id`, `folder` | `filename`, `size_bytes`, `content_encoding`, `content`, `path` |

All tool responses MUST use the standard envelope with `ok`, `result`, `warnings`, `errors`, and `meta` fields.

---

## 7. Acceptance Criteria (examples)

1. Non-admin users cannot modify profile configuration or RBAC.
2. Search/get/extract/list/download flows work identically through MCP and API contracts.
3. Mutation operations are blocked when profile write policy is disabled.
4. WebUI can complete profile CRUD, diagnostics, and log/audit review using API-only calls.
5. Correlation IDs are visible from API responses through logs and audit entries.
6. WebUI displays API error code and status for failed operations without fallback masking.

---

## 8. Out of Scope (explicit)

- End-user email composition/sending workflows
- Direct browser-to-IMAP access
- Any UI behaviour that bypasses API validation and policy checks

## Configuration CRUD Requirements (CFG)

Profile concept for this project: mailbox profiles defining IMAP connectivity, auth mode, folder policy, retention, write controls, RBAC, and audit policy.

| ID | Requirement |
|----|-------------|
| CFG-01 | The system SHALL support creating a new mailbox profile via the API with all profile settings that would otherwise be available via environment variables or env-file configuration. |
| CFG-02 | The system SHALL support reading mailbox profiles via the API, including both list and detail retrieval. |
| CFG-03 | The system SHALL support updating an existing mailbox profile via the API. |
| CFG-04 | The system SHALL support deleting a mailbox profile via the API. |
| CFG-05 | Mailbox profile CRUD operations SHALL be available as MCP tools with equivalent functionality. |
| CFG-06 | Mailbox profile change events SHALL be broadcast via the A2A interface per **PS-72 §A2A-change-events** (canonical envelope `{type, topic, timestamp, payload}`; reference implementation `cloud_dog_api_kit.a2a.events` ≥0.11.0; see platform-standards `docs/standards/PS-72-agent-to-agent.md`). |
| CFG-07 | Mailbox profile CRUD operations SHALL be available in the WebUI with RBAC enforcement. |
| CFG-08 | The system SHALL support creating, reading, updating, and deleting users via the API. |
| CFG-09 | The system SHALL support creating, reading, updating, and deleting groups with role assignments via the API. |
| CFG-10 | The system SHALL support creating, listing, and revoking API keys with per-key capability scoping via the API. |
| CFG-11 | User, group, and API-key management SHALL be available via MCP, A2A, and WebUI with RBAC. |
| CFG-12 | All CRUD operations SHALL be audit logged with user identity, action, timestamp, and outcome. |
| CFG-13 | Only admin users SHALL be able to create, update, and delete mailbox profiles and manage users or groups; read-only access SHALL be available to authorised non-admin users. |


## W28A-883 PS-78 Cross-Platform File Handling Addendum

### Verified current state

- IMAP attachment handling exists through the MCP tools `mail_list_attachments` and `mail_download_attachment`.
- Downloaded attachment content can be returned as `text` or `base64`, and attachments are written into a `cloud_dog_storage` local downloads directory.
- No general `/files/upload`, `/files`, `DELETE /files/{id}`, or WebUI file surface was found.

### Required additions to satisfy PS-78

- Add a standard service file lifecycle API for operator-provided files and downloaded attachment artifacts.
- Add a standard API download path for stored attachment artifacts instead of relying only on tool envelopes.
- Add WebUI attachment/file browser and download surfaces.
- Add A2A file transfer conventions for attachment exchange and agent workflows.
- Add URI-source intake only where IMAP workflow policy explicitly allows it.

### Required PS-78 test plan

- API: upload operator-provided file, list stored artifacts, download, delete.
- MCP: list attachments, download attachment as text/base64, validate metadata.
- A2A: transfer an attachment artifact or file reference between agents.
- WebUI: browse attachments/files, download artifact, delete cached artifact.
- Mail workflow: seed a real attachment-bearing message, verify tool and API surfaces return consistent metadata and content.

## 9. W28A-897 WebUI Standards Merge

### Existing umbrella requirements

- `FR-10` remains the EXISTING umbrella requirement for WebUI operational scope.
- `FR-11` remains the EXISTING umbrella requirement for WebUI/API parity and CRUD completeness.
- `CFG-07` remains the EXISTING umbrella requirement for WebUI CRUD with RBAC enforcement.

### New page-level merge requirements

The following page-level requirements are NEW additions merged from PS-71 through PS-84 during W28A-897 Phase 1.

| Page | Route | Interaction family | Primary standards | Required components/patterns | Origin |
|---|---|---|---|---|---|
| DashboardPage | `/` | Shell/pane | PS-77, PS-76 | `DashboardLayout`, `ServiceStatusBar`, `HealthWidget`, `MetricCard`, `QuickActionBar`, `DataTable` | NEW |
| ProfilesPage | `/profiles` | List/detail | PS-77, PS-80, PS-71 | `DataTable`, `EntityDialog`, structured detail viewer, RBAC-aware CRUD | NEW |
| SearchRetrievePage | `/search-retrieve` | List/detail | PS-77, PS-79 | `SearchPanel`, governed results surface (`DataTable` or mailbox list/detail), loading/error states, keyboard search controls | NEW |
| FileBrowserPage mailbox workspace | canonical mailbox route required; current compatibility route is `/mutation-gating` | Tree/workspace | PS-77, PS-82 | `FolderTree`, `MessageList`, `MessageViewer`, attachment panel, mutation controls scoped to selected message(s) | NEW |
| LegacyLoginPage | `/login` | Shell/pane | PS-30, PS-77 | accessible sign-in form, explicit error state, no duplicate field semantics in long-term target | NEW |
| AdminUsersPage | `/admin/users` | List/detail | PS-71, PS-77 | `DataTable`, `EntityDialog`, bulk actions, status badges, group cross-links | NEW |
| AdminGroupsPage | `/admin/groups` | List/detail | PS-71, PS-77 | `AdminGroupsPage` shared pattern, `EntityDialog`, grouped membership management | NEW |
| AdminApiKeysPage | `/admin/api-keys` | List/detail | PS-71, PS-77 | `DataTable`, `EntityDialog`, bulk revoke, structured created-key display | NEW |
| AdminRbacPage | `/admin/rbac` | List/detail | PS-71, PS-77, PS-81 | shared RBAC page, `DataTable`, structured policy inspection for nested policy data | NEW |
| JobsPage | `/jobs` | List/detail | PS-76, PS-77, PS-81 | `DataTable`, `EntityDialog`, `MetricCard`, structured payload/result inspection | NEW |
| McpToolsPage | `/mcp-console` | Viewer/editor | PS-72, PS-77, PS-84 | `ToolBrowser`, `McpConsole`, governed viewer/editor surfaces for payload/result inspection | NEW |
| A2aConsolePage | `/a2a-console` | Viewer/editor | PS-72, PS-77 | `A2aConsole` with catalogue-backed tool selection and result surface | NEW |
| ApiDocsPage | `/api-docs` | Viewer/editor | PS-74, PS-77, PS-81 | `ApiDocsPanel`, governed MCP/A2A reference tabs, `DocumentViewer`, structured schema inspection | NEW |
| SettingsPage | `/settings` | Viewer/editor | PS-73, PS-77, PS-81, PS-84 | `SettingsPanel`, section cards, nested config inspection via `JsonExplorer`, governed import/export viewers/editors | NEW |
| DiagnosticsAuditPage | canonical structured audit route required | List/detail | PS-77, PS-40, PS-81 | `DataTable`, metrics panel, structured log/audit inspection, export controls | NEW |
| LegacyAdminControlPage | `/admin-control` | Shell/pane | PS-71, PS-72, PS-77 | compatibility-only parity surface; long-term target is replacement by split standard pages | NEW |
| LegacyDiagnosticsAuditPage | `/diagnostics-audit` | List/detail | PS-77, PS-40 | compatibility-only diagnostics trace surface; long-term target is replacement by the structured audit/log page | NEW |

### FR-14 WebUI page inventory and route contract

- The service SHALL maintain an explicit inventory of all WebUI pages, including both canonical routes and compatibility-only legacy routes.
- Every routed page SHALL declare a primary PS standard family and a primary CW-IF interaction family.
- Hidden or orphaned pages SHALL be treated as implementation drift until either routed or formally deprecated.

### FR-15 Mailbox workspace requirement

- The IMAP mailbox browsing surface SHALL align to the PS-82 MessageWorkspace pattern.
- The primary mailbox workspace SHALL provide:
  - folder hierarchy navigation,
  - mailbox/message list interaction,
  - message detail viewing,
  - attachment inspection and download,
  - mutation actions scoped to selected messages where policy allows.
- Message composition/sending remains OUT OF SCOPE for the current service unless the service requirements are separately expanded beyond IMAP retrieval and mutation.

### FR-16 Search page standard alignment

- The Search & Retrieve page SHALL align to PS-79.
- Search controls SHALL be defined as a governed search surface rather than a bespoke form wrapper.
- Search results SHALL remain coupled to message detail and attachment retrieval flows through a consistent list/detail interaction model.

### FR-17 Structured inspection and editor alignment

- Nested settings, policy, metadata, and result payloads deeper than two levels SHALL use `JsonExplorer` rather than `JsonBlock` alone.
- Read-only code/config/text surfaces SHALL use `CodeViewer` where plain text inspection is the primary interaction.
- Editable config/text surfaces SHALL use `CodeEditor` where multi-line editing is the primary interaction.

### FR-18 Legacy compatibility page governance

- `LegacyAdminControlPage` and `LegacyDiagnosticsAuditPage` SHALL be treated as compatibility surfaces, not the long-term canonical implementations.
- Where a standard split page exists for the same capability, the canonical route SHOULD point to the standard page and the legacy page SHOULD be deprecated after parity is verified.
- Compatibility pages SHALL not become the only routed implementation for capabilities that already have a governed standard page.

## PS-40 / W28A-619 Logging and Audit Requirements

The service MUST use `cloud_dog_logging` as the only application and audit logging implementation. Raw stdlib logging setup, direct `logging.getLogger()` calls, bespoke audit emitters, and print-based operational logging are not compliant except inside the platform logging package itself.

Every auditable event MUST emit a PS-40/NIST AU-3 audit record with: `event_type`, `action`, `timestamp`, `service`, `component`, `service_instance`, `environment`, `source_host`, `source_process`, `source_application`, `source_address` where available, `destination_address` where available, `outcome`, actor identity including user/service/system plus account/process/device identifiers where available, `target`, `process_id`, `affected_files` where relevant, `correlation_id`, `trace_id`, and `request_id`.

Auditable events MUST include authentication and authorisation decisions, user/group/API-key/RBAC changes, mailbox/message/attachment/search/audit/admin operations, MCP/A2A/API calls, job lifecycle changes, configuration changes, data access and mutation, denials, failures, and privileged operations. Secrets MUST be redacted before persistence. Tests MUST cover schema fields, event coverage, redaction, append-only audit persistence, retention/integrity, and WebUI observability rendering/filtering.

## 5. Cyber Security & Negative Flows

Mandatory schema per PS-REQ-TEST-TRACE v1.0 §3.4. Every project covers anon-denied, wrong-role-denied, missing-param-error per declared surface. The CS rows below are platform-baseline; project-specific extensions append in §5.1.

| ID | Threat / negative scenario | Surface | Role(s) attempted | Expected | Tests |
|---|---|---|---|---|---|
| `CS-001` | Anon attempts data read | `api`, `mcp`, `a2a`, `webui` | `anon` | `401` | (to be bound in Instruction 4 by operator) |
| `CS-002` | read-only attempts write | `api`, `mcp` | `read-only` | `403` | (to be bound in Instruction 4 by operator) |
| `CS-003` | Missing required param | `api` | `admin` | `422` | (to be bound in Instruction 4 by operator) |
| `CS-004` | Wrong-role privileged op | `mcp` | `read-write` | `403` | (to be bound in Instruction 4 by operator) |


<!-- W28C-1710b design-delta additions (2026-06-14T18:01:23Z); SHA chain in working/W28C-1710b/KNOWLEDGE-PRESERVATION-DELTA.md -->

## PS-REQ-TEST-TRACE schema completion (W28C-1710b)

Per the binding contract (`docs/standards/PS-REQ-TEST-TRACE.md` §2 + §3), every FR-NNN row in this file declares the following schema (default values; operator amends per row in W28C-1711):

```yaml
surface: ['api', 'mcp', 'a2a']  # programme default for imap-mcp-server
priority: must  # default; operator amends per FR
since: 2026-06-14  # carried forward unless older anchor known
last-verified: 2026-06-14
tests: []  # populated by W28C-1711 binding
crud: N/A  # default; operator amends per FR
```

## Baseline CS-NNN rows (PS-REQ-TEST-TRACE §3.4 — added by W28C-1710b)

Every project MUST have CS-NNN rows for `anon-denied`, `wrong-role-denied`, `missing-param-error` per surface. Programme baseline:

| CS-NNN | Scenario | Surface | Expected | Roles |
|---|---|---|---|---|
| `CS-005` | anon-denied | `api` | `401` | `anon` |
| `CS-006` | anon-denied | `mcp` | `401` | `anon` |
| `CS-007` | anon-denied | `a2a` | `401` | `anon` |
| `CS-008` | wrong-role-denied | `api` | `403` | `read-only` |
| `CS-009` | wrong-role-denied | `mcp` | `403` | `read-only` |
| `CS-010` | wrong-role-denied | `a2a` | `403` | `read-only` |
| `CS-011` | missing-param-error | `api` | `422` | `*` |
| `CS-012` | missing-param-error | `mcp` | `422` | `*` |
| `CS-013` | missing-param-error | `a2a` | `422` | `*` |

Each baseline CS-NNN row binds to one or more `@pytest.mark.negative` tests with an explicit expected denial code (bound in this lane — see `docs/REQ-COVERAGE.md`).

### 5.1 Project-specific negative flows (imap-mcp)

| ID | Threat / negative scenario | Surface | Role(s) attempted | Expected | Tests |
|---|---|---|---|---|---|
| `CS-014` | Stored credentials / secrets are written to application or audit logs, or returned to a non-admin caller | `api`, `mcp`, `a2a`, `internal` | `*` | secrets redacted / `***REDACTED***` | `test_QT1_1_SecretsNeverLogged`, `test_qt1_security_suite` |
| `CS-015` | Attachment download or archive path escapes the sandbox via path traversal | `api`, `mcp` | `read-write` | rejected / contained | `test_QT1_2_PathSandboxEnforced`, `test_qt1_security_suite` |


## 4.A Additional functional requirements (FR-19..FR-23 — capabilities present in `src/`)

These rows give explicit semantic FR-NNN cover to capabilities that exist in `src/` and were previously only reachable through the W28C-1711-R3 tier-bucket shims (now retired — see §4.C). Each is bound to its own per-capability tests via `@pytest.mark.req("FR-NN")`.

### FR-19 Managed asynchronous jobs
- SHALL run long-running operations (index rebuild, sweep, archive/export, sync) through the `cloud_dog_jobs` managed queue rather than bespoke threads.
- SHALL persist job state and support enqueue, claim, completion, failure-with-attempt-tracking, retry, and timeout recovery/requeue.
- SHALL expose a jobs admin API and report queue status including backend and per-job tracking.

### FR-20 Duplicate detection and sweep
- SHALL detect duplicate messages by Message-ID, content hash, and heuristic signal.
- SHALL apply a deterministic duplicate-selection policy when choosing the surviving message.
- SHALL support a duplicate-sweep workflow (with dry-run) that reports affected messages before any mutation.

### FR-21 Mail archive and export
- SHALL compute deterministic archive paths and write archived artefacts idempotently.
- SHALL provide a direct archive exporter and an archive/export end-to-end workflow.

### FR-22 Search and result caching layer
- SHALL support a cache-mode search path that stores and retrieves results without a live IMAP round-trip.
- SHALL use the platform cache package posture (no bespoke in-process cache) for cached search/result storage.

### FR-23 Database abstraction and multi-backend persistence
- SHALL use `cloud_dog_db` engine/session/CRUD abstractions for all persistence (search ledger, admin state, jobs).
- SHALL validate startup CRUD and schema migration across SQLite, MySQL, and PostgreSQL dialects (extends R-DB-01..R-DB-10).

## 4.B Consolidated Functional Requirements table (mandatory PS-REQ-TEST-TRACE §3.3 schema)

This is the canonical machine-readable FR table. `Since` is the short SHA at which each FR's semantic description was first published; `Tests` lists a representative bound test (full binding is enforced by `@pytest.mark.req(...)` and `docs/REQ-COVERAGE.md`).

| ID | Requirement | Surface | Priority | Since | Last-verified | Use cases | Tests |
|---|---|---|---|---|---|---|---|
| `FR-01` | Interfaces: MCP/A2A + HTTP API + Admin WebUI with health, error contracts, correlation IDs | `api`, `mcp`, `a2a`, `webui` | `must` | `17916cc` | `36d775d 2026-06-23` | `UC-001` | `IT1.1`, `IT1.5`, `IT1.6`, `UT1.27` |
| `FR-02` | Configuration precedence via `cloud_dog_config`; no hard-coded values; Vault-backed secrets | `internal`, `api` | `must` | `17916cc` | `36d775d 2026-06-23` | `UC-002` | `UT1.1`, `UT1.2`, `UT1.3`, `UT1.42` |
| `FR-03` | Multi-profile mailbox management (runtime CRUD, folder policy, retention, write policy) | `api`, `mcp`, `a2a`, `webui` | `must` | `17916cc` | `36d775d 2026-06-23` | `UC-003`, `UC-004` | `UT1.4`, `UT1.8`, `IT1.10`, `AT1.5` |
| `FR-04` | Authentication and authorisation via `cloud_dog_idam`; RBAC over profiles + mutating ops | `api`, `mcp`, `a2a`, `webui` | `must` | `17916cc` | `36d775d 2026-06-23` | `UC-005`, `UC-020` | `UT1.5`, `IT1.3`, `IT1.4`, `AT1.8` |
| `FR-05` | Mail retrieval and extraction (search, get, extract, list/download attachments) | `api`, `mcp` | `must` | `17916cc` | `36d775d 2026-06-23` | `UC-006`, `UC-007` | `UT1.19`, `UT1.20`, `IT1.12`, `AT1.1` |
| `FR-06` | Optional mutation controls (move/delete/flag), disabled by default, all attempts audited | `api`, `mcp` | `must` | `17916cc` | `36d775d 2026-06-23` | `UC-008` | `UT1.35`, `IT1.17`, `IT1.18`, `QT1.3` |
| `FR-07` | Search ledger and delta semantics (canonical keys, high-water-mark, query metadata) | `api`, `mcp`, `internal` | `must` | `17916cc` | `36d775d 2026-06-23` | `UC-009` | `UT1.11`, `UT1.12`, `ST1.9`, `IT1.9` |
| `FR-08` | TLS and connection policy (SSL/STARTTLS/XOAUTH2, CA bundle, fail-closed) | `internal` | `must` | `17916cc` | `36d775d 2026-06-23` | `UC-010` | `UT1.26`, `UT1.31`, `ST1.1`, `ST1.2` |
| `FR-09` | Audit logging via `cloud_dog_logging` (NIST AU-3 fields, redaction, append-only) | `api`, `mcp`, `a2a`, `internal` | `must` | `17916cc` | `36d775d 2026-06-23` | `UC-011` | `UT1.6`, `UT1.40`, `ST1.12`, `IT1.7` |
| `FR-10` | WebUI operational scope (admin/operator + user flows; API-only, no bypass) | `webui` | `must` | `17916cc` | `36d775d 2026-06-23` | `UC-012` | `AT_WEBUI_Login`, `AT_WEBUI_McpTools` |
| `FR-11` | WebUI/API parity and CRUD completeness; destructive-action confirmation | `webui`, `api` | `must` | `17916cc` | `36d775d 2026-06-23` | `UC-013` | `AT1.12`, `IT1.19`, `IT1.20`, `AT_WEBUI_ProfileCRUD` |
| `FR-12` | Index reconciliation tool (ledger vs remote drift report) | `api`, `mcp` | `should` | `17916cc` | `36d775d 2026-06-23` | `UC-014` | `UT1.22`, `UT1.29`, `IT1.8` |
| `FR-13` | Group-admin delegation (scoped membership, keys, profile access; no cross-group/system) | `api`, `mcp`, `webui` | `must` | `17916cc` | `36d775d 2026-06-23` | `UC-015`, `UC-021` | `test_st_group_admin_delegation`, `test_cascade_resolves` |
| `FR-14` | WebUI page inventory and route contract (canonical + compatibility routes declared) | `webui` | `should` | `17916cc` | `36d775d 2026-06-23` | `UC-016` | `AT_WEBUI_Dashboard`, `AT_WEBUI_AuditLog` |
| `FR-15` | Mailbox workspace (PS-82 MessageWorkspace: folder tree, list/detail, attachments, mutate) | `webui` | `should` | `17916cc` | `36d775d 2026-06-23` | `UC-017` | `AT_WEBUI_MailSearch` |
| `FR-16` | Search & Retrieve page standard alignment (PS-79 governed search surface) | `webui` | `should` | `17916cc` | `36d775d 2026-06-23` | `UC-017` | `AT_WEBUI_MailSearch` |
| `FR-17` | Structured inspection/editor alignment (`JsonExplorer`/`CodeViewer`/`CodeEditor`) | `webui` | `should` | `17916cc` | `36d775d 2026-06-23` | `UC-018` | `AT_WEBUI_Settings` |
| `FR-18` | Legacy compatibility page governance (compat-only; canonical split pages preferred) | `webui` | `may` | `17916cc` | `36d775d 2026-06-23` | `UC-016` | `AT_WEBUI_AuditLog` |
| `FR-19` | Managed asynchronous jobs via `cloud_dog_jobs` (enqueue/claim/complete/retry/recover) | `api`, `mcp`, `internal` | `must` | `36d775d` | `36d775d 2026-06-23` | `UC-019` | `UT1.25`, `UT1.39`, `UT1.41`, `ST1.11`, `IT1.21`, `IT1.22` |
| `FR-20` | Duplicate detection and sweep (message-id/content-hash/heuristic + selection policy) | `mcp`, `internal` | `should` | `36d775d` | `36d775d 2026-06-23` | `UC-022` | `UT1.15`, `UT1.16`, `ST1.10`, `AT1.3` |
| `FR-21` | Mail archive and export (deterministic path, idempotent write, exporter, workflow) | `mcp`, `internal` | `should` | `36d775d` | `36d775d 2026-06-23` | `UC-023` | `UT1.23`, `UT1.24`, `UT1.30`, `AT1.4` |
| `FR-22` | Search/result caching layer (cache-mode search, platform cache posture) | `mcp`, `internal` | `should` | `36d775d` | `36d775d 2026-06-23` | `UC-009` | `ST1.7`, `ST1.8`, `UT1.43` |
| `FR-23` | Database abstraction and multi-backend persistence via `cloud_dog_db` | `internal` | `must` | `36d775d` | `36d775d 2026-06-23` | `UC-024` | `UT1.34`, `ST1.14`, `IT1.16`, `AT1.9` |

## 4.C Retired mechanical bindings (W28C-1711-R3 tier-bucket shims — superseded by W28E-1803A)

The W28C-1711-R3 forensic pass introduced three-digit tier-bucket shim identifiers (FR-012 "legacy R2 / negative-auth", FR-013 "unit", FR-014 "application", FR-015 "system", FR-016 "smoke", FR-017 "integration", FR-018 "security") and bound every test to its tier rather than to the capability it exercises. Per PS-CLOSEOUT-WARRANTY §6 a tier-bucket stub is not an acceptable requirement. Those shim identifiers are **retired** in this lane: every test formerly bound to them is rebound to the semantic `FR-NN` / `NF-NNN` / `CS-NNN` row that describes its actual intent (see `docs/TESTS.md` §2 and `docs/REQ-COVERAGE.md`). The three-digit shim IDs retain their history here but carry no active test binding and are not part of the live requirement set.

## 6. Non-Functional Requirements (NF — verifiable posture)

The §5 narrative above states the non-functional intent; the rows below give it machine-checkable NF-NNN identifiers bound to the quality/compliance (`QT`) suites.

| ID | Requirement | Surface | Priority | Since | Tests |
|---|---|---|---|---|---|
| `NF-001` | Platform-package adoption — config/logging/api/auth/jobs/db/llm/vdb go through the `cloud_dog_*` packages; no bespoke replacements | `internal` | `must` | `36d775d` | `test_qt_package_adoption`, `test_package_compliance`, `test_qt_migration_completeness`, `test_qt27_bespoke_code_scan` |
| `NF-002` | Configuration and secret hygiene — no hard-coded URLs/credentials/hostnames; secrets in Vault expressions or scoped private env files; defaults/config carry no plaintext secrets | `internal` | `must` | `36d775d` | `test_qt_vault_config_contract`, `test_qt26_secrets_separation`, `test_qt_rules_compliance` |
| `NF-003` | Engineering discipline — no `skip`/mock in IT/AT tiers; file headers and function docstrings present | `internal` | `should` | `36d775d` | `test_qt_rules_compliance` |
| `NF-004` | Requirement↔test traceability and documentation completeness — unique test IDs, every REQ has a test, no orphan test files, UK-English public docs, LICENCE/README present | `internal` | `should` | `36d775d` | `test_qt_traceability`, `test_qt3_documentation_suite`, `test_QT1_4_UKEnglishCompliance` |
