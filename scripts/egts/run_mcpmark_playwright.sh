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
export PLAYWRIGHT_BROWSER="${PLAYWRIGHT_BROWSER:-chromium}"
export PLAYWRIGHT_HEADLESS="${PLAYWRIGHT_HEADLESS:-true}"
export PLAYWRIGHT_WEBARENA_ACCESS_HOST="${PLAYWRIGHT_WEBARENA_ACCESS_HOST:-host.docker.internal}"

echo "=== MCPMark Playwright EGTS Exploration ==="
echo "config: configs/egts/mcpmark_playwright.yaml"
echo "task suite: ${MCPMARK_TASK_SUITE}"
echo "browser: ${PLAYWRIGHT_BROWSER} (headless=${PLAYWRIGHT_HEADLESS})"
echo "webarena access host: ${PLAYWRIGHT_WEBARENA_ACCESS_HOST}"

WORLD_URL="http://127.0.0.1:30009"
if curl -sf "${WORLD_URL}/admin/status" > /dev/null 2>&1; then
    echo "World reachable at ${WORLD_URL}"
else
    echo "ERROR: World not reachable at ${WORLD_URL}"
    echo "Start the world service first (default port 30009)."
    exit 1
fi

echo
exec python src/egts/data_collection/main.py --config configs/egts/mcpmark_playwright.yaml
