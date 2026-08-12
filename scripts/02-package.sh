#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_NAME="diagnosis-agent"
TS="$(date +%Y%m%d-%H%M%S)"
TAR_DIR="${SCRIPT_DIR}/tar"
OUT_TS="${TAR_DIR}/${PROJECT_NAME}-${TS}.tar.gz"
SKILLS_SOURCE="${SCRIPT_DIR}/../jz-claude-skills/skills"

echo "[${PROJECT_NAME}] packaging..."

mkdir -p "${TAR_DIR}"

TAR_ARGS=(
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='.env' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache' \
  --exclude='tar' \
  --exclude='runtime' \
  --exclude='data' \
  --exclude='graph.png' \
)

if [[ -d "${SKILLS_SOURCE}" ]]; then
  echo "[${PROJECT_NAME}] bundling complete Skills from ${SKILLS_SOURCE}"
  tar "${TAR_ARGS[@]}" \
    --transform='s,^skills,diagnosis-agent/skills,' \
    -czf "${OUT_TS}" \
    -C "$(dirname "${SCRIPT_DIR}")" "$(basename "${SCRIPT_DIR}")" \
    -C "$(dirname "${SKILLS_SOURCE}")" "skills"
else
  echo "[${PROJECT_NAME}] complete Skills source not found; using bundled fallback"
  tar "${TAR_ARGS[@]}" \
    -czf "${OUT_TS}" -C "$(dirname "${SCRIPT_DIR}")" "$(basename "${SCRIPT_DIR}")"
fi

echo "[${PROJECT_NAME}] done: ${OUT_TS}"
echo "  size: $(du -h "${OUT_TS}" | cut -f1)"
