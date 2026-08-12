#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_NAME="diagnosis-agent"
TAR_DIR="${SCRIPT_DIR}/tar"
PACKAGE_GLOB="${TAR_DIR}/${PROJECT_NAME}-*.tar.gz"

REMOTE_USER="jz"
REMOTE_HOST="172.19.3.79"
REMOTE_PASS="1"
REMOTE_BASE="/home/jz/zhr"
REMOTE_PROJECT="${REMOTE_BASE}/${PROJECT_NAME}"
PORT="${PORT:-6001}"

INTERNAL_TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || date +%s | sha256sum | cut -c1-32)

if ! command -v sshpass >/dev/null 2>&1; then
  echo "[deploy] 缺少 sshpass，请安装: sudo apt-get install -y sshpass"
  exit 1
fi

LATEST_PACKAGE="$(ls -1t ${PACKAGE_GLOB} 2>/dev/null | head -n 1 || true)"
if [[ -z "${LATEST_PACKAGE}" ]]; then
  echo "[deploy] 未找到部署包: ${PACKAGE_GLOB}"
  echo "[deploy] 先执行: bash scripts/02-package.sh"
  exit 1
fi

PACKAGE_NAME="$(basename "${LATEST_PACKAGE}")"

echo "[deploy] package: ${PACKAGE_NAME}"

echo "[deploy] uploading..."
sshpass -p "${REMOTE_PASS}" scp -o StrictHostKeyChecking=no "${LATEST_PACKAGE}" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_BASE}/"
rm -f "${LATEST_PACKAGE}"

REMOTE_SCRIPT=$(mktemp)
cat > "${REMOTE_SCRIPT}" << REOF
set -e
export PATH="\$HOME/.local/bin:\$PATH"

# 停旧服务，保留 .venv / .env / data / runtime
if [ -x "${REMOTE_PROJECT}/run_on_pc_daemon.sh" ]; then
  bash "${REMOTE_PROJECT}/run_on_pc_daemon.sh" stop || true
  
  rm -rf "${REMOTE_BASE}/.diag_preserve" 2>/dev/null || true
  mkdir -p "${REMOTE_BASE}/.diag_preserve"
  [ -d "${REMOTE_PROJECT}/.venv" ] && mv "${REMOTE_PROJECT}/.venv" "${REMOTE_BASE}/.diag_preserve/.venv" || true
  [ -f "${REMOTE_PROJECT}/.env" ] && mv "${REMOTE_PROJECT}/.env" "${REMOTE_BASE}/.diag_preserve/.env" || true
  [ -d "${REMOTE_PROJECT}/data" ] && mv "${REMOTE_PROJECT}/data" "${REMOTE_BASE}/.diag_preserve/data" || true
  [ -d "${REMOTE_PROJECT}/runtime" ] && mv "${REMOTE_PROJECT}/runtime" "${REMOTE_BASE}/.diag_preserve/runtime" || true
  
  rm -rf "${REMOTE_PROJECT}"
fi
mkdir -p "${REMOTE_PROJECT}"

# 解压
cd "${REMOTE_BASE}"
tar -xzf "${PACKAGE_NAME}" && rm -f "${PACKAGE_NAME}"

# 恢复
[ -d .diag_preserve/.venv ] && mv .diag_preserve/.venv "${REMOTE_PROJECT}/.venv" || true
[ -f .diag_preserve/.env ] && mv .diag_preserve/.env "${REMOTE_PROJECT}/.env" || true
[ -d .diag_preserve/data ] && mv .diag_preserve/data "${REMOTE_PROJECT}/data" || true
[ -d .diag_preserve/runtime ] && mv .diag_preserve/runtime "${REMOTE_PROJECT}/runtime" || true
rm -rf .diag_preserve

cd "${REMOTE_PROJECT}"

# 首次：创建 venv 和 .env
if [ ! -d .venv ]; then
  echo "[deploy] creating venv..."
  python3 -m venv .venv
fi

if [ ! -f .env ]; then
  echo "[deploy] generating .env..."
  cat > .env << ENVEOF
PORT=${PORT}
MANAGEMENT_SYSTEM_URL=http://127.0.0.1:5002
DIAGNOSIS_USER_WORKSPACES_ROOT=/home/jz/jz_workspace/management-system/backend/runtime/users
DIAGNOSIS_INTERNAL_TOKEN=${INTERNAL_TOKEN}
DIAGNOSIS_CORS_ORIGINS=http://127.0.0.1:5002,http://localhost:5002
DIAGNOSIS_ENV=production
DIAGNOSIS_STORAGE_ROOT=${REMOTE_PROJECT}/data/storage
DIAGNOSIS_UPLOAD_MAX_BYTES=2147483648
DIAGNOSIS_WORKER_POLL_SECONDS=1
DIAGNOSIS_ALLOW_ANONYMOUS=false
DIAGNOSIS_DEFAULT_RUNTIME=graph-v1
ENVEOF
  echo "[deploy] .env created"
fi

echo "[deploy] installing deps..."
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q

echo "[deploy] starting..."
bash run_on_pc_daemon.sh start
REOF

echo "[deploy] executing..."
sshpass -p "${REMOTE_PASS}" scp -o StrictHostKeyChecking=no "${REMOTE_SCRIPT}" "${REMOTE_USER}@${REMOTE_HOST}:/tmp/diag-deploy.sh"
sshpass -p "${REMOTE_PASS}" ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" \
  "bash /tmp/diag-deploy.sh && rm -f /tmp/diag-deploy.sh"
rm -f "${REMOTE_SCRIPT}"

echo ""
echo "[deploy] done."
echo "  Web:  http://${REMOTE_HOST}:${PORT}"
echo "  API:  http://${REMOTE_HOST}:${PORT}/health"
echo "  logs: ssh ${REMOTE_USER}@${REMOTE_HOST} 'cd ${REMOTE_PROJECT} && bash run_on_pc_daemon.sh logs'"
