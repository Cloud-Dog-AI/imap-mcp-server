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

"""W25A migration completeness static checks."""

from __future__ import annotations

from pathlib import Path
import pytest


def _src_text(src_python_files: list[Path]) -> str:
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in src_python_files)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-001")


def test_no_yaml_safe_load_for_config(src_python_files: list[Path]) -> None:
    text = _src_text(src_python_files)
    assert "yaml.safe_load" not in text and "yaml.load(" not in text, (
        "yaml.safe_load/yaml.load found in src/ for config paths"
    )
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-001")


def test_no_raw_fastapi(
    src_python_files: list[Path], project_root: Path, allowlist_matcher
) -> None:
    violations: list[str] = []
    for path in src_python_files:
        rel = str(path.relative_to(project_root))
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            if "FastAPI(" in line and not allowlist_matcher("raw_fastapi", rel):
                violations.append(f"{rel}:{lineno}: {line.strip()}")
    assert not violations, "Raw FastAPI usage found:\n" + "\n".join(violations)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-001")


def test_no_bespoke_auth(src_python_files: list[Path], project_root: Path) -> None:
    violations: list[str] = []
    for path in src_python_files:
        rel = str(path.relative_to(project_root))
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            if "APIKeyHeader" in line or "def verify_token" in line:
                violations.append(f"{rel}:{lineno}: {line.strip()}")
    assert not violations, "Bespoke auth patterns found:\n" + "\n".join(violations)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-001")


def test_no_os_environ_for_config(
    src_python_files: list[Path], project_root: Path, allowlist_matcher
) -> None:
    violations: list[str] = []
    for path in src_python_files:
        rel = str(path.relative_to(project_root))
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            if "os.getenv(" in line or "os.environ" in line:
                if allowlist_matcher("os_environ_for_config", rel):
                    continue
                violations.append(f"{rel}:{lineno}: {line.strip()}")
    assert not violations, (
        "os.getenv/os.environ config access outside adapter allowlist:\n" + "\n".join(violations)
    )
