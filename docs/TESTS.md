---
template-id: T-TST
template-version: 1.1
applies-to: docs/TESTS.md
project: imap-mcp-server
doc-last-updated: 2026-06-23T00:00:00Z
doc-git-commit: 17916ccd7ef96daa5140d4892c792a5ea14a44ad
doc-git-branch: main
doc-age-policy: 90d
doc-conformance-stamp: 2026-06-23T00:00:00Z
req-trace-version: 1.0
total-tests: 219
coverage-percent: 100
---

# Tests

## Service Scope
Mailbox sync, search, attachment, archive, jobs, audit, profile CRUD, and profile-driven email workflows exposed through API, MCP, A2A, and the WebUI.

## Test Inventory
| Tier | Present | Notes |
|------|---------|-------|
| `quality` | Yes | Repository contains the `quality` compliance suites. |
| `unit` | Yes | Repository contains the `unit` test tier. |
| `system` | Yes | Repository contains the `system` test tier. |
| `integration` | Yes | Repository contains the `integration` test tier. |
| `application` | Yes | Repository contains the `application` test tier. |
| `security` | Yes | Repository contains the `security` test tier. |
| `helpers` | Yes | Repository contains helper utilities used by executable suites. |
| `private` | Yes | Repository contains private env overlays used by executable suites. |

## Current Evidence Model
- The repository keeps execution evidence in repo-local working reports and rerunnable pytest suites.
- Before release, rerun the relevant `QT`, `UT`, `ST`, `IT`, and `AT` tiers against the intended environment overlays.
- This document records the current catalogue rather than claiming a release verdict.

## Standard Commands
```bash
python3 -m pytest tests/quality --env tests/env-QT -q
python3 -m pytest tests/unit --env tests/env-UT -q
python3 -m pytest tests/system --env tests/env-ST -q
python3 -m pytest tests/integration --env tests/env-IT -q
python3 -m pytest tests/application --env tests/env-AT -q
python3 -m pytest tests/security --env tests/env-QT -q
python3 -m pytest tests/ -v --env tests/env-AT --env tests/env-FORENSIC-WEB
```

## Requirement Traceability Highlights
| Test ID | File | Covers | Notes |
|---|---|---|---|
| `IT1.1` | `tests/integration/IT1.1_APIHealthEndpoint/test_IT1_1_APIHealthEndpoint.py` | `FR-01`, `FR-10` | Verifies API health plus SPA shell and runtime config availability on the web listener. |
| `IT1.8` | `tests/integration/IT1.8_IndexReconcileAfterSync/test_IT1_8_IndexReconcileAfterSync.py` | `FR-12` | Validates index reconciliation after a real sync and detects ledger drift handling. |
| `AT1.12` | `tests/application/AT1.12_ConfigCrudA2AWebUI/test_AT1_12_ConfigCrudA2AWebUI.py` | `FR-11`, `CFG-06`, `CFG-07`, `CFG-08`, `CFG-09`, `CFG-10`, `CFG-11`, `CFG-12`, `CFG-13` | Covers CRUD parity across API, MCP, A2A, and WebUI-managed admin flows. |
| `UI-T7` | `tests/application/AT_WEBUI_MailSearch/test_webui_mail_search.py` | `FR-15`, `FR-16`, `FR-17` | Covers the Search & Retrieve page, message/detail inspection, extracted payload rendering, and attachment retrieval flow. |
| `UI-T8` | `tests/application/AT_WEBUI_Dashboard/test_webui_dashboard.py` | `FR-14` | Verifies the dashboard route, widgets, and quick-action shell exposed from the governed WebUI route inventory. |
| `UI-T10` | `tests/application/AT_WEBUI_AuditLog/test_webui_audit_log.py` | `FR-14`, `FR-18` | Exercises the diagnostics-audit compatibility route and structured audit detail flow. |
| `UI-T11` | `tests/application/AT_WEBUI_Settings/test_webui_settings.py` | `FR-17` | Verifies governed settings editing plus structured inspector surfaces. |
| `ST1.15` | `tests/test_st_group_admin_delegation.py` | `FR-13` | Real API system test for delegated group-admin creation within the managed group and `403` denial outside group scope. Traceability: E2E W28A-500 Steps 9-10. |

## Repository Test File Index
- `tests/application/AT1.10_DynamicSpamProfileLifecycle/test_dynamic_spam_profile_lifecycle.py`
- `tests/application/AT1.12_ConfigCrudA2AWebUI/test_AT1_12_ConfigCrudA2AWebUI.py`
- `tests/application/AT1.1_FullWorkflow_SyncSearchRetrieve/test_AT1_1_FullWorkflow_SyncSearchRetrieve.py`
- `tests/application/AT1.2_FullWorkflow_DeltaSearch/test_AT1_2_FullWorkflow_DeltaSearch.py`
- `tests/application/AT1.3_FullWorkflow_DuplicateSweep/test_AT1_3_FullWorkflow_DuplicateSweep.py`
- `tests/application/AT1.4_FullWorkflow_ArchiveExport/test_AT1_4_FullWorkflow_ArchiveExport.py`
- `tests/application/AT1.5_FullWorkflow_AdminProfileSetup/test_AT1_5_FullWorkflow_AdminProfileSetup.py`
- `tests/application/AT1.6_RealIMAPFullWorkflow/test_AT1_6_RealIMAPFullWorkflow.py`
- `tests/application/AT1.7_RealIMAPAPIMCPAdvancedSearchRetrieve/test_AT1_7_RealIMAPAPIMCPAdvancedSearchRetrieve.py`
- `tests/application/AT1.8_A2AAuthHealthFlow/test_AT1_8_A2AAuthHealthFlow.py`
- `tests/application/AT1.9_DatabaseE2EProfileWorkflow/test_AT1_9_DatabaseE2EProfileWorkflow.py`
- `tests/application/AT_SPAM_PROFILE/test_spam_profile_lifecycle.py`
- `tests/application/AT_SpamProfile/test_spam_profile.py`
- `tests/application/AT_WEBUI_ApiKeyCRUD/test_webui_api_key_crud.py`
- `tests/application/AT_WEBUI_AuditLog/test_webui_audit_log.py`
- `tests/application/AT_WEBUI_Dashboard/test_webui_dashboard.py`
- `tests/application/AT_WEBUI_GroupCRUD/test_webui_group_crud.py`
- `tests/application/AT_WEBUI_Login/test_webui_login.py`
- `tests/application/AT_WEBUI_MailSearch/test_webui_mail_search.py`
- `tests/application/AT_WEBUI_McpTools/test_webui_mcp_tools.py`
- `tests/application/AT_WEBUI_ProfileCRUD/test_webui_profile_crud.py`
- `tests/application/AT_WEBUI_RbacEnforcement/test_webui_rbac_enforcement.py`
- `tests/application/AT_WEBUI_Settings/test_webui_settings.py`
- `tests/application/AT_WEBUI_UserCRUD/test_webui_user_crud.py`
- `tests/application/webui_e2e.py`
- `tests/integration/IT1.10_ProfileCRUDViaAPI/test_IT1_10_ProfileCRUDViaAPI.py`
- `tests/integration/IT1.11_RealIMAPSyncFlow/test_IT1_11_RealIMAPSyncFlow.py`
- `tests/integration/IT1.12_RealIMAPSearchViaAPI/test_IT1_12_RealIMAPSearchViaAPI.py`
- `tests/integration/IT1.13_RealIMAPAttachmentListViaAPI/test_IT1_13_RealIMAPAttachmentListViaAPI.py`
- `tests/integration/IT1.14_RealIMAPAttachmentDownloadViaAPI/test_IT1_14_RealIMAPAttachmentDownloadViaAPI.py`
- `tests/integration/IT1.15_A2AAuthContract/test_IT1_15_A2AAuthContract.py`
- `tests/integration/IT1.16_DatabaseStartupCRUD/test_IT1_16_DatabaseStartupCRUD.py`
- `tests/integration/IT1.17_DeleteMutation/test_IT1_17_DeleteMutation.py`
- `tests/integration/IT1.18_FlagMutation/test_IT1_18_FlagMutation.py`
- `tests/integration/IT1.19_ConfigCRUDViaAPI/test_IT1_19_ConfigCRUDViaAPI.py`
- `tests/integration/IT1.1_APIHealthEndpoint/test_IT1_1_APIHealthEndpoint.py`
- `tests/integration/IT1.20_MCPAdminConfigParity/test_IT1_20_MCPAdminConfigParity.py`
- `tests/integration/IT1.21_ConcurrentJobExecution/test_IT1_21_ConcurrentJobExecution.py`
- `tests/integration/IT1.22_JobRecoveryAfterTimeout/test_IT1_22_JobRecoveryAfterTimeout.py`
- `tests/integration/IT1.25_IdamBaselineAndOverlayMerge/test_IT1_25_IdamBaselineAndOverlayMerge.py`
- `tests/integration/IT1.2_APIAuthReject/test_IT1_2_APIAuthReject.py`
- `tests/integration/IT1.3_APIAuthAccept/test_IT1_3_APIAuthAccept.py`
- `tests/integration/IT1.4_APIRBACWriteGating/test_IT1_4_APIRBACWriteGating.py`
- `tests/integration/IT1.5_MCPToolCatalogue/test_IT1_5_MCPToolCatalogue.py`
- `tests/integration/IT1.6_MCPToolExecution/test_IT1_6_MCPToolExecution.py`
- `tests/integration/IT1.7_CorrelationIDPropagation/test_IT1_7_CorrelationIDPropagation.py`
- `tests/integration/IT1.8_IndexReconcileAfterSync/test_IT1_8_IndexReconcileAfterSync.py`
- `tests/integration/IT1.9_DeltaSearchViaAPI/test_IT1_9_DeltaSearchViaAPI.py`
- `tests/quality/QT_COMPLIANCE/test_qt1_security_suite.py`
- `tests/quality/QT_COMPLIANCE/test_qt26_secrets_separation.py`
- `tests/quality/QT_COMPLIANCE/test_qt27_bespoke_code_scan.py`
- `tests/quality/QT_COMPLIANCE/test_qt3_documentation_suite.py`
- `tests/quality/QT_COMPLIANCE/test_qt_migration_completeness.py`
- `tests/quality/QT_COMPLIANCE/test_qt_package_adoption.py`
- `tests/quality/QT_COMPLIANCE/test_qt_rules_compliance.py`
- `tests/quality/QT_COMPLIANCE/test_qt_traceability.py`
- `tests/quality/QT_COMPLIANCE/test_qt_vault_config_contract.py`
- `tests/quality/QT_LoggingCompliance/test_logging_compliance.py`
- `tests/quality/QT_PACKAGE_COMPLIANCE/test_package_compliance.py`
- `tests/security/QT1.1_SecretsNeverLogged/test_QT1_1_SecretsNeverLogged.py`
- `tests/security/QT1.2_PathSandboxEnforced/test_QT1_2_PathSandboxEnforced.py`
- `tests/security/QT1.3_MutationGatingWhenDisabled/test_QT1_3_MutationGatingWhenDisabled.py`
- `tests/security/QT1.4_UKEnglishCompliance/test_QT1_4_UKEnglishCompliance.py`
- `tests/system/ST1.10_DuplicateSweepDryRun/test_ST1_10_DuplicateSweepDryRun.py`
- `tests/system/ST1.11_JobEnqueueAndExecute/test_ST1_11_JobEnqueueAndExecute.py`
- `tests/system/ST1.12_AuditLogPersistence/test_ST1_12_AuditLogPersistence.py`
- `tests/system/ST1.13_RealIMAPLoginSearchFetch/test_ST1_13_RealIMAPLoginSearchFetch.py`
- `tests/system/ST1.14_DatabaseMigration/test_database_migration.py`
- `tests/system/ST1.14_DatabaseMigration/test_database_migration_multibackend.py`
- `tests/system/ST1.1_IMAPConnectSSL/test_ST1_1_IMAPConnectSSL.py`
- `tests/system/ST1.2_IMAPConnectSTARTTLS/test_ST1_2_IMAPConnectSTARTTLS.py`
- `tests/system/ST1.3_IMAPOAuth2XOAUTH2/test_ST1_3_IMAPOAuth2XOAUTH2.py`
- `tests/system/ST1.7_CacheStoreAndRetrieve/test_ST1_7_CacheStoreAndRetrieve.py`
- `tests/system/ST1.8_SearchCacheMode/test_ST1_8_SearchCacheMode.py`
- `tests/system/ST1.9_SearchLedgerRecord/test_ST1_9_SearchLedgerRecord.py`
- `tests/system/ST_IntegrityVerifier/test_integrity_running.py`
- `tests/system/ST_LogRotation/test_rotation_config.py`
- `tests/test_st_group_admin_delegation.py`
- `tests/unit/UT1.10_RetentionEvictionOrder/test_retention_eviction_order.py`
- `tests/unit/UT1.11_QueryNormalisation/test_query_normalisation.py`
- `tests/unit/UT1.12_SimilarityKeyDeterminism/test_similarity_determinism.py`
- `tests/unit/UT1.13_SimilarityKeyVolatileExclusion/test_similarity_volatile_exclusion.py`
- `tests/unit/UT1.14_SimilarityKeyPinning/test_similarity_pinning.py`
- `tests/unit/UT1.15_DuplicateDetectMessageID/test_duplicate_message_id.py`
- `tests/unit/UT1.16_DuplicateDetectContentHash/test_duplicate_content_hash.py`
- `tests/unit/UT1.17_DuplicateDetectHeuristic/test_duplicate_heuristic.py`
- `tests/unit/UT1.18_DuplicateSelectionPolicy/test_duplicate_selection_policy.py`
- `tests/unit/UT1.19_MessageMetadataNormalise/test_message_metadata_normalise.py`
- `tests/unit/UT1.1_ConfigLoaderPrecedence/test_config_loader_precedence.py`
- `tests/unit/UT1.20_AttachmentMIMEParsing/test_attachment_mime_parsing.py`
- `tests/unit/UT1.21_AttachmentSizeLimits/test_attachment_size_limits.py`
- `tests/unit/UT1.22_IndexMetadataSchema/test_index_metadata_schema.py`
- `tests/unit/UT1.23_ArchivePathDeterminism/test_archive_path_determinism.py`
- `tests/unit/UT1.24_ArchiveIdempotency/test_archive_idempotency.py`
- `tests/unit/UT1.25_JobModelValidation/test_job_model_validation.py`
- `tests/unit/UT1.26_TLSPolicyValidation/test_tls_policy_validation.py`
- `tests/unit/UT1.27_ToolDefinitionSchemas/test_tool_definition_schemas.py`
- `tests/unit/UT1.28_HighWaterMarkPriority/test_high_water_mark_priority.py`
- `tests/unit/UT1.29_IndexManagerUpsert/test_UT1_29_IndexManagerUpsert.py`
- `tests/unit/UT1.2_ConfigVaultIntegration/test_config_vault_integration.py`
- `tests/unit/UT1.30_ArchiveExporterDirect/test_UT1_30_ArchiveExporterDirect.py`
- `tests/unit/UT1.31_XOAuth2AuthString/test_UT1_31_XOAuth2AuthString.py`
- `tests/unit/UT1.32_SyncCursorAdvancement/test_sync_cursor_advancement.py`
- `tests/unit/UT1.33_A2AAuthValidatorParity/test_UT1_33_A2AAuthValidatorParity.py`
- `tests/unit/UT1.34_DatabaseAbstraction/test_database_abstraction.py`
- `tests/unit/UT1.35_MutationHandlers/test_mutation_handlers.py`
- `tests/unit/UT1.36_AdminStateCRUD/test_admin_state_crud.py`
- `tests/unit/UT1.37_AdminToolHandlers/test_admin_tool_handlers.py`
- `tests/unit/UT1.38_ProfileSearchDefaults/test_profile_search_defaults.py`
- `tests/unit/UT1.39_JobsRuntimeMigration/test_jobs_runtime_migration.py`
- `tests/unit/UT1.39_ProfileScopedToolAccess/test_profile_scoped_tool_access.py`
- `tests/unit/UT1.3_ConfigValidation/test_config_validation.py`
- `tests/unit/UT1.40_NistLoggingCompliance/test_nist_logging_compliance.py`
- `tests/unit/UT1.41_JobsAdminApi/test_jobs_admin_api.py`
- `tests/unit/UT1.42_RuntimeFallbackConfig/test_runtime_fallback_config.py`
- `tests/unit/UT1_42_NegativeAuthGate/test_negative_auth_gate.py`
- `tests/unit/UT1.43_CachePackagePosture/test_cache_package_posture.py`
- `tests/unit/UT1_44_CoreRequirementsTrace/test_core_requirements_trace.py`
- `tests/unit/UT1.4_ProfileModelValidation/test_profile_model_validation.py`
- `tests/unit/UT1.5_RBACPolicyEval/test_rbac_policy_eval.py`
- `tests/unit/UT1.6_AuditEventShape/test_audit_event_shape.py`
- `tests/unit/UT1.7_AuditRedaction/test_audit_redaction.py`
- `tests/unit/UT1.8_FolderPolicyIncludeExclude/test_folder_policy.py`
- `tests/unit/UT1.9_RetentionWindowCalc/test_retention_window.py`
- `tests/unit/UT_AuditLogFormat/test_audit_log_format.py`

## Notes
- Environment overlays and private credentials are intentionally not published in this document set.
- `tests/helpers/`, `conftest.py`, and package `__init__.py` files support executable suites and are intentionally not catalogued as standalone test cases.

## W28A-750 — IDAM cascade smoke (b-4)

- `tests/smoke/test_cascade_resolves.py` — T3-IMAP-CASCADE (resolver + live tool gate),
  T2-SECRET-MASK, profile_list list-filter, admin-wildcard, and flat-role regression
  guard for the W28A-741 RBACBinding cascade (group:G -> mailbox_profile:P). Covers
  FR-04/FR-13, CFG-09/CFG-13. Run with `--env tests/env-UT`.

## 2. Coverage map

Mandatory 10-column schema per PS-REQ-TEST-TRACE v1.0 §4.2. Every test module binds to its semantic `@pytest.mark.req(...)` requirement(s); the W28C-1711-R3 `@pytest.mark.probe` / tier-bucket placeholders were retired and rebound to capability requirements in W28E-1803A (see `docs/REQUIREMENTS.md` §4.C). `Last run commit` is `design-bound (run: Stream-B)` because Stream-A binds and designs; execution verdicts are produced by Stream-B (UT/IT/AT) and Stream-C (WebUI/E2E). Rows are keyed by test-module ID; a module may contain several `def test_*` functions sharing the module's bindings.

| Test ID | Tier | Use case | Requirement | Surface | Scenario | Variants | Env files | Known issue | Last run commit |
|---|---|---|---|---|---|---|---|---|---|
| `AT1.10_DynamicSpamProfileLifecycle` | AT | UC-003 | `FR-03` | `mcp` | DynamicSpamProfileLifecycle | — | tests/env-AT | — | design-bound (run: Stream-B) |
| `AT1.12_ConfigCrudA2AWebUI` | AT | UC-013 | `FR-11` | `webui` | ConfigCrudA2AWebUI | — | tests/env-AT | — | design-bound (run: Stream-B) |
| `AT1.1_FullWorkflow_SyncSearchRetrieve` | AT | UC-006 | `FR-05` | `mcp` | FullWorkflow SyncSearchRetrieve | — | tests/env-AT | — | design-bound (run: Stream-B) |
| `AT1.2_FullWorkflow_DeltaSearch` | AT | UC-009 | `FR-07` | `mcp` | FullWorkflow DeltaSearch | — | tests/env-AT | — | design-bound (run: Stream-B) |
| `AT1.3_FullWorkflow_DuplicateSweep` | AT | UC-022 | `FR-20` | `mcp` | FullWorkflow DuplicateSweep | — | tests/env-AT | — | design-bound (run: Stream-B) |
| `AT1.4_FullWorkflow_ArchiveExport` | AT | UC-023 | `FR-21` | `mcp` | FullWorkflow ArchiveExport | — | tests/env-AT | — | design-bound (run: Stream-B) |
| `AT1.5_FullWorkflow_AdminProfileSetup` | AT | UC-003 | `FR-03` | `mcp` | FullWorkflow AdminProfileSetup | — | tests/env-AT | — | design-bound (run: Stream-B) |
| `AT1.6_RealIMAPFullWorkflow` | AT | UC-006 | `FR-05` | `mcp` | RealIMAPFullWorkflow | — | tests/env-AT | — | design-bound (run: Stream-B) |
| `AT1.7_RealIMAPAPIMCPAdvancedSearchRetrieve` | AT | UC-006 | `FR-05` | `mcp` | RealIMAPAPIMCPAdvancedSearchRetrieve | — | tests/env-AT | — | design-bound (run: Stream-B) |
| `AT1.8_A2AAuthHealthFlow` | AT | UC-005 | `FR-04` | `mcp` | A2AAuthHealthFlow | — | tests/env-AT | — | design-bound (run: Stream-B) |
| `AT1.9_DatabaseE2EProfileWorkflow` | AT | UC-024 | `FR-23` | `mcp` | DatabaseE2EProfileWorkflow | — | tests/env-AT | — | design-bound (run: Stream-B) |
| `AT_SPAM_PROFILE` | AT | UC-003 | `FR-03` | `mcp` | SPAM PROFILE | — | tests/env-AT | — | design-bound (run: Stream-B) |
| `AT_SpamProfile` | AT | UC-003 | `FR-03` | `mcp` | SpamProfile | — | tests/env-AT | — | design-bound (run: Stream-B) |
| `AT_WEBUI_ApiKeyCRUD` | AT | UC-013 | `FR-11` | `webui` | WEBUI ApiKeyCRUD | — | tests/env-AT | — | design-bound (run: Stream-B) |
| `AT_WEBUI_AuditLog` | AT | UC-016 | `FR-14`, `FR-18` | `webui` | WEBUI AuditLog | — | tests/env-AT | — | design-bound (run: Stream-B) |
| `AT_WEBUI_Dashboard` | AT | UC-016 | `FR-14` | `webui` | WEBUI Dashboard | — | tests/env-AT | — | design-bound (run: Stream-B) |
| `AT_WEBUI_GroupCRUD` | AT | UC-013 | `FR-11` | `webui` | WEBUI GroupCRUD | — | tests/env-AT | — | design-bound (run: Stream-B) |
| `AT_WEBUI_Login` | AT | UC-012 | `FR-10` | `webui` | WEBUI Login | — | tests/env-AT | — | design-bound (run: Stream-B) |
| `AT_WEBUI_MailSearch` | AT | UC-017 | `FR-15`, `FR-16` | `webui` | WEBUI MailSearch | — | tests/env-AT | — | design-bound (run: Stream-B) |
| `AT_WEBUI_McpTools` | AT | UC-012 | `FR-10` | `webui` | WEBUI McpTools | — | tests/env-AT | — | design-bound (run: Stream-B) |
| `AT_WEBUI_ProfileCRUD` | AT | UC-013 | `FR-11` | `webui` | WEBUI ProfileCRUD | — | tests/env-AT | — | design-bound (run: Stream-B) |
| `AT_WEBUI_RbacEnforcement` | AT | UC-005 | `FR-04` | `webui` | WEBUI RbacEnforcement | — | tests/env-AT | — | design-bound (run: Stream-B) |
| `AT_WEBUI_Settings` | AT | UC-018 | `FR-17` | `webui` | WEBUI Settings | — | tests/env-AT | — | design-bound (run: Stream-B) |
| `AT_WEBUI_UserCRUD` | AT | UC-013 | `FR-11` | `webui` | WEBUI UserCRUD | — | tests/env-AT | — | design-bound (run: Stream-B) |
| `IT1.10_ProfileCRUDViaAPI` | IT | UC-003,UC-004 | `FR-03` | `mcp` | ProfileCRUDViaAPI | — | tests/env-IT | — | design-bound (run: Stream-B) |
| `IT1.11_RealIMAPSyncFlow` | IT | UC-006 | `FR-05` | `mcp` | RealIMAPSyncFlow | — | tests/env-IT | — | design-bound (run: Stream-B) |
| `IT1.12_RealIMAPSearchViaAPI` | IT | UC-006 | `FR-05` | `mcp` | RealIMAPSearchViaAPI | — | tests/env-IT | — | design-bound (run: Stream-B) |
| `IT1.13_RealIMAPAttachmentListViaAPI` | IT | UC-006 | `FR-05` | `mcp` | RealIMAPAttachmentListViaAPI | — | tests/env-IT | — | design-bound (run: Stream-B) |
| `IT1.14_RealIMAPAttachmentDownloadViaAPI` | IT | UC-006 | `FR-05` | `mcp` | RealIMAPAttachmentDownloadViaAPI | — | tests/env-IT | — | design-bound (run: Stream-B) |
| `IT1.15_A2AAuthContract` | IT | UC-005,UC-020 | `CS-007`, `FR-04` | `mcp` | A2AAuthContract | — | tests/env-IT | — | design-bound (run: Stream-B) |
| `IT1.16_DatabaseStartupCRUD` | IT | UC-024 | `FR-23` | `mcp` | DatabaseStartupCRUD | — | tests/env-IT | — | design-bound (run: Stream-B) |
| `IT1.17_DeleteMutation` | IT | UC-008 | `FR-06` | `mcp` | DeleteMutation | — | tests/env-IT | — | design-bound (run: Stream-B) |
| `IT1.18_FlagMutation` | IT | UC-008 | `FR-06` | `mcp` | FlagMutation | — | tests/env-IT | — | design-bound (run: Stream-B) |
| `IT1.19_ConfigCRUDViaAPI` | IT | UC-013 | `FR-11` | `mcp` | ConfigCRUDViaAPI | — | tests/env-IT | — | design-bound (run: Stream-B) |
| `IT1.1_APIHealthEndpoint` | IT | UC-001 | `FR-01` | `mcp` | APIHealthEndpoint | — | tests/env-IT | — | design-bound (run: Stream-B) |
| `IT1.20_MCPAdminConfigParity` | IT | UC-013 | `FR-11` | `mcp` | MCPAdminConfigParity | — | tests/env-IT | — | design-bound (run: Stream-B) |
| `IT1.21_ConcurrentJobExecution` | IT | UC-019 | `FR-19` | `mcp` | ConcurrentJobExecution | — | tests/env-IT | — | design-bound (run: Stream-B) |
| `IT1.22_JobRecoveryAfterTimeout` | IT | UC-019 | `FR-19` | `mcp` | JobRecoveryAfterTimeout | — | tests/env-IT | — | design-bound (run: Stream-B) |
| `IT1.23_MCPJsonRpcToolsCall` | IT | UC-001,UC-005 | `FR-01`, `FR-04` | `mcp` | MCPJsonRpcToolsCall | — | tests/env-IT | — | design-bound (run: Stream-B) |
| `IT1.25_IdamBaselineAndOverlayMerge` | IT | UC-005,UC-021 | `FR-04`, `FR-13` | `internal` | IdamBaselineAndOverlayMerge — six undeletable baseline roles + role_overlay baseline merge (PS-IDAM-ROLE-CASCADE) | — | tests/env-IT | — | W28E-1803B |
| `IT1.2_APIAuthReject` | IT | UC-020 | `CS-005` | `mcp` | APIAuthReject | — | tests/env-IT | — | design-bound (run: Stream-B) |
| `IT1.3_APIAuthAccept` | IT | UC-005 | `FR-04` | `mcp` | APIAuthAccept | — | tests/env-IT | — | design-bound (run: Stream-B) |
| `IT1.4_APIRBACWriteGating` | IT | UC-005,UC-021 | `CS-002`, `CS-008`, `FR-04` | `mcp` | APIRBACWriteGating | — | tests/env-IT | — | design-bound (run: Stream-B) |
| `IT1.5_MCPToolCatalogue` | IT | UC-001 | `FR-01` | `mcp` | MCPToolCatalogue | — | tests/env-IT | — | design-bound (run: Stream-B) |
| `IT1.6_MCPToolExecution` | IT | UC-001 | `FR-01` | `mcp` | MCPToolExecution | — | tests/env-IT | — | design-bound (run: Stream-B) |
| `IT1.7_CorrelationIDPropagation` | IT | UC-011 | `FR-09` | `mcp` | CorrelationIDPropagation | — | tests/env-IT | — | design-bound (run: Stream-B) |
| `IT1.8_IndexReconcileAfterSync` | IT | UC-014 | `FR-12` | `mcp` | IndexReconcileAfterSync | — | tests/env-IT | — | design-bound (run: Stream-B) |
| `IT1.9_DeltaSearchViaAPI` | IT | UC-009 | `FR-07` | `mcp` | DeltaSearchViaAPI | — | tests/env-IT | — | design-bound (run: Stream-B) |
| `QT1.1_SecretsNeverLogged` | UT | UC-011 | `CS-014` | `mcp` | SecretsNeverLogged | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `QT1.2_PathSandboxEnforced` | UT | UC-007 | `CS-015` | `mcp` | PathSandboxEnforced | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `QT1.3_MutationGatingWhenDisabled` | UT | UC-008 | `FR-06` | `mcp` | MutationGatingWhenDisabled | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `QT1.4_UKEnglishCompliance` | UT | UC-001 | `NF-004` | `mcp` | UKEnglishCompliance | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `QT_COMPLIANCE` | QT | UC-001,UC-007,UC-011 | `CS-014`, `CS-015`, `NF-001`, `NF-002`, `NF-003`, `NF-004` | `mcp` | COMPLIANCE | — | tests/env-QT | — | design-bound (run: Stream-B) |
| `QT_LoggingCompliance` | QT | UC-011 | `FR-09` | `mcp` | LoggingCompliance | — | tests/env-QT | — | design-bound (run: Stream-B) |
| `QT_PACKAGE_COMPLIANCE` | QT | UC-001,UC-002,UC-012 | `FR-10`, `NF-001`, `NF-002`, `NF-004` | `mcp` | PACKAGE COMPLIANCE | — | tests/env-QT | — | design-bound (run: Stream-B) |
| `ST1.10_DuplicateSweepDryRun` | ST | UC-022 | `FR-20` | `mcp` | DuplicateSweepDryRun | — | tests/env-ST | — | design-bound (run: Stream-B) |
| `ST1.11_JobEnqueueAndExecute` | ST | UC-019 | `FR-19` | `mcp` | JobEnqueueAndExecute | — | tests/env-ST | — | design-bound (run: Stream-B) |
| `ST1.12_AuditLogPersistence` | ST | UC-011 | `FR-09` | `mcp` | AuditLogPersistence | — | tests/env-ST | — | design-bound (run: Stream-B) |
| `ST1.13_RealIMAPLoginSearchFetch` | ST | UC-006 | `FR-05` | `mcp` | RealIMAPLoginSearchFetch | — | tests/env-ST | — | design-bound (run: Stream-B) |
| `ST1.14_DatabaseMigration` | ST | UC-024 | `FR-23` | `mcp` | DatabaseMigration | — | tests/env-ST | — | design-bound (run: Stream-B) |
| `ST1.1_IMAPConnectSSL` | ST | UC-010 | `FR-08` | `mcp` | IMAPConnectSSL | — | tests/env-ST | — | design-bound (run: Stream-B) |
| `ST1.2_IMAPConnectSTARTTLS` | ST | UC-010 | `FR-08` | `mcp` | IMAPConnectSTARTTLS | — | tests/env-ST | — | design-bound (run: Stream-B) |
| `ST1.3_IMAPOAuth2XOAUTH2` | ST | UC-010 | `FR-08` | `mcp` | IMAPOAuth2XOAUTH2 | — | tests/env-ST | — | design-bound (run: Stream-B) |
| `ST1.7_CacheStoreAndRetrieve` | ST | UC-009 | `FR-22` | `mcp` | CacheStoreAndRetrieve | — | tests/env-ST | — | design-bound (run: Stream-B) |
| `ST1.8_SearchCacheMode` | ST | UC-009 | `FR-22` | `mcp` | SearchCacheMode | — | tests/env-ST | — | design-bound (run: Stream-B) |
| `ST1.9_SearchLedgerRecord` | ST | UC-009 | `FR-07` | `mcp` | SearchLedgerRecord | — | tests/env-ST | — | design-bound (run: Stream-B) |
| `ST_IntegrityVerifier` | ST | UC-011 | `FR-09` | `mcp` | IntegrityVerifier | — | tests/env-ST | — | design-bound (run: Stream-B) |
| `ST_LogRotation` | ST | UC-011 | `FR-09` | `mcp` | LogRotation | — | tests/env-ST | — | design-bound (run: Stream-B) |
| `UT1.10_RetentionEvictionOrder` | UT | UC-003 | `FR-03` | `mcp` | RetentionEvictionOrder | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.11_QueryNormalisation` | UT | UC-009 | `FR-07` | `mcp` | QueryNormalisation | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.12_SimilarityKeyDeterminism` | UT | UC-009 | `FR-07` | `mcp` | SimilarityKeyDeterminism | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.13_SimilarityKeyVolatileExclusion` | UT | UC-009 | `FR-07` | `mcp` | SimilarityKeyVolatileExclusion | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.14_SimilarityKeyPinning` | UT | UC-009 | `FR-07` | `mcp` | SimilarityKeyPinning | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.15_DuplicateDetectMessageID` | UT | UC-022 | `FR-20` | `mcp` | DuplicateDetectMessageID | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.16_DuplicateDetectContentHash` | UT | UC-022 | `FR-20` | `mcp` | DuplicateDetectContentHash | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.17_DuplicateDetectHeuristic` | UT | UC-022 | `FR-20` | `mcp` | DuplicateDetectHeuristic | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.18_DuplicateSelectionPolicy` | UT | UC-022 | `FR-20` | `mcp` | DuplicateSelectionPolicy | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.19_MessageMetadataNormalise` | UT | UC-006 | `FR-05` | `mcp` | MessageMetadataNormalise | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.1_ConfigLoaderPrecedence` | UT | UC-002 | `FR-02` | `mcp` | ConfigLoaderPrecedence | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.20_AttachmentMIMEParsing` | UT | UC-006 | `FR-05` | `mcp` | AttachmentMIMEParsing | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.21_AttachmentSizeLimits` | UT | UC-006 | `FR-05` | `mcp` | AttachmentSizeLimits | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.22_IndexMetadataSchema` | UT | UC-014 | `FR-12` | `mcp` | IndexMetadataSchema | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.23_ArchivePathDeterminism` | UT | UC-023 | `FR-21` | `mcp` | ArchivePathDeterminism | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.24_ArchiveIdempotency` | UT | UC-023 | `FR-21` | `mcp` | ArchiveIdempotency | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.25_JobModelValidation` | UT | UC-019 | `FR-19` | `mcp` | JobModelValidation | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.26_TLSPolicyValidation` | UT | UC-010 | `FR-08` | `mcp` | TLSPolicyValidation | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.27_ToolDefinitionSchemas` | UT | UC-001,UC-021 | `CS-011`, `CS-012`, `CS-013`, `FR-01` | `mcp` | ToolDefinitionSchemas | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.28_HighWaterMarkPriority` | UT | UC-009 | `FR-07` | `mcp` | HighWaterMarkPriority | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.29_IndexManagerUpsert` | UT | UC-014 | `FR-12` | `mcp` | IndexManagerUpsert | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.2_ConfigVaultIntegration` | UT | UC-002 | `FR-02` | `mcp` | ConfigVaultIntegration | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.30_ArchiveExporterDirect` | UT | UC-023 | `FR-21` | `mcp` | ArchiveExporterDirect | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.31_XOAuth2AuthString` | UT | UC-010 | `FR-08` | `mcp` | XOAuth2AuthString | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.32_SyncCursorAdvancement` | UT | UC-009 | `FR-07` | `mcp` | SyncCursorAdvancement | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.33_A2AAuthValidatorParity` | UT | UC-005,UC-021 | `CS-010`, `FR-04` | `mcp` | A2AAuthValidatorParity | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.34_DatabaseAbstraction` | UT | UC-024 | `FR-23` | `mcp` | DatabaseAbstraction | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.35_MutationHandlers` | UT | UC-008 | `FR-06` | `mcp` | MutationHandlers | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.36_AdminStateCRUD` | UT | UC-003 | `FR-03` | `mcp` | AdminStateCRUD | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.37_AdminToolHandlers` | UT | UC-003 | `FR-03` | `mcp` | AdminToolHandlers | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.38_ProfileSearchDefaults` | UT | UC-003 | `FR-03` | `mcp` | ProfileSearchDefaults | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.39_JobsRuntimeMigration` | UT | UC-019 | `FR-19` | `mcp` | JobsRuntimeMigration | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.39_ProfileScopedToolAccess` | UT | UC-005 | `FR-04` | `mcp` | ProfileScopedToolAccess | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.3_ConfigValidation` | UT | UC-002 | `FR-02` | `mcp` | ConfigValidation | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.40_NistLoggingCompliance` | UT | UC-011 | `FR-09` | `mcp` | NistLoggingCompliance | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.41_JobsAdminApi` | UT | UC-019 | `FR-19` | `mcp` | JobsAdminApi | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.42_RuntimeFallbackConfig` | UT | UC-002 | `FR-02` | `mcp` | RuntimeFallbackConfig | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.43_CachePackagePosture` | UT | UC-009 | `FR-22` | `mcp` | CachePackagePosture | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.4_ProfileModelValidation` | UT | UC-003 | `FR-03` | `mcp` | ProfileModelValidation | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.5_RBACPolicyEval` | UT | UC-005 | `FR-04` | `mcp` | RBACPolicyEval | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.6_AuditEventShape` | UT | UC-011 | `FR-09` | `mcp` | AuditEventShape | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.7_AuditRedaction` | UT | UC-011 | `FR-09` | `mcp` | AuditRedaction | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.8_FolderPolicyIncludeExclude` | UT | UC-003 | `FR-03` | `mcp` | FolderPolicyIncludeExclude | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1.9_RetentionWindowCalc` | UT | UC-003 | `FR-03` | `mcp` | RetentionWindowCalc | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1_42_NegativeAuthGate` | UT | UC-005,UC-020 | `CS-001`, `CS-005`, `CS-006`, `CS-007`, `FR-04` | `mcp` | 42 NegativeAuthGate | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT1_44_CoreRequirementsTrace` | UT | UC-001,UC-002,UC-003,UC-005,UC-006,UC-008,UC-009,UC-010,UC-011,UC-012,UC-013,UC-014,UC-015,UC-020,UC-021 | `CS-001`, `CS-002`, `CS-003`, `CS-004`, `FR-01`, `FR-02`, `FR-03`, `FR-04`, `FR-05`, `FR-06`, `FR-07`, `FR-08`, `FR-09`, `FR-10`, `FR-11`, `FR-12`, `FR-13` | `api`, `internal`, `mcp`, `webui` | 44 CoreRequirementsTrace | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `UT_AuditLogFormat` | UT | UC-011 | `FR-09` | `mcp` | AuditLogFormat | — | tests/env-UT | — | design-bound (run: Stream-B) |
| `smoke` | QT | UC-005,UC-015 | `FR-04`, `FR-13` | `mcp` | smoke | — | tests/env-QT | — | design-bound (run: Stream-B) |
| `st_group_admin_delegation` | UT | UC-013,UC-015,UC-021 | `CS-004`, `CS-009`, `CS-010`, `FR-11`, `FR-13` | `mcp` | st group admin delegation | — | tests/env-UT | — | design-bound (run: Stream-B) |


<!-- W28C-1710b design-delta additions (2026-06-14T18:01:23Z) -->

## W28C-1710b design-delta — planned tests catalogue (T-TST v1.1 10-col schema)

Per T-TST v1.1, the planned tests catalogue carries 10 columns: `test-id | tier | use-case | requirement | surface | scenario | variants | env-files | known-issue | last-run-commit`. Test binding (replacement of probe markers with `@pytest.mark.req("FR-NNN")`) is W28C-1711 work.

Consolidation rules (per W28C-1711):

1. One primary test per FR-NNN; variants via `pytest.parametrize`.
2. Common scenarios (login, RBAC matrix, anon-denied) in `tests/helpers/`.
3. Cross-surface FR uses parametrized test file; not duplicate files.
4. Every `surface: webui` FR has a Playwright test (cookie-login + RBAC matrix + screenshot + DOM-assert + console-error-gate + CW-pattern).
5. Every `surface: api|mcp|a2a` FR has a protocol-level test.
6. Every `CS-NNN` binds to `@pytest.mark.negative` test with expected denial code.
7. CRUD-applicable entities have C/R/U/D coverage.
8. Orphan retirement requires knowledge-extract worksheet.
