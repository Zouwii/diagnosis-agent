#!/bin/bash
# ============================================================================
# DiagKit ttyd 用户连接脚本 (v3 — auth-proxy 写入身份，launch 只读取)
# 由 ttyd 在用户连接时自动执行（ttyd 监听 5434 内部端口）
#
# 认证流程（由 auth-proxy 在 5433 完成）：
#   Browser → :5433 auth-proxy → 钉钉 OAuth → 写入 pending file
#   → auth-proxy 代理到 ttyd :5434 → launch.sh 读取 pending file
# ============================================================================
set -euo pipefail

# ── 路径 ──────────────────────────────────────────────────────
DIAGKIT_ROOT="${HOME}/diagkit"
SKILLS_DIR="${DIAGKIT_ROOT}/jz-claude-skills"
PENDING_DIR="${DIAGKIT_ROOT}/.pending_users"
export DIAGNOSIS_CLI="${SKILLS_DIR}/scripts/diagnosis"

# ── 模型网关 ──────────────────────────────────────────────────
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"
export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-http://one-api.server22.jz}"
export ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-deepseek-v4-flash}"

unset OPENAI_API_KEY OPENAI_API_BASE OPENAI_BASE_URL OPENAI_MODEL 2>/dev/null || true
export no_proxy="${no_proxy:-},one-api.server22.jz,server01.jz,172.19.3.79"
export NO_PROXY="${no_proxy}"

# ── PATH ──────────────────────────────────────────────────────
for p in \
  "${HOME}/.nvm/versions/node/v20.20.2/bin" \
  "${HOME}/.nvm/versions/node/v20.20.1/bin" \
  "${HOME}/.local/bin"
do
  if [ -d "${p}" ] && [[ ":${PATH}:" != *":${p}:"* ]]; then
    PATH="${p}:${PATH}"
  fi
done
export PATH

# ── safe_owner ─────────────────────────────────────────────────
safe_owner() {
  echo -n "${1:-anonymous}" | sha256sum | awk '{print $1}' | cut -c1-24
}

# ── 从 pending file 读取用户身份（auth-proxy 在 WS 连接前写入）─
read_pending_user() {
  local latest user_id name
  latest=$(ls -t "${PENDING_DIR}"/*.json 2>/dev/null | head -1 || echo "")
  if [ -z "${latest}" ] || [ ! -f "${latest}" ]; then
    echo "[diagkit] 警告: 未找到用户身份文件，使用默认用户" >&2
    echo "anonymous|匿名用户"
    return 0
  fi

  user_id=$(python3 -c "import json; d=json.load(open('${latest}')); print(d.get('userId',''))" 2>/dev/null || echo "")
  name=$(python3 -c "import json; d=json.load(open('${latest}')); print(d.get('name',''))" 2>/dev/null || echo "")

  # 清理旧 pending 文件（> 60s）
  find "${PENDING_DIR}" -name "*.json" -mmin +1 -delete 2>/dev/null || true

  if [ -z "${user_id}" ]; then
    echo "anonymous|匿名用户"
  else
    echo "${user_id}|${name}"
  fi
}

# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════

# 等待 pending 文件出现（auth-proxy 可能还在写入）
WAITED=0
while [ ! "$(ls -t "${PENDING_DIR}"/*.json 2>/dev/null | head -1 || echo "")" ] && [ "${WAITED}" -lt 5 ]; do
  sleep 0.5
  WAITED=$((WAITED + 1))
done

AUTH_INFO=$(read_pending_user)
USER_ID="${AUTH_INFO%%|*}"
USER_NAME="${AUTH_INFO##*|}"

if [ "${USER_NAME}" = "${USER_ID}" ] || [ -z "${USER_NAME}" ]; then
  USER_NAME="用户"
fi

SAFE=$(safe_owner "${USER_ID}")

# ── per-user 工作区 ───────────────────────────────────────────
USER_DIAGKIT="${DIAGKIT_ROOT}/users/${SAFE}"
WORKSPACE_DIR="${USER_DIAGKIT}/workspace"
CASE_DIR="${USER_DIAGKIT}/diagnosis-cases"

mkdir -p "${WORKSPACE_DIR}" "${CASE_DIR}"
export DIAGNOSIS_CASE_ROOT="${CASE_DIR}"
export DIAGKIT_QUOTA_GB="${DIAGKIT_QUOTA_GB:-20}"

# ── 加载诊断 skill ────────────────────────────────────────────
CLAUDE_SKILLS_DIR="${HOME}/.claude/skills"
rm -rf "${CLAUDE_SKILLS_DIR}" 2>/dev/null || true
mkdir -p "${CLAUDE_SKILLS_DIR}"
if [ -d "${SKILLS_DIR}/skills" ]; then
  for skill_dir in "${SKILLS_DIR}/skills"/*/; do
    skill_name="$(basename "${skill_dir}")"
    if [ -f "${skill_dir}SKILL.md" ]; then
      ln -sf "${skill_dir}" "${CLAUDE_SKILLS_DIR}/${skill_name}"
    fi
  done
fi

# ── 默认权限：跳过信任检查 + 白名单 ───────────────────────────
mkdir -p "${HOME}/.claude"
cat > "${HOME}/.claude/settings.json" << 'SETEOF'
{
  "permissions": {
    "allow": [
      "Bash(*)",
      "Read(**)",
      "Write(**)",
      "Edit(**)"
    ]
  }
}
SETEOF

# 在当前工作区也创建 .claude/settings.json（跳过信任检查）
mkdir -p "${WORKSPACE_DIR}/.claude"
cat > "${WORKSPACE_DIR}/.claude/settings.json" << 'SETEOF'
{
  "permissions": {
    "allow": [
      "Bash(*)",
      "Read(**)",
      "Write(**)",
      "Edit(**)"
    ]
  }
}
SETEOF

# ── 写入 CLAUDE.md：环境约束，避免 Claude 踩坑 ──────────────
cat > "${WORKSPACE_DIR}/CLAUDE.md" << 'CLAUDE_EOF'
# DiagKit 诊断终端环境约束

你运行在迦智诊断助手的终端环境中。以下约束请在诊断时注意，无需用户确认。

## 诊断入口路由（强制）

当用户提供以下任一诊断输入时，必须先使用 `diagnosis-orchestrator` 作为唯一入口，创建或续接 Case；不得直接以 `teambition`、`robot-peek`、`remote-hand`、`robot-diagnosis` 或其他专项 Skill 承接并结束该请求：

- Teambition/TB 链接或任务 ID；
- 公司内网机器人 IP；
- 远程现场 frp 端口加机器人 IP；
- 本地日志文件或目录路径。

入口处理顺序：

1. 识别唯一输入来源；一个 Case 只允许一个来源。
2. 调用 `diagnosis-orchestrator`，并优先执行 `$DIAGNOSIS_CLI run --source <tb|robot|remote|local> ...` 创建 Case、采集和归档材料。
3. 读取生成的 `context.json`、`report.md`、`human-handoff.md` 和 `next-prompt.md`，再由 `diagnosis-orchestrator` 决定是否调用底层采集或专项分析 Skill。
4. 若 Case 创建或材料获取失败，如实说明失败和待补材料；不得退化为直接查询 TB 后就把任务视为已诊断。

`teambition` 只作为诊断 Case 内的 TB 数据采集能力使用。仅当用户明确说“只查询/只修改 TB 字段或评论”，且没有诊断、排障、日志、现场问题意图时，才可以直接使用 `teambition`。

## SSH 连接机器人

- 本环境**没有** `sshpass`，也**不能** `sudo apt-get install`
- 首次连接机器人请用 `ssh-copy-id` 配置密钥（密码由运维人员提供）：
  ```bash
  ssh-keygen -t rsa -b 2048 -f ~/.ssh/id_rsa -N ''
  ssh-copy-id -o StrictHostKeyChecking=no jz@<robot_ip>
  ```
- 密钥配置后所有命令使用 `ssh jz@<IP> '...'` 非交互式执行
- 机器人 MOTD（登录横幅）可能很长，非交互式 SSH 不会受干扰

## 机器人诊断工具

- `emma_errors` / `emma_wtf` 可能因 ROS Python2.7 日志权限报 `Permission denied`——这是已知 bug，**不是根因**
- 如果上述命令报错，直接 `grep` 读原始日志文件替代：
  - `/opt/jz/log/nav-manager.log` — 导航/伺服
  - `/opt/jz/log/iosys_iobox.log` — 底盘硬件
  - `/opt/jz/log/servo-action.log` — 伺服动作
  - `/opt/jz/log/circus.log` — 进程管理
  - `/opt/jz/log/jz-system.log` — 系统/WiFi
- 执行机器人命令前加 `export PATH=/opt/jz/bin:$PATH`

## 知识库与代码

- 钉钉知识库 token 在 `~/.config/jz-dingtalk/proxy-token`，**可能不存在**
- 如果 token 不存在，跳过知识库查询，不要反复尝试——日志分析通常已足够闭环
- GitLab 同理：`~/.config/jz-gitlab/token` 可能不存在

## 外部证据读取

- 需要外部证据（钉钉文档、GitLab 代码）时先检查对应配置文件是否存在
- 不需要外部证据也能给出可信结论时，直接基于日志闭环，不阻塞流程

## 操作原则

- **只读诊断**：不重启服务、不修改配置、不写机器人文件系统
- 诊断结论置信度标记：`confirmed` > `likely` > `need_human` > `insufficient_data`
- 离线日志分析直接交给 `robot-diagnosis` 专项 skill
CLAUDE_EOF

# ── 磁盘用量 ──────────────────────────────────────────────────
CASE_USAGE=$(du -sh "${CASE_DIR}" 2>/dev/null | cut -f1 || echo "0")

cat <<EOF

=====================================
 迦智诊断助手
 用户: ${USER_NAME}
 Case 用量: ${CASE_USAGE} / ${DIAGKIT_QUOTA_GB}G
 模型: ${ANTHROPIC_MODEL}
=====================================

四种使用方式：

  1️⃣  给 IP          172.22.0.222 到点后一直旋转不走
  2️⃣  给 TB 链接      https://teambition.com/task/684xxxx
  3️⃣  给远程端口      frp 32001 + 192.168.1.100 无法导航
  4️⃣  给日志路径      /home/user/logs/ 分析离线日志

EOF

cd "${WORKSPACE_DIR}"
exec claude --add-dir="${SKILLS_DIR}" --dangerously-skip-permissions
