"""Helpers for W28A-408-F WebUI Playwright AT cases."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from tests.helpers.ports import listener_host, listener_port


RUNNER = Path(__file__).resolve().parent / "webui_e2e_runner.mjs"


def run_webui_case(case_id: str) -> dict[str, object]:
    env = os.environ.copy()
    env.setdefault(
        "WEBUI_BASE_URL",
        f"http://{listener_host('CLOUD_DOG__WEB_SERVER__HOST')}:{listener_port('CLOUD_DOG__WEB_SERVER__PORT')}",
    )
    completed = subprocess.run(
        ["node", str(RUNNER), case_id],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    stdout = completed.stdout.strip().splitlines()
    stderr = completed.stderr.strip()
    payload_line = stdout[-1] if stdout else "{}"
    try:
        payload = json.loads(payload_line)
    except json.JSONDecodeError:
        payload = {
            "caseId": case_id,
            "status": "FAIL",
            "details": "Runner did not return JSON",
            "stdout": completed.stdout,
        }
    payload["exit_code"] = completed.returncode
    payload["stderr"] = stderr
    return payload
