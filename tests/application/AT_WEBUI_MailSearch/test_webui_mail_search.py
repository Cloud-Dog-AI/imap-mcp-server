"""T7 WebUI E2E case."""

from __future__ import annotations

import json

from tests.application.webui_e2e import run_webui_case
import pytest
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-15")
@pytest.mark.req("FR-16")


def test_t7_mail_search() -> None:
    result = run_webui_case("T7")
    assert result["status"] == "PASS", json.dumps(result, indent=2, sort_keys=True)
