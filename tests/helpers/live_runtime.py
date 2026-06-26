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

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from fastapi.testclient import TestClient
import pytest
from cloud_dog_config.vault.client import (  # type: ignore[import-untyped]
    VaultClient,
    VaultConnectionConfig,
)

from imap_hub_server.api_server import create_api_app
from imap_hub_server.mcp_server import create_mcp_app


@dataclass(slots=True)
class RuntimeImapSettings:
    host: str
    port: int
    username: str
    password: str


@dataclass(slots=True)
class RuntimeRouteSettings:
    api_base_path: str
    mcp_base_path: str
    web_base_path: str
    a2a_base_path: str


def _normalise_base_path(value: str, fallback: str) -> str:
    candidate = (value or fallback).strip() or fallback
    if not candidate.startswith("/"):
        candidate = "/" + candidate
    if candidate != "/":
        candidate = candidate.rstrip("/")
    return candidate


def runtime_route_settings() -> RuntimeRouteSettings:
    return RuntimeRouteSettings(
        api_base_path=_normalise_base_path(os.environ.get("TEST_API_BASE_PATH", ""), "/api/v1"),
        mcp_base_path=_normalise_base_path(os.environ.get("TEST_MCP_BASE_PATH", ""), "/mcp"),
        web_base_path=_normalise_base_path(os.environ.get("TEST_WEB_BASE_PATH", ""), "/"),
        a2a_base_path=_normalise_base_path(os.environ.get("TEST_A2A_BASE_PATH", ""), "/a2a"),
    )


def api_path(path: str) -> str:
    route = runtime_route_settings()
    suffix = path if path.startswith("/") else f"/{path}"
    return f"{route.api_base_path}{suffix}"


def mcp_path(path: str) -> str:
    route = runtime_route_settings()
    suffix = path if path.startswith("/") else f"/{path}"
    return f"{route.mcp_base_path}{suffix}"


def _default_env_files(env_files: list[str] | None = None) -> list[str]:
    if env_files:
        return env_files
    tier = os.environ.get("TEST_ENV_TIER", "").strip().upper()
    if not tier:
        raise RuntimeError(
            "Missing TEST_ENV_TIER. Provide --env tests/env-<TIER> so runtime env selection is explicit."
        )
    return [f"tests/env-{tier}"]


def _load_vault_config() -> dict[str, Any]:
    addr = os.environ.get("VAULT_ADDR", "").strip()
    token = os.environ.get("VAULT_TOKEN", "").strip()
    mount = os.environ.get("VAULT_MOUNT_POINT", "").strip()
    config_path = os.environ.get("VAULT_CONFIG_PATH", "").strip()
    if not addr or not token or not mount:
        return {}

    read_path = _vault_read_path(config_path=config_path, mount_point=mount)

    try:
        client = VaultClient(
            VaultConnectionConfig(
                server=addr.rstrip("/"),
                token=token,
                timeout_seconds=10.0,
                mount_point=mount.strip("/"),
            )
        )
        payload = client.read(read_path) or {}
    except Exception:
        return {}

    if isinstance(payload, dict):
        if "dev" in payload:
            return payload
        content_blob = payload.get("content")
        if isinstance(content_blob, str) and content_blob.strip():
            try:
                parsed = json.loads(content_blob)
                if isinstance(parsed, dict):
                    return parsed
            except ValueError:
                pass
        json_blob = payload.get("json")
        if isinstance(json_blob, dict):
            return json_blob
        if isinstance(json_blob, str) and json_blob.strip():
            try:
                parsed_json = json.loads(json_blob)
                if isinstance(parsed_json, dict):
                    return parsed_json
            except ValueError:
                pass
    return {}


def _vault_read_path(config_path: str, mount_point: str) -> str:
    cleaned_path = config_path.strip("/") or "config"
    if "/" in cleaned_path:
        return cleaned_path
    mount_root = mount_point.strip("/").split("/", 1)[0]
    if not mount_root:
        return cleaned_path
    return f"{mount_root}/{cleaned_path}"


def _vault_imap_operations_settings() -> dict[str, Any]:
    config = _load_vault_config()
    dev = config.get("dev", {})
    if not isinstance(dev, dict):
        return {}
    email = dev.get("email", {})
    if not isinstance(email, dict):
        return {}
    operations = email.get("imap_operations_cloud_dog_net", {})
    return operations if isinstance(operations, dict) else {}


def _runtime_env_value(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if value.startswith("${vault.") and value.endswith("}"):
        return ""
    return value


@contextmanager
def _runtime_overlay_env_file(env_files: list[str]) -> Iterator[list[str]]:
    # Allow explicit environment overrides for selected keys. Test env files
    # provide default values; no synthetic placeholders are injected here.
    overlay: dict[str, str] = {}
    for key in ("GOOGLE_CLIENT_SECRET", "MS_CLIENT_SECRET"):
        value = os.environ.get(key, "").strip()
        if value:
            overlay[key] = value

    if not overlay:
        yield list(env_files)
        return

    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            "w",
            delete=False,
            encoding="utf-8",
            prefix="imap-mcp-test-overlay-",
            suffix=".env",
        ) as handle:
            temp_path = Path(handle.name)
            for key, value in overlay.items():
                handle.write(f"{key}={value}\n")
            handle.flush()
            yield [*env_files, str(temp_path)]
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def runtime_imap_settings() -> RuntimeImapSettings:
    vault_imap = _vault_imap_operations_settings()
    host = (
        _runtime_env_value("IMAP_OPERATIONS_HOST")
        or str(vault_imap.get("host", "")).strip()
    )
    port_raw = (
        _runtime_env_value("IMAP_OPERATIONS_PORT")
        or str(vault_imap.get("port", "")).strip()
    )
    username = (
        _runtime_env_value("IMAP_OPERATIONS_USERNAME")
        or str(vault_imap.get("username", "")).strip()
    )
    password = (
        _runtime_env_value("IMAP_OPERATIONS_PASSWORD")
        or str(vault_imap.get("password", "")).strip()
    )

    try:
        port = int(port_raw) if port_raw else 143
    except ValueError:
        port = 143

    return RuntimeImapSettings(
        host=host,
        port=port,
        username=username,
        password=password,
    )


def api_client(env_files: list[str] | None = None) -> tuple[TestClient, str]:
    try:
        files = _default_env_files(env_files)
    except RuntimeError as exc:
        pytest.fail(str(exc))
    with _runtime_overlay_env_file(files) as resolved_files:
        app = create_api_app(env_files=resolved_files)
    client = TestClient(app)
    return client, app.state.seed_api_key


def mcp_client(env_files: list[str] | None = None) -> TestClient:
    try:
        files = _default_env_files(env_files)
    except RuntimeError as exc:
        pytest.fail(str(exc))
    with _runtime_overlay_env_file(files) as resolved_files:
        app = create_mcp_app(env_files=resolved_files)
    return TestClient(app)
