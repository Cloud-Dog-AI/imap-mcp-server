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

# imap-mcp-server — Docker Health Check (PS-91)
set -euo pipefail
ENV_FILE="${CLOUD_DOG_ENV_FILE:-}"
API_PORT="${CLOUD_DOG__API_SERVER__PORT:-}"
if [[ -z "${API_PORT}" && -n "${ENV_FILE}" && -f "${ENV_FILE}" ]]; then
  API_PORT="$(grep -E '^CLOUD_DOG__API_SERVER__PORT=' "${ENV_FILE}" | tail -n1 | cut -d= -f2- || true)"
fi
: "${API_PORT:?CLOUD_DOG__API_SERVER__PORT must be set}"
curl -fsS "http://127.0.0.1:${API_PORT}/health" >/dev/null
