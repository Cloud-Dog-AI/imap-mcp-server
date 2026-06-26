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

"""W25A requirements/tests/code traceability checks."""

from __future__ import annotations

from pathlib import Path
import re
import pytest


REQ_RE = re.compile(r"\b(?:FR|UC|NF|CS|BR|BO|SV|CFG)-\d+(?:\.\d+)?\b")
TEST_ID_RE = re.compile(r"\b(?:UT|ST|IT|AT|QT)\d+\.\d+\b|\bUI-(?:IT|AT)\d+\.\d+\b")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _requirement_ids(requirements_text: str) -> list[str]:
    ids = sorted(set(REQ_RE.findall(requirements_text)))
    return ids


def _catalogue_rows(docs_tests_text: str) -> list[str]:
    return [line for line in docs_tests_text.splitlines() if line.strip().startswith("|")]


def _docs_test_ids(docs_tests_text: str) -> list[str]:
    ids: set[str] = set()
    for line in _catalogue_rows(docs_tests_text):
        for tid in TEST_ID_RE.findall(line):
            ids.add(tid)
    return sorted(ids)


def _code_paths_exist(project_root: Path, paths: list[str]) -> bool:
    return all((project_root / p).exists() for p in paths)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-004")


def test_all_requirements_have_tests(
    docs_requirements_path: Path,
    docs_tests_path: Path,
    test_python_files: list[Path],
    manual_requirement_test_map: dict[str, list[str]],
    allowlist_matcher,
) -> None:
    req_text = _read(docs_requirements_path)
    tests_doc = _read(docs_tests_path)
    all_test_text = "\n".join(_read(p) for p in test_python_files)

    missing: list[str] = []
    for req in _requirement_ids(req_text):
        has_explicit = req in tests_doc or req in all_test_text
        has_manual = bool(manual_requirement_test_map.get(req))
        if not (has_explicit or has_manual):
            if not allowlist_matcher("traceability_missing_req_tests", req):
                missing.append(req)
    assert not missing, "Requirements without test traceability:\n" + "\n".join(sorted(missing))
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-004")


def test_all_tests_have_requirements(docs_tests_path: Path, allowlist_matcher) -> None:
    text = _read(docs_tests_path)
    orphan: list[str] = []
    for line in _catalogue_rows(text):
        ids = TEST_ID_RE.findall(line)
        if not ids:
            continue
        has_req = bool(REQ_RE.search(line)) or "NFR" in line.upper()
        if has_req:
            continue
        for tid in ids:
            if allowlist_matcher("traceability_orphan_tests", tid):
                continue
            orphan.append(f"{tid}: {line.strip()}")
    assert not orphan, "Test entries without requirement linkage:\n" + "\n".join(orphan)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-004")


def test_all_requirements_have_code(
    docs_requirements_path: Path,
    src_python_files: list[Path],
    project_root: Path,
    manual_requirement_code_map: dict[str, list[str]],
) -> None:
    req_text = _read(docs_requirements_path)
    src_text = "\n".join(_read(p) for p in src_python_files)

    missing: list[str] = []
    for req in _requirement_ids(req_text):
        has_explicit = req in src_text
        mapped_paths = manual_requirement_code_map.get(req, [])
        has_manual = bool(mapped_paths) and _code_paths_exist(project_root, mapped_paths)
        if not (has_explicit or has_manual):
            missing.append(req)
    assert not missing, "Requirements without code mapping:\n" + "\n".join(sorted(missing))
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-004")


def test_delivery_matrix_complete(
    docs_requirements_path: Path,
    docs_tests_path: Path,
    test_python_files: list[Path],
    src_python_files: list[Path],
    manual_requirement_test_map: dict[str, list[str]],
    manual_requirement_code_map: dict[str, list[str]],
    project_root: Path,
) -> None:
    reqs = _requirement_ids(_read(docs_requirements_path))
    tests_doc = _read(docs_tests_path)
    tests_text = "\n".join(_read(p) for p in test_python_files)
    src_text = "\n".join(_read(p) for p in src_python_files)

    rows: list[tuple[str, str, str, str]] = []
    delivered = 0
    fr_total = 0
    for req in reqs:
        if req.startswith("FR-"):
            fr_total += 1
        code_paths = manual_requirement_code_map.get(req, [])
        code_ok = (req in src_text) or (
            bool(code_paths) and _code_paths_exist(project_root, code_paths)
        )
        test_ids = manual_requirement_test_map.get(req, [])
        test_ok = (req in tests_doc or req in tests_text) or bool(test_ids)

        if code_ok and test_ok:
            status = "DELIVERED"
            if req.startswith("FR-"):
                delivered += 1
        elif code_ok and not test_ok:
            status = "UNTESTABLE"
        elif not code_ok and test_ok:
            status = "PARTIAL"
        else:
            status = "NOT STARTED"

        rows.append((req, ", ".join(code_paths) or "-", ", ".join(test_ids) or "-", status))

    matrix = ["| Req ID | Code | Test | Status |", "|---|---|---|---|"]
    matrix.extend([f"| {r} | {c} | {t} | {s} |" for r, c, t, s in rows])
    ratio = 1.0 if fr_total == 0 else delivered / fr_total
    assert ratio >= 0.80, (
        f"FR delivered ratio below 80% ({delivered}/{fr_total}={ratio:.2%})\n" + "\n".join(matrix)
    )
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-004")


def test_no_orphan_test_files(
    project_root: Path,
    docs_tests_path: Path,
    test_python_files: list[Path],
    allowlist_matcher,
) -> None:
    docs = _read(docs_tests_path)
    orphan: list[str] = []
    for path in test_python_files:
        rel = str(path.relative_to(project_root)).replace("\\", "/")
        if rel.endswith("__init__.py") or rel.endswith("conftest.py"):
            continue
        if "/helpers/" in rel:
            continue
        if "__pycache__" in rel:
            continue
        if allowlist_matcher("orphan_test_files", rel):
            continue

        stem = path.stem
        parent_id = ""
        for part in path.parts:
            match = re.match(r"(?:UT|ST|IT|AT|QT)\d+\.\d+", part)
            if match:
                parent_id = match.group(0)
                break

        if rel in docs or stem in docs or (parent_id and parent_id in docs):
            continue
        orphan.append(rel)

    assert not orphan, "Test files not referenced in docs/TESTS.md:\n" + "\n".join(sorted(orphan))
