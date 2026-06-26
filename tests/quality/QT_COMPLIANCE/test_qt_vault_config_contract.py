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

"""W25A vault/config/secrets contract checks."""

from __future__ import annotations

from pathlib import Path
import re
import pytest


SECRET_PAT = re.compile(r"(?i)(password|token|api[_-]?key|secret)\s*[:=]\s*['\"]([^'\"]+)['\"]")
VAULT_EXPR_PAT = re.compile(r"\$\{vault\.dev\.[^}]+\}")
ENV_EXPR_PAT = re.compile(r"^\$\{[A-Z0-9_]+\}$")


def _is_dynamic_secret_reference(value: str) -> bool:
    return bool(ENV_EXPR_PAT.match(value) or VAULT_EXPR_PAT.match(value))


def _scan_secret_literals(path: Path) -> list[str]:
    findings: list[str] = []
    for lineno, line in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
    ):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        match = SECRET_PAT.search(line)
        if match is None:
            continue
        value = match.group(2).strip()
        if _is_dynamic_secret_reference(value):
            continue
        if match:
            findings.append(f"{path}:{lineno}: {s}")
    return findings
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-002")


def test_defaults_yaml_exists(project_root: Path) -> None:
    assert (project_root / "defaults.yaml").exists(), "defaults.yaml missing"
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-002")


def test_defaults_yaml_no_secrets(project_root: Path) -> None:
    path = project_root / "defaults.yaml"
    findings = _scan_secret_literals(path)
    assert not findings, "Secret-like literals in defaults.yaml:\n" + "\n".join(findings)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-002")


def test_config_yaml_no_secrets(project_root: Path) -> None:
    path = project_root / "config.yaml"
    if not path.exists():
        return
    findings = _scan_secret_literals(path)
    assert not findings, "Secret-like literals in config.yaml:\n" + "\n".join(findings)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-002")


def test_env_files_use_vault_expressions(project_root: Path) -> None:
    issues: list[str] = []
    for tier in ["IT", "AT"]:
        for suffix in ["", "-local-docker", "-local-server"]:
            path = project_root / "tests" / f"env-{tier}{suffix}"
            if not path.exists():
                continue
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            for lineno, line in enumerate(lines, 1):
                if line.startswith("IMAP_OPERATIONS_PASSWORD="):
                    value = line.split("=", 1)[1].strip()
                    if value and not VAULT_EXPR_PAT.search(value):
                        issues.append(f"{path}:{lineno}: {line.strip()}")
    assert not issues, "IT/AT env credential keys without vault expression:\n" + "\n".join(issues)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-002")


def test_no_secrets_in_source(src_python_files: list[Path], project_root: Path) -> None:
    findings: list[str] = []
    for path in src_python_files:
        rel = str(path.relative_to(project_root))
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            s = line.strip()
            if s.startswith("#"):
                continue
            # allow empty-string assignment patterns
            if re.search(r"(?i)(password|token|api[_-]?key|secret)\s*=\s*['\"]{2}", line):
                continue
            if SECRET_PAT.search(line):
                findings.append(f"{rel}:{lineno}: {s}")
    assert not findings, "Secret-like literals found in source:\n" + "\n".join(findings)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-002")


def test_env_files_exist_per_tier(project_root: Path) -> None:
    missing: list[str] = []
    for tier in ["UT", "ST", "IT", "AT"]:
        path = project_root / "tests" / f"env-{tier}"
        if not path.exists():
            missing.append(str(path))
    assert not missing, "Missing tier env files:\n" + "\n".join(missing)
