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

from imap_hub_server.api_server import run_api

# W28A-654: Patch cloud_dog_logging ContextVar defaults at module import time.
# ContextVars are task-scoped in asyncio — set_environment() in one task does NOT
# propagate to AuditMiddleware in another. Patching defaults ensures all tasks inherit.
try:
    import contextvars as _ctxvars
    from cloud_dog_logging import correlation as _cmod
    _cmod._environment_var = _ctxvars.ContextVar(
        "environment", default="unknown")
    _cmod._service_name_var = _ctxvars.ContextVar(
        "service_name", default="imap-mcp-server")
    _cmod._service_instance_var = _ctxvars.ContextVar(
        "service_instance", default="imap-mcp-local")
    del _ctxvars, _cmod
except Exception:
    pass  # cloud_dog_logging not installed or incompatible version



def main():
    """
    Purpose: Implement `main` behaviour for this module.
    Inputs: Parameters are defined by the function/class signature.
    Outputs: Returns values according to the module contract.
    Dependencies: Uses internal project modules and configured services.
    Related tests: See TESTS.md and tests/ for coverage mapping.
    """
    run_api()


if __name__ == "__main__":
    main()
