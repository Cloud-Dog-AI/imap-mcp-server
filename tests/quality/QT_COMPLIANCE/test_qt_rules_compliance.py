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

"""W25A rules-oriented static compliance checks."""

from __future__ import annotations

import ast
from pathlib import Path
import re
import pytest


EXTERNAL_LIBS = [
    "requests",
    "httpx",
    "smtplib",
    "chromadb",
    "openai",
    "ollama",
    "qdrant_client",
    "sqlalchemy",
]


def _iter_lines(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    for idx, line in enumerate(text.splitlines(), start=1):
        yield idx, line
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-002")


def test_no_hardcoded_urls(src_python_files: list[Path], project_root: Path) -> None:
    violations: list[str] = []
    pat = re.compile(r"(https?://|localhost\b|127\.0\.0\.1\b)")
    for path in src_python_files:
        rel = str(path.relative_to(project_root))
        for lineno, line in _iter_lines(path):
            s = line.strip()
            if s.startswith("#"):
                continue
            if pat.search(line):
                violations.append(f"{rel}:{lineno}: {s}")
    assert not violations, "Hardcoded URL/host markers found:\n" + "\n".join(violations)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-002")


def test_no_hardcoded_credentials(src_python_files: list[Path], project_root: Path) -> None:
    violations: list[str] = []
    pat = re.compile(r"\b(password|token|api_key|secret)\b\s*=\s*['\"][^'\"]+['\"]", re.IGNORECASE)
    for path in src_python_files:
        rel = str(path.relative_to(project_root))
        for lineno, line in _iter_lines(path):
            s = line.strip()
            if s.startswith("#"):
                continue
            if pat.search(line):
                violations.append(f"{rel}:{lineno}: {s}")
    assert not violations, "Hardcoded credential literals found:\n" + "\n".join(violations)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-001")


def test_no_direct_external_imports(
    src_python_files: list[Path],
    project_root: Path,
    allowlist_matcher,
) -> None:
    imports: dict[str, set[str]] = {lib: set() for lib in EXTERNAL_LIBS}
    imp_re = re.compile(r"^\s*(from|import)\s+([a-zA-Z0-9_\.]+)")
    for path in src_python_files:
        rel = str(path.relative_to(project_root))
        for _, line in _iter_lines(path):
            m = imp_re.match(line)
            if not m:
                continue
            target = m.group(2).split(".")[0]
            if target in imports:
                imports[target].add(rel)

    violations: list[str] = []
    for lib, modules in imports.items():
        if len(modules) > 1 and not allowlist_matcher("external_import_multi", lib):
            violations.append(f"{lib}: {sorted(modules)}")
    assert not violations, "External imports used in multiple modules:\n" + "\n".join(violations)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-003")


def test_no_pytest_skip_in_it_at(test_python_files: list[Path], project_root: Path) -> None:
    violations: list[str] = []
    for path in test_python_files:
        rel = str(path.relative_to(project_root))
        if not (rel.startswith("tests/integration/") or rel.startswith("tests/application/")):
            continue
        for lineno, line in _iter_lines(path):
            if "pytest.skip(" in line:
                violations.append(f"{rel}:{lineno}: {line.strip()}")
    assert not violations, "pytest.skip found in IT/AT:\n" + "\n".join(violations)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-003")


def test_no_mock_in_it_at(test_python_files: list[Path], project_root: Path) -> None:
    violations: list[str] = []
    pat = re.compile(r"MagicMock|MockTransport|local_mode\s*=\s*True")
    for path in test_python_files:
        rel = str(path.relative_to(project_root))
        if not (rel.startswith("tests/integration/") or rel.startswith("tests/application/")):
            continue
        for lineno, line in _iter_lines(path):
            if pat.search(line):
                violations.append(f"{rel}:{lineno}: {line.strip()}")
    assert not violations, "Mock/local_mode violations in IT/AT:\n" + "\n".join(violations)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-003")


def test_file_headers_present(
    src_python_files: list[Path], project_root: Path, allowlist_matcher
) -> None:
    violations: list[str] = []
    for path in src_python_files:
        rel = str(path.relative_to(project_root))
        if allowlist_matcher("missing_header", rel):
            continue
        first = path.read_text(encoding="utf-8", errors="replace").splitlines()[:10]
        blob = "\n".join(first)
        has_header = "imap-mcp-server" in blob.lower() or '"""' in blob
        if not has_header:
            violations.append(rel)
    assert not violations, "Missing file headers:\n" + "\n".join(sorted(violations))
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-003")


def test_functions_have_docstrings(src_python_files: list[Path], project_root: Path) -> None:
    total = 0
    with_doc = 0
    parse_errors: list[str] = []
    for path in src_python_files:
        rel = str(path.relative_to(project_root))
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as exc:
            parse_errors.append(f"{rel}: {exc}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue
                total += 1
                if ast.get_docstring(node):
                    with_doc += 1
    assert not parse_errors, "Syntax parse errors:\n" + "\n".join(parse_errors)
    ratio = 1.0 if total == 0 else with_doc / total
    assert ratio >= 0.80, f"Docstring coverage below 80%: {with_doc}/{total} ({ratio:.2%})"
