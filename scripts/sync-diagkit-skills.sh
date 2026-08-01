#!/usr/bin/env bash
# ============================================================================
# 同步 DiagKit 技能到服务器
# 只同步 skills/ 目录，deploy 脚本由 onekey-deploy.sh 单独处理
# ============================================================================
set -euo pipefail

REMOTE_USER="jz"
REMOTE_HOST="172.19.3.79"
REMOTE_PASS="${DIAGKIT_REMOTE_PASS:-}"
REMOTE_DIR="/home/jz/diagkit/jz-claude-skills"
LOCAL_CLAUDE_SKILLS="/home/zhr/zhr_ws/src/ai/jz-claude-skills"

if ! command -v sshpass >/dev/null 2>&1; then
  echo "[sync] 缺少 sshpass，请先安装: sudo apt-get install -y sshpass"
  exit 1
fi

if [ -z "${REMOTE_PASS}" ]; then
  echo "[sync] 请设置 DIAGKIT_REMOTE_PASS"
  exit 1
fi

if [ ! -d "${LOCAL_CLAUDE_SKILLS}/skills" ]; then
  echo "[sync] 错误: 找不到 jz-claude-skills 仓库: ${LOCAL_CLAUDE_SKILLS}"
  exit 1
fi

echo "[sync] 源: ${LOCAL_CLAUDE_SKILLS}/skills"
echo "[sync] 目标: ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/skills"

echo "[sync] 确保远程目录存在..."
sshpass -p "${REMOTE_PASS}" ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" \
  "mkdir -p ${REMOTE_DIR}/skills"

echo "[sync] 同步 skills..."
sshpass -p "${REMOTE_PASS}" scp -r -o StrictHostKeyChecking=no \
  "${LOCAL_CLAUDE_SKILLS}/skills/"* \
  "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/skills/"

echo "[sync] 完成。服务器上的技能:"
sshpass -p "${REMOTE_PASS}" ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" \
  "ls ${REMOTE_DIR}/skills/"
