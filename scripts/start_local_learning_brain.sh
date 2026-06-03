#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${ROOT}/.local-runs/learning-brain"
LOG_DIR="${RUN_DIR}/logs"
BACKEND_PORT="${BACKEND_PORT:-8001}"
WEB_PORT="${WEB_PORT:-3000}"
BACKEND_URL="http://127.0.0.1:${BACKEND_PORT}"
WEB_URL="http://127.0.0.1:${WEB_PORT}"

mkdir -p "${LOG_DIR}" "${RUN_DIR}/user-data"

usage() {
  cat <<EOF
Usage:
  scripts/start_local_learning_brain.sh start [--no-web]
  scripts/start_local_learning_brain.sh stop
  scripts/start_local_learning_brain.sh restart [--no-web]
  scripts/start_local_learning_brain.sh status
  scripts/start_local_learning_brain.sh logs

Env:
  BACKEND_PORT=${BACKEND_PORT}
  WEB_PORT=${WEB_PORT}
  LEARNING_BRAIN_LOCAL_SUPABASE=0  # set to 1 only when you intentionally want remote Supabase writeback

Wechat DevTools should use:
  ${BACKEND_URL}
EOF
}

pid_alive() {
  local pid="${1:-}"
  [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1
}

read_pid() {
  local file="$1"
  [[ -f "${file}" ]] && cat "${file}" || true
}

port_owner() {
  local port="$1"
  lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null | head -1 || true
}

stop_one() {
  local name="$1"
  local pid_file="${RUN_DIR}/${name}.pid"
  local pid
  pid="$(read_pid "${pid_file}")"
  if pid_alive "${pid}"; then
    echo "Stopping ${name} PID=${pid}"
    kill "${pid}" >/dev/null 2>&1 || true
    for _ in $(seq 1 30); do
      if ! pid_alive "${pid}"; then
        break
      fi
      sleep 0.2
    done
    if pid_alive "${pid}"; then
      kill -9 "${pid}" >/dev/null 2>&1 || true
    fi
  fi
  rm -f "${pid_file}"
}

stop_all() {
  stop_one web
  stop_one backend
}

assert_port_free_or_ours() {
  local port="$1"
  local pid_file="$2"
  local owner
  owner="$(port_owner "${port}")"
  [[ -z "${owner}" ]] && return 0
  local ours
  ours="$(read_pid "${pid_file}")"
  if [[ "${owner}" == "${ours}" ]] && pid_alive "${ours}"; then
    return 0
  fi
  echo "Port ${port} is already occupied by PID=${owner}. Stop it first or set a different port." >&2
  return 1
}

load_env() {
  if [[ -f "${ROOT}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${ROOT}/.env"
    set +a
  fi
  export PYTHONUNBUFFERED=1
  export BACKEND_PORT="${BACKEND_PORT}"
  export DEEPTUTOR_ENV="${DEEPTUTOR_ENV:-local}"
  export DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA="${DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA:-1}"
  export DEEPTUTOR_LEARNING_BRAIN_LOCAL_PROJECTION_FALLBACK="${DEEPTUTOR_LEARNING_BRAIN_LOCAL_PROJECTION_FALLBACK:-1}"
  export DEEPTUTOR_ALLOW_LOCAL_WALLET_FALLBACK="${DEEPTUTOR_ALLOW_LOCAL_WALLET_FALLBACK:-1}"
  export DEEPTUTOR_ALLOW_DEV_WECHAT_LOGIN=1
  export DEEPTUTOR_MISTAKE_BOOK_ENABLED=1
  export DEEPTUTOR_MISTAKE_BOOK_WRITE_ENABLED=1
  export DEEPTUTOR_MISTAKE_BOOK_LOCAL_FALLBACK=1
  export DEEPTUTOR_USER_DATA_DIR="${DEEPTUTOR_USER_DATA_DIR:-${RUN_DIR}/user-data}"
  export LANGFUSE_ENABLED="${LANGFUSE_ENABLED:-false}"
  if [[ "${LEARNING_BRAIN_LOCAL_SUPABASE:-0}" != "1" ]]; then
    unset SUPABASE_URL SUPABASE_SERVICE_ROLE_KEY SUPABASE_KEY SUPABASE_DB_URL
    unset SUPABASE_URL_V5 SUPABASE_SERVICE_ROLE_KEY_V5 SUPABASE_ANON_KEY SUPABASE_ANON_KEY_V5
    unset NEXT_PUBLIC_SUPABASE_URL NEXT_PUBLIC_SUPABASE_ANON_KEY
    export FF_AUTH_SUPABASE_BACKEND=false
    export SUPABASE_RAG_ENABLED=false
  fi
}

wait_for_http() {
  local url="$1"
  local label="$2"
  for _ in $(seq 1 90); do
    if curl -fsS "${url}" >/dev/null 2>&1; then
      echo "${label} ready: ${url}"
      return 0
    fi
    sleep 1
  done
  echo "${label} did not become ready: ${url}" >&2
  return 1
}

start_backend() {
  assert_port_free_or_ours "${BACKEND_PORT}" "${RUN_DIR}/backend.pid"
  local pid
  pid="$(read_pid "${RUN_DIR}/backend.pid")"
  if pid_alive "${pid}"; then
    echo "Backend already running: PID=${pid} ${BACKEND_URL}"
    return 0
  fi
  echo "Starting backend on ${BACKEND_URL}"
  (
    cd "${ROOT}"
    load_env
    python - "${LOG_DIR}/backend.log" "${ROOT}" "${BACKEND_PORT}" <<'PY'
import os
import subprocess
import sys

log_path, cwd, port = sys.argv[1], sys.argv[2], sys.argv[3]
log = open(log_path, "ab", buffering=0)
proc = subprocess.Popen(
    [
        sys.executable,
        "-m",
        "uvicorn",
        "deeptutor.api.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        port,
    ],
    cwd=cwd,
    stdin=subprocess.DEVNULL,
    stdout=log,
    stderr=subprocess.STDOUT,
    env=os.environ.copy(),
    start_new_session=True,
    close_fds=True,
)
print(proc.pid)
PY
  ) > "${RUN_DIR}/backend.pid"
  wait_for_http "${BACKEND_URL}/healthz" "Backend"
}

start_web() {
  assert_port_free_or_ours "${WEB_PORT}" "${RUN_DIR}/web.pid"
  local pid
  pid="$(read_pid "${RUN_DIR}/web.pid")"
  if pid_alive "${pid}"; then
    echo "Web already running: PID=${pid} ${WEB_URL}"
    return 0
  fi
  if [[ ! -d "${ROOT}/web/node_modules" ]]; then
    echo "web/node_modules not found. Run npm install in web/ first, or start with --no-web." >&2
    return 1
  fi
  echo "Starting web on ${WEB_URL}"
  (
    cd "${ROOT}/web"
    export NEXT_API_PROXY_TARGET="${BACKEND_URL}"
    python - "${LOG_DIR}/web.log" "${ROOT}/web" "${WEB_PORT}" <<'PY'
import os
import subprocess
import sys

log_path, cwd, port = sys.argv[1], sys.argv[2], sys.argv[3]
log = open(log_path, "ab", buffering=0)
proc = subprocess.Popen(
    ["npm", "run", "dev", "--", "--hostname", "127.0.0.1", "--port", port],
    cwd=cwd,
    stdin=subprocess.DEVNULL,
    stdout=log,
    stderr=subprocess.STDOUT,
    env=os.environ.copy(),
    start_new_session=True,
    close_fds=True,
)
print(proc.pid)
PY
  ) > "${RUN_DIR}/web.pid"
  wait_for_http "${WEB_URL}/" "Web"
}

status() {
  local backend_pid web_pid
  backend_pid="$(read_pid "${RUN_DIR}/backend.pid")"
  web_pid="$(read_pid "${RUN_DIR}/web.pid")"
  if pid_alive "${backend_pid}"; then
    echo "backend: running PID=${backend_pid} ${BACKEND_URL}"
  else
    echo "backend: stopped"
  fi
  if pid_alive "${web_pid}"; then
    echo "web:     running PID=${web_pid} ${WEB_URL}"
  else
    echo "web:     stopped"
  fi
  echo "logs:    ${LOG_DIR}"
}

show_logs() {
  echo "== backend =="
  tail -n 80 "${LOG_DIR}/backend.log" 2>/dev/null || true
  echo
  echo "== web =="
  tail -n 80 "${LOG_DIR}/web.log" 2>/dev/null || true
}

cmd="${1:-start}"
shift || true
start_web_enabled=1
for arg in "$@"; do
  case "${arg}" in
    --no-web) start_web_enabled=0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: ${arg}" >&2; usage; exit 2 ;;
  esac
done

case "${cmd}" in
  start)
    start_backend
    if [[ "${start_web_enabled}" == "1" ]]; then
      start_web
    fi
    status
    echo
    echo "Wechat DevTools local backend: ${BACKEND_URL}"
    echo "Backend QA page: ${BACKEND_URL}/wechat-harness"
    if [[ "${start_web_enabled}" == "1" ]]; then
      echo "Web QA page: ${WEB_URL}/wechat-harness"
    fi
    ;;
  restart)
    stop_all
    start_backend
    if [[ "${start_web_enabled}" == "1" ]]; then
      start_web
    fi
    status
    ;;
  stop)
    stop_all
    status
    ;;
  status)
    status
    ;;
  logs)
    show_logs
    ;;
  -h|--help)
    usage
    ;;
  *)
    echo "Unknown command: ${cmd}" >&2
    usage
    exit 2
    ;;
esac
