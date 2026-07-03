---
template-id: T-RUC
template-version: 1.1
applies-to: docs/ROLES-AND-USECASES.md
registry: service
required: must-have
when-applicable: ""
template-last-updated: 2026-06-12
template-owner: public-standards

project: imap-mcp-server
doc-last-updated: 2026-06-23
doc-git-commit: 7683f39
doc-git-branch: main
doc-source-shas: []
doc-age-policy: 90d
doc-conformance-stamp: 2026-06-23T00:00:00Z
---

# imap-mcp-server — Roles & Use-Cases (b-3 traceability matrix)

**Lane:** W28A-750 (IDAM Thread-b, Sequence 10 — imap-mcp IDAM consumer).
**Method:** b-3 of the b-method (IDAM-B6 worked-example shape, instantiated for imap-mcp).
**Source basis (read in full, this lane):** `docs/REQUIREMENTS.md` (v1.1: FR-01..FR-18, CFG-01..CFG-13, R-DB, PS-40/PS-78 addenda) · in-code role vocabularies (`src/imap_hub_core/tools/tool_rbac.py`, `src/imap_hub_server/web_flat_roles.py`, `src/imap_hub_server/admin/state_models.py`, `state_idam.py`) · `docs/standards/82-access-control-session-test-matrix.md` (PS-82) · `docs/standards/83-canonical-role-catalog.md` (PS-83, W28A-740) · `IDAM-B2-IDENTITY-DOMAIN-WIRING-DESIGN-2026-06-10.md` (the keystone wiring, W28A-741, idam 0.5.0).
**Use-case text is lifted VERBATIM from `docs/REQUIREMENTS.md`.** Business roles are reconciled from code + CFG-13 + PS-82/PS-83 — not invented; where the source is silent it is recorded as a GAP (§6), not filled.

---

## 1. Entities + object model (extracted)

Two distinct object families exist in imap-mcp, and **they are not joined** today — this is the §6 G1 finding, and the W28A-741 `RBACBinding` resolver is the data path this lane wires in.

### 1.1 Identity family (JSON-snapshot store; `admin/state_models.py`, `state_idam.py`)
| Entity | Backing | Key fields (verbatim from model) | Relationships |
|---|---|---|---|
| **User** (`UserRecord`) | `AdminStateSnapshot.users` (JSON) | `user_id`, `username`, `email`, `display_name`, `status`, `role`, `is_system_user`, `tenant_id` | M:N → Group via `GroupRecord.members[]` |
| **Group** (`GroupRecord`) | `AdminStateSnapshot.groups` (JSON) | `group_id`, `name`, `description`, `roles[]`, `members[]`, `group_admins[]`, `tenant_id` | M:N → User (`members[]`); carries delegated `group_admins[]` (FR-13); **owns role assignment** (`roles[]`) |
| **ApiKey** (`APIKeyRecord`) | `AdminStateSnapshot.api_keys` (JSON) | `api_key_id`, `owner_user_id`, `key_prefix`, `key_hash`, `status`, `scopes[]`, `description`, `expires_at` | N:1 → User; carries capability `scopes[]` |
| **Role** | `cloud_dog_idam` `SqlAlchemyRoleStore` (`state_roles.py`) | `role_id`, `name`, `permissions[]` | referenced by name in `GroupRecord.roles[]` + `UserRecord.role` |
| **RBACBinding** *(NEW — W28A-750)* | `AdminStateSnapshot.bindings` (JSON) → `ImapBindingRepository.by_subject` | `binding_id`, `subject_type∈{user,group}`, `subject_id`, `project`, `resource_type`, `resource_id`, `permission`, `granted_by` | the group→resource edge consumed by the idam 0.5.0 resolver |

**Identity model shape:** `User —(GroupRecord.members)— Group —(roles[])— Role`; `ApiKey → User`. Engine hydrated at runtime from the snapshot via `sync_rbac_engine` (`state_idam.py:343`).

### 1.2 Domain family (the mailbox object model)
| Entity | Backing | Key fields / concept | Relationships |
|---|---|---|---|
| **MailboxProfile** (`ProfileConfig`) | `AdminStateSnapshot.profiles` + `config/models.py` | `provider` (gmail/o365/imap_generic), `imap` (host/port/security), `auth`, `credentials` (username/**password**), `sync`/`write`/`index`/`archive`/`search_ledger`, `allowed_groups[]` | 1 server hosts N profiles (FR-03/CFG-01); each has own scope/auth/policy (FR-03) |
| **MailboxScope** | inside profile (`sync.folders` include/exclude) | allowed folder set + mutation policy | constrains every mail op (FR-03/FR-06) |
| **Folder** | IMAP backend / include globs | a folder within scope | list/create/delete (RBAC `imap:folder:*`) |
| **Message** | IMAP backend (not a DB row) | a message UID within a folder | search/get/extract; mutation move/delete/flag (FR-05/FR-06) |
| **Attachment** | message part + `data/downloads/` | `part_id`, `filename`, `content_type`, `size_bytes` | list/download (FR-05; PS-78 addendum) |
| **SearchLedger** entry | `cloud_dog_db` (search ledger) | canonical query key + high-water-mark | delta search + `index_reconcile` (FR-07/FR-12) |
| **AuditEvent** | `cloud_dog_logging` (append-only) | AU-3 record: ts, actor, profile/folder scope, op, outcome, correlation_id | 1 per mutating/admin op (FR-09, PS-40) |
| **Job** (managed) | `cloud_dog_jobs` | long-running op lifecycle (e.g. index rebuild) | `/api/v1/jobs*` |

**Entity count: 12** — Identity: User, Group, ApiKey, Role, RBACBinding (5); Domain: MailboxProfile, MailboxScope, Folder, Message, Attachment, SearchLedger, AuditEvent, Job — primary domain **resource = MailboxProfile** (7 + scope).

### 1.3 The cascade primitive (the b-3 group cascade)
`GroupRecord.members[]` binds users to groups; `GroupRecord.roles[]` holds role names. The cascade the plan requires — **group-admin adds user to group → member inherits access to the group's mailbox profile** (FR-13 + CFG-09 + CFG-13) — is expressed by a `RBACBinding(subject_type=group, subject_id=G, resource_type=mailbox_profile, resource_id=P, permission=imap:mail:read)`. Adding a user to G grants that user read of profile P; removing revokes it. **W28A-750 wires this** via `AdminStateSnapshot.bindings` + `ImapBindingRepository` + `ImapMembershipResolver.groups_of` (over `state.groups_for_user`, `state_idam.py:375`) feeding `cloud_dog_idam.rbac.grants.authorise/allowed_resource_ids` (idam 0.5.0, W28A-741). Today the families are **DISJOINT** (G1) — `ProfileConfig.allowed_groups[]` is a coarse list, not an enforced resource binding.

---

## 2. Roles — reconciled catalog (central + imap business roles)

### 2.1 What the code actually defines (extracted; disagreements flagged)

**Three non-reconciled role/permission vocabularies exist in the code**, plus the REQUIREMENTS list:

| Source (file:line) | Vocabulary | Status |
|---|---|---|
| `docs/REQUIREMENTS.md` FR-04 | `reader` / `writer` / `maintainer` / `admin` | **REQUIREMENTS** (documentary) |
| `tools/tool_rbac.py:16-49` `_TOOL_PERMISSION_MAP` | permission strings `imap:mail:{read,write,delete}`, `imap:folder:{read,write,delete}`, `imap:index:{read,write}`, `imap:admin:*` | **LIVE** per-tool MCP gate |
| `web_flat_roles.py:99-134` `FLAT_ROLES` | `admin` (`*`) / `read-write` / `read-only` | **LIVE** flat WebUI login (W28A-735-R5), incl. read-only write-gate |
| `admin/state_models.py:66` `UserRecord.role` default `"viewer"`; `state_idam.py:409` maps `is_system_admin → admin/user` | `viewer` (default) / `admin` | **LIVE** user-record default |
| `docs/standards/83-canonical-role-catalog.md` (PS-83) | central `admin` / `group-admin` / `user` / `restricted` + `job-control` + `audit-log` grants | **CANONICAL** (W28A-740) |

**Disagreements / dated language found (flagged, not papered — §6):**
- **D1 — non-admin id drift:** REQUIREMENTS says `reader`/`writer`; live flat-login says `read-only`/`read-write`; `UserRecord` default is `viewer`; PS-83 canonical id is `user`. Four names for ~two concepts.
- **D2 — `maintainer` undefined:** FR-04 lists `maintainer` but no code path or permission set implements it. GAP.
- **D3 — no PS-82 §7.2 baseline grant via the resolver:** the live gate is flat `RBACEngine.has_permission(user, perm)` (`tool_rbac.py:54`); it does **not** consult `RBACBinding` rows (idam 0.5.0 resolver unused) → the cascade has no data path (G1). W28A-750 fixes this.
- **D4 — group-admin role:** FR-13 delegates `group_admins[]` on the group, but there is no central `group-admin` permission set; delegation is enforced ad-hoc. Reconcile to PS-83 `group-admin`.

### 2.2 The reconciled role catalog (ONE format)

**A. Common central roles (PS-83 §, owned by `cloud_dog_idam`; identical across all 9 services):**

| Role id | Intent | Baseline permissions (PS-82 §7.2 / PS-83) |
|---|---|---|
| `admin` | full control | `*` |
| `group-admin` | manages membership + resource bindings of owned group(s) | `idam.groups.write` (own), `idam.users.read`, manage `GroupRecord.members`/bindings for owned groups; **drives the cascade** (FR-13) |
| `user` | least-privilege self-service + in-scope read | `webui.access`, `mcp.access`, `a2a.access`, `apidocs.access`; self read/self-write; `apikeys.*_own`; `config.read` (masked); `logs.read` (own/service); `profiles.read`; `imap:mail:read` (in group-scope) |
| `restricted` | quarantined — below `user`; explicit grants only | none until bound |
| *grant* `job-control` | manage managed jobs | `jobs.read` + `jobs.control` |
| *grant* `audit-log` | read audit/log surfaces | `logs.read` (own/service); elevated `logs.read.all` |

**B. imap-mcp BUSINESS roles (extracted; reconciled to the central shape):**

| Role id | Source | Domain permissions | Maps to central |
|---|---|---|---|
| `admin` | flat-login `admin` (`*`); `UserRecord.role="admin"`; bootstrap admin (`state_idam.py:486`) | `imap:*`, `imap:admin:*`, profile/user/group/api-key CRUD (CFG-13) | = `admin` |
| `read-write` (≈REQUIREMENTS `writer`) | flat-login `read-write` (`web_flat_roles.py`); `imap:mail:write` path (`tool_rbac.py`) | `imap:mail:read`, `imap:folder:read`, `imap:index:read` + `imap:mail:write`/`imap:folder:write`/`imap:index:write`, `profile:write` | = `user` + write grant |
| `read-only` (≈REQUIREMENTS `reader`; `UserRecord` default `viewer`) | flat-login `read-only`; read-only write-gate (`web_server.py`); `tool_rbac` read perms | `imap:mail:read`, `imap:folder:read`, `imap:index:read` (read-only) | = `user` baseline (read-only) |
| `group-scoped` *(business cascade role)* | NEW — `RBACBinding(group:G → mailbox_profile:P)` | exactly profile P's `imap:mail:read`, nothing on other profiles | = `GROUPUSER` scoped to profile P (PS-82 §1) |
| `service` (machine) | api-key principal, MCP/A2A only | its key's `scopes[]` | = `SERVICE` |

**Role count: 11** — 6 central (admin, group-admin, user, restricted, +job-control, +audit-log) + 5 imap business (admin, read-write, read-only, group-scoped, service). Mapping: `admin→admin`, `read-write→user+write`, `read-only→user(read)`, `group-scoped→GROUPUSER`, `service→SERVICE`. (`maintainer` from FR-04 is unmapped — D2 GAP.)

> **Recommendation (W28A-750):** standardise the non-admin id on the live `read-only`/`read-write` flat roles (they are deployed and proven by W28A-735-R5); surface PS-83 `user`/`group-admin`/`restricted` as the canonical equivalence; make `GroupRecord.members` the cascade source and `RBACBinding(group:G→mailbox_profile:P)` the resource binding consumed by the idam 0.5.0 resolver; keep flat `RBACEngine.has_permission` as the surface-gate fallback (resolver `authorise` already falls back to it).

---

## 3. The b-3 traceability matrix (one row per use-case; use-cases VERBATIM)

`Req | Entity | Action | Use-case (verbatim from REQUIREMENTS.md) | Role | Surfaces | Test-IDs`

| Req | Entity | Action | Use-case (verbatim) | Role | Surfaces | Test-IDs |
|---|---|---|---|---|---|---|
| FR-05 | Message | R(search) | "SHALL provide core operations: search, get message, extract content, list attachments, download attachments." | read-only/read-write | MCP, API, A2A, WebUI(Search) | T0-IMAP-SEARCH, T3-IMAP-SEARCH |
| FR-05 | Message | R(get) | "search, get message, extract content…" | read-only | MCP, API, WebUI(Workspace) | T0-IMAP-GET, T3-IMAP-GET |
| FR-05 | Message | R(extract) | "SHALL support extraction outputs in JSON and Markdown forms." | read-only | MCP, API | T3-IMAP-EXTRACT |
| FR-05 | Attachment | R(list/download) | "list attachments, download attachments." | read-only | MCP, API, WebUI | T3-IMAP-ATTACH |
| FR-06 | Message | U/D(mutate) | "SHALL support optional move/delete/flag operations where enabled by profile policy. Mutation tools SHALL be disabled by default unless explicitly enabled." | read-write | MCP, API, WebUI(Workspace) | T2-IMAP-MUTATE-GATE, T3-IMAP-MUTATE |
| FR-06/FR-09 | AuditEvent | C | "All mutation attempts SHALL be audit logged." | (system) | all | T1-IMAP-AUDIT-COVERAGE |
| FR-07/FR-12 | SearchLedger | R | "SHALL canonicalise search input into deterministic ledger keys… delta queries using high-water-mark baseline." / "provide an `index_reconcile` tool that compares the local search ledger with remote IMAP mailbox state." | read-write | MCP, API | T3-IMAP-LEDGER, T3-IMAP-RECONCILE |
| FR-08 | MailboxProfile | gate | "SHALL fail closed for invalid TLS policy." | admin | (config) | T3-IMAP-TLS-FAILCLOSED |
| CFG-01 | MailboxProfile | C | "The system SHALL support creating a new mailbox profile via the API with all profile settings…" | admin | API, MCP(CFG-05), A2A(CFG-06), WebUI(CFG-07) | T3-IMAP-PROFILE-C, T2-PROFILE-ADMIN |
| CFG-02 | MailboxProfile | R | "The system SHALL support reading mailbox profiles via the API, including both list and detail retrieval." | admin / read-only(read) | API, MCP, WebUI(Profiles) | T3-IMAP-PROFILE-R |
| CFG-03 | MailboxProfile | U | "The system SHALL support updating an existing mailbox profile via the API." | admin | API, MCP, WebUI | T3-IMAP-PROFILE-U |
| CFG-04 | MailboxProfile | D | "The system SHALL support deleting a mailbox profile via the API." | admin | API, MCP, WebUI | T3-IMAP-PROFILE-D |
| CFG-08 | User | CRUD | "The system SHALL support creating, reading, updating, and deleting users via the API." | admin (CRUD); user (own read/self-write) | API, MCP(CFG-11), A2A, WebUI(AdminUsers) | T1-USERS-ADMIN, T1-USERS-OWNROW, T2-USERS-403 |
| CFG-09 | Group | CRUD | "The system SHALL support creating, reading, updating, and deleting groups with role assignments via the API." | admin / group-admin | API, MCP, A2A, WebUI(AdminGroups) | T1-GROUPS-ADMIN, T2-GROUPS-RO |
| CFG-10 | ApiKey | C/R/D | "The system SHALL support creating, listing, and revoking API keys with per-key capability scoping via the API." | admin (all); user (own) | API, MCP, A2A, WebUI(AdminApiKeys) | T1-KEYS-ADMIN, T1-KEYS-OWN, T2-KEYS-NOSECRET |
| **CFG-09 + CFG-13 + FR-13 (CASCADE)** | **Group+members+MailboxProfile** | **U(add member)→R(mail)** | **"…groups with role assignments…" (CFG-09) + "read-only access SHALL be available to authorised non-admin users." (CFG-13) + "A group admin SHALL be able to … modify profile access permissions for their group" (FR-13)** | **group-admin adds; member = group-scoped** | **API/MCP/A2A/WebUI** | **T3-IMAP-CASCADE** |
| CFG-12 | AuditEvent | C | "All CRUD operations SHALL be audit logged with user identity, action, timestamp, and outcome." | (system) | all | T1-IMAP-AUDIT-COVERAGE |
| CFG-13 | MailboxProfile/User/Group | gate | "Only admin users SHALL be able to create, update, and delete mailbox profiles and manage users or groups; read-only access SHALL be available to authorised non-admin users." | admin (write) / user (read) | all | T2-CFG13-ADMINONLY |
| FR-04 | (auth) | gate | "Admin-only operations SHALL be denied to non-admin roles with explicit error code." (default-deny) | ANON/non-admin | API/MCP/A2A/WebUI | T1-AUTH-401, T2-USERS-403, T0-NO-UNGUARDED-ROUTE |
| FR-04 | A2A health | gate | "A2A health endpoint `/a2a/health` SHALL enforce authentication… SHALL return `401` with no auth or wrong key, and `200` for `Authorisation: Bearer 12345678`." | ANON / SERVICE | A2A | T1-A2A-401 |
| FR-13 | User/Group | U | "A group admin SHALL be able to: add and remove users within their group, create API keys for users within their group, modify profile access permissions for their group… SHALL NOT … modify users or groups outside their own group." | group-admin | API/MCP/WebUI | T2-GROUPADMIN-SCOPE, T3-IMAP-CASCADE |
| CFG-13 / PS-82 §3.4 | MailboxProfile/Config | gate(mask) | "secrets never logged" (NFR) + "Only admin… non-admin read-only access" (CFG-13) → non-admin never sees stored secret on any surface | non-admin | API/MCP/A2A/WebUI | T2-SECRET-MASK |
| **806-tail (PORT_IN_THIS_LANE)** | **Config (effective)** | **R** | **PS-73 v2 Settings effective-config surface (`/admin/effective-config`) — resolved runtime config, secret-masked for non-admin** | **admin (full) / non-admin (masked)** | **API, WebUI(Settings)** | **T2-EFFCONFIG-MASK, T3-IMAP-EFFCONFIG** |
| PS-78 | Attachment/File | CRUD | "Add a standard service file lifecycle API… download path for stored attachment artifacts… WebUI attachment/file browser." | read-only(read)/read-write(write) | API, MCP, A2A, WebUI | T3-IMAP-FILES-REST *(PS-78 addendum — see §6 G-PS78)* |

**Matrix row count: 22** — covering FR-04..FR-13, CFG-01..CFG-13, the bolded **cascade row** (CFG-09+CFG-13+FR-13 → `T3-IMAP-CASCADE`), the FR-04 A2A-401 row, the secret-mask row, and the **806 effective-config PORT row**.

---

## 4. The T0–T3 test list (named; under `imap-mcp-server/tests/{smoke,e2e}/`)

> **Placement (PS-82 §4 / PS-95):** new access-control suites land under `tests/smoke/` (pytest) + `tests/e2e/` (Playwright), alongside existing tiers. **Neither `tests/smoke/` nor `tests/e2e/` exists today** (verified) — net-new for this lane. Existing RBAC unit/IT tests (`UT1.5_RBACPolicyEval`, `UT1.39_ProfileScopedToolAccess`, `UT1_42_NegativeAuthGate`, `IT1.4_APIRBACWriteGating`, `AT_WEBUI_RbacEnforcement`, `test_st_group_admin_delegation`) are kept and cross-referenced.

### T0 — smoke "does it work" (no 404s)
| ID | Asserts | Surface |
|---|---|---|
| `T0-IMAP-LIFECYCLE` | server start/stop/status via env file; `/health`,`/ready`,`/live` 200 | script/API |
| `T0-IMAP-SEARCH` / `T0-IMAP-GET` | `mail_search`/`mail_get_message` return content (FR-05) | MCP/API |
| `T0-NO-UNGUARDED-ROUTE` | every API/MCP/A2A route is guard-registered OR in `PUBLIC_ALLOWLIST` (IDAM-B2 §3.2 meta-test) | all |
| `T0-WEBUI-PAGES` | every FR-14 routed page renders 200, no 404, no console error | WebUI |

### T1 — common IDAM (PS-82 §3, §7.4 baseline)
| ID | Asserts | Surface |
|---|---|---|
| `T1-AUTH-401` | ANON → 401 on `/auth/me` + one gated endpoint per surface; never materialised to admin (PS-82 §3.1/§8.3) | API/MCP/A2A |
| `T1-A2A-401` | `GET /a2a/health` no-auth/wrong-key → 401; `Bearer 12345678` → 200 strict-local (FR-04) | A2A |
| `T1-WEBUI-401-LOGOUT` | 401/403 forces logout, no fake success | WebUI |
| `T1-BASELINE-USER` | freshly-seeded `read-only` user can load shell, open MCP/A2A console, read Settings(masked), read own logs/keys, read in-scope mail | all |
| `T1-USERS-ADMIN` / `T1-USERS-OWNROW` | admin CRUD any user; user sees only own row + self-write (CFG-08) | API/WebUI |
| `T1-GROUPS-ADMIN` | admin full CRUD groups + role assignment (CFG-09) | API/WebUI |
| `T1-KEYS-ADMIN` / `T1-KEYS-OWN` | admin manages all keys; user sees only own; create reveals once then masked (CFG-10) | API/WebUI |
| `T1-IMAP-AUDIT-COVERAGE` | every CRUD/mutation emits a PS-40 AU-3 record (CFG-12, FR-09) | all |

### T2 — RBAC-by-role (PS-82 §3, §8, §9.4)
| ID | Asserts | Surface |
|---|---|---|
| `T2-USERS-403` / `T2-GROUPS-RO` | non-admin → 403 on user/group write (PS-82 §3.2) | API/MCP/WebUI |
| `T2-CFG13-ADMINONLY` | only admin C/U/D profiles + manage users/groups; non-admin read-only (CFG-13) | API/MCP/WebUI |
| `T2-IMAP-MUTATE-GATE` | move/delete/flag blocked when profile `write.enabled=false` AND for read-only role (FR-06) | MCP/API |
| `T2-KEYS-NOSECRET` / `T2-SECRET-MASK` | non-admin never sees another principal's secret; profile/config secrets masked on every surface (PS-82 §3.4; IDAM-B2 §3.3) | API/MCP/A2A/WebUI |
| `T2-EFFCONFIG-MASK` | `/admin/effective-config` returns secret-masked payload for non-admin; cleartext for admin (806 PORT) | API/WebUI |
| `T2-GROUPADMIN-SCOPE` | group-admin manages only own group; cannot touch other groups/system admin (FR-13) | API/WebUI |
| `T2-PROXY-FORWARD` | non-admin admin op THROUGH WebUI proxy → 403; no service-admin-key substitution (PS-82 §8.3) | WebUI→API |
| `T2-SERVICE-SCOPE` | SERVICE key 200 in-scope / 403 out-of-scope; no WebUI session | MCP/A2A |

### T3 — project business use-cases + the GROUP CASCADE
| ID | Asserts | Surface |
|---|---|---|
| `T3-IMAP-SEARCH`/`GET`/`EXTRACT`/`ATTACH` | search/get/extract/list+download flows (FR-05) | MCP/API |
| `T3-IMAP-MUTATE` | move/delete/flag when policy enabled → audited (FR-06/FR-09) | MCP/API |
| `T3-IMAP-LEDGER`/`RECONCILE` | delta search ledger + `index_reconcile` drift report (FR-07/FR-12) | MCP/API |
| `T3-IMAP-PROFILE-{C,R,U,D}` | full profile CRUD via API/MCP/WebUI (CFG-01..04); A2A change-event (CFG-06) | all |
| `T3-IMAP-EFFCONFIG` | `/admin/effective-config` resolves runtime config (806 PORT); masked per role | API/WebUI |
| **`T3-IMAP-CASCADE`** | **group-admin adds `read-only` USER to group G (bound `RBACBinding group:G → mailbox_profile:P = imap:mail:read`) → that user can now `mail_search`/`mail_get` profile P but NOT profile Q, and NOT write; removing from G revokes it, live, no restart (CFG-09+CFG-13+FR-13, PS-82 §1 GROUPUSER, IDAM-B2 §4.3).** | **API/MCP/A2A/WebUI** |

---

## 5. Docs-harmonisation note (b-7)

imap-mcp `docs/` today (17 files) needs consolidation to the canonical PS-82/b-7 set: `REQUIREMENTS.md`, `ROLES-AND-USECASES.md` (this file), `ARCHITECTURE.md`, `API-REFERENCE.md`, `DATA-MODEL.md`, `TESTS.md`.

| Canonical doc | Built from | Action on current files |
|---|---|---|
| `REQUIREMENTS.md` | keep (v1.1) | KEEP — single source; de-date the W28A-421 banner |
| `ROLES-AND-USECASES.md` | **§2 + §3 of THIS doc** | CREATE (this file) — folds in `ROLES-AND-USECASES.md` |
| `ARCHITECTURE.md` | keep | KEEP — correct role refs to the §2.2 reconciled catalog |
| `API-REFERENCE.md` | merge | MERGE `API-REFERENCE.md` + `API-REFERENCE.md` + `MCP-REFERENCE.md` + `openapi.json` ref |
| `DATA-MODEL.md` | **§1 of THIS doc** + ARCHITECTURE ER | CREATE |
| `TESTS.md` | keep + add **§4 T0-T3** | KEEP, extend with the access-control matrix suite |

**Archive (dated, never deleted):** `API-REFERENCE.md`, `API-REFERENCE.md`, `MCP-REFERENCE.md`, `ROLES-AND-USECASES.md`, `PARAMETERS.md`, `ENV-REFERENCE.md`, `AUDIT-EVENTS.md`, `BUILD.md`, `DEPLOY.md`, `DOCKER.md`, `PREPROD.md`, `TASKS.md`, `NORMALISED_QUERY.md`.

**Dated/wrong language found (correct on move):** REQUIREMENTS `W28A-421 Review Status` + `Version 1.1 • 2026-02-28` banner; FR-04 role names (`reader/writer/maintainer`) vs live `read-only/read-write` (align per §2 D1/D2).

---

## 6. GAPS (for coordinator/user — NOT papered over)

- **G1 — identity and domain models are disjoint.** `UserRecord`/`GroupRecord` (identity) and `ProfileConfig` (domain) share no enforced binding; `ProfileConfig.allowed_groups[]` is a coarse list never consulted by the live `RBACEngine.has_permission` gate. The cascade has **no data path today**. **W28A-750 closes this** by wiring the idam 0.5.0 `RBACBinding` resolver (the keystone, W28A-741). THE central deliverable of this lane.
- **G2 — three+ non-reconciled non-admin role ids** (`reader`/`writer` REQUIREMENTS vs `read-only`/`read-write` live vs `viewer` default vs `user` PS-83). Reconciled in §2.2; D1.
- **G3 — `maintainer` (FR-04) is undefined** — no permission set, no code path. D2. Recommend dropping from REQUIREMENTS or mapping to `read-write`+`job-control`.
- **G4 — resolver unused.** idam 0.5.0 `effective_grants`/`authorise`/`allowed_resource_ids`/`guard_registry`/`secret_masking` are NOT imported in imap `src/` (pin is `>=0.4.3`). W28A-750 adopts them (pin `>=0.5.0`).
- **G5 — no central secret-masking on egress.** Profile/config reads can leak `credentials.password`/tokens to non-admin. W28A-750 adds `mask_secrets` on the egress path (incl. the 806 `/admin/effective-config`).
- **G6 — A2A `/a2a/health` auth must be verified.** FR-04 mandates anon→401, `Bearer 12345678`→200 strict-local. (imap's MCP gate was fixed in W28A-735-R5; this lane re-verifies A2A per FR-04 — the imap analog of file-mcp F-741-1.)
- **G7 — no access-control test suites.** No `tests/smoke/` or `tests/e2e/` access-control matrix; the entire T0-T3 suite (§4) is net-new (existing RBAC tests are unit/IT, kept + cross-referenced).
- **G-PS78 — PS-78 file lifecycle** (FR REQUIREMENTS addendum) is broader than this IDAM lane; `T3-IMAP-FILES-REST` is recorded but PS-78 file-surface delivery is tracked separately (W28A-883 family), not this lane's IDAM scope.
- **G-806 — PORT_IN_THIS_LANE (Gate 0C):** `/admin/effective-config` (PS-73 v2 Settings) from branch `w28a-806-settings-imap-mcp` is ported into this lane, secret-masked; `auth_mode` is already on main (W28A-735-R5) so only the effective-config endpoint + UI consumer are ported (no widening into other settings/UI work).

---

## 7. b-5 — UI justification (every WebUI page → use-case + role; no orphan page)

Per PS-82 §9.4 the WebUI is a strict client of the HTTP API (FR-10/FR-11). Every routed page (FR-14 inventory) maps to a use-case + role; no orphan pages. RBAC is enforced by the BACKEND guard (the WebUI proxy forwards the session principal; no WebUI-side authz decision).

| Page (route) | Use-case (matrix §3) | Role(s) | API/MCP backing | Cascade-aware |
|---|---|---|---|---|
| DashboardPage `/` | service status/health overview | any authenticated | `/health`, `/admin/jobs/queue/status` | — |
| ProfilesPage `/profiles` | CFG-01..04 profile CRUD | admin (CUD) / read-only (R) | `/api/v1/profiles*`, `profile_*` MCP | **yes — list scoped by `allowed_resource_ids` (GROUPUSER sees only bound profiles)** |
| SearchRetrievePage `/search-retrieve` | FR-05 search/get/extract | read-only/read-write | `mail_search`/`mail_get_message`/… | **yes — point check `authorise(mailbox_profile:P)`** |
| FileBrowserPage (mailbox workspace) | FR-05/FR-06 read + mutate | read-only (R) / read-write (mutate) | mail read + move/delete/flag | **yes** + `write.enabled` gate |
| AdminUsersPage `/admin/users` | CFG-08 user CRUD | admin (all) / user (own row) | `/api/v1/admin/users*` | — |
| AdminGroupsPage `/admin/groups` | CFG-09 group CRUD + membership | admin / group-admin (own) | `/api/v1/admin/groups*` | drives the cascade (membership) |
| AdminApiKeysPage `/admin/api-keys` | CFG-10 key CRUD | admin (all) / user (own) | `/api/v1/admin/api-keys*` | secret reveal-once |
| AdminRbacPage `/admin/rbac` | RBAC + bindings inspection | admin | role/binding surfaces | shows `RBACBinding` rows |
| SettingsPage `/settings` | PS-73 v2 effective config | admin only | **`/admin/effective-config`** (secret-masked) | secret-masked egress (GATE-3) |
| McpToolsPage `/mcp-console` | PS-72 MCP console | per-tool RBAC | `/mcp` | tool gate (cascade) |
| A2aConsolePage `/a2a-console` | PS-72 A2A console | SERVICE/api-key | `/a2a/*` (auth; `/a2a/health`→401 anon) | — |
| ApiDocsPage `/api-docs` | PS-74 API reference | any authenticated | openapi | — |
| JobsPage `/jobs` | PS-76 job control | job-control/admin | `/api/v1/admin/jobs*` | — |
| DiagnosticsAuditPage / AuditLogPage | FR-09/PS-40 audit view | audit-log/admin | `/api/v1/admin/logs` | — |
| LegacyLoginPage `/login` | flat login (admin/read-write/read-only) | ANON→authenticated | `/auth/login` | — |

**No orphan page:** every FR-14 routed page above maps to a matrix use-case + role. Legacy compatibility pages (`/admin-control`, `/diagnostics-audit`, `/mutation-gating`) are governed by FR-18 (compatibility-only; canonical split pages preferred). WebUI↔API parity holds (FR-11): each mutating page action has an API endpoint; non-admin write attempts are denied 403 by the backend (read-only write-gate + RBAC).



<!-- W28C-1710a recovery: full content from archive/2026-06-12/USE_CASES.md (archived sha256=056908ba7524, 15 lines) -->

## Recovered domain content — `archive/2026-06-12/USE_CASES.md` (15 lines)

_This section carries forward the full content of the archived predecessor doc verbatim. Topic checklist + SHA256 chain in `public release checklist/working/evidence/W28C-1710a/per-doc/imap-mcp-server/USE_CASES.md.topics.tsv`. Archive contents are unchanged (sha256 stable)._

# IMAP MCP Use Cases

## UC-CFG-01 New SPAM Analysis Profile

1. Clone an existing mailbox profile into a new SPAM-focused profile.
2. Update folder policy to target the SPAM folder and set retention/search limits.
3. Verify the new profile is visible through admin profile endpoints.
4. Use MCP tools to search and retrieve messages with the new profile.
5. Update the profile retention or folder policy and re-run the search flow.
6. Delete the profile and confirm subsequent reads return `404`.

Current status:
- API admin profile lifecycle is delivered.
- MCP and WebUI admin flows are substantially delivered.
- User/group/API-key CRUD remains out of scope for the current product surface.


<!-- W28C-1710b design-delta additions (2026-06-14T18:01:23Z) -->

## Cross-surface UC mappings (W28C-1710b)

Per T-RUC v1.1 + PS-REQ-TEST-TRACE §3.5, every UC-NNN maps to one OR MORE FR-NNN across surfaces.

This service's surface set: **api, mcp, a2a**.

Detailed UC-by-UC operator-review pass + per-FR cross-surface mapping deferred to W28C-1711. The cross-surface declarations are enabled here.

```yaml
# Schema for every UC-NNN (default; operator amends per UC):
surfaces: ['api', 'mcp', 'a2a']
roles: [admin, read-write, read-only, anon]
FR-mapping: []  # populated by W28C-1711
```

---

## 8. Canonical Use-Case Inventory (UC-NNN) — W28E-1803A

This is the canonical, machine-readable use-case inventory (PS-REQ-TEST-TRACE §2/§3.5). Each UC names its primary actor, goal, surfaces, and the FR/CS rows it drives. The narrative b-3 matrix in §3 remains the detailed cross-surface view; these UC-NNN rows are the stable identifiers Stream-B and Stream-C bind their tests and pages against.

Actors: `admin`, `group-admin`, `read-write`, `read-only`, `anon`, `service` (machine api-key principal).

| UC | Actor(s) | Goal | Surfaces | Requirements |
|---|---|---|---|---|
| `UC-001` | any authenticated | Discover and call the service across MCP/A2A/HTTP API with health, error contracts, and correlation IDs | api, mcp, a2a, webui | `FR-01` |
| `UC-002` | admin / operator | Run the service with layered configuration and Vault-backed secrets and no hard-coded values | internal, api | `FR-02` |
| `UC-003` | admin | Create a new mailbox profile (connection, folder policy, retention, write policy) at runtime | api, mcp, webui | `FR-03`, `CFG-01` |
| `UC-004` | admin | Read, update, and delete an existing mailbox profile through its full lifecycle | api, mcp, webui | `FR-03`, `CFG-02`, `CFG-03`, `CFG-04` |
| `UC-005` | admin / read-write / read-only | Authenticate (API key/JWT) and have RBAC enforced over profiles and mutating operations | api, mcp, a2a, webui | `FR-04` |
| `UC-006` | read-only / read-write | Search a mailbox and get a specific message through MCP or the API | api, mcp | `FR-05` |
| `UC-007` | read-only / read-write | Extract message content and list/download attachments | api, mcp | `FR-05` |
| `UC-008` | read-write | Move, delete, or flag messages where the profile write policy enables it (audited) | api, mcp | `FR-06` |
| `UC-009` | read-write | Run a delta search using the canonical ledger and high-water-mark, served from cache when possible | api, mcp | `FR-07`, `FR-22` |
| `UC-010` | admin | Configure TLS/STARTTLS/XOAUTH2 connection policy that fails closed on invalid settings | internal | `FR-08` |
| `UC-011` | system | Emit an append-only NIST AU-3 audit record (with redaction and correlation ID) for every mutating/admin operation | api, mcp, a2a | `FR-09`, `CFG-12` |
| `UC-012` | admin / operator / read-only | Operate the service through the Admin WebUI, which is a strict API client | webui | `FR-10` |
| `UC-013` | admin | Complete every CRUD action in the WebUI with API parity and destructive-action confirmation | webui, api | `FR-11`, `CFG-07` |
| `UC-014` | read-write | Reconcile the local search ledger against remote IMAP state and obtain a drift report | api, mcp | `FR-12` |
| `UC-015` | group-admin | Manage membership, keys, and profile access for an owned group (delegated administration) | api, mcp, webui | `FR-13`, `CFG-09`, `CFG-13` |
| `UC-016` | admin | Enumerate every WebUI page from the governed route inventory, including compatibility routes | webui | `FR-14`, `FR-18` |
| `UC-017` | read-only / read-write | Browse the mailbox workspace and the Search & Retrieve page (folder tree, list/detail, attachments) | webui | `FR-15`, `FR-16` |
| `UC-018` | admin | Inspect nested settings/policy/result payloads with the structured viewer/editor surfaces | webui | `FR-17` |
| `UC-019` | admin / system | Enqueue, track, retry, and recover long-running managed jobs via the platform queue | api, mcp | `FR-19` |
| `UC-020` | anon | Be denied (401/403) on principal, data, and admin surfaces without credentials | api, mcp, a2a, webui | `FR-04`, `CS-001`, `CS-005`, `CS-006`, `CS-007` |
| `UC-021` | read-only | Be denied (403) when attempting a privileged or out-of-group operation | api, mcp, webui | `CS-002`, `CS-004`, `CS-008`, `CS-009`, `CS-010` |
| `UC-022` | read-write | Detect and sweep duplicate messages (message-id/content-hash/heuristic) with a dry-run preview | mcp | `FR-20` |
| `UC-023` | read-write / system | Archive and export mailbox content to deterministic, idempotent artefact paths | mcp | `FR-21` |
| `UC-024` | admin / system | Persist ledger, admin state, and jobs through the database abstraction across SQLite/MySQL/PostgreSQL | internal | `FR-23`, `CFG-08` |

**UC count: 24** — covering every FR (FR-01..FR-23) and the negative-flow CS rows, mapped to the admin / group-admin / read-write / read-only / anon / service actor set.
