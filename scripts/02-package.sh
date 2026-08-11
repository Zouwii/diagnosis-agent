#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_NAME="diagnosis-agent"
TS="$(date +%Y%m%d-%H%M%S)"
TAR_DIR="${SCRIPT_DIR}/tar"
OUT_TS="${TAR_DIR}/${PROJECT_NAME}-${TS}.tar.gz"

echo "[${PROJECT_NAME}] packaging..."

mkdir -p "${TAR_DIR}"

tar \
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
  -czf "${OUT_TS}" -C "$(dirname "${SCRIPT_DIR}")" "$(basename "${SCRIPT_DIR}")"

echo "[${PROJECT_NAME}] done: ${OUT_TS}"
echo "  size: $(du -h "${OUT_TS}" | cut -f1)"
