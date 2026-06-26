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

from imap_hub_core.tools.registry import TOOL_REGISTRY

# Ensure handlers are registered
from imap_hub_core.tools import handlers  # noqa: F401


def tool_dispatch(tool_name: str, payload: dict):
    """
    Purpose: Implement `tool_dispatch` behaviour for this module.
    Inputs: Parameters are defined by the function/class signature.
    Outputs: Returns values according to the module contract.
    Dependencies: Uses internal project modules and configured services.
    Related tests: See TESTS.md and tests/ for coverage mapping.
    """
    handler = TOOL_REGISTRY.get(tool_name)
    if not handler:
        return {
            "ok": False,
            "errors": [{"code": "tool_not_found", "message": tool_name}],
            "warnings": [],
            "result": None,
            "meta": {},
        }
    return handler(payload)
