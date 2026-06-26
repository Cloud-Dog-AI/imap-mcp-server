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

"""Shared fixtures for W25A static compliance checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import pytest


@dataclass(frozen=True)
class AllowItem:
    pattern: str
    reason: str


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def src_dir(project_root: Path) -> Path:
    return project_root / "src"


@pytest.fixture(scope="session")
def src_python_files(src_dir: Path) -> list[Path]:
    return sorted(src_dir.rglob("*.py"))


@pytest.fixture(scope="session")
def test_python_files(project_root: Path) -> list[Path]:
    return sorted((project_root / "tests").rglob("*.py"))


@pytest.fixture(scope="session")
def docs_tests_path(project_root: Path) -> Path:
    return project_root / "docs" / "TESTS.md"


@pytest.fixture(scope="session")
def docs_requirements_path(project_root: Path) -> Path:
    return project_root / "docs" / "REQUIREMENTS.md"


@pytest.fixture(scope="session")
def allowlist() -> dict[str, list[AllowItem]]:
    return {
        "missing_header": [],
        "raw_fastapi": [],
        "os_environ_for_config": [],
        "external_import_multi": [
            AllowItem(
                r"^sqlalchemy$", "Platform DB integration spans model/runtime modules by design."
            ),
        ],
        "traceability_orphan_tests": [],
        "traceability_missing_req_tests": [],
        "orphan_test_files": [],
    }


@pytest.fixture(scope="session")
def manual_requirement_test_map() -> dict[str, list[str]]:
    return {
        "FR-14": ["AT1.12", "UI-T8", "UI-T10"],
        "FR-15": ["UI-T7"],
        "FR-16": ["UI-T7"],
        "FR-17": ["UI-T7", "UI-T11"],
        "FR-18": ["AT1.12", "UI-T10"],
        "CFG-01": ["IT1.10", "AT1.10"],
        "CFG-02": ["IT1.10"],
        "CFG-03": ["IT1.10", "AT1.10"],
        "CFG-04": ["IT1.10", "AT1.10"],
        "CFG-05": ["IT1.5", "IT1.6", "AT1.10"],
        "CFG-06": ["AT1.12"],
        "CFG-07": ["AT1.12", "UI-AT1.6"],
        "CFG-08": ["UT1.36", "UT1.37", "IT1.19", "AT1.12", "UI-AT1.6"],
        "CFG-09": ["UT1.36", "UT1.37", "IT1.19", "IT1.20", "UI-AT1.6"],
        "CFG-10": ["UT1.36", "UT1.37", "IT1.19", "IT1.20", "AT1.12", "UI-AT1.6"],
        "CFG-11": ["UT1.36", "UT1.37", "IT1.20", "AT1.12", "UI-AT1.6"],
        "CFG-12": ["UT1.36", "UT1.37", "IT1.19", "IT1.20"],
        "CFG-13": ["UT1.36", "IT1.19", "IT1.20"],
    }


@pytest.fixture(scope="session")
def manual_requirement_code_map() -> dict[str, list[str]]:
    return {
        "FR-14": ["../cloud-dog-ai-ui-monorepo/apps/imap-mcp/src/routes/App.tsx"],
        "FR-15": ["../cloud-dog-ai-ui-monorepo/apps/imap-mcp/src/views/FileBrowserPage.tsx"],
        "FR-16": ["../cloud-dog-ai-ui-monorepo/apps/imap-mcp/src/views/SearchPage.tsx"],
        "FR-17": [
            "../cloud-dog-ai-ui-monorepo/apps/imap-mcp/src/views/SearchPage.tsx",
            "../cloud-dog-ai-ui-monorepo/apps/imap-mcp/src/views/SettingsPage.tsx",
            "../cloud-dog-ai-ui-monorepo/apps/imap-mcp/src/views/FileBrowserPage.tsx",
        ],
        # FR-18 (legacy compatibility page governance): the legacy compatibility
        # pages (LegacyAdminControlPage / LegacyDiagnosticsAuditPage) have been
        # RETIRED in favour of the governed standard split pages — which is the
        # governance outcome the requirement mandates. Traceability now maps to
        # the route map (App.tsx — proves the canonical route points to the
        # standard page, not a legacy-only implementation) and the standard
        # governed pages that replaced the legacy admin + diagnostics surfaces.
        "FR-18": [
            "../cloud-dog-ai-ui-monorepo/apps/imap-mcp/src/routes/App.tsx",
            "../cloud-dog-ai-ui-monorepo/apps/imap-mcp/src/views/AdminUsersPage.tsx",
            "../cloud-dog-ai-ui-monorepo/apps/imap-mcp/src/views/AuditLogPage.tsx",
        ],
        "CFG-01": ["src/imap_hub_server/admin/endpoints.py"],
        "CFG-02": ["src/imap_hub_server/admin/endpoints.py"],
        "CFG-03": ["src/imap_hub_server/admin/endpoints.py"],
        "CFG-04": ["src/imap_hub_server/admin/endpoints.py"],
        "CFG-05": ["src/imap_hub_core/tools/handlers.py"],
        "CFG-06": ["src/imap_hub_server/api_server.py", "src/imap_hub_server/admin/state.py"],
        "CFG-07": ["src/imap_hub_server/api_server.py", "ui/dist/index.html"],
        "CFG-08": ["src/imap_hub_server/admin/state.py", "src/imap_hub_server/admin/endpoints.py"],
        "CFG-09": ["src/imap_hub_server/admin/state.py", "src/imap_hub_server/admin/endpoints.py"],
        "CFG-10": ["src/imap_hub_server/admin/state.py", "src/imap_hub_server/admin/endpoints.py"],
        "CFG-11": [
            "src/imap_hub_core/tools/handlers.py",
            "src/imap_hub_server/mcp_server.py",
            "src/imap_hub_server/api_server.py",
            "ui/dist/index.html",
        ],
        "CFG-12": [
            "src/imap_hub_server/admin/endpoints.py",
            "src/imap_hub_core/tools/handlers.py",
            "src/imap_hub_server/admin/state.py",
        ],
        "CFG-13": ["src/imap_hub_server/admin/endpoints.py", "src/imap_hub_server/mcp_server.py"],
        "CS-001": ["src/imap_hub_server/auth/middleware.py"],
        "CS-002": ["src/imap_hub_server/auth/middleware.py"],
        "CS-003": ["src/imap_hub_server/api_server.py"],
        "CS-004": ["src/imap_hub_server/mcp_server.py"],
        "CS-005": ["src/imap_hub_server/auth/middleware.py"],
        "CS-006": ["src/imap_hub_server/auth/middleware.py"],
        "CS-007": ["src/imap_hub_server/api_server.py"],
        "CS-008": ["src/imap_hub_server/mcp_server.py"],
        "CS-009": ["src/imap_hub_server/api_server.py"],
        "CS-010": ["src/imap_hub_server/admin/endpoints.py"],
        "CS-011": ["src/imap_hub_server/admin/endpoints.py"],
        "CS-012": ["src/imap_hub_server/admin/endpoints.py"],
        "CS-013": ["src/imap_hub_server/admin/endpoints.py"],
        "FR-012": ["src/imap_hub_core/tools/handlers.py"],
        "FR-013": ["src/imap_hub_server/admin/endpoint_roles.py"],
        "FR-014": ["src/imap_hub_server/api_server.py"],
        "FR-015": ["src/imap_hub_server/admin/endpoints.py"],
        "FR-016": ["src/imap_hub_server/api_server.py"],
        "FR-017": ["src/imap_hub_server/a2a_server.py"],
        "FR-018": ["src/imap_hub_server/web_server.py"],
        # Use-case → implementing-module map (W28E-1803B). Each UC is realised by
        # the source module(s) that implement its mapped FR (see docs/REQUIREMENTS.md
        # §4.B "Use cases" column and docs/WARRANTY-1.0RC01.md Section A).
        "UC-001": [
            "src/imap_hub_server/api_server.py",
            "src/imap_hub_server/mcp_server.py",
            "src/imap_hub_server/a2a_server.py",
        ],
        "UC-002": ["src/imap_hub_core/config/loader.py"],
        "UC-003": ["src/imap_hub_server/admin/endpoints.py"],
        "UC-004": ["src/imap_hub_server/admin/endpoints.py"],
        "UC-005": ["src/imap_hub_server/auth/middleware.py"],
        "UC-006": ["src/imap_hub_core/tools/read_handler.py"],
        "UC-007": ["src/imap_hub_core/tools/read_handler.py"],
        "UC-008": ["src/imap_hub_core/tools/write_handler.py"],
        "UC-009": ["src/imap_hub_core/ledger/store.py", "src/imap_hub_core/cache/store.py"],
        "UC-010": ["src/imap_hub_core/imap/connection.py"],
        "UC-011": ["src/imap_hub_core/audit/logger.py"],
        "UC-012": ["src/imap_hub_server/web_server.py"],
        "UC-013": ["src/imap_hub_server/api_server.py", "ui/dist/index.html"],
        "UC-014": ["src/imap_hub_server/admin/endpoints.py"],
        "UC-015": ["src/imap_hub_server/admin/endpoints.py"],
        "UC-016": ["../cloud-dog-ai-ui-monorepo/apps/imap-mcp/src/routes/App.tsx"],
        "UC-017": [
            "../cloud-dog-ai-ui-monorepo/apps/imap-mcp/src/views/FileBrowserPage.tsx",
            "../cloud-dog-ai-ui-monorepo/apps/imap-mcp/src/views/SearchPage.tsx",
        ],
        "UC-018": ["../cloud-dog-ai-ui-monorepo/apps/imap-mcp/src/views/SettingsPage.tsx"],
        "UC-019": ["src/imap_hub_core/jobs/runtime.py"],
        "UC-020": ["src/imap_hub_server/auth/middleware.py"],
        "UC-021": ["src/imap_hub_server/mcp_server.py"],
        "UC-022": ["src/imap_hub_core/duplicate/detector.py"],
        "UC-023": ["src/imap_hub_core/archive/exporter.py"],
        "UC-024": ["src/imap_hub_core/db/runtime.py"],
        # Non-functional posture requirements → the module/doc that embodies each.
        "NF-001": ["src/imap_hub_server/main.py", "src/imap_hub_core/db/runtime.py"],
        "NF-002": ["src/imap_hub_core/config/loader.py"],
        "NF-003": ["src/imap_hub_server/logging_runtime.py"],
        "NF-004": ["docs/REQ-COVERAGE.md"],
    }


def is_allowlisted(allowlist: dict[str, list[AllowItem]], key: str, value: str) -> bool:
    for item in allowlist.get(key, []):
        if re.search(item.pattern, value):
            return True
    return False


@pytest.fixture(scope="session")
def allowlist_matcher(allowlist: dict[str, list[AllowItem]]):
    def _match(key: str, value: str) -> bool:
        return is_allowlisted(allowlist, key, value)

    return _match
