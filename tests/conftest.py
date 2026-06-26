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

import asyncio
import json
import os
import re
import sys
from contextlib import suppress
from functools import lru_cache
from pathlib import Path

import pytest
from cloud_dog_config.compiler.vault_resolver import resolve_vault_identifier
from cloud_dog_config.vault.client import VaultClient, VaultConnectionConfig

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

_VAULT_REF_PATTERN = re.compile(r"^\$\{(vault\.[^}]+)\}$")


def _install_anyio_asyncio_cancel_compat() -> None:
    """Avoid Python 3.11+ Task.cancel(msg=...) deprecations during ASGI tests."""
    if sys.version_info < (3, 11):
        return

    try:
        from anyio._backends import _asyncio as anyio_asyncio
    except Exception:
        return

    cancel_scope = anyio_asyncio.CancelScope
    if getattr(cancel_scope, "_cloud_dog_cancel_compat", False):
        return

    original_is_anyio_cancellation = anyio_asyncio.is_anyio_cancellation

    def _is_anyio_cancellation(exc: asyncio.CancelledError) -> bool:
        if not exc.args:
            return True
        return original_is_anyio_cancellation(exc)

    def _deliver_cancellation(self, origin) -> bool:  # type: ignore[no-untyped-def]
        should_retry = False
        current = anyio_asyncio.current_task()
        for task in self._tasks:
            should_retry = True
            if task._must_cancel:  # type: ignore[attr-defined]
                continue

            if task is not current and (
                task is self._host_task or anyio_asyncio._task_started(task)
            ):
                waiter = task._fut_waiter  # type: ignore[attr-defined]
                if not isinstance(waiter, asyncio.Future) or not waiter.done():
                    task.cancel()
                    if (
                        task is origin._host_task
                        and origin._pending_uncancellations is not None
                    ):
                        origin._pending_uncancellations += 1

        for scope in self._child_scopes:
            if not scope._shield and not scope.cancel_called:
                should_retry = scope._deliver_cancellation(origin) or should_retry

        if origin is self:
            if should_retry:
                self._cancel_handle = anyio_asyncio.get_running_loop().call_soon(
                    self._deliver_cancellation, origin
                )
            else:
                self._cancel_handle = None

        return should_retry

    anyio_asyncio.is_anyio_cancellation = _is_anyio_cancellation
    cancel_scope._deliver_cancellation = _deliver_cancellation
    cancel_scope._cloud_dog_cancel_compat = True


def _is_unresolved_env_value(value: str | None) -> bool:
    if value is None:
        return True
    candidate = value.strip()
    if not candidate:
        return True
    return bool(_VAULT_REF_PATTERN.match(candidate))


@lru_cache(maxsize=1)
def _vault_client() -> VaultClient | None:
    addr = os.environ.get("VAULT_ADDR", "").strip()
    token = os.environ.get("VAULT_TOKEN", "").strip()
    if not addr or not token:
        return None

    mount = os.environ.get("VAULT_MOUNT_POINT", "").strip().strip("/")
    config_path = os.environ.get("VAULT_CONFIG_PATH", "").strip().strip("/")
    if config_path:
        mount = "/".join([part for part in (mount, config_path) if part])

    try:
        return VaultClient(
            VaultConnectionConfig(
                server=addr,
                token=token,
                timeout_seconds=10.0,
                mount_point=mount,
            )
        )
    except Exception:
        return None


def _extract_vault_root_tree(root: object) -> dict[str, object] | None:
    if not isinstance(root, dict):
        return None
    raw_json = root.get("json")
    if isinstance(raw_json, dict):
        return raw_json
    if isinstance(raw_json, str) and raw_json.strip():
        try:
            decoded = json.loads(raw_json)
        except ValueError:
            return None
        return decoded if isinstance(decoded, dict) else None
    content = root.get("content")
    if isinstance(content, str) and content.strip():
        try:
            decoded_content = json.loads(content)
        except ValueError:
            return None
        return decoded_content if isinstance(decoded_content, dict) else None
    return root


def _resolve_env_value_from_root_blob(identifier: str, client: VaultClient) -> str | None:
    parts = identifier.split(".")
    if len(parts) < 3 or parts[0] != "vault":
        return None
    try:
        root = client.read("secret")
    except Exception:
        return None

    current: object = _extract_vault_root_tree(root)
    for part in parts[1:]:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    if isinstance(current, (str, int, float, bool)):
        text = str(current).strip()
        return text or None
    return None


def _resolve_env_value(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return value

    match = _VAULT_REF_PATTERN.match(value)
    if match is None:
        return value

    client = _vault_client()
    if client is None:
        return value

    resolved = resolve_vault_identifier(match.group(1), vault=client)
    if isinstance(resolved, (str, int, float, bool)):
        resolved_text = str(resolved).strip()
        if resolved_text:
            return resolved_text
    root_value = _resolve_env_value_from_root_blob(match.group(1), client)
    if root_value:
        return root_value
    return value


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add required --env option for environment tier selection."""
    with suppress(ValueError):
        parser.addoption(
            "--env",
            action="append",
            required=True,
            help="Test environment(s): UT, ST, IT, AT, QT or env file path",
        )


@pytest.fixture(scope="session")
def envs(request: pytest.FixtureRequest) -> list[str]:
    """Return canonical environment IDs from --env arguments."""
    values = request.config.getoption("--env")
    if isinstance(values, str):
        raw_values = [values]
    elif isinstance(values, list):
        raw_values = values
    else:
        raw_values = []

    resolved: list[str] = []
    for value in raw_values:
        candidate = value.strip()
        if not candidate:
            continue
        if candidate.upper() in {"UT", "ST", "IT", "AT", "QT"}:
            resolved.append(candidate.upper())
            continue
        name = Path(candidate).name
        if name.startswith("env-"):
            resolved.append(name.removeprefix("env-").upper())
        else:
            resolved.append(candidate.upper())

    return list(dict.fromkeys(resolved))


def _candidate_env_paths(
    raw_value: str, env_id: str, tests_dir: Path, project_root: Path
) -> list[Path]:
    explicit = Path(raw_value)
    if explicit.exists():
        return [explicit]

    return [
        tests_dir / f"env-{env_id}",
        project_root / f"private/env-{env_id.lower()}",
        project_root / "private" / raw_value,
    ]


@pytest.fixture(scope="session", autouse=True)
def load_env_files(request: pytest.FixtureRequest, envs: list[str]) -> dict[str, str]:
    """Load env files from tests/env-<TIER> (primary) or private/env-<name> (fallback for non-Vault credentials)."""
    _install_anyio_asyncio_cancel_compat()
    values = request.config.getoption("--env")
    if isinstance(values, str):
        raw_values = [values]
    elif isinstance(values, list):
        raw_values = values
    else:
        raw_values = []

    tests_dir = Path(__file__).parent
    loaded: dict[str, str] = {}
    for raw in raw_values:
        candidate = raw.strip()
        if not candidate:
            continue
        env_id = (
            candidate.upper()
            if candidate.upper() in {"UT", "ST", "IT", "AT", "QT"}
            else Path(candidate).name
        )
        env_id = env_id.removeprefix("env-").upper()

        selected_path: Path | None = None
        for path in _candidate_env_paths(candidate, env_id, tests_dir=tests_dir, project_root=ROOT):
            if path.exists():
                selected_path = path
                break

        if selected_path is None:
            continue

        for line in selected_path.read_text(encoding="utf-8").splitlines():
            content = line.strip()
            if not content or content.startswith("#") or "=" not in content:
                continue
            key, value = content.split("=", 1)
            env_key = key.strip()
            resolved_value = _resolve_env_value(value.strip())
            if env_key in os.environ and not _is_unresolved_env_value(os.environ[env_key]):
                loaded[env_key] = os.environ[env_key]
                continue
            os.environ[env_key] = resolved_value
            loaded[env_key] = resolved_value

    return loaded


@pytest.fixture(scope="session")
def env(envs: list[str]) -> str:
    """Backwards-compatible single env fixture for existing tests."""
    return envs[0] if envs else ""


# --- PS-REQ-TEST-TRACE marker enforcement (added by rtt-2026-06-12 Instruction 3 uplift) ---
# See PS-REQ-TEST-TRACE v1.0 §6.2 — fails session if any test lacks tier + surface + req()/probe markers.

import sys

_PS_REQ_TIER_MARKERS = {"QT", "UT", "ST", "IT", "AT"}
_PS_REQ_SURFACE_MARKERS = {"api", "mcp", "a2a", "webui", "cli", "internal"}


def pytest_collection_modifyitems(config, items):
    """PS-REQ-TEST-TRACE marker enforcement."""
    failures = []
    for item in items:
        marker_names = {m.name for m in item.iter_markers()}
        is_probe = "probe" in marker_names
        if not (marker_names & _PS_REQ_TIER_MARKERS):
            failures.append(f"{item.nodeid}: missing @pytest.mark.<tier> per PS-REQ-TEST-TRACE §6")
        if not (marker_names & _PS_REQ_SURFACE_MARKERS):
            failures.append(f"{item.nodeid}: missing @pytest.mark.<surface> per PS-REQ-TEST-TRACE §6")
        if not is_probe:
            req_marker = item.get_closest_marker("req")
            if req_marker is None or not req_marker.args:
                failures.append(
                    f"{item.nodeid}: missing @pytest.mark.req('FR-NNN') per PS-REQ-TEST-TRACE §6 "
                    "(add @pytest.mark.probe to mark as orphan)"
                )
    if failures:
        msg = "PS-REQ-TEST-TRACE marker enforcement failed for " + str(len(failures)) + " test(s):\n  " + "\n  ".join(failures[:20])
        if len(failures) > 20:
            msg += f"\n  ... and {len(failures) - 20} more"
        print(msg, file=sys.stderr)
        import pytest
        pytest.exit(msg, returncode=2)
