---
template-id: T-RUL
template-version: 1.0
applies-to: RULES.md
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

# imap-mcp-server — RULES.md

## Common Rules

This project follows the [Cloud-Dog AI Platform Common Rules](../cloud-dog-ai-platform-standards/RULES.md) v2.7+.
Common rules are NOT restated here; consult central for: integrity (§1), environment+config (§2),
server+process management (§3), code+change management (§4), testing (§5), documentation (§6),
repo structure (§7), operational controls (§8), security boundaries (§9), infrastructure
protection (§10), Vault path verification (§11), implementation truthfulness (§12),
sandbox dispatch preconditions (§13, W28A-882 Phase F), completion standards (§14), mandatory reading (§15).

Cross-cutting incident records relevant to this service (see central RULES.md for the full text):
- §1.1 Falsification — IMAP/SMTP/OAuth evidence, cache/index claims, report claims
- §1.3 Fabrication — mailbox hosts, OAuth provider settings, scope roots, port assignments
- §1.4 Config workaround — this repository was named in the original incident; never bypass `cloud_dog_config` or Vault resolution here
- §1.5 Production firewall — any Docker/Terraform deployment or remote validation involving this service

## Project-Specific Rules

### Vault sections used by this project
Load before any operation:
```bash
set -a; source /opt/iac/Development/cloud-dog-ai/env-vault; set +a
```
Validate access: `bash scripts/validate-vault.sh`

Vault sections consumed:
- `dev.databases` — PostgreSQL/SQLite connection for cache DB
- `dev.email` — IMAP/SMTP credentials (transitional; OAuth tokens stored encrypted locally)
- `dev.vdbs` — Vector database connections (for optional managed indexing)
- `dev.repository` — PyPI/NPM registry credentials

### Credential storage layout (service-specific)
Standard test env files (committed, non-secret) — hosts, ports, folder names, feature flags only:
- `tests/env-UT` — unit test config
- `tests/env-ST` — system test config
- `tests/env-IT` — integration test config
- `tests/env-AT` — application test config
- `tests/env-QT` — quality/security test config

Private env files (ONLY if credentials not yet in Vault):
- `private/env-<name>-secrets` — credentials (IMAP passwords, OAuth tokens, API keys)
- `private/env-<name>-google-secrets` — Google OAuth client ID/secret (if not in Vault)
- `private/env-<name>-microsoft-secrets` — Microsoft OAuth client ID/secret (if not in Vault)

`private/` is NOT required by default — if all credentials are in Vault, tests only need `tests/env-<TIER>` + sourcing `env-vault`.

Additional service-specific credential rules (binding on top of central §2.3):
- OAuth tokens MUST be stored encrypted at rest in the profile credential store
- CA bundles and certificates may live in `certs/` (non-secret, committable)

### Package pinning (W28A-846)
The active `cloud-dog-api-kit` pin for this service is `==0.12.1` in `pyproject.toml`. The published package already exposes `WebApiProxy` and the MCP/A2A transport surfaces — do not edit `cloud_dog_api_kit/` locally to add proxy features; install the published package and use it. (The historical W28A-846 reference to `0.4.1` was correct at that time but is no longer the active pin.)

### Port assignments and AT-tier exception (central §4.4 carve-out)
Verified against [tests/env-ST](/opt/iac/Development/cloud-dog-ai/imap-mcp-server/tests/env-ST):
- API server: `8070`
- Web server: `8071`
- MCP server: `8072`
- A2A server: `8073`

Local-AT exception: `tests/env-AT` runs the native AT stack on a non-standard port band: `28983` API, `28980` Web, `28981` MCP, `28982` A2A. This deviates from the central §4.4 8070-series allocation; treat the active env file as authoritative for the tier you are running. Older cross-project tables still mentioning `8050-8053` are stale — ignore them for imap-mcp work.

### Library / server separation
- `imap_hub_core/` MUST NOT import FastAPI, uvicorn, or MCP transport code
- `imap_hub_server/` MUST NOT contain IMAP/cache/search logic beyond dispatch and auth
- All domain logic MUST be testable without starting a server

### IMAP safety
- NEVER store raw IMAP passwords in plain text; use the encrypted credential store
- OAuth tokens MUST be refreshed automatically; never expose refresh tokens in logs
- IMAP connections MUST respect TLS policy per profile (no downgrade attacks)
- Self-signed certificates require explicit `allow_self_signed: true` per profile
- NEVER delete messages from an IMAP server unless the operation is explicitly requested by the caller AND the calling principal holds the matching RBAC permission AND `write.enabled=true` for the profile

### Write operations
- All write operations (move/delete/flags) require `write.enabled=true` AND RBAC permission
- Write operations MUST be idempotent where possible
- All mutations MUST be audit-logged

### Cache integrity
- Cache is source-of-truth for derived capabilities (index, archive metadata)
- Managed index is a derivative view reconciled from cache state
- Retention enforcement MUST cascade: cache → blobs → index → ledger
- The offline read path / mailbox cache-mode `offline` fixtures must be exercised whenever cache invariants are touched; fixture parity with online reads is a binding correctness check (W28A-846)

### MailboxWorkspacePage folder tree
`MailboxWorkspacePage` is a real page, but its folder tree is built from profile config include globs plus defaults — it is NOT backed by a real IMAP folder-list contract. Treat the include globs as authoritative for folder presentation; do not assume server-side LIST results match what the UI shows.

### AU-3 audit display rules
The IMAP WebUI log/audit surfaces depend on the backend exposing normalized multi-source rows from `/api/v1/admin/logs`. The UI cannot meet AU-3 display requirements if the backend only returns message text. Audit row payloads must already contain the AU-3 fields (event_type, actor, target, outcome, timestamps, correlation IDs); the shared `@cloud-dog/ui` `DataTable` handles presentation once column defaults are seeded into `localStorage`.

### PS-92 base path migration (W28A-970b)
See central [AGENT-LESSONS.md §6.37](../cloud-dog-ai-platform-standards/AGENT-LESSONS.md) for the cross-platform PS-92 Traefik `stripPrefix` migration lesson. This service was one of the original W28A-970b adopters; follow the central guidance for any further base-path / proxy-stripping work here.

### Testing (project-specific extensions)
Platform testing rules (central §5) apply in full. Local extensions:
- Integration tests require a real IMAP server and a running API server
- NEVER mock IMAP operations in ST/IT/AT tests
- See TESTS.md for the complete test plan

## Incident Records

### W28A-846 — Native Playwright / WebApiProxy / Offline Read Path
- Backend unit baseline after the W28A-846 fixes was `64 passed`. Deviations from this number are a real regression signal, not noise.
- W28A-846 introduced the native health contract used by all subsequent native AT runs (see AGENT-LESSONS.md §W28A-846 for the full contract).
- W28A-846 report compliance requires the exact prime-directive string at the top and the exact warranty string at the bottom of final reports.

### W28A-962 — Completion Sweep
- Before W28A-962, one-shot native starts were unreliable because `server_control.sh` could reuse stale PID files and report `started` before the requested listener was actually live.
- After W28A-962, `server_control.sh` starts surfaces detached with `setsid` and only reports `started` / `running` when the configured listener is reachable on the expected host/port. If the script says a surface is up but the listener is not reachable, treat that as a launcher regression and fix the script — do not work around it.
- AT-tier port discovery: `tests/env-AT` uses the `28983/28980/28981/28982` band (see "Port assignments and AT-tier exception" above). A Playwright failure showing `Service is shutting down` or `ERR_CONNECTION_REFUSED` against `http://127.0.0.1:28980` is not necessarily an application bug — in W28A-962 the root cause was the Playwright runtime wrapper exiting mid-suite, not the IMAP service logic.
- PID files in `.pids/` are only trustworthy when tied to the expected port. During W28A-962 investigation, a stale API PID pointed at a process listening on `8070` while the active `tests/env-AT` run expected `28983`. Port-ownership validation with `ss` is necessary for reliable status/start semantics.
- Image push target: `registry.cloud-dog.net:443/cloud-dog/imap-mcp-server:latest`. The W28A-962 completion push published digest `sha256:21c86a87741dfebb97fdc694937e0342cc5a52267cbcbc1810eedb70d417cf97`.
- Documentation drift can block completion as hard as code drift. Placeholder domains, fake registries, and stale local ports in `docs/` were enough to require remediation during the W28A-962 sweep.
- Preprod health for the deployed IMAP service is checked at `https://imapmcpserver0.cloud-dog.net/health`. The W28A-962 expected result was a JSON `status: ok` response after the targeted container replacement.

### W28A-662 — env-AT port surprise
`tests/env-AT` sets `CLOUD_DOG__API_SERVER__PORT=28983` (not the allocated 8070). The server started successfully but a health check pointed at 8070 failed. Always read the env file for the active tier before asserting port values.

### W28A-970b — PS-92 Base Path Migration
This service was an early adopter of the PS-92 Traefik `stripPrefix` pattern. The cross-platform lessons from that migration have been rolled up into central [AGENT-LESSONS.md §6.37](../cloud-dog-ai-platform-standards/AGENT-LESSONS.md); consult that section before doing further base-path or reverse-proxy work here.
