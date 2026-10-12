#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".env" ]]; then
  set -a
  source ".env"
  set +a
fi

export PYTHONPATH="$ROOT_DIR/src/egts:${PYTHONPATH:-}"
export MCPMARK_TASK_SUITE="${MCPMARK_TASK_SUITE:-standard}"

echo "=== MCPMark Postgres EGTS Exploration ==="
echo "config: configs/egts/mcpmark_postgres.yaml"
echo "task suite: ${MCPMARK_TASK_SUITE}"

WORLD_URL="http://127.0.0.1:30010"
if curl -sf "${WORLD_URL}/admin/status" > /dev/null 2>&1; then
    echo "World reachable at ${WORLD_URL}"
else
    echo "ERROR: World not reachable at ${WORLD_URL}"
    echo "Start the world service first (default port 30010)."
    exit 1
fi

echo
exec python src/egts/data_collection/main.py --config configs/egts/mcpmark_postgres.yaml
