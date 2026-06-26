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

"""W25A platform package adoption checks."""

from __future__ import annotations

from pathlib import Path
import re
import pytest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python <3.11 fallback
    import tomli as tomllib


def _src_text(src_python_files: list[Path]) -> str:
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in src_python_files)


def _pyproject_dependencies(project_root: Path) -> set[str]:
    data = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))
    deps = set()
    for dep in data.get("project", {}).get("dependencies", []):
        name = re.split(r"[<>=!~ ]", dep.strip(), maxsplit=1)[0].strip()
        if name:
            deps.add(name)
    return deps
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-001")


def test_config_uses_cloud_dog_config(src_python_files: list[Path]) -> None:
    text = _src_text(src_python_files)
    assert "cloud_dog_config" in text, "cloud_dog_config not imported in src/"
    assert "yaml.safe_load" not in text and "yaml.load(" not in text, (
        "Bespoke YAML config loading found in src/"
    )
    assert "dotenv.load_dotenv" not in text, "dotenv.load_dotenv found; use cloud_dog_config"
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-001")


def test_logging_uses_cloud_dog_logging(src_python_files: list[Path]) -> None:
    text = _src_text(src_python_files)
    assert "cloud_dog_logging" in text, "cloud_dog_logging not imported in src/"
    assert "logging.getLogger" not in text and "logging.basicConfig" not in text, (
        "Bespoke logging setup found in src/"
    )
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-001")


def test_api_uses_cloud_dog_api_kit(
    src_python_files: list[Path], project_root: Path, allowlist_matcher
) -> None:
    text = _src_text(src_python_files)
    assert "cloud_dog_api_kit" in text, "cloud_dog_api_kit not imported in src/"
    violations: list[str] = []
    for path in src_python_files:
        rel = str(path.relative_to(project_root))
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            if "FastAPI(" in line and not allowlist_matcher("raw_fastapi", rel):
                violations.append(f"{rel}:{lineno}: {line.strip()}")
    assert not violations, "Raw FastAPI() usage found:\n" + "\n".join(violations)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-001")


def test_auth_uses_cloud_dog_idam(src_python_files: list[Path]) -> None:
    text = _src_text(src_python_files)
    assert "cloud_dog_idam" in text, "cloud_dog_idam not imported in src/"
    assert "APIKeyHeader" not in text and "def verify_token" not in text, (
        "Bespoke auth patterns found in src/"
    )
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-001")


def test_no_bespoke_db_access(src_python_files: list[Path]) -> None:
    text = _src_text(src_python_files)
    assert "sqlite3.connect(" not in text and "create_engine(" not in text, (
        "Bespoke DB access found in src/"
    )
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-001")


def test_no_bespoke_llm_calls(src_python_files: list[Path]) -> None:
    text = _src_text(src_python_files)
    assert "openai.OpenAI(" not in text and "ollama.chat(" not in text, (
        "Bespoke LLM calls found in src/"
    )
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-001")


def test_no_bespoke_vdb_calls(src_python_files: list[Path]) -> None:
    text = _src_text(src_python_files)
    assert "chromadb.Client(" not in text and "qdrant_client.QdrantClient(" not in text, (
        "Bespoke VDB calls found in src/"
    )
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-001")


def test_pyproject_declares_platform_packages(
    project_root: Path, src_python_files: list[Path]
) -> None:
    deps = _pyproject_dependencies(project_root)
    src = _src_text(src_python_files)
    required = {"cloud_dog_config", "cloud_dog_logging", "cloud_dog_api_kit", "cloud_dog_idam"}

    # Applicable by source usage.
    if "cloud_dog_db" in src:
        required.add("cloud_dog_db")
    if "cloud_dog_jobs" in src:
        required.add("cloud_dog_jobs")

    missing = sorted(pkg for pkg in required if pkg not in deps)
    assert not missing, f"Missing platform packages in pyproject dependencies: {missing}"
