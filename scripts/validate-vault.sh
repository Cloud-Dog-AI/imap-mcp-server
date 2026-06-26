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

# imap-mcp-server — Vault validation script
# Licence: Proprietary — Cloud-Dog AI Platform
# Owner: Cloud-Dog AI
# Description: Validates live Vault access and required section key presence.

set -euo pipefail

if [[ -z "${VAULT_ADDR:-}" || -z "${VAULT_TOKEN:-}" || -z "${VAULT_MOUNT_POINT:-}" || -z "${VAULT_CONFIG_PATH:-}" ]]; then
  echo "Missing Vault environment variables. Source /opt/iac/Development/cloud-dog-ai/env-vault first." >&2
  exit 1
fi

payload_file="$(mktemp)"
trap 'rm -f "$payload_file"' EXIT

curl -fsS -H "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/${VAULT_MOUNT_POINT}/data/${VAULT_CONFIG_PATH}" > "$payload_file"

python3 - "$payload_file" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
root = payload["data"]["data"]
content_blob = root.get("content", "")
if not isinstance(content_blob, str) or not content_blob.strip():
    raise SystemExit("Vault payload missing content blob")
content = json.loads(content_blob)

required = {
    "dev.email": [
        "imap_operations_cloud_dog_net.host",
        "imap_operations_cloud_dog_net.username",
        "imap_operations_cloud_dog_net.password",
    ],
    "dev.databases.providers": [
        "postgres.host",
        "postgres.port",
        "postgres.username",
        "postgres.password",
    ],
    "dev.vdbs": [
        "chroma.base_url",
        "qdrant.url",
    ],
    "dev.repository": [
        "pypi.url",
        "pypi.username",
        "pypi.password",
    ],
}


def get_path(node, dotted: str):
    current = node
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current

has_error = False
for section, keys in required.items():
    section_obj = get_path(content, section)
    print(f"[{section}]")
    if section_obj is None:
        print("  MISSING SECTION")
        has_error = True
        continue

    for key in keys:
        value = get_path(section_obj, key)
        if value is None:
            print(f"  MISSING KEY: {key}")
            has_error = True
        else:
            print(f"  OK: {key}")

if has_error:
    raise SystemExit(2)
PY

echo "Vault validation passed."
