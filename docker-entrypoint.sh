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

# imap-mcp-server — Docker Entrypoint (PS-91)
set -euo pipefail

echo "============================================================"
echo "imap-mcp-server container"
echo "Mode: ${1:-all} | Python: $(python3 --version 2>&1)"
echo "============================================================"

if ! mkdir -p /app/logs /app/data/audit /app/data/downloads /app/data/archive /app/.pids /app/certs; then
  echo "[WARN] Unable to create one or more runtime directories; continuing with existing mounts."
fi

# ── CA Bundle ────────────────────────────────────────────────────
CA_PATH="${CLOUD_DOG_TLS_CA_BUNDLE:-${REQUESTS_CA_BUNDLE:-}}"
if [[ -n "${CA_PATH}" && -f "${CA_PATH}" ]]; then
  if ! cp "${CA_PATH}" /usr/local/share/ca-certificates/custom-ca.crt 2>/dev/null; then
    echo "[WARN] Unable to install custom CA bundle into system trust store; using process-level CA env only."
  else
    update-ca-certificates 2>/dev/null || true
  fi
fi
export REQUESTS_CA_BUNDLE="${REQUESTS_CA_BUNDLE:-/etc/ssl/certs/ca-certificates.crt}"
export SSL_CERT_FILE="${SSL_CERT_FILE:-/etc/ssl/certs/ca-certificates.crt}"
export CURL_CA_BUNDLE="${CURL_CA_BUNDLE:-/etc/ssl/certs/ca-certificates.crt}"
export GIT_SSL_CAINFO="${GIT_SSL_CAINFO:-/etc/ssl/certs/ca-certificates.crt}"
export NODE_EXTRA_CA_CERTS="${NODE_EXTRA_CA_CERTS:-/etc/ssl/certs/ca-certificates.crt}"

# ── Durable Gmail OAuth state ───────────────────────────────────
# The provider callback writes only this 0600 host-mounted sidecar. Reload its
# allow-listed fields before the runtime environment snapshot is created so a
# Terraform-managed container replacement keeps using XOAUTH2 without a Vault
# write or an image/config mutation.
GMAIL_OAUTH_STATE_FILE="${IMAP_MCP_GMAIL_STATE_FILE:-/app/logs/gmail_oauth_state-gmail_personal.json}"
if [[ -f "${GMAIL_OAUTH_STATE_FILE}" ]]; then
  GMAIL_OAUTH_STATE_LOADED=true
  for key in \
    IMAP_MCP_GMAIL_USER_EMAIL \
    IMAP_MCP_GMAIL_REFRESH_TOKEN \
    IMAP_MCP_GMAIL_REDIRECT_URI \
    IMAP_MCP_GMAIL_TOKEN_URI \
    IMAP_MCP_GMAIL_OAUTH_SCOPE \
    IMAP_MCP_GMAIL_CLIENT_ID; do
    value="$(python3 - "${GMAIL_OAUTH_STATE_FILE}" "${key}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    value = json.load(handle).get(sys.argv[2], "")
if isinstance(value, str):
    sys.stdout.write(value)
PY
)" || {
      echo "[WARN] Gmail OAuth state sidecar could not be read; continuing fail-closed."
      GMAIL_OAUTH_STATE_LOADED=false
      break
    }
    if [[ -n "${value}" ]]; then
      export "${key}=${value}"
    fi
  done
  if [[ "${GMAIL_OAUTH_STATE_LOADED}" == "true" ]]; then
    export GOOGLE_CLIENT_ID="${IMAP_MCP_GMAIL_CLIENT_ID:-${GOOGLE_CLIENT_ID:-}}"
    export GOOGLE_REDIRECT_URL="${IMAP_MCP_GMAIL_REDIRECT_URI:-${GOOGLE_REDIRECT_URL:-}}"
    echo "[INFO] Loaded durable Gmail OAuth state for gmail_personal."
  fi
fi

API_PORT="${CLOUD_DOG__API_SERVER__PORT:-}"
if [[ -z "${API_PORT}" && -n "${ENV_FILE:-}" && -f "${ENV_FILE:-}" ]]; then
  API_PORT="$(grep -E '^CLOUD_DOG__API_SERVER__PORT=' "${ENV_FILE}" | tail -n1 | cut -d= -f2- || true)"
fi

# ── Env file loading ────────────────────────────────────────────
ENV_FILE="${CLOUD_DOG_ENV_FILE:-}"
ENV_ARGS=()
TEMP_ENV_FILE=""
if [[ -z "${ENV_FILE}" ]]; then
  TEMP_ENV_FILE="/tmp/imap-mcp-runtime.env"
  printenv > "${TEMP_ENV_FILE}"
  ENV_FILE="${TEMP_ENV_FILE}"
fi
if [[ -n "${ENV_FILE}" && -f "${ENV_FILE}" ]]; then
  ENV_ARGS=(--env "${ENV_FILE}")
fi

runtime_env_value() {
  local key="$1"
  local current="${!key:-}"
  if [[ -n "${current}" ]]; then
    printf '%s\n' "${current}"
    return 0
  fi
  if [[ -n "${ENV_FILE}" && -f "${ENV_FILE}" ]]; then
    grep -E "^${key}=" "${ENV_FILE}" | tail -n1 | cut -d= -f2- || true
    return 0
  fi
  return 0
}

normalise_runtime_permissions() {
  local app_logs=(
    /app/logs/api_server.log
    /app/logs/web_server.log
    /app/logs/mcp_server.log
    /app/logs/a2a_server.log
    /app/logs/api.log
    /app/logs/web.log
    /app/logs/mcp.log
    /app/logs/a2a.log
    /app/logs/audit-integrity.log
  )
  local audit_logs=(
    /app/logs/audit.log.jsonl
    /app/data/audit/audit.jsonl
  )
  for path in "${app_logs[@]}"; do
    [[ -e "${path}" ]] || continue
    chmod 0644 "${path}" 2>/dev/null || true
  done
  for path in "${audit_logs[@]}"; do
    [[ -e "${path}" ]] || continue
    chmod 0600 "${path}" 2>/dev/null || true
  done
}

normalise_runtime_permissions_window() {
  local attempts="${1:-10}"
  local delay="${2:-1}"
  local attempt=1
  while (( attempt <= attempts )); do
    normalise_runtime_permissions
    sleep "${delay}"
    ((attempt++))
  done
  normalise_runtime_permissions
}

# ── Graceful shutdown ───────────────────────────────────────────
shutdown() {
  echo "[INFO] Stopping services..."
  /app/server_control.sh ${ENV_ARGS[@]+"${ENV_ARGS[@]}"} stop all 2>/dev/null || true
  if [[ -n "${TEMP_ENV_FILE}" ]]; then
    rm -f "${TEMP_ENV_FILE}"
  fi
}
trap shutdown INT TERM

# ── Mode dispatch ───────────────────────────────────────────────
case "${1:-all}" in
  all)
    /app/server_control.sh ${ENV_ARGS[@]+"${ENV_ARGS[@]}"} start all
    normalise_runtime_permissions_window 12 1 &
    tail -F /app/logs/*.log 2>/dev/null &
    wait $!
    ;;
  api|web|mcp|a2a)
    /app/server_control.sh ${ENV_ARGS[@]+"${ENV_ARGS[@]}"} start "$1"
    normalise_runtime_permissions_window 12 1 &
    tail -F /app/logs/*.log 2>/dev/null &
    wait $!
    ;;
  status)
    /app/server_control.sh ${ENV_ARGS[@]+"${ENV_ARGS[@]}"} status all
    ;;
  test)
    /app/server_control.sh ${ENV_ARGS[@]+"${ENV_ARGS[@]}"} start api
    sleep 5
    : "${API_PORT:?CLOUD_DOG__API_SERVER__PORT must be set for test mode}"
    if curl -fs "http://127.0.0.1:${API_PORT}/health" >/dev/null; then
      echo "HEALTH CHECK PASSED"
      /app/server_control.sh ${ENV_ARGS[@]+"${ENV_ARGS[@]}"} stop all
      exit 0
    else
      echo "HEALTH CHECK FAILED"
      /app/server_control.sh ${ENV_ARGS[@]+"${ENV_ARGS[@]}"} stop all
      exit 1
    fi
    ;;
  shell|bash)
    exec /bin/bash
    ;;
  *)
    echo "Usage: imap-mcp-server [all|api|web|mcp|a2a|status|test|shell]"
    exit 1
    ;;
esac
