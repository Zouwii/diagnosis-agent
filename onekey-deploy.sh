#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_USER="${DIAGNOSIS_DEPLOY_USER:-jz}"
DEPLOY_HOST="${DIAGNOSIS_DEPLOY_HOST:-172.19.3.79}"
DEPLOY_BASE="${DIAGNOSIS_DEPLOY_BASE:-/home/jz/zhr/diagnosis-agent}"
DEPLOY_PASSWORD="${DIAGNOSIS_DEPLOY_PASSWORD:-}"
PORT="${PORT:-6001}"
MANAGEMENT_USERS_ROOT="${DIAGNOSIS_USER_WORKSPACES_ROOT:-/home/jz/zhr/tb_tool_bt/backend/runtime/users}"
RELEASE_ID="$(date +%Y%m%d-%H%M%S)"
TEMP_DIR="$(mktemp -d /tmp/diagnosis-deploy-XXXXXX)"
PACKAGE="${TEMP_DIR}/diagnosis-agent-${RELEASE_ID}.tar.gz"

cleanup() {
  rm -rf "${TEMP_DIR}"
}
trap cleanup EXIT

if (( PORT < 6001 )); then
  echo "[deploy] ERROR: Agent services must use port 6001 or above (got ${PORT})"
  exit 1
fi

SSH=(ssh -o StrictHostKeyChecking=no)
SCP=(scp -o StrictHostKeyChecking=no)
if [[ -n "${DEPLOY_PASSWORD}" ]]; then
  command -v sshpass >/dev/null 2>&1 || { echo "[deploy] sshpass is required when DIAGNOSIS_DEPLOY_PASSWORD is set"; exit 1; }
  SSH=(sshpass -p "${DEPLOY_PASSWORD}" ssh -o StrictHostKeyChecking=no)
  SCP=(sshpass -p "${DEPLOY_PASSWORD}" scp -o StrictHostKeyChecking=no)
fi

echo "[deploy] package diagnosis-agent release=${RELEASE_ID}"
tar \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='.env' \
  --exclude='data' \
  --exclude='runtime' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  -czf "${PACKAGE}" -C "${PROJECT_DIR}" .

REMOTE="${DEPLOY_USER}@${DEPLOY_HOST}"
REMOTE_RELEASE="${DEPLOY_BASE}/releases/${RELEASE_ID}"
echo "[deploy] target ${REMOTE}:${REMOTE_RELEASE}, API port=${PORT}"

"${SSH[@]}" "${REMOTE}" "mkdir -p '${REMOTE_RELEASE}' '${DEPLOY_BASE}/shared/runtime' '${DEPLOY_BASE}/shared/storage'"
"${SCP[@]}" "${PACKAGE}" "${REMOTE}:${REMOTE_RELEASE}/package.tar.gz"

"${SSH[@]}" "${REMOTE}" "bash -lc \"
  set -euo pipefail
  if [ -L '${DEPLOY_BASE}/current' ] && [ -x '${DEPLOY_BASE}/current/run_on_pc_daemon.sh' ]; then
    DIAGNOSIS_RUNTIME_DIR='${DEPLOY_BASE}/shared/runtime' bash '${DEPLOY_BASE}/current/run_on_pc_daemon.sh' stop || true
  fi
  cd '${REMOTE_RELEASE}'
  tar -xzf package.tar.gz
  rm -f package.tar.gz
  if [ ! -f '${DEPLOY_BASE}/shared/.env' ]; then
    cp .env.example '${DEPLOY_BASE}/shared/.env'
    sed -i 's/^PORT=.*/PORT=${PORT}/' '${DEPLOY_BASE}/shared/.env'
    sed -i 's|^DIAGNOSIS_STORAGE_ROOT=.*|DIAGNOSIS_STORAGE_ROOT=${DEPLOY_BASE}/shared/storage|' '${DEPLOY_BASE}/shared/.env'
    sed -i 's|^DIAGNOSIS_USER_WORKSPACES_ROOT=.*|DIAGNOSIS_USER_WORKSPACES_ROOT=${MANAGEMENT_USERS_ROOT}|' '${DEPLOY_BASE}/shared/.env'
  fi
  if [ ! -x '${DEPLOY_BASE}/shared/.venv/bin/python' ]; then
    python3 -m venv '${DEPLOY_BASE}/shared/.venv'
  fi
  ln -sfn '${DEPLOY_BASE}/shared/.env' .env
  ln -sfn '${DEPLOY_BASE}/shared/.venv' .venv
  DIAGNOSIS_RUNTIME_DIR='${DEPLOY_BASE}/shared/runtime' bash run_on_pc_daemon.sh install
  ln -sfn '${REMOTE_RELEASE}' '${DEPLOY_BASE}/current'
  DIAGNOSIS_RUNTIME_DIR='${DEPLOY_BASE}/shared/runtime' bash '${DEPLOY_BASE}/current/run_on_pc_daemon.sh' start
  '${DEPLOY_BASE}/current/.venv/bin/python' -c 'import urllib.request; urllib.request.urlopen(\"http://127.0.0.1:${PORT}/health\", timeout=5).read()'
\""

echo "[deploy] done: http://${DEPLOY_HOST}:${PORT}/health"
echo "[deploy] configure ${DEPLOY_BASE}/shared/.env before production use, especially DIAGNOSIS_INTERNAL_TOKEN"
