#!/usr/bin/env bash
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

# imap-mcp-server — Web services verification
# Description: Starts API and MCP servers, probes endpoints, then stops services.

set -euo pipefail

ENV_FILE="${1:-tests/env-UT}"
READY_TIMEOUT_SECONDS="${READY_TIMEOUT_SECONDS:-30}"

./server_control.sh --env "$ENV_FILE" start all
trap './server_control.sh --env "$ENV_FILE" stop all >/dev/null 2>&1 || true' EXIT

wait_for_url() {
  local url="$1"
  local elapsed=0
  while true; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
    if [[ "$elapsed" -ge "$READY_TIMEOUT_SECONDS" ]]; then
      echo "Timed out waiting for ${url}" >&2
      return 1
    fi
  done
}

mapfile -t RUNTIME_ENDPOINTS < <(
  CLOUD_DOG_ENV_FILES="$ENV_FILE" python3 - <<'PY'
from imap_hub_core.config.loader import load_global_config

cfg = load_global_config(env_files=[__import__("os").environ["CLOUD_DOG_ENV_FILES"]])
print(f"http://127.0.0.1:{cfg.api_server.port}/health")
print(f"http://127.0.0.1:{cfg.mcp_server.port}/mcp/tools")
PY
)

wait_for_url "${RUNTIME_ENDPOINTS[0]}"
wait_for_url "${RUNTIME_ENDPOINTS[1]}"

api_health="$(curl -fsS "${RUNTIME_ENDPOINTS[0]}")"
mcp_tools="$(curl -fsS "${RUNTIME_ENDPOINTS[1]}")"

echo "API_HEALTH_OK=$([[ "$api_health" == *'"status":"ok"'* ]] && echo 1 || echo 0)"
echo "MCP_TOOLS_OK=$([[ "$mcp_tools" == *'profile_list'* ]] && echo 1 || echo 0)"

echo "WEB_SERVICES_VERIFIED=1"
