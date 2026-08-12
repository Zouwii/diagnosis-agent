#!/usr/bin/env bash
# ============================================================================
# DiagKit ttyd 远程管理
# SSH 到服务器执行 start/stop/restart/status
#
# 被 onekey-deploy.sh 调用：bash scripts/manage-diagkit-ttyd.sh restart
# 不想用 diagkit 了：注释掉 onekey 里的这一行即可
# ============================================================================
set -euo pipefail

REMOTE_USER="jz"
REMOTE_HOST="172.19.3.79"
REMOTE_PASS="${DIAGKIT_REMOTE_PASS:-}"
REMOTE_SCRIPT="/home/jz/diagkit/scripts/diagkit-ttyd-service.sh"
ACTION="${1:-restart}"

if ! command -v sshpass >/dev/null 2>&1; then
  echo "[diagkit-ttyd] 缺少 sshpass"
  exit 1
fi

if [ -z "${REMOTE_PASS}" ]; then
  echo "[diagkit-ttyd] 请设置 DIAGKIT_REMOTE_PASS"
  exit 1
fi

sshpass -p "${REMOTE_PASS}" ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" \
  "bash ${REMOTE_SCRIPT} ${ACTION}"
