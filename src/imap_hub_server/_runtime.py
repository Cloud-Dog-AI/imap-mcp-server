"""imap-mcp-server — project-local Python 3.13 runtime contract.

License: Apache-2.0
Ownership: Cloud-Dog, Viewdeck Engineering Limited
Description: imap-mcp-server is a Python 3.13+ service. The W28R-3015 supply-chain
  remediation cleared the fixable CPython High/Critical CVEs
  (CVE-2026-3298/3644/4224/4786/6100/7210/9669) by moving the runtime to
  CPython 3.13.14 (base image ``python:3.13-slim``). That guarantee only holds while
  the interpreter is >= 3.13, so this module makes 3.13 the enforced project-local
  runtime floor: importing the package on an out-of-contract interpreter fails fast
  with a clear error instead of silently running an unsupported (and CVE-exposed)
  runtime for local development, tests, or builds.
Requirements: NF-005
Tasks: IMAP-R3015
Architecture: IP1.1
Tests: QT (tests/quality/QT_COMPLIANCE/test_qt_python_runtime_contract.py)
Recent Change History:
- 2026-07-13: Added the Python 3.13 runtime contract for W28R-3015 supply-chain remediation.
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

from __future__ import annotations

import sys
from collections.abc import Sequence

# The single source of truth for the supported runtime floor. Keep this in lockstep
# with ``requires-python`` (pyproject.toml), ``.python-version``, and the Ruff target
# (asserted by tests/quality/QT_COMPLIANCE/test_qt_python_runtime_contract.py).
MIN_PYTHON: tuple[int, int] = (3, 13)


def runtime_ok(version_info: Sequence[int] = sys.version_info) -> bool:
    """Return True when ``version_info`` satisfies the project runtime floor."""
    return tuple(version_info[:2]) >= MIN_PYTHON


def enforce_runtime(version_info: Sequence[int] = sys.version_info) -> None:
    """Raise ``RuntimeError`` when running under an interpreter older than the floor.

    Called at package import time so any local dev/test/build run on an
    out-of-contract interpreter fails immediately rather than running the
    CVE-exposed 3.12 interpreter the W28R-3015 remediation retired.
    """
    if not runtime_ok(version_info):
        running = ".".join(str(part) for part in tuple(version_info[:3]))
        required = ".".join(str(part) for part in MIN_PYTHON)
        raise RuntimeError(
            f"imap-mcp-server requires Python >= {required}; running {running}. "
            "The W28R-3015 supply-chain remediation (base image python:3.13-slim, "
            "CPython 3.13.14) is only valid on Python 3.13+. Create the project venv "
            "with `python3.13 -m venv .venv` (see docs/BUILD.md / docs/TESTS.md)."
        )
