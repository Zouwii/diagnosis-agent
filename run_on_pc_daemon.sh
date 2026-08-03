#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PROJECT_DIR}"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

PORT="${PORT:-6001}"
HOST="${HOST:-0.0.0.0}"
DIAGNOSIS_RUNTIME_DIR="${DIAGNOSIS_RUNTIME_DIR:-${PROJECT_DIR}/runtime}"
DIAGNOSIS_STORAGE_ROOT="${DIAGNOSIS_STORAGE_ROOT:-${DIAGNOSIS_RUNTIME_DIR}/storage}"
API_PID_FILE="${DIAGNOSIS_RUNTIME_DIR}/diagnosis-api.pid"
WORKER_PID_FILE="${DIAGNOSIS_RUNTIME_DIR}/diagnosis-worker.pid"
API_LOG_FILE="${DIAGNOSIS_RUNTIME_DIR}/diagnosis-api.log"
WORKER_LOG_FILE="${DIAGNOSIS_RUNTIME_DIR}/diagnosis-worker.log"
PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"

export PORT DIAGNOSIS_STORAGE_ROOT
mkdir -p "${DIAGNOSIS_RUNTIME_DIR}" "${DIAGNOSIS_STORAGE_ROOT}"

if (( PORT < 6001 )); then
  echo "[diagnosis] ERROR: Agent services must use port 6001 or above (got ${PORT})"
  exit 1
fi

is_running() {
  local pid_file="$1"
  [[ -f "${pid_file}" ]] || return 1
  local pid
  pid="$(cat "${pid_file}")"
  [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1
}

install_deps() {
  if [[ ! -x "${PYTHON_BIN}" ]]; then
    python3 -m venv .venv
  fi
  "${PYTHON_BIN}" -m pip install --upgrade pip
  "${PYTHON_BIN}" -m pip install -r requirements.txt
}

start_services() {
  if [[ ! -x "${PYTHON_BIN}" ]]; then
    echo "[diagnosis] virtualenv missing; run: bash run_on_pc_daemon.sh install"
    exit 1
  fi
  if is_running "${API_PID_FILE}" || is_running "${WORKER_PID_FILE}"; then
    echo "[diagnosis] service already running; use restart"
    exit 1
  fi

  nohup "${PYTHON_BIN}" -m uvicorn server.main:app --host "${HOST}" --port "${PORT}" >>"${API_LOG_FILE}" 2>&1 &
  echo $! >"${API_PID_FILE}"
  nohup "${PYTHON_BIN}" -m server.worker >>"${WORKER_LOG_FILE}" 2>&1 &
  echo $! >"${WORKER_PID_FILE}"
  sleep 1

  if ! is_running "${API_PID_FILE}" || ! is_running "${WORKER_PID_FILE}"; then
    echo "[diagnosis] ERROR: startup failed"
    tail -n 50 "${API_LOG_FILE}" "${WORKER_LOG_FILE}" || true
    exit 1
  fi
  echo "[diagnosis] API started: http://${HOST}:${PORT}"
  echo "[diagnosis] Worker started (no listening port)"
}

stop_one() {
  local name="$1"
  local pid_file="$2"
  if ! is_running "${pid_file}"; then
    rm -f "${pid_file}"
    return
  fi
  local pid
  pid="$(cat "${pid_file}")"
  echo "[diagnosis] stopping ${name} pid=${pid}"
  kill "${pid}" >/dev/null 2>&1 || true
  for _ in $(seq 1 15); do
    kill -0 "${pid}" >/dev/null 2>&1 || break
    sleep 1
  done
  if kill -0 "${pid}" >/dev/null 2>&1; then
    kill -9 "${pid}" >/dev/null 2>&1 || true
  fi
  rm -f "${pid_file}"
}

stop_services() {
  stop_one "worker" "${WORKER_PID_FILE}"
  stop_one "api" "${API_PID_FILE}"
}

show_status() {
  if is_running "${API_PID_FILE}"; then
    echo "[diagnosis] API running pid=$(cat "${API_PID_FILE}") port=${PORT}"
  else
    echo "[diagnosis] API stopped"
  fi
  if is_running "${WORKER_PID_FILE}"; then
    echo "[diagnosis] Worker running pid=$(cat "${WORKER_PID_FILE}")"
  else
    echo "[diagnosis] Worker stopped"
  fi
}

case "${1:-start}" in
  install) install_deps ;;
  start) start_services ;;
  stop) stop_services ;;
  restart) stop_services; start_services ;;
  status) show_status ;;
  logs) tail -n 100 -f "${API_LOG_FILE}" "${WORKER_LOG_FILE}" ;;
  *) echo "Usage: bash run_on_pc_daemon.sh {install|start|stop|restart|status|logs}"; exit 1 ;;
esac
