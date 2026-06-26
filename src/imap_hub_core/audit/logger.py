"""imap-mcp-server module."""

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

# Covers: FR-09
# Covers: CS-014

import json
from inspect import signature
from typing import Any

from cloud_dog_storage.backends.local import LocalStorage
from cloud_dog_logging import get_audit_logger, setup_logging
from cloud_dog_logging.audit_schema import Actor, AuditEvent, Target

from imap_hub_core.audit.audit_log import append_audit_line
from imap_hub_core.audit.events import AuditRecord
from imap_hub_core.storage_paths import join_fs_path, parent_fs_path
from imap_hub_server.logging_runtime import ensure_runtime_log_permissions


def default_app_log_path(audit_path: str) -> str:
    """Derive the application log path from the configured audit log path."""
    return join_fs_path(parent_fs_path(audit_path), "application.log.jsonl")


def _event_payload(event: AuditEvent) -> dict[str, Any]:
    """Serialise AuditEvent across pydantic v1/v2 variants."""
    to_dict = getattr(event, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    dump = getattr(event, "model_dump", None)
    if callable(dump):
        return dump(exclude_none=True, mode="json")
    json_dump = getattr(event, "json", None)
    if callable(json_dump):
        return json.loads(json_dump(exclude_none=True))
    legacy_dump = getattr(event, "dict", None)
    if callable(legacy_dump):
        return legacy_dump(exclude_none=True)
    raise TypeError("Unsupported AuditEvent serialisation API")


class AuditWriter:
    """Persist typed audit records using cloud_dog_logging."""

    def __init__(
        self,
        audit_path: str,
        service_name: str = "imap-mcp-server",
        *,
        server_id: str = "imap-mcp-local",
        environment: str = "unknown",
        app_log_path: str | None = None,
        platform_audit_path: str | None = None,
        integrity_log_path: str | None = None,
    ) -> None:
        """
        Purpose: Implement `__init__` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        LocalStorage(root_path=parent_fs_path(audit_path))
        self._service_name = service_name
        self._server_id = server_id
        self._environment = environment
        self._canonical_audit_path = audit_path
        self._platform_audit_path = platform_audit_path or audit_path
        self._app_log_path = app_log_path or default_app_log_path(self._platform_audit_path)
        self._integrity_log_path = integrity_log_path
        setup_logging(
            {
                "service_name": service_name,
                "service_instance": server_id,
                "environment": environment,
                "log": {
                    "format": "json",
                    "console": False,
                    "app_log": self._app_log_path,
                    "audit_log": self._platform_audit_path,
                    "integrity": {
                        "enabled": True,
                        "log_file": integrity_log_path or "logs/audit-integrity.log",
                    },
                },
            }
        )
        self._logger: Any = get_audit_logger()
        self._actor_fields = set(signature(Actor).parameters.keys())
        self._target_fields = set(signature(Target).parameters.keys())
        self._audit_event_fields = set(signature(AuditEvent).parameters.keys())
        ensure_runtime_log_permissions(
            app_log_path=self._app_log_path,
            audit_log_path=self._platform_audit_path,
            integrity_log_path=self._integrity_log_path,
            canonical_audit_path=self._canonical_audit_path,
        )

    def _build_actor(self, record: AuditRecord) -> Actor:
        """Construct an audit actor compatible with the installed schema version."""
        payload: dict[str, Any] = {
            "type": record.actor.actor_type,
            "id": record.actor.actor_id,
            "roles": record.actor.roles,
        }
        if "ip" in self._actor_fields:
            payload["ip"] = record.actor.ip
        if "user_agent" in self._actor_fields:
            payload["user_agent"] = record.actor.user_agent
        return Actor(**payload)

    def emit(self, record: AuditRecord) -> None:
        """Emit a single audit event with redacted parameters."""
        outcome = record.status
        if outcome == "ok":
            outcome = "success"
        elif outcome in {"failed", "fail"}:
            outcome = "failure"
        elif outcome not in {"success", "failure", "error", "denied"}:
            outcome = "error"

        target_payload: dict[str, Any] = {
            "type": record.target_type or "operation",
            "id": record.target_id or record.operation or "unknown",
        }
        if "name" in self._target_fields:
            target_payload["name"] = record.target_name
        target = Target(**target_payload)

        event_payload: dict[str, Any] = {
            "event_type": f"imap_mcp.{record.operation}",
            "actor": self._build_actor(record),
            "action": record.operation,
            "outcome": outcome,
            "correlation_id": record.correlation_id,
            "service": self._service_name,
            "timestamp": record.timestamp,
            "target": target,
            "details": {
                "component": record.component,
                "source_identifier": record.source_identifier,
                "profile_id": record.profile_id,
                "params": record.redacted_params(),
                "warnings": record.warnings,
                "errors": record.errors,
            },
        }
        if "service_instance" in self._audit_event_fields:
            event_payload["service_instance"] = record.server_id or self._server_id
        if "environment" in self._audit_event_fields:
            event_payload["environment"] = record.environment or self._environment
        if "severity" in self._audit_event_fields:
            event_payload["severity"] = "INFO"

        event = AuditEvent(**event_payload)
        self._logger.emit(event)
        if self._canonical_audit_path != self._platform_audit_path:
            append_audit_line(self._canonical_audit_path, _event_payload(event))
        ensure_runtime_log_permissions(
            app_log_path=self._app_log_path,
            audit_log_path=self._platform_audit_path,
            integrity_log_path=self._integrity_log_path,
            canonical_audit_path=self._canonical_audit_path,
        )

    def close(self) -> None:
        """Flush and close the logging sink when available."""
        flush = getattr(self._logger, "flush", None)
        if callable(flush):
            flush()
        close = getattr(self._logger, "close", None)
        if callable(close):
            close()
