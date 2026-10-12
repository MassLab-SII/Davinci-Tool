#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${ROOT_DIR}"

# Load environment
if [ -f "${ROOT_DIR}/.env" ]; then
  set -a; source "${ROOT_DIR}/.env"; set +a
fi

CONFIG_PATH="${1:-configs/egts/appworld.yaml}"
WORLD_URL="http://127.0.0.1:30002"

echo "=== AppWorld EGTS Exploration ==="
echo "config: ${CONFIG_PATH}"

if curl -sf "${WORLD_URL}/admin/status" > /dev/null 2>&1; then
    echo "World reachable at ${WORLD_URL}"
else
    echo "ERROR: World not reachable at ${WORLD_URL}"
    echo "AppWorld is not yet deployed on the cloud server (port 30002)."
    exit 1
fi

export PYTHONPATH="${ROOT_DIR}/src/egts"
exec python src/egts/data_collection/main.py --config "${CONFIG_PATH}"
