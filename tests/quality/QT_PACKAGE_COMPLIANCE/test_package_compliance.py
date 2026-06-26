"""
Automated package compliance test.
This test FAILS if any bespoke code exists that should use a platform package.
It runs as part of QT and enforces compliance automatically.
"""

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

import pathlib
import subprocess

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
SRC_DIR = PROJECT_ROOT / "src"
AUTH_BRIDGE_FILES = (
    SRC_DIR / "imap_hub_server" / "auth" / "__init__.py",
    SRC_DIR / "imap_hub_server" / "auth" / "middleware.py",
)


def _grep_count(pattern: str, exclude_pattern: str | None = None) -> list[str]:
    """Grep ``src/`` for a pattern and return matching file:line entries."""
    cmd = f"grep -rnE '{pattern}' {SRC_DIR} --include='*.py'"
    if exclude_pattern:
        cmd += f" | grep -vE '{exclude_pattern}'"
    cmd += " | grep -v __pycache__"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)
    return [line for line in result.stdout.strip().split("\n") if line]


def _auth_bridge_uses_platform_package() -> bool:
    """Return True when the project auth bridge delegates to cloud_dog_idam."""
    for file_path in AUTH_BRIDGE_FILES:
        if not file_path.exists():
            continue
        content = file_path.read_text(encoding="utf-8")
        if "cloud_dog_idam" in content:
            return True
    return False


class TestPackageCompliance:
    """Every test here must pass. Zero bespoke code allowed."""
    @pytest.mark.QT
    @pytest.mark.mcp
    @pytest.mark.req("NF-001")

    def test_no_bespoke_logging(self):
        """All logging must use cloud_dog_logging. Zero logging.getLogger calls."""
        hits = _grep_count("logging\\.getLogger", "cloud_dog")
        assert len(hits) == 0, (
            f"FAIL: {len(hits)} bespoke logging calls found. "
            f"Replace with cloud_dog_logging:\n" + "\n".join(hits[:10])
        )
    @pytest.mark.QT
    @pytest.mark.mcp
    @pytest.mark.req("NF-001")

    def test_no_bespoke_config_manager(self):
        """Config must use cloud_dog_config. Zero bespoke ConfigManager references."""
        hits = _grep_count("ConfigManager|config_manager", "cloud_dog")
        real_hits = [hit for hit in hits if "cloud_dog_config" not in hit]
        assert len(real_hits) == 0, (
            f"FAIL: {len(real_hits)} bespoke config calls found:\n"
            + "\n".join(real_hits[:10])
        )
    @pytest.mark.QT
    @pytest.mark.mcp
    @pytest.mark.req("NF-001")

    def test_no_bespoke_auth(self):
        """Auth must use cloud_dog_idam. Zero bespoke auth imports outside bridges."""
        hits = _grep_count("^(from|import).*auth", "cloud_dog")
        real_hits: list[str] = []
        for hit in hits:
            filepath = hit.split(":")[0]
            if "imap_hub_server.auth" in hit and _auth_bridge_uses_platform_package():
                continue
            try:
                content = pathlib.Path(filepath).read_text(encoding="utf-8")
            except OSError:
                real_hits.append(hit)
                continue
            if "cloud_dog_idam" in content:
                continue
            real_hits.append(hit)
        assert len(real_hits) == 0, (
            "FAIL: "
            f"{len(real_hits)} bespoke auth imports not delegating to cloud_dog_idam:\n"
            + "\n".join(real_hits[:10])
        )
    @pytest.mark.QT
    @pytest.mark.mcp
    @pytest.mark.req("NF-001")

    def test_no_memory_queue(self):
        """Jobs must use cloud_dog_jobs. Zero bespoke queue/thread calls."""
        hits = _grep_count("MemoryQueue(?!Backend)|ThreadPoolExecutor|asyncio\\.Queue", "cloud_dog")
        assert len(hits) == 0, (
            f"FAIL: {len(hits)} bespoke queue/thread calls found:\n"
            + "\n".join(hits[:10])
        )
    @pytest.mark.QT
    @pytest.mark.mcp
    @pytest.mark.req("NF-001")

    def test_no_direct_llm_calls(self):
        """LLM calls must use a platform package. Zero direct ollama/openai calls."""
        hits = _grep_count(
            "httpx\\.AsyncClient.*ollama|requests\\.post.*ollama|openai\\.ChatCompletion",
            "cloud_dog",
        )
        assert len(hits) == 0, (
            f"FAIL: {len(hits)} direct LLM calls found:\n" + "\n".join(hits[:10])
        )
    @pytest.mark.QT
    @pytest.mark.mcp
    @pytest.mark.req("NF-002")

    def test_no_hardcoded_secrets(self):
        """Zero hardcoded passwords or secrets in source."""
        hits = _grep_count(
            "password.*=.*['\\\"]|secret.*=.*['\\\"]|api_key.*=.*['\\\"]"
        )
        real_hits = [
            hit
            for hit in hits
            if not any(
                token in hit.lower()
                for token in [
                    "test",
                    "example",
                    "placeholder",
                    "changeme",
                    "12345",
                    "os.environ",
                    "config.get",
                ]
            )
        ]
        assert len(real_hits) == 0, (
            f"FAIL: {len(real_hits)} hardcoded secrets found:\n"
            + "\n".join(real_hits[:10])
        )
    @pytest.mark.QT
    @pytest.mark.mcp
    @pytest.mark.req("NF-002")

    def test_no_internal_hostnames(self):
        """Zero internal hostnames in source. These must come from config or Vault."""
        hits = _grep_count("cloud-dog\\.net|viewdeck\\.com|vault0\\.|server0\\.|db1\\.app")
        real_hits = [
            hit
            for hit in hits
            if not any(
                token in hit for token in ["#", '"""', "vault.", "test", "PREPROD", "example"]
            )
        ]
        assert len(real_hits) == 0, (
            f"FAIL: {len(real_hits)} internal hostnames in source:\n"
            + "\n".join(real_hits[:10])
        )
    @pytest.mark.QT
    @pytest.mark.mcp
    @pytest.mark.req("FR-10")

    def test_ui_dist_exists(self):
        """PS-30: ui/dist/ must exist when a web server is present."""
        ui_dist = PROJECT_ROOT / "ui" / "dist"
        if not (SRC_DIR / "imap_hub_server" / "web_server.py").exists():
            pytest.skip("No web server - UI not applicable")
        assert ui_dist.exists(), "FAIL: ui/dist/ not found. SPA must be built."
    @pytest.mark.QT
    @pytest.mark.mcp
    @pytest.mark.req("FR-10")

    def test_runtime_config_endpoint(self):
        """PS-30: /runtime-config.js must be served by the web server."""
        web_files = list(SRC_DIR.rglob("*.py"))
        has_runtime_config = any(
            "runtime-config" in file_path.read_text(encoding="utf-8")
            or "runtime_config" in file_path.read_text(encoding="utf-8")
            for file_path in web_files
            if file_path.stat().st_size < 100000
        )
        if not (SRC_DIR / "imap_hub_server" / "web_server.py").exists():
            pytest.skip("No web server - runtime-config not applicable")
        assert has_runtime_config, "FAIL: No /runtime-config.js endpoint found in web server."
    @pytest.mark.QT
    @pytest.mark.mcp
    @pytest.mark.req("NF-001")

    def test_server_control_exists(self):
        """server_control.sh must exist."""
        assert (PROJECT_ROOT / "server_control.sh").exists(), "FAIL: server_control.sh missing."
    @pytest.mark.QT
    @pytest.mark.mcp
    @pytest.mark.req("NF-004")

    def test_licence_exists(self):
        """LICENCE file must exist."""
        assert (PROJECT_ROOT / "LICENCE").exists(), "FAIL: LICENCE file missing."
    @pytest.mark.QT
    @pytest.mark.mcp
    @pytest.mark.req("NF-004")

    def test_readme_exists(self):
        """README.md must exist."""
        assert (PROJECT_ROOT / "README.md").exists(), "FAIL: README.md missing."
