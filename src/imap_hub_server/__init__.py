"""imap-mcp-server module."""

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

# W28R-3015: enforce the project-local Python 3.13 runtime contract at import time.
# The supply-chain remediation (base image python:3.13-slim, CPython 3.13.14) is only
# valid on Python 3.13+; fail fast if imported under an out-of-contract interpreter.
from imap_hub_server._runtime import enforce_runtime

enforce_runtime()

# W28E-1863 (IMAP-013/022): single source of truth for the imap-mcp-server version.
# Every version-bearing surface (API/MCP/A2A transport titles, health routers, the
# A2A agent card, the MCP serverInfo, and the /status envelopes) imports this string
# so no transport can drift from the packaged version again. It is the installed
# distribution version (driven by pyproject `version`); a source checkout without
# installed dist metadata falls back to a clearly-marked sentinel rather than a
# stale literal. Mirrors chat-client CC8 (W28C-1703) and sbom-mcp.
from importlib.metadata import PackageNotFoundError, version as _dist_version

try:
    __version__ = _dist_version("imap-mcp-server")
except PackageNotFoundError:  # pragma: no cover - source checkout without dist metadata
    __version__ = "0.0.0+source"

__all__ = ["__version__"]
