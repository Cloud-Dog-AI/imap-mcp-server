---
template-id: T-TPR
template-version: 1.0
applies-to: tests/fixtures/TEST-PACK-REFERENCE.md
project: imap-mcp-server
doc-last-updated: 2026-06-23T00:00:00Z
doc-age-policy: 90d
---

# imap-mcp-server — Test-Pack Reference

> Generated for W28E-1803A from `cloud-dog-ai-platform-standards/test-packs/REGISTRY.tsv`
> per PS-TEST-PACKS-REGISTRY. This file references central pack IDs, source zips, and
> SHA256 values; it does not copy unpacked dump contents.

## 1. Service-specific pack

`imap-mcp-server` has **no service-specific test pack** registered in
`test-packs/REGISTRY.tsv` (no `owner_service: imap-mcp-server` row). imap is a mature
service whose test catalogue (219 functions across 125 modules) is authored in-repo under
`tests/` and bound to requirements via `@pytest.mark.req(...)`; there is therefore no
external service zip to consume.

## 2. Shared / cross-service packs consumed

`imap-mcp-server` is in scope for the programme-wide packs whose `applies_to_services` is `all`:

| pack_id | pack_kind | source_zip (relative to platform-standards) | sha256 | size_bytes | stream_binding |
|---|---|---|---|---|---|
| `TP-COMMON` | shared | `working/evidence/W28C-1711-KNOWLEDGE-FILES/INBOX-ARCHIVE/Test-Design-Audit-Jun26-2026-06-16/common-test-suite.zip` | `3af79a7b19fcd3d4161ad9bff8b79f3fa6dce07e4c8ebf9de74058fd5511c754` | 6598 | A/B/C |
| `TP-INTEGRATION-EXAMPLES` | cross-service | `working/evidence/W28C-1711-KNOWLEDGE-FILES/INBOX-ARCHIVE/Test-Design-Audit-Jun26-2026-06-16/integration-examples-test-suite.zip` | `50f8aa7463c83635527098ddca8f1f2186085d66cd7516c432aa05052a6d9467` | 11730 | A/B/C |

The `TP-AJOBS` platform pack is NOT consumed by imap (its `applies_to_services` list names
notification-agent / expert-agent / code-runner / scheduler only); imap's managed-jobs cover
(`FR-19`) is exercised by in-repo tests against `cloud_dog_jobs`.

## 3. Design-seed source

imap-mcp-server's Stream-A design seed is `working/evidence/W28C-1711-KNOWLEDGE-FILES/imap-mcp-server-KNOWLEDGE.md`
(W28C-1711 knowledge-preservation file). Its Test-Design-Audit-Jun26 SUPPLEMENT (`imap/WebuiReview.md`,
`imap/imap server Smoke Test.md`) carried no ticked operator disposition box at ingest and is treated as
deferred WebUI feedback for Stream-C, not as new Stream-A requirements.
