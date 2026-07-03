---
template-id: T-DMT
template-version: 1.0
applies-to: docs/DATA-MODEL.md
registry: service
required: must-have
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

# imap-mcp-server — Data Model (b-7 canonical)

**Lane:** W28A-750 (IDAM Thread-b). Built from §1 of `ROLES-AND-USECASES.md` + `ARCHITECTURE.md`. Identity and domain families are distinct; the W28A-741 `RBACBinding` (persisted in the imap JSON snapshot as `RBACBindingRecord`) is the group→resource edge that joins them.

## Identity family (JSON snapshot: `admin/state_models.py`, `state.py`; roles via `cloud_dog_idam` `SqlAlchemyRoleStore`)
| Entity | Store | Key fields | Relationships |
|---|---|---|---|
| User (`UserRecord`) | `AdminStateSnapshot.users` | `user_id, username, email, display_name, status, role, is_system_user, tenant_id` | M:N Group via `GroupRecord.members[]` |
| Group (`GroupRecord`) | `AdminStateSnapshot.groups` | `group_id, name, description, roles[], members[], group_admins[], tenant_id` | M:N User; delegated `group_admins[]` (FR-13); `roles[]` |
| ApiKey (`APIKeyRecord`) | `AdminStateSnapshot.api_keys` | `api_key_id, owner_user_id, key_prefix, key_hash, status, scopes[], description, expires_at` | N:1 User |
| Role | `cloud_dog_idam` SqlAlchemyRoleStore | `role_id, name, permissions[]` | named in `GroupRecord.roles[]` / `UserRecord.role` |
| **RBACBinding** (`RBACBindingRecord`, W28A-750) | `AdminStateSnapshot.bindings` | `binding_id, subject_type∈{user,group}, subject_id, project, resource_type, resource_id, permission, granted_by` | the group→resource edge; read by `ImapBindingRepository.by_subject` → idam 0.5.0 resolver |

## Domain family (mailbox)
| Entity | Backing | Key fields / concept |
|---|---|---|
| MailboxProfile (`ProfileConfig`) | `AdminStateSnapshot.profiles` + `config/models.py` | `provider, imap{host,port,security}, auth, credentials{username,password}, sync/write/index/archive/search_ledger, allowed_groups[]` — **primary resource (`mailbox_profile`)** |
| MailboxScope | profile `sync.folders` | allowed folder set + mutation policy |
| Folder / Message / Attachment | IMAP backend + `data/downloads/` | scoped ops; mutation gated by `write.enabled` + RBAC |
| SearchLedger | `cloud_dog_db` | canonical query + high-water-mark (FR-07/FR-12) |
| AuditEvent | `cloud_dog_logging` (append-only) | AU-3 record (FR-09, PS-40) |
| Job | `cloud_dog_jobs` | long-running op lifecycle |

## The cascade edge (W28A-750)
`User —(GroupRecord.members: U∈G)→ Group —(RBACBinding: group:G → mailbox_profile:P = imap:mail:read)→ MailboxProfile P`. Resolved live by `cloud_dog_idam.rbac.grants.authorise` via `ImapMembershipResolver.groups_of` + `ImapBindingRepository.by_subject` (`imap_hub_server/rbac_seam.py`). Enforced at `_check_profile_access` (point check + `profile_list` filter) and the MCP tool gate (`ToolRegistry._authorise`, grant-only).
