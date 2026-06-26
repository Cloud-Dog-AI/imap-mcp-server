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

# Covers: FR-13

import os
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from tests.helpers.ports import listener_host, listener_port

ROOT = Path(__file__).resolve().parents[1]
SERVER_CONTROL = ROOT / "server_control.sh"


def _runtime_api_key() -> str:
    for key_name in ("IMAP_API_KEY", "CLOUD_DOG__IMAP__API_KEY", "API_KEY"):
        value = os.environ.get(key_name, "").strip()
        if value:
            return value
    raise RuntimeError("Missing IMAP API key in the active test environment.")


def _api_base_url() -> str:
    return (
        f"http://{listener_host('CLOUD_DOG__API_SERVER__HOST')}:"
        f"{listener_port('CLOUD_DOG__API_SERVER__PORT')}"
    )


def _run_server_control(
    action: str,
    *,
    env_file: Path,
    env: dict[str, str],
    check: bool,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SERVER_CONTROL), "--env", str(env_file), action, "all"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=check,
    )


def _wait_for_health(url: str, timeout_seconds: float = 60.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = "no response"
    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=20.0)
            if response.status_code == 200:
                return
            last_error = f"status={response.status_code} body={response.text[:200]}"
        except Exception as exc:  # noqa: BLE001
            last_error = repr(exc)
        time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def _env_file_from_request(request: pytest.FixtureRequest) -> Path:
    values = request.config.getoption("--env")
    if isinstance(values, str):
        raw_values = [values]
    elif isinstance(values, list):
        raw_values = values
    else:
        raw_values = []
    candidate = Path(raw_values[0]) if raw_values else ROOT / "tests" / "env-AT"
    if not candidate.exists():
        raise RuntimeError(f"Missing env file for group-admin ST: {candidate}")
    return candidate


def _admin_headers(api_key: str) -> dict[str, str]:
    return {
        "x-api-key": api_key,
        "Authorization": f"Bearer {api_key}",
        "x-role": "admin",
    }


def _user_headers(api_key: str) -> dict[str, str]:
    return {
        "x-api-key": api_key,
        "Authorization": f"Bearer {api_key}",
    }


@pytest.fixture(scope="module")
def running_api_server(request: pytest.FixtureRequest) -> Iterator[tuple[str, str]]:
    api_key = _runtime_api_key()
    env_file = _env_file_from_request(request)
    server_env = os.environ.copy()
    server_env["IMAP_API_KEY"] = api_key
    _run_server_control("stop", env_file=env_file, env=server_env, check=False)
    started = False
    try:
        start = _run_server_control("start", env_file=env_file, env=server_env, check=False)
        if start.returncode != 0:
            pytest.fail(
                f"Failed to start runtime for group-admin ST:\nstdout:\n{start.stdout}\n\nstderr:\n{start.stderr}"
            )
        started = True
        _wait_for_health(f"{_api_base_url()}/health")
        yield _api_base_url(), api_key
    finally:
        if started:
            _run_server_control("stop", env_file=env_file, env=server_env, check=False)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.negative
@pytest.mark.req("FR-13")
@pytest.mark.req("FR-11")
@pytest.mark.req("CS-004")
@pytest.mark.req("CS-009")
@pytest.mark.req("CS-010")


def test_st_group_admin_delegation(running_api_server: tuple[str, str]) -> None:
    api_base_url, seed_api_key = running_api_server
    suffix = uuid4().hex[:8]
    admin_headers = _admin_headers(seed_api_key)
    group_id = f"w28a509_group_{suffix}"
    other_group_id = f"w28a509_other_group_{suffix}"
    user1_id = f"w28a509_user1_{suffix}"
    user2_id = f"w28a509_user2_{suffix}"
    blocked_group_user_id = f"w28a509_blocked_group_{suffix}"
    blocked_system_user_id = f"w28a509_blocked_system_{suffix}"
    managed_api_key_id = ""

    with httpx.Client(base_url=api_base_url, timeout=30.0) as client:
        try:
            create_group = client.post(
                "/api/v1/admin/groups",
                headers=admin_headers,
                json={
                    "group_id": group_id,
                    "name": group_id,
                    "description": "W28A-509 delegated admin group",
                },
            )
            assert create_group.status_code == 200, create_group.text

            create_other_group = client.post(
                "/api/v1/admin/groups",
                headers=admin_headers,
                json={
                    "group_id": other_group_id,
                    "name": other_group_id,
                    "description": "W28A-509 out-of-scope group",
                },
            )
            assert create_other_group.status_code == 200, create_other_group.text

            create_user1 = client.post(
                "/api/v1/admin/users",
                headers=admin_headers,
                json={
                    "user_id": user1_id,
                    "username": user1_id,
                    "email": f"{user1_id}@example.com",
                    "display_name": "W28A-509 Group Admin Candidate",
                    "role": "viewer",
                },
            )
            assert create_user1.status_code == 200, create_user1.text

            add_member = client.post(
                f"/api/v1/admin/groups/{group_id}/members",
                headers=admin_headers,
                json={"user_id": user1_id},
            )
            assert add_member.status_code == 200, add_member.text

            promote_group_admin = client.put(
                f"/api/v1/admin/groups/{group_id}",
                headers=admin_headers,
                json={"group_admins": [user1_id]},
            )
            assert promote_group_admin.status_code == 200, promote_group_admin.text
            assert user1_id in promote_group_admin.json()["result"]["group_admins"]

            create_group_admin_key = client.post(
                "/api/v1/admin/api-keys",
                headers=admin_headers,
                json={
                    "owner_user_id": user1_id,
                    "description": "W28A-509 delegated admin key",
                    "scopes": [],
                },
            )
            assert create_group_admin_key.status_code == 200, create_group_admin_key.text
            key_result = create_group_admin_key.json()["result"]
            managed_api_key_id = str(key_result["api_key_id"])
            group_admin_headers = _user_headers(str(key_result["raw_key"]))

            create_user2 = client.post(
                "/api/v1/admin/users",
                headers=group_admin_headers,
                json={
                    "user_id": user2_id,
                    "username": user2_id,
                    "email": f"{user2_id}@example.com",
                    "display_name": "W28A-509 Managed User",
                    "role": "viewer",
                    "group_id": group_id,
                },
            )
            assert create_user2.status_code == 200, create_user2.text
            assert create_user2.json()["result"]["user_id"] == user2_id

            verify_group = client.get(f"/api/v1/admin/groups/{group_id}", headers=admin_headers)
            assert verify_group.status_code == 200, verify_group.text
            group_payload = verify_group.json()["result"]
            assert user1_id in group_payload["group_admins"]
            assert user2_id in group_payload["members"]

            blocked_other_group = client.post(
                "/api/v1/admin/users",
                headers=group_admin_headers,
                json={
                    "user_id": blocked_group_user_id,
                    "username": blocked_group_user_id,
                    "email": f"{blocked_group_user_id}@example.com",
                    "display_name": "Blocked cross-group user",
                    "role": "viewer",
                    "group_id": other_group_id,
                },
            )
            assert blocked_other_group.status_code == 403, blocked_other_group.text

            blocked_system_level = client.post(
                "/api/v1/admin/users",
                headers=group_admin_headers,
                json={
                    "user_id": blocked_system_user_id,
                    "username": blocked_system_user_id,
                    "email": f"{blocked_system_user_id}@example.com",
                    "display_name": "Blocked system-level user",
                    "role": "viewer",
                },
            )
            assert blocked_system_level.status_code == 403, blocked_system_level.text
        finally:
            if managed_api_key_id:
                client.delete(
                    f"/api/v1/admin/api-keys/{managed_api_key_id}",
                    headers=admin_headers,
                )
            for user_id in (
                blocked_group_user_id,
                blocked_system_user_id,
                user2_id,
                user1_id,
            ):
                client.delete(f"/api/v1/admin/users/{user_id}", headers=admin_headers)
            for created_group_id in (other_group_id, group_id):
                client.delete(f"/api/v1/admin/groups/{created_group_id}", headers=admin_headers)
