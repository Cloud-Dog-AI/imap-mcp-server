---
template-id: T-SCM
template-version: 1.0
applies-to: tests/SCOPE-MAP.md
project: imap-mcp-server
doc-last-updated: 2026-06-23T00:00:00Z
doc-git-commit: 17916ccd7ef96daa5140d4892c792a5ea14a44ad
doc-git-branch: main
doc-age-policy: 30d
doc-conformance-stamp: 2026-06-23T00:00:00Z
---

# imap-mcp-server — Test scope map

> **Template version:** T-SCM v1.0 — required by PS-REQ-TEST-TRACE §5.
> Maps each `src/` module-area glob to the test modules (and their semantic FR/CS/NF) that exercise it, enabling RULES.md §5.8 scoped runs. Refreshed in W28E-1803A after the semantic rebinding.

## Mapping

| Source glob | Requirement(s) | Test IDs |
|---|---|---|
| `src/imap_hub_core/config/**` | `FR-02` | `UT1.1`, `UT1.2`, `UT1.3`, `UT1.42` |
| `src/imap_hub_core/rbac/**`, `src/imap_hub_server/auth/**`, `src/imap_hub_server/rbac_seam.py` | `FR-04`, `CS-001`, `CS-005`, `CS-006`, `CS-007`, `CS-008`, `CS-009`, `CS-010` | `UT1.5`, `UT1.39_ProfileScopedToolAccess`, `UT1_42_NegativeAuthGate`, `UT1.33`, `IT1.2`, `IT1.3`, `IT1.4`, `IT1.15`, `AT1.8`, `AT_WEBUI_RbacEnforcement` |
| `src/imap_hub_core/audit/**`, `src/imap_hub_server/logging_runtime.py` | `FR-09`, `CS-014` | `UT1.6`, `UT1.7`, `UT1.40`, `UT_AuditLogFormat`, `ST1.12`, `ST_LogRotation`, `ST_IntegrityVerifier`, `IT1.7`, `QT1.1`, `QT_LoggingCompliance` |
| `src/imap_hub_core/ledger/**` | `FR-07` | `UT1.11`, `UT1.12`, `UT1.13`, `UT1.14`, `UT1.28`, `UT1.32`, `ST1.9`, `IT1.9`, `AT1.2` |
| `src/imap_hub_core/message/**`, `src/imap_hub_core/extract/**`, `src/imap_hub_core/attachment/**` | `FR-05`, `CS-015` | `UT1.19`, `UT1.20`, `UT1.21`, `ST1.13`, `IT1.11`, `IT1.12`, `IT1.13`, `IT1.14`, `QT1.2`, `AT1.1`, `AT1.6`, `AT1.7` |
| `src/imap_hub_core/imap/**` | `FR-08` | `UT1.26`, `UT1.31`, `ST1.1`, `ST1.2`, `ST1.3` |
| `src/imap_hub_core/index/**` | `FR-12` | `UT1.22`, `UT1.29`, `IT1.8` |
| `src/imap_hub_core/jobs/**` | `FR-19` | `UT1.25`, `UT1.39_JobsRuntimeMigration`, `UT1.41`, `ST1.11`, `IT1.21`, `IT1.22` |
| `src/imap_hub_core/duplicate/**` | `FR-20` | `UT1.15`, `UT1.16`, `UT1.17`, `UT1.18`, `ST1.10`, `AT1.3` |
| `src/imap_hub_core/archive/**` | `FR-21` | `UT1.23`, `UT1.24`, `UT1.30`, `AT1.4` |
| `src/imap_hub_core/cache/**` | `FR-22` | `ST1.7`, `ST1.8`, `UT1.43` |
| `src/imap_hub_core/db/**` | `FR-23` | `UT1.34`, `ST1.14`, `IT1.16`, `AT1.9` |
| `src/imap_hub_core/tools/**`, `src/imap_hub_core/storage_paths.py` | `FR-01`, `FR-06`, `CS-011`, `CS-012`, `CS-013` | `UT1.27`, `UT1.35`, `IT1.5`, `IT1.6`, `IT1.17`, `IT1.18`, `QT1.3` |
| `src/imap_hub_server/api_server.py`, `mcp_server.py`, `a2a_server.py`, `main.py` | `FR-01` | `IT1.1`, `IT1.5`, `IT1.6` |
| `src/imap_hub_server/web_server.py`, `web_flat_roles.py`, `static/**` | `FR-10`, `FR-14`, `FR-15`, `FR-16`, `FR-17`, `FR-18` | `AT_WEBUI_Login`, `AT_WEBUI_Dashboard`, `AT_WEBUI_MailSearch`, `AT_WEBUI_Settings`, `AT_WEBUI_AuditLog`, `AT_WEBUI_McpTools` |
| `src/imap_hub_server/admin/**` | `FR-03`, `FR-11`, `FR-13` | `UT1.4`, `UT1.8`, `UT1.9`, `UT1.10`, `UT1.36`, `UT1.37`, `UT1.38`, `IT1.10`, `IT1.19`, `IT1.20`, `AT1.5`, `AT1.10`, `AT1.12`, `AT_WEBUI_ProfileCRUD`, `AT_WEBUI_UserCRUD`, `AT_WEBUI_GroupCRUD`, `AT_WEBUI_ApiKeyCRUD`, `test_st_group_admin_delegation`, `test_cascade_resolves` |
| `src/**` (platform-package adoption + repo hygiene, cross-cutting) | `NF-001`, `NF-002`, `NF-003`, `NF-004` | `test_qt_package_adoption`, `test_package_compliance`, `test_qt_vault_config_contract`, `test_qt26_secrets_separation`, `test_qt_rules_compliance`, `test_qt_traceability`, `test_qt3_documentation_suite`, `test_QT1_4_UKEnglishCompliance`, `test_qt27_bespoke_code_scan`, `test_qt_migration_completeness` |

## Cross-references

- Platform standard: PS-REQ-TEST-TRACE v1.0 §5
- Tier policy: standards/TEST-POLICY-SCOPED.md
