#!/bin/bash
# ============================================================================
# DiagKit 服务管理脚本 (v3 — auth-proxy + ttyd)
#
# 架构:
#   Browser → :5433 auth-proxy (登录页面 + 反向代理)
#           → :5434 ttyd (内部端口，不对外暴露)
#
# 用法:
#   bash diagkit-ttyd-service.sh start      启动所有服务
#   bash diagkit-ttyd-service.sh stop       停止所有服务
#   bash diagkit-ttyd-service.sh restart    重启所有服务
#   bash diagkit-ttyd-service.sh status     查看状态
# ============================================================================
set -euo pipefail

DIAGKIT_ROOT="${HOME}/diagkit"
SCRIPTS_DIR="${DIAGKIT_ROOT}/scripts"
LAUNCH_SCRIPT="${SCRIPTS_DIR}/diagkit-launch.sh"
PROXY_SCRIPT="${SCRIPTS_DIR}/diagkit-auth-proxy.py"

TTYD_PORT="${DIAKIT_TTYD_PORT_INTERNAL:-5434}"
PROXY_PORT="${DIAKIT_PROXY_PORT:-5433}"

PID_FILE="${DIAGKIT_ROOT}/ttyd.pid"
PID_FILE_PROXY="${DIAGKIT_ROOT}/proxy.pid"
LOG_FILE="${DIAGKIT_ROOT}/ttyd.log"
LOG_FILE_PROXY="${DIAGKIT_ROOT}/proxy.log"

mkdir -p "${DIAGKIT_ROOT}"

# ── 检查 ttyd 是否已安装 ──────────────────────────────────────
ttyd_bin() {
  if command -v ttyd >/dev/null 2>&1; then
    echo "ttyd"
  elif [ -x "/usr/local/bin/ttyd" ]; then
    echo "/usr/local/bin/ttyd"
  else
    echo ""
  fi
}

# ── cron ───────────────────────────────────────────────────────
setup_cron() {
  local cleanup_script="${SCRIPTS_DIR}/diagkit-cleanup.sh"
  if [ ! -f "${cleanup_script}" ]; then
    echo "[diagkit] 跳过 cron: ${cleanup_script} 不存在" >&2
    return
  fi
  if crontab -l 2>/dev/null | grep -q 'diagkit-cleanup'; then
    echo "[diagkit] cron 已注册 (diagkit-cleanup)"
    return
  fi
  (crontab -l 2>/dev/null; echo "0 3 * * * bash ${cleanup_script}") | crontab -
  echo "[diagkit] 已注册 cron: 每天凌晨3点 TTL 清理"
}

# ── start ttyd (内部端口 5434) ────────────────────────────────
start_ttyd() {
  TTYD=$(ttyd_bin)
  if [ -z "${TTYD}" ]; then
    echo "[diagkit] 错误: ttyd 未安装" >&2
    exit 1
  fi

  if [ -f "${PID_FILE}" ]; then
    PID=$(cat "${PID_FILE}")
    if kill -0 "${PID}" 2>/dev/null; then
      echo "[diagkit] ttyd 已在运行 (PID: ${PID}, 内部端口: ${TTYD_PORT})"
      return 0
    fi
    rm -f "${PID_FILE}"
  fi

  if [ ! -f "${LAUNCH_SCRIPT}" ]; then
    echo "[diagkit] 错误: 找不到启动脚本 ${LAUNCH_SCRIPT}" >&2
    exit 1
  fi

  echo "[diagkit] 启动内部 ttyd 端口 ${TTYD_PORT}..."
  nohup "${TTYD}" \
    -W \
    -i 127.0.0.1 \
    -p "${TTYD_PORT}" \
    bash "${LAUNCH_SCRIPT}" \
    >> "${LOG_FILE}" 2>&1 &

  TTYD_PID=$!
  echo "${TTYD_PID}" > "${PID_FILE}"

  sleep 1
  if kill -0 "${TTYD_PID}" 2>/dev/null; then
    echo "[diagkit] ttyd 启动成功 (PID: ${TTYD_PID}, 内部端口: ${TTYD_PORT})"
  else
    echo "[diagkit] ttyd 启动失败，查看: tail -20 ${LOG_FILE}" >&2
    rm -f "${PID_FILE}"
    return 1
  fi
}

# ── start auth-proxy (对外端口 5433) ──────────────────────────
start_proxy() {
  if [ ! -f "${PROXY_SCRIPT}" ]; then
    echo "[diagkit] 错误: 找不到代理脚本 ${PROXY_SCRIPT}" >&2
    exit 1
  fi

  if [ -f "${PID_FILE_PROXY}" ]; then
    PID=$(cat "${PID_FILE_PROXY}")
    if kill -0 "${PID}" 2>/dev/null; then
      echo "[diagkit] 代理已在运行 (PID: ${PID}, 端口: ${PROXY_PORT})"
      return 0
    fi
    rm -f "${PID_FILE_PROXY}"
  fi

  echo "[diagkit] 启动 auth-proxy 端口 ${PROXY_PORT}..."
  nohup python3 "${PROXY_SCRIPT}" \
    --port "${PROXY_PORT}" \
    --ttyd-port "${TTYD_PORT}" \
    >> "${LOG_FILE_PROXY}" 2>&1 &

  PROXY_PID=$!
  echo "${PROXY_PID}" > "${PID_FILE_PROXY}"

  sleep 1
  if kill -0 "${PROXY_PID}" 2>/dev/null; then
    echo "[diagkit] auth-proxy 启动成功 (PID: ${PROXY_PID}, 端口: ${PROXY_PORT})"
  else
    echo "[diagkit] auth-proxy 启动失败，查看: tail -20 ${LOG_FILE_PROXY}" >&2
    rm -f "${PID_FILE_PROXY}"
    return 1
  fi
}

# ── stop ──────────────────────────────────────────────────────
stop_proc() {
  local name="$1" pid_file="$2"
  if [ ! -f "${pid_file}" ]; then
    echo "[diagkit] ${name} 未在运行"
    return
  fi
  PID=$(cat "${pid_file}")
  if kill -0 "${PID}" 2>/dev/null; then
    echo "[diagkit] 停止 ${name} (PID: ${PID})..."
    kill "${PID}" 2>/dev/null || true
    sleep 1
    kill -9 "${PID}" 2>/dev/null || true
    echo "[diagkit] ${name} 已停止"
  else
    echo "[diagkit] ${name} 进程已不存在"
  fi
  rm -f "${pid_file}"
}

# ── status ────────────────────────────────────────────────────
check_proc() {
  local name="$1" pid_file="$2" port="$3"
  if [ -f "${pid_file}" ]; then
    PID=$(cat "${pid_file}")
    if kill -0 "${PID}" 2>/dev/null; then
      echo "[diagkit] ${name} 运行中 (PID: ${PID}, 端口: ${port})"
      return 0
    fi
    rm -f "${pid_file}"
  fi
  echo "[diagkit] ${name} 未运行"
  return 1
}

# ── start ─────────────────────────────────────────────────────
do_start() {
  start_ttyd || exit 1
  start_proxy || exit 1
  setup_cron

  SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "172.19.3.79")
  echo ""
  echo "[diagkit] ✅ 诊断终端已就绪"
  echo "[diagkit] 浏览器访问: http://${SERVER_IP}:${PROXY_PORT}"
}

do_stop() {
  stop_proc "auth-proxy" "${PID_FILE_PROXY}"
  stop_proc "ttyd" "${PID_FILE}"
}

do_status() {
  check_proc "auth-proxy" "${PID_FILE_PROXY}" "${PROXY_PORT}"
  check_proc "ttyd" "${PID_FILE}" "${TTYD_PORT}"
}

# ── 主入口 ────────────────────────────────────────────────────
ACTION="${1:-status}"

case "${ACTION}" in
  start)   do_start ;;
  stop)    do_stop ;;
  restart) do_stop; sleep 1; do_start ;;
  status)  do_status ;;
  *)
    echo "用法: bash diagkit-ttyd-service.sh {start|stop|restart|status}"
    exit 1
    ;;
esac
