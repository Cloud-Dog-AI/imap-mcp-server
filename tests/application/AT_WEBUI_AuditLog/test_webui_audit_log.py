"""T10 WebUI E2E case."""

from __future__ import annotations

import json

from tests.application.webui_e2e import run_webui_case
import pytest
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-14")
@pytest.mark.req("FR-18")


def test_t10_audit_log() -> None:
    result = run_webui_case("T10")
    assert result["status"] == "PASS", json.dumps(result, indent=2, sort_keys=True)
