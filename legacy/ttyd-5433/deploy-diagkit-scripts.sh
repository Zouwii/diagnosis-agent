#!/usr/bin/env bash
# ============================================================================
# 部署 DiagKit 运维脚本到服务器
# 把 diagkit-ttyd-service.sh 和 diagkit-launch.sh 推送到 ~/diagkit/scripts/
# ============================================================================
set -euo pipefail

REMOTE_USER="jz"
REMOTE_HOST="172.19.3.79"
REMOTE_PASS="${DIAGKIT_REMOTE_PASS:-}"
REMOTE_SCRIPTS_DIR="/home/jz/diagkit/scripts"
LOCAL_SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v sshpass >/dev/null 2>&1; then
  echo "[deploy-scripts] 缺少 sshpass"
  exit 1
fi

if [ -z "${REMOTE_PASS}" ]; then
  echo "[deploy-scripts] 请设置 DIAGKIT_REMOTE_PASS"
  exit 1
fi

echo "[deploy-scripts] 确保远程目录存在..."
sshpass -p "${REMOTE_PASS}" ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" \
  "mkdir -p ${REMOTE_SCRIPTS_DIR}"

echo "[deploy-scripts] 推送 diagkit-ttyd-service.sh (原 start-diagkit-ttyd.sh)..."
sshpass -p "${REMOTE_PASS}" scp -o StrictHostKeyChecking=no \
  "${LOCAL_SCRIPTS_DIR}/diagkit-ttyd-service.sh" \
  "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_SCRIPTS_DIR}/"

echo "[deploy-scripts] 推送 diagkit-launch.sh (原 launch-diagkit.sh)..."
sshpass -p "${REMOTE_PASS}" scp -o StrictHostKeyChecking=no \
  "${LOCAL_SCRIPTS_DIR}/diagkit-launch.sh" \
  "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_SCRIPTS_DIR}/"

echo "[deploy-scripts] 推送 diagkit-cleanup.sh (TTL 清理)..."
sshpass -p "${REMOTE_PASS}" scp -o StrictHostKeyChecking=no \
  "${LOCAL_SCRIPTS_DIR}/diagkit-cleanup.sh" \
  "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_SCRIPTS_DIR}/"

echo "[deploy-scripts] 推送 diagkit-auth-proxy.py (登录代理)..."
sshpass -p "${REMOTE_PASS}" scp -o StrictHostKeyChecking=no \
  "${LOCAL_SCRIPTS_DIR}/diagkit-auth-proxy.py" \
  "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_SCRIPTS_DIR}/"

echo "[deploy-scripts] 推送 requirements-diagkit.txt..."
sshpass -p "${REMOTE_PASS}" scp -o StrictHostKeyChecking=no \
  "${LOCAL_SCRIPTS_DIR}/requirements-diagkit.txt" \
  "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_SCRIPTS_DIR}/"

echo "[deploy-scripts] 安装 DiagKit 依赖（apt）..."
sshpass -p "${REMOTE_PASS}" ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" \
  "echo '${REMOTE_PASS}' | sudo -S apt-get install -y -qq \$(cat ${REMOTE_SCRIPTS_DIR}/requirements-diagkit.txt)"

echo "[deploy-scripts] 设置权限..."
sshpass -p "${REMOTE_PASS}" ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" \
  "chmod +x ${REMOTE_SCRIPTS_DIR}/*.sh"

echo "[deploy-scripts] 完成。"
