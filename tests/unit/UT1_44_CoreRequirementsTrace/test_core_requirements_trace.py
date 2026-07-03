from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from imap_hub_core.audit.events import AuditActor, AuditRecord
from imap_hub_core.config.models import (
    AuthProfileConfig,
    FolderPolicyConfig,
    IMAPProfileConfig,
    PartsPolicyConfig,
    ProfileConfig,
    RetentionConfig,
    SyncProfileConfig,
    TLSConfig,
    WriteConfig,
)
from imap_hub_core.imap.folder_policy import filter_folders
from imap_hub_core.ledger.similarity import build_similarity_key
from imap_hub_core.security.rbac import AccessDeniedError, build_rbac_engine, require_tool_access
from imap_hub_core.tools.definitions import (
    MailDownloadAttachmentInput,
    MailMoveMessagesInput,
    MailSearchInput,
    ToolEnvelope,
)

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"


def _minimal_profile(**overrides: object) -> ProfileConfig:
    data = {
        "provider": "imap_generic",
        "imap": {"host": "imap.example.test", "port": 993, "security": "ssl"},
        "auth": {"mode": "app_password"},
        "sync": {
            "retention": {
                "max_age_days": 30,
                "max_total_bytes": 1000000,
                "max_messages": 100,
            },
            "folder_policy": {
                "include_globs": ["INBOX", "Ops/*"],
                "exclude_globs": ["Ops/Archive"],
            },
            "parts_policy": {},
        },
    }
    data.update(overrides)
    return ProfileConfig.model_validate(data)


@pytest.mark.UT
@pytest.mark.api
@pytest.mark.req("FR-01")
def test_core_interfaces_expose_canonical_api_mcp_a2a_webui_sources() -> None:
    api_server = (SRC / "imap_hub_server" / "api_server.py").read_text()
    mcp_server = (SRC / "imap_hub_server" / "mcp_server.py").read_text()
    web_server = (SRC / "imap_hub_server" / "web_server.py").read_text()

    assert "join_base_path(api_base_path, \"/health\")" in api_server
    assert "@app.get(\"/a2a/tools\"" in api_server
    assert "create_a2a_events_router" in api_server
    assert "\"tools/list\"" in mcp_server
    assert "join_base_path(web_base_path, \"/login\")" in web_server


@pytest.mark.UT
@pytest.mark.internal
@pytest.mark.req("FR-02")
def test_config_models_reject_unknown_runtime_fields_and_keep_tls_closed() -> None:
    assert TLSConfig().allow_self_signed is False
    assert WriteConfig().enabled is False

    with pytest.raises(ValidationError):
        IMAPProfileConfig.model_validate(
            {
                "host": "imap.example.test",
                "port": 993,
                "security": "ssl",
                "hard_coded_secret": "<secret>",
            }
        )


@pytest.mark.UT
@pytest.mark.api
@pytest.mark.req("FR-03")
def test_profile_model_captures_mailbox_connection_folder_and_retention_policy() -> None:
    profile = _minimal_profile()

    assert profile.provider == "imap_generic"
    assert profile.imap.host == "imap.example.test"
    assert profile.auth.mode == "app_password"
    assert profile.sync.retention.max_messages == 100
    assert filter_folders(
        ["INBOX", "Ops/Queue", "Ops/Archive", "Trash"],
        profile.sync.folder_policy.include_globs,
        profile.sync.folder_policy.exclude_globs,
    ) == ["INBOX", "Ops/Queue"]


@pytest.mark.UT
@pytest.mark.api
@pytest.mark.req("FR-04")
def test_rbac_enforces_profile_read_and_write_permissions() -> None:
    engine = build_rbac_engine({"reader": {"mail_search"}, "admin": {"*"}})
    engine.assign_role_to_user("alice", "reader")

    require_tool_access(engine, "alice", "mail_search")
    with pytest.raises(AccessDeniedError):
        require_tool_access(engine, "alice", "admin_profile_update")


@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-05")
def test_mail_retrieval_and_attachment_schemas_use_stable_envelopes() -> None:
    search = MailSearchInput.model_validate({"profile_id": "ops", "query": "invoice"})
    download = MailDownloadAttachmentInput.model_validate(
        {"profile_id": "ops", "uid": "42", "part_id": "2"}
    )
    envelope = ToolEnvelope(ok=True, result={"messages": []})

    assert search.mode == "cache"
    assert download.folder == "INBOX"
    assert envelope.model_dump()["errors"] == []


@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-06")
def test_mutation_inputs_are_explicit_and_profile_write_defaults_off() -> None:
    profile = _minimal_profile()
    mutation = MailMoveMessagesInput.model_validate(
        {"profile_id": "ops", "uids": ["1", "2"], "destination_folder": "Archive"}
    )

    assert profile.write.enabled is False
    assert mutation.folder == "INBOX"
    assert mutation.destination_folder == "Archive"


@pytest.mark.UT
@pytest.mark.internal
@pytest.mark.req("FR-07")
def test_search_ledger_similarity_key_is_deterministic_for_delta_queries() -> None:
    key_a, canonical_a = build_similarity_key(
        "ops", "cache", " Invoice  ", {"folder": "INBOX", "after": "2026-06-01"}
    )
    key_b, canonical_b = build_similarity_key(
        "ops", "cache", "invoice", {"after": "2026-06-01", "folder": "INBOX"}
    )

    assert key_a == key_b
    assert canonical_a == canonical_b
    assert canonical_a["query_norm"] == "invoice"


@pytest.mark.UT
@pytest.mark.internal
@pytest.mark.req("FR-08")
def test_tls_policy_supports_ssl_starttls_and_explicit_self_signed_opt_in() -> None:
    ssl_profile = _minimal_profile()
    starttls_profile = _minimal_profile(
        imap={
            "host": "imap.example.test",
            "port": 143,
            "security": "starttls",
            "tls": {"allow_self_signed": True},
        }
    )

    assert ssl_profile.imap.security == "ssl"
    assert ssl_profile.imap.tls.allow_self_signed is False
    assert starttls_profile.imap.security == "starttls"
    assert starttls_profile.imap.tls.allow_self_signed is True


@pytest.mark.UT
@pytest.mark.internal
@pytest.mark.req("FR-09")
def test_audit_records_redact_secrets_and_keep_correlation_identity() -> None:
    record = AuditRecord(
        operation="mail_search",
        status="success",
        correlation_id="corr-123",
        actor=AuditActor(actor_id="alice", roles=["reader"]),
        profile_id="ops",
        params={"query": "invoice", "api_key": "<api-key>"},
    )

    assert record.correlation_id == "corr-123"
    assert record.redacted_params()["api_key"] == "***REDACTED***"
    assert record.redacted_params()["query"] == "invoice"


@pytest.mark.UT
@pytest.mark.webui
@pytest.mark.req("FR-10")
def test_webui_routes_are_api_backed_and_do_not_bypass_policy() -> None:
    web_server = (SRC / "imap_hub_server" / "web_server.py").read_text()

    assert "WebApiProxy.from_config" in web_server
    assert "_server_base(config.api_server.host, config.api_server.port)" in web_server
    assert '"/api"' in web_server
    assert '"/mcp"' in web_server
    assert '"/a2a"' in web_server
    assert "__cloudDogDirectListener" in web_server
    assert "async def proxy_web_api" in web_server


@pytest.mark.UT
@pytest.mark.api
@pytest.mark.req("FR-11")
def test_webui_api_parity_exposes_admin_identity_and_profile_endpoints() -> None:
    endpoint_identity = (SRC / "imap_hub_server" / "admin" / "endpoint_identity.py").read_text()
    endpoint_profiles = (SRC / "imap_hub_server" / "admin" / "endpoint_profiles.py").read_text()

    for route_fragment in ("/admin/users", "/admin/groups", "/admin/api-keys"):
        assert route_fragment in endpoint_identity
    assert "/admin/profiles" in endpoint_profiles
    assert "Request" in endpoint_identity


@pytest.mark.UT
@pytest.mark.api
@pytest.mark.req("FR-12")
def test_index_reconcile_contract_is_present_in_api_and_tool_layers() -> None:
    endpoint_profiles = (
        SRC / "imap_hub_server" / "admin" / "endpoint_profiles.py"
    ).read_text()
    index_manager = (SRC / "imap_hub_core" / "index" / "manager.py").read_text()

    assert "/admin/index/reconcile" in endpoint_profiles
    assert "reconcile_index" in endpoint_profiles
    assert "managed reconcile workflows" in index_manager


@pytest.mark.UT
@pytest.mark.api
@pytest.mark.req("FR-13")
def test_group_admin_delegation_state_and_endpoints_are_present() -> None:
    state_models = (SRC / "imap_hub_server" / "admin" / "state_models.py").read_text()
    endpoint_identity = (SRC / "imap_hub_server" / "admin" / "endpoint_identity.py").read_text()

    assert "group_admins" in state_models
    assert "group_admin" in endpoint_identity


@pytest.mark.UT
@pytest.mark.api
@pytest.mark.negative
@pytest.mark.req("CS-004")
@pytest.mark.req("CS-003")
@pytest.mark.req("CS-002")
@pytest.mark.req("CS-001")
def test_negative_auth_and_validation_contracts_are_explicit_in_source() -> None:
    middleware = (SRC / "imap_hub_server" / "auth" / "middleware.py").read_text()
    seam = (SRC / "imap_hub_server" / "rbac_seam.py").read_text()

    assert "401" in middleware
    assert "403" in middleware
    assert "default-DENY" in seam or "Default-DENY" in seam
    with pytest.raises(ValidationError):
        MailSearchInput.model_validate({"query": "missing-profile"})
