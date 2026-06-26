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

# imap-mcp-server — Server control script
# Usage: ./server_control.sh [--env <file>] {start|stop|restart|status} {api|web|mcp|a2a|all}

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="${SCRIPT_DIR}/.pids"
mkdir -p "${PID_DIR}"
export PYTHONPATH="${SCRIPT_DIR}/src:${PYTHONPATH:-}"
PYTHON_BIN="${SCRIPT_DIR}/.venv/bin/python"

interpreter_supports_runtime() {
  local candidate="$1"
  [[ -x "${candidate}" ]] || return 1
  "${candidate}" - <<'PY' >/dev/null 2>&1
import importlib.util

required = ("cloud_dog_storage",)
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    raise SystemExit(1)

has_web_proxy_module = importlib.util.find_spec("cloud_dog_api_kit.web.proxy") is not None
if has_web_proxy_module:
    raise SystemExit(0)

try:
    from cloud_dog_api_kit import WebApiProxy  # noqa: F401
except Exception:
    raise SystemExit(1)

raise SystemExit(0)
PY
}

if ! interpreter_supports_runtime "${PYTHON_BIN}"; then
  PYTHON_BIN="python3"
fi

LOG_DIR="${CLOUD_DOG_LOG_DIR:-}"
if [[ -z "${LOG_DIR}" ]]; then
  if [[ "${SCRIPT_DIR}" == "/app" || -d "/app" ]]; then
    LOG_DIR="/app/logs"
  else
    LOG_DIR="${SCRIPT_DIR}/logs"
  fi
fi
mkdir -p "${LOG_DIR}"

ENV_FILE=""
if [[ "${1:-}" == "--env" ]]; then
  ENV_FILE="${2:-}"
  if [[ -z "${ENV_FILE}" || ! -f "${ENV_FILE}" ]]; then
    echo "Missing or invalid --env file" >&2
    exit 1
  fi
  if [[ -n "${CLOUD_DOG_ENV_FILES:-}" ]]; then
    export CLOUD_DOG_ENV_FILES="${ENV_FILE},${CLOUD_DOG_ENV_FILES}"
  else
    export CLOUD_DOG_ENV_FILES="${ENV_FILE}"
  fi
  shift 2
elif [[ -n "${CLOUD_DOG_ENV_FILE:-}" && -f "${CLOUD_DOG_ENV_FILE}" ]]; then
  export CLOUD_DOG_ENV_FILES="${CLOUD_DOG_ENV_FILE}"
fi

hydrate_plain_env_from_file() {
  [[ -n "${ENV_FILE}" && -f "${ENV_FILE}" ]] || return 0
  eval "$("${PYTHON_BIN}" - "${ENV_FILE}" <<'PY'
from __future__ import annotations

import shlex
import sys
from pathlib import Path


env_path = Path(sys.argv[1]).resolve()
for raw in env_path.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    key = key.strip()
    if not key or key.startswith("CLOUD_DOG__") or key.startswith("CLOUD_DOG_DB__"):
        continue
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    print(f"export {key}={shlex.quote(value)}")
PY
  )"
}

hydrate_plain_env_from_file

ACTION="${1:-status}"
TARGET="${2:-all}"

declare -A MODULES=(
  [api]="imap_hub_server.api_server"
  [web]="imap_hub_server.web_server"
  [mcp]="imap_hub_server.mcp_server"
  [a2a]="imap_hub_server.a2a_server"
)

surface_port_key() {
  local name="$1"
  case "${name}" in
    api) echo "CLOUD_DOG__API_SERVER__PORT" ;;
    web) echo "CLOUD_DOG__WEB_SERVER__PORT" ;;
    mcp) echo "CLOUD_DOG__MCP_SERVER__PORT" ;;
    a2a) echo "CLOUD_DOG__A2A_SERVER__PORT" ;;
    *) return 1 ;;
  esac
}

surface_host_key() {
  local name="$1"
  case "${name}" in
    api) echo "CLOUD_DOG__API_SERVER__HOST" ;;
    web) echo "CLOUD_DOG__WEB_SERVER__HOST" ;;
    mcp) echo "CLOUD_DOG__MCP_SERVER__HOST" ;;
    a2a) echo "CLOUD_DOG__A2A_SERVER__HOST" ;;
    *) return 1 ;;
  esac
}

config_value_from_env_files() {
  local key="$1"
  local value="${!key:-}"
  if [[ -n "${value}" ]]; then
    printf '%s\n' "${value}"
    return
  fi

  local env_file raw_line raw_value
  IFS=',' read -ra env_files <<< "${CLOUD_DOG_ENV_FILES:-}"
  for env_file in "${env_files[@]}"; do
    [[ -f "${env_file}" ]] || continue
    raw_line="$(grep -E "^${key}=" "${env_file}" | tail -n 1 || true)"
    raw_value="${raw_line#*=}"
    if [[ -n "${raw_value}" && "${raw_value}" != "${raw_line}" ]]; then
      value="${raw_value}"
    fi
  done

  printf '%s\n' "${value}"
}

surface_listener_host() {
  local name="$1"
  local host_key host
  host_key="$(surface_host_key "${name}")" || return 1
  host="$(config_value_from_env_files "${host_key}")"
  if [[ -z "${host}" || "${host}" == "0.0.0.0" ]]; then
    host="127.0.0.1"
  fi
  printf '%s\n' "${host}"
}

surface_listener_port() {
  local name="$1"
  local port_key
  port_key="$(surface_port_key "${name}")" || return 1
  config_value_from_env_files "${port_key}"
}

listener_ready() {
  local host="$1"
  local port="$2"
  python3 - "$host" "$port" <<'PY' >/dev/null 2>&1
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
with socket.create_connection((host, port), timeout=0.5):
    pass
PY
}

pid_matches_listener() {
  local pid="$1"
  local port="$2"
  if ! command -v ss >/dev/null 2>&1; then
    return 0
  fi
  ss -ltnp "( sport = :${port} )" 2>/dev/null | grep -q "pid=${pid},"
}

start_server() {
  local name="$1"
  local module="${MODULES[$name]}"
  local pid_file="${PID_DIR}/${name}.pid"
  local log_file="${LOG_DIR}/${name}.log"
  local host port

  ensure_log_file_writable() {
    local path="$1"
    local directory
    directory="$(dirname "${path}")"
    mkdir -p "${directory}"

    if [[ -e "${path}" && ! -w "${path}" ]]; then
      # Host-mounted files may keep restrictive ownership from previous runs.
      rm -f "${path}" 2>/dev/null || {
        echo "Cannot write log file: ${path}" >&2
        return 1
      }
    fi

    touch "${path}" 2>/dev/null || {
      echo "Cannot create log file: ${path}" >&2
      return 1
    }
  }

  host="$(surface_listener_host "${name}")"
  port="$(surface_listener_port "${name}")"

  if [[ -f "${pid_file}" ]] && kill -0 "$(cat "${pid_file}")" 2>/dev/null; then
    local existing_pid
    existing_pid="$(cat "${pid_file}")"
    if [[ -n "${port}" ]] && pid_matches_listener "${existing_pid}" "${port}" && listener_ready "${host}" "${port}"; then
      echo "${name}: running (PID ${existing_pid})"
      return
    fi
    echo "${name}: removing stale pid ${existing_pid}" >&2
    rm -f "${pid_file}"
  fi
  ensure_log_file_writable "${log_file}"
  : > "${log_file}"
  setsid bash -lc "cd '${SCRIPT_DIR}' && export PYTHONPATH='${PYTHONPATH}' && export PYTHONUNBUFFERED=1 PYTHONFAULTHANDLER=1 && echo \$\$ > '${pid_file}' && exec '${PYTHON_BIN}' -m '${module}'" >"${log_file}" 2>&1 < /dev/null &

  local pid="" attempt
  for attempt in {1..50}; do
    if [[ -f "${pid_file}" ]]; then
      pid="$(cat "${pid_file}")"
    fi
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      if [[ -n "${port}" ]] && listener_ready "${host}" "${port}" && pid_matches_listener "${pid}" "${port}"; then
        echo "${name}: started (PID ${pid})"
        return
      fi
    elif [[ -n "${pid}" ]]; then
      break
    fi
    sleep 0.2
  done

  echo "${name}: failed to start (listener ${host}:${port:-unknown} not ready; see ${log_file})" >&2
  rm -f "${pid_file}"
  return 1
}

stop_server() {
  local name="$1"
  local module="${MODULES[$name]}"
  local pid_file="${PID_DIR}/${name}.pid"

  terminate_pid() {
    local target_pid="$1"
    if ! kill -0 "${target_pid}" 2>/dev/null; then
      return
    fi
    kill "${target_pid}" 2>/dev/null || true
    for _ in {1..20}; do
      if ! kill -0 "${target_pid}" 2>/dev/null; then
        return
      fi
      sleep 0.1
    done
    kill -9 "${target_pid}" 2>/dev/null || true
  }

  if [[ -f "${pid_file}" ]]; then
    local pid
    pid="$(cat "${pid_file}")"
    terminate_pid "${pid}"
    rm -f "${pid_file}"
  fi

  while read -r orphan_pid; do
    terminate_pid "${orphan_pid}"
  done < <(pgrep -f " -m ${module}( |$)" || true)

  echo "${name}: stopped"
}

status_server() {
  local name="$1"
  local pid_file="${PID_DIR}/${name}.pid"
  local host port pid
  host="$(surface_listener_host "${name}")"
  port="$(surface_listener_port "${name}")"
  pid="$(cat "${pid_file}" 2>/dev/null || true)"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null && pid_matches_listener "${pid}" "${port}" && listener_ready "${host}" "${port}"; then
    echo "${name}: running (PID $(cat "${pid_file}"))"
  else
    rm -f "${pid_file}" 2>/dev/null || true
    echo "${name}: stopped"
  fi
}

if [[ "${TARGET}" == "all" ]]; then
  TARGETS=(api web mcp a2a)
else
  TARGETS=("${TARGET}")
fi

for server in "${TARGETS[@]}"; do
  case "${ACTION}" in
    start) start_server "${server}" ;;
    stop) stop_server "${server}" ;;
    restart) stop_server "${server}"; sleep 1; start_server "${server}" ;;
    status) status_server "${server}" ;;
    *)
      echo "Usage: $0 [--env <file>] {start|stop|restart|status} {api|mcp|all}" >&2
      echo "Supported targets: api web mcp a2a all" >&2
      exit 1
      ;;
  esac
done
