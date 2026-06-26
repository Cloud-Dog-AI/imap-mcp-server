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

import os
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from tests.helpers.ports import listener_host, listener_port


@dataclass(frozen=True, slots=True)
class ApplicationServer:
    api_base_url: str
    web_base_url: str
    mcp_base_url: str
    a2a_base_url: str
    api_base_path: str
    web_base_path: str
    mcp_base_path: str
    a2a_base_path: str
    api_key: str

    def api_path(self, suffix: str) -> str:
        tail = suffix if suffix.startswith("/") else f"/{suffix}"
        return f"{self.api_base_path}{tail}"

    def mcp_path(self, suffix: str) -> str:
        tail = suffix if suffix.startswith("/") else f"/{suffix}"
        return f"{self.mcp_base_path}{tail}"


ROOT = Path(__file__).resolve().parents[2]
SERVER_CONTROL = ROOT / "server_control.sh"


@dataclass(frozen=True, slots=True)
class RuntimeMode:
    mode: str
    use_external_runtime: bool
    api_base_url: str
    web_base_url: str
    mcp_base_url: str
    a2a_base_url: str
    api_base_path: str
    web_base_path: str
    mcp_base_path: str
    a2a_base_path: str


def _runtime_api_key() -> str:
    for key_name in ("IMAP_API_KEY", "CLOUD_DOG__IMAP__API_KEY", "API_KEY"):
        value = os.environ.get(key_name, "").strip()
        if value:
            return value
    raise RuntimeError(
        "Missing API key: set IMAP_API_KEY/CLOUD_DOG__IMAP__API_KEY/API_KEY via env or Vault."
    )


def _normalise_base_path(value: str, fallback: str) -> str:
    candidate = (value or fallback).strip() or fallback
    if not candidate.startswith("/"):
        candidate = "/" + candidate
    if candidate != "/":
        candidate = candidate.rstrip("/")
    return candidate


def _runtime_mode() -> RuntimeMode:
    mode = os.environ.get("TEST_RUNTIME_MODE", "local-server").strip().lower()
    if mode not in {"local-server", "local-docker", "remote-runtime"}:
        raise RuntimeError(f"Invalid TEST_RUNTIME_MODE: {mode}")

    use_external_raw = os.environ.get("TEST_USE_EXTERNAL_RUNTIME", "false").strip().lower()
    use_external_runtime = use_external_raw in {"1", "true", "yes", "on"}
    if mode in {"local-docker", "remote-runtime"} and not use_external_runtime:
        raise RuntimeError(f"TEST_USE_EXTERNAL_RUNTIME must be true for TEST_RUNTIME_MODE={mode}")

    api_base_url = os.environ.get("TEST_API_BASE_URL", "").strip()
    if not api_base_url:
        api_base_url = (
            f"http://{listener_host('CLOUD_DOG__API_SERVER__HOST')}:"
            f"{listener_port('CLOUD_DOG__API_SERVER__PORT')}"
        )
    mcp_base_url = os.environ.get("TEST_MCP_BASE_URL", "").strip()
    if not mcp_base_url:
        mcp_base_url = (
            f"http://{listener_host('CLOUD_DOG__MCP_SERVER__HOST')}:"
            f"{listener_port('CLOUD_DOG__MCP_SERVER__PORT')}"
        )
    web_base_url = os.environ.get("TEST_WEB_ROOT_URL", "").strip()
    if not web_base_url:
        web_base_url = (
            f"http://{listener_host('CLOUD_DOG__WEB_SERVER__HOST')}:"
            f"{listener_port('CLOUD_DOG__WEB_SERVER__PORT')}"
        )
    a2a_base_url = os.environ.get("TEST_A2A_ROOT_URL", "").strip()
    if not a2a_base_url:
        a2a_base_url = (
            f"http://{listener_host('CLOUD_DOG__A2A_SERVER__HOST')}:"
            f"{listener_port('CLOUD_DOG__A2A_SERVER__PORT')}"
        )
    api_base_path = _normalise_base_path(os.environ.get("TEST_API_BASE_PATH", ""), "/api/v1")
    web_base_path = _normalise_base_path(os.environ.get("TEST_WEB_BASE_PATH", ""), "/")
    mcp_base_path = _normalise_base_path(os.environ.get("TEST_MCP_BASE_PATH", ""), "/mcp")
    a2a_base_path = _normalise_base_path(os.environ.get("TEST_A2A_BASE_PATH", ""), "/a2a")
    return RuntimeMode(
        mode=mode,
        use_external_runtime=use_external_runtime,
        api_base_url=api_base_url.rstrip("/"),
        web_base_url=web_base_url.rstrip("/"),
        mcp_base_url=mcp_base_url.rstrip("/"),
        a2a_base_url=a2a_base_url.rstrip("/"),
        api_base_path=api_base_path,
        web_base_path=web_base_path,
        mcp_base_path=mcp_base_path,
        a2a_base_path=a2a_base_path,
    )


def _server_env(api_key: str) -> dict[str, str]:
    env = os.environ.copy()
    env["IMAP_API_KEY"] = api_key
    return env


def _run_server_control(
    action: str,
    env: dict[str, str],
    env_files: list[Path],
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    env = dict(env)
    env["CLOUD_DOG_ENV_FILES"] = ",".join(str(item) for item in env_files)
    return subprocess.run(
        [str(SERVER_CONTROL), "--env", str(env_files[0]), action, "all"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=check,
    )


def _wait_for_http_200(
    url: str,
    timeout_seconds: float = 60.0,
    *,
    headers: dict[str, str] | None = None,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = "no response"
    while time.monotonic() < deadline:
        try:
            # Health readiness can include live IMAP probes, so allow a wider read timeout.
            response = httpx.get(url, timeout=30.0, headers=headers, follow_redirects=True)
            if response.status_code == 200:
                return
            last_error = f"status={response.status_code} body={response.text[:120]}"
        except Exception as exc:  # noqa: BLE001
            last_error = repr(exc)
        time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def _wait_for_api_runtime(runtime: RuntimeMode) -> None:
    candidates = [
        f"{runtime.api_base_url}/health",
        f"{runtime.api_base_url}{runtime.api_base_path}/health",
    ]
    errors: list[str] = []
    for candidate in candidates:
        try:
            _wait_for_http_200(candidate)
            return
        except RuntimeError as exc:
            errors.append(str(exc))
    raise RuntimeError(" | ".join(errors))


def _wait_for_mcp_runtime(runtime: RuntimeMode, api_key: str) -> None:
    candidates = [
        (
            f"{runtime.mcp_base_url}{runtime.mcp_base_path}/tools",
            {"x-api-key": api_key},
        ),
        (f"{runtime.mcp_base_url}/tools", {"x-api-key": api_key}),
        (f"{runtime.mcp_base_url}{runtime.mcp_base_path}", None),
        (f"{runtime.mcp_base_url}/health", None),
    ]
    errors: list[str] = []
    for candidate, headers in candidates:
        try:
            _wait_for_http_200(candidate, headers=headers)
            return
        except RuntimeError as exc:
            errors.append(str(exc))
    raise RuntimeError(" | ".join(errors))


def _wait_for_web_runtime(runtime: RuntimeMode) -> None:
    candidates = [
        f"{runtime.web_base_url}{runtime.web_base_path}",
        runtime.web_base_url,
    ]
    errors: list[str] = []
    for candidate in candidates:
        try:
            _wait_for_http_200(candidate)
            return
        except RuntimeError as exc:
            errors.append(str(exc))
    raise RuntimeError(" | ".join(errors))


def _wait_for_a2a_runtime(runtime: RuntimeMode, api_key: str) -> None:
    candidates = [
        (
            f"{runtime.a2a_base_url}{runtime.a2a_base_path}/tools",
            {"x-api-key": api_key, "Authorization": f"Bearer {api_key}"},
        ),
        (f"{runtime.a2a_base_url}{runtime.a2a_base_path}/health", None),
    ]
    errors: list[str] = []
    for candidate, headers in candidates:
        try:
            _wait_for_http_200(candidate, headers=headers)
            return
        except RuntimeError as exc:
            errors.append(str(exc))
    raise RuntimeError(" | ".join(errors))


@pytest.fixture(autouse=True)
def _webui_runner_runtime_env(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Start the real local runtime for Node Playwright WebUI wrapper tests."""

    if request.node.get_closest_marker("webui") is None:
        yield
        return

    server = request.getfixturevalue("application_server")
    monkeypatch.setenv("WEBUI_BASE_URL", server.web_base_url)
    monkeypatch.setenv("IMAP_API_KEY", server.api_key)
    yield


@pytest.fixture(scope="session")
def application_server(request: pytest.FixtureRequest) -> Iterator[ApplicationServer]:
    if not SERVER_CONTROL.exists():
        pytest.fail(f"Missing server control script: {SERVER_CONTROL}")

    try:
        api_key = _runtime_api_key()
        runtime = _runtime_mode()
    except RuntimeError as exc:
        pytest.fail(str(exc))

    env_values = request.config.getoption("--env")
    if isinstance(env_values, str):
        env_items = [env_values]
    elif isinstance(env_values, list):
        env_items = env_values
    else:
        env_items = []
    env_files = [Path(item) for item in env_items] if env_items else [ROOT / "tests" / "env-AT"]
    missing = [path for path in env_files if not path.exists()]
    if missing:
        pytest.fail(f"Missing application env file(s): {', '.join(str(path) for path in missing)}")

    server_env = _server_env(api_key)

    if runtime.use_external_runtime:
        try:
            _wait_for_api_runtime(runtime)
            _wait_for_web_runtime(runtime)
            _wait_for_mcp_runtime(runtime, api_key)
            _wait_for_a2a_runtime(runtime, api_key)
        except RuntimeError as exc:
            pytest.fail(
                "External application runtime unavailable for "
                f"mode={runtime.mode} api={runtime.api_base_url} mcp={runtime.mcp_base_url}: {exc}"
            )
        yield ApplicationServer(
            api_base_url=runtime.api_base_url,
            web_base_url=runtime.web_base_url,
            mcp_base_url=runtime.mcp_base_url,
            a2a_base_url=runtime.a2a_base_url,
            api_base_path=runtime.api_base_path,
            web_base_path=runtime.web_base_path,
            mcp_base_path=runtime.mcp_base_path,
            a2a_base_path=runtime.a2a_base_path,
            api_key=api_key,
        )
        return

    _run_server_control("stop", env=server_env, env_files=env_files, check=False)
    started = False
    try:
        start = _run_server_control("start", env=server_env, env_files=env_files, check=False)
        if start.returncode != 0:
            pytest.fail(
                f"Failed to start application services:\nstdout:\n{start.stdout}\nstderr:\n{start.stderr}"
            )
        started = True

        _wait_for_api_runtime(runtime)
        _wait_for_web_runtime(runtime)
        _wait_for_mcp_runtime(runtime, api_key)
        _wait_for_a2a_runtime(runtime, api_key)
        yield ApplicationServer(
            api_base_url=runtime.api_base_url,
            web_base_url=runtime.web_base_url,
            mcp_base_url=runtime.mcp_base_url,
            a2a_base_url=runtime.a2a_base_url,
            api_base_path=runtime.api_base_path,
            web_base_path=runtime.web_base_path,
            mcp_base_path=runtime.mcp_base_path,
            a2a_base_path=runtime.a2a_base_path,
            api_key=api_key,
        )
    finally:
        if started:
            _run_server_control("stop", env=server_env, env_files=env_files, check=False)
