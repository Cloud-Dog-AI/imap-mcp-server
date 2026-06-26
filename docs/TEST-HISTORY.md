---
template-id: T-TSH
template-version: 1.0
applies-to: docs/TEST-HISTORY.md
registry: service
required: must-have
when-applicable: ""
template-last-updated: 2026-06-12
template-owner: platform-standards

project: imap-mcp-server
doc-last-updated: 2026-06-12
doc-git-commit: ce74719b4887c6f80da2e6514e76b8f470b9ab13
doc-git-branch: main
doc-source-shas: []
doc-age-policy: indefinite
doc-conformance-stamp: 2026-06-12T12:00:00Z
---

# imap-mcp-server — TEST-HISTORY

> **Template version:** T-TSH v1.0 — appended to by `scripts/update-test-state.py`. Roll-archive to `archive/test-history/<YYYY-MM>.md` when >500 lines.

## Runs (most recent first)

### 2026-06-24T07:30:00+00:00
- Commit: `b2864f7fd8d0098c0e30fb08bbb5b2aae375b594` (W28E-1803C Stream-C WebUI/E2E/1.0RC01)
- Suite: AT_WEBUI Playwright (local-docker) T1..T11 — Totals: 11 / P 11 / F 0 / S 0
- Preprod parity: AT_WEBUI Playwright (preprod) — Totals: 11 / P 11 / F 0 / S 0
- axe a11y 18/18 0-violation (local + preprod); URL canonical 40/40 (local + preprod)
- Added UT1.36 test_ut136_export_preserves_seed_credentials_when_override_blanks_them (FR-03)
- Delta: new-fails 0 | newly-green 4 (AT_WEBUI T2/T3/T4/T9 deferred from Stream-B now green)

### 2026-06-17T11:09:43.931683+00:00
- Commit: `353914ae72e95d3d74834360cbb7dcd11c1f88de` (W28C-1714-100pct-fix)
- Totals: 14 / P 14 / F 0 / S 0
- Delta: new-fails 0 | newly-green 5

### 2026-06-13T10:59:11.393524+00:00
- Commit: `a42dac177eb3dba8f038c70c236a3d58d3ae9bbc` (main)
- Totals: 192 / P 187 / F 5 / S 0
- Delta: new-fails 5 | newly-green 3

### 2026-06-13T10:18:36.285778+00:00
- Commit: `a42dac177eb3dba8f038c70c236a3d58d3ae9bbc` (main)
- Totals: 167 / P 164 / F 3 / S 0
- Delta: new-fails 3 | newly-green 0

### 2026-06-12T12:00:00Z
- Commit: `ce74719b4887c6f80da2e6514e76b8f470b9ab13` (main)
- Totals: N / P n / F n / S n
- Delta: new-fails 0 | newly-green 0
