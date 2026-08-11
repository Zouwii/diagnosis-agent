#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PROJECT_DIR}"

if [[ -f .env ]]; then
  set -a; source .env; set +a
fi

PORT="${PORT:-6001}"
HOST="${HOST:-0.0.0.0}"
RUNTIME_DIR="${RUNTIME_DIR:-${PROJECT_DIR}/runtime}"
STORAGE_ROOT="${DIAGNOSIS_STORAGE_ROOT:-${RUNTIME_DIR}/storage}"
API_PID_FILE="${RUNTIME_DIR}/diagnosis-api.pid"
WORKER_PID_FILE="${RUNTIME_DIR}/diagnosis-worker.pid"
API_LOG="${RUNTIME_DIR}/diagnosis-api.log"
WORKER_LOG="${RUNTIME_DIR}/diagnosis-worker.log"

export PORT DIAGNOSIS_STORAGE_ROOT="${STORAGE_ROOT}"
mkdir -p "${RUNTIME_DIR}" "${STORAGE_ROOT}"

if (( PORT < 6001 )); then
  echo "[diagnosis] ERROR: port must be >= 6001, got ${PORT}"
  exit 1
fi

# 优先 .venv，其次 poetry，最后 system python
if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
elif command -v poetry >/dev/null 2>&1; then
  PYTHON_BIN="poetry run python"
else
  PYTHON_BIN="python3"
fi

is_running() {
  [[ -f "$1" ]] || return 1
  local pid; pid="$(cat "$1")"
  [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1
}

start_services() {
  if is_running "${API_PID_FILE}" || is_running "${WORKER_PID_FILE}"; then
    echo "[diagnosis] already running, use restart"
    exit 1
  fi

  nohup ${PYTHON_BIN} -m uvicorn server.main:app --host "${HOST}" --port "${PORT}" >> "${API_LOG}" 2>&1 &
  echo $! > "${API_PID_FILE}"
  nohup ${PYTHON_BIN} -m server.worker >> "${WORKER_LOG}" 2>&1 &
  echo $! > "${WORKER_PID_FILE}"
  sleep 2

  if ! is_running "${API_PID_FILE}"; then
    echo "[diagnosis] ERROR: API startup failed"
    tail -20 "${API_LOG}" || true
    exit 1
  fi

  echo "[diagnosis] API:  http://${HOST}:${PORT}"
  echo "[diagnosis] Worker started (no port)"
}

stop_services() {
  for name_file in "worker:${WORKER_PID_FILE}" "api:${API_PID_FILE}"; do
    local name="${name_file%%:*}" pid_file="${name_file##*:}"
    if ! is_running "${pid_file}"; then rm -f "${pid_file}"; continue; fi
    local pid; pid="$(cat "${pid_file}")"
    echo "[diagnosis] stopping ${name} (pid=${pid})"
    kill "${pid}" 2>/dev/null || true
    for _ in $(seq 1 10); do kill -0 "${pid}" 2>/dev/null || break; sleep 1; done
    kill -9 "${pid}" 2>/dev/null || true
    rm -f "${pid_file}"
  done
  echo "[diagnosis] stopped"
}

show_status() {
  if is_running "${API_PID_FILE}"; then
    echo "[diagnosis] API running  pid=$(cat "${API_PID_FILE}")  port=${PORT}"
  else
    echo "[diagnosis] API stopped"
  fi
  if is_running "${WORKER_PID_FILE}"; then
    echo "[diagnosis] Worker running  pid=$(cat "${WORKER_PID_FILE}")"
  else
    echo "[diagnosis] Worker stopped"
  fi
}

case "${1:-start}" in
  start)   start_services ;;
  stop)    stop_services ;;
  restart) stop_services; start_services ;;
  status)  show_status ;;
  logs)    tail -n 100 -f "${API_LOG}" "${WORKER_LOG}" ;;
  *) echo "Usage: bash run_on_pc_daemon.sh {start|stop|restart|status|logs}"; exit 1 ;;
esac
