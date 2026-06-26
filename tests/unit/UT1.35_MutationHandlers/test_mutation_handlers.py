# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from imap_hub_core.audit.context import AuditRequestContext, reset_audit_request_context, set_audit_request_context
from imap_hub_core.tools.handlers import ImapToolHandlers
import pytest


@dataclass
class _FakeAuditWriter:
    records: list[Any] = field(default_factory=list)

    def emit(self, record: Any) -> None:
        self.records.append(record)


class _FakeImapClient:
    def __init__(self) -> None:
        self.stores: list[tuple[str, str, str]] = []
        self.copies: list[tuple[str, str]] = []
        self.expunge_calls = 0
        self.logout_calls = 0

    def uid(self, command: str, uid: str, *args: str):
        if command == "STORE":
            action, flag = args
            self.stores.append((uid, action, flag))
            return "OK", [b""]
        if command == "COPY":
            destination, = args
            self.copies.append((uid, destination))
            return "OK", [b""]
        raise AssertionError(f"Unexpected UID command: {command}")

    def store(self, uid: str, action: str, flag: str):
        self.stores.append((uid, action, flag))
        return "OK", [b""]

    def copy(self, uid: str, destination: str):
        self.copies.append((uid, destination))
        return "OK", [b""]

    def expunge(self):
        self.expunge_calls += 1
        return "OK", [b""]

    def logout(self):
        self.logout_calls += 1
        return "BYE", [b""]


def _handlers(write_enabled: bool, audit_writer: _FakeAuditWriter) -> ImapToolHandlers:
    return ImapToolHandlers(
        profiles={"operations": {"write": {"enabled": write_enabled}}},
        audit_writer=audit_writer,
    )


def _admin_context() -> AuditRequestContext:
    return AuditRequestContext(
        correlation_id="ut135-mutation-handlers",
        actor_id="unit-admin",
        roles=["admin"],
        source_identifier="unit-test",
        component="unit-test",
        server_id="imap-mcp-unit",
        environment="test",
    )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-06")


def test_ut135_mutation_handlers_return_write_disabled_when_policy_off() -> None:
    audit = _FakeAuditWriter()
    handlers = _handlers(write_enabled=False, audit_writer=audit)

    payload = {"profile_id": "operations", "uids": ["1"], "folder": "INBOX"}
    token = set_audit_request_context(_admin_context())
    try:
        response = handlers.mail_delete_messages(payload)
    finally:
        reset_audit_request_context(token)

    assert response["ok"] is False
    assert response["errors"][0]["code"] == "write_disabled"
    assert audit.records
    assert audit.records[-1].operation == "mail_delete_messages"
    assert audit.records[-1].status == "denied"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-06")


def test_ut135_mail_set_seen_executes_imap_store_when_policy_on(monkeypatch) -> None:
    audit = _FakeAuditWriter()
    handlers = _handlers(write_enabled=True, audit_writer=audit)
    fake_client = _FakeImapClient()

    monkeypatch.setattr(
        handlers,
        "_open_imap_client",
        lambda profile_id, folder, readonly: (fake_client, object()),
    )

    token = set_audit_request_context(_admin_context())
    try:
        response = handlers.mail_set_seen(
            {"profile_id": "operations", "uids": ["10", "11"], "seen": True, "folder": "INBOX"}
        )
    finally:
        reset_audit_request_context(token)

    assert response["ok"] is True
    assert response["result"]["updated"] == ["10", "11"]
    assert fake_client.stores == [
        ("10", "+FLAGS.SILENT", "\\Seen"),
        ("11", "+FLAGS.SILENT", "\\Seen"),
    ]
    assert fake_client.expunge_calls == 1
    assert audit.records[-1].operation == "mail_set_seen"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-06")


def test_ut135_mail_move_messages_executes_copy_and_delete(monkeypatch) -> None:
    audit = _FakeAuditWriter()
    handlers = _handlers(write_enabled=True, audit_writer=audit)
    fake_client = _FakeImapClient()

    monkeypatch.setattr(
        handlers,
        "_open_imap_client",
        lambda profile_id, folder, readonly: (fake_client, object()),
    )

    token = set_audit_request_context(_admin_context())
    try:
        response = handlers.mail_move_messages(
            {
                "profile_id": "operations",
                "uids": ["20"],
                "folder": "INBOX",
                "destination_folder": "Archive",
            }
        )
    finally:
        reset_audit_request_context(token)

    assert response["ok"] is True
    assert response["result"]["moved"] == ["20"]
    assert fake_client.copies == [("20", "Archive")]
    assert fake_client.stores == [("20", "+FLAGS.SILENT", "\\Deleted")]
    assert fake_client.expunge_calls == 1
    assert audit.records[-1].operation == "mail_move_messages"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-06")


def test_ut135_mail_delete_messages_executes_store_and_expunge(monkeypatch) -> None:
    audit = _FakeAuditWriter()
    handlers = _handlers(write_enabled=True, audit_writer=audit)
    fake_client = _FakeImapClient()

    monkeypatch.setattr(
        handlers,
        "_open_imap_client",
        lambda profile_id, folder, readonly: (fake_client, object()),
    )

    token = set_audit_request_context(_admin_context())
    try:
        response = handlers.mail_delete_messages(
            {"profile_id": "operations", "uids": ["30", "31"], "folder": "INBOX"}
        )
    finally:
        reset_audit_request_context(token)

    assert response["ok"] is True
    assert response["result"]["deleted"] == ["30", "31"]
    assert fake_client.stores == [
        ("30", "+FLAGS.SILENT", "\\Deleted"),
        ("31", "+FLAGS.SILENT", "\\Deleted"),
    ]
    assert fake_client.expunge_calls == 1
    assert audit.records[-1].operation == "mail_delete_messages"
