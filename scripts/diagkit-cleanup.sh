#!/bin/bash
# ============================================================================
# DiagKit TTL 清理脚本
# 删除 7 天前的 raw/ 和 extracted/ 目录，保留文本产物
#
# 部署方式（服务器上）：
#   sudo cp diagkit-cleanup.sh /etc/cron.daily/diagkit-cleanup
#   sudo chmod +x /etc/cron.daily/diagkit-cleanup
#
# 手动执行：
#   bash diagkit-cleanup.sh [--dry-run] [--ttl-days N]
# ============================================================================
set -euo pipefail

TTL_DAYS="${TTL_DAYS:-7}"
DRY_RUN=false

for arg in "$@"; do
  case "${arg}" in
    --dry-run) DRY_RUN=true ;;
    --ttl-days) TTL_DAYS="${2:-7}"; shift ;;
  esac
  shift 2>/dev/null || true
done

CASE_ROOT="${HOME}/diagkit/users"
FIND_MAXDEPTH=5  # users/<safe_id>/diagnosis-cases/<bucket>/<case_id>/raw

CLEANED_COUNT=0
CLEANED_BYTES=0
KEPT_FILES=("report.md" "context.json" "status.json" "events.jsonl" "human-handoff.md" "next-prompt.md")
LOG_FILE="${HOME}/diagkit/cleanup.log"

log() {
  echo "[diagkit-cleanup $(date '+%Y-%m-%d %H:%M:%S')] $*"
}

cleanup_case_root() {
  local root="$1"
  if [ ! -d "${root}" ]; then
    return
  fi

  while IFS= read -r -d '' case_dir; do
    local raw_dir="${case_dir}/raw"
    local extracted_dir="${case_dir}/extracted"
    local tmp_dir="${case_dir}/tmp"

    for target in "${raw_dir}" "${extracted_dir}" "${tmp_dir}"; do
      if [ -d "${target}" ]; then
        local dir_size
        dir_size=$(du -sb "${target}" 2>/dev/null | cut -f1 || echo 0)
        if [ "${DRY_RUN}" = true ]; then
          log "[dry-run] would remove: ${target} ($(du -sh "${target}" 2>/dev/null | cut -f1))"
        else
          rm -rf "${target}"
          log "removed: ${target} ($(numfmt --to=iec ${dir_size}))"
        fi
        CLEANED_COUNT=$((CLEANED_COUNT + 1))
        CLEANED_BYTES=$((CLEANED_BYTES + dir_size))
      fi
    done

    # ensure text artifacts are kept
    local keeps=0
    for fname in "${KEPT_FILES[@]}"; do
      if [ -f "${case_dir}/${fname}" ]; then
        keeps=$((keeps + 1))
      fi
    done
    if [ "${keeps}" -gt 0 ] && [ "${DRY_RUN}" = false ]; then
      log "kept ${keeps} text artifacts in: ${case_dir}"
    fi
  done < <(find "${root}" -maxdepth ${FIND_MAXDEPTH} -type d -name 'raw' -mtime "+${TTL_DAYS}" -printf '%h\0' 2>/dev/null)
}

main() {
  log "TTL cleanup started (ttl=${TTL_DAYS} days, dry_run=${DRY_RUN})"

  if [ -d "${CASE_ROOT}" ]; then
    cleanup_case_root "${CASE_ROOT}"
  else
    log "case root not found: ${CASE_ROOT}"
  fi

  if [ "${CLEANED_COUNT}" -eq 0 ]; then
    log "no expired case directories found"
  else
    log "cleaned ${CLEANED_COUNT} directories, freed $(numfmt --to=iec ${CLEANED_BYTES})"
  fi

  # 全局水位告警
  for mount_point in / /home; do
    local usage_pct
    usage_pct=$(df "${mount_point}" 2>/dev/null | awk 'NR>1 {print $5}' | sed 's/%//' || echo 0)
    if [ -n "${usage_pct}" ] && [ "${usage_pct}" -gt 80 ]; then
      log "WARNING: disk usage ${usage_pct}% on ${mount_point} - consider cleaning old cases"
    fi
  done

  log "cleanup complete"
}

main "$@" >> "${LOG_FILE}" 2>&1
