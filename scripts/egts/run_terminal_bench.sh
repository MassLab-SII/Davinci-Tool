#!/usr/bin/env bash
set -euo pipefail

# ======================================
# Terminal-Bench World Exploration Pipeline
# ======================================
# Starts Terminal-Bench Docker world, waits for it to be healthy, then runs pipeline.
# Usage: bash run_terminal_bench.sh

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
EVAL_ROOT="$(cd "$PROJECT_ROOT/environments/egts/terminal-bench-world" && pwd)"
PROJECT_ENV_FILE="$PROJECT_ROOT/.env"
cd "$PROJECT_ROOT"

# ==============================
# Edit parameters here
# ==============================
PYTHON_BIN="python"
CONFIG_PATH="configs/egts/terminal-bench.yaml"

WORLD_URL="http://127.0.0.1:30016"
HEALTH_TIMEOUT=180                        # seconds to wait for world to start

# ==============================
# Step 0: Load env
# ==============================
if [ -f "$PROJECT_ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$PROJECT_ENV_FILE"
  set +a
fi

if [ -z "${EXPLORATION_MODEL_BASE_URL:-}" ] || [ -z "${EXPLORATION_MODEL_API_KEY:-}" ]; then
  echo "ERROR: Missing exploration model configuration."
  echo "Set EXPLORATION_MODEL_BASE_URL and EXPLORATION_MODEL_API_KEY in $PROJECT_ENV_FILE or the current shell."
  exit 1
fi

# ==============================
# Step 1: Start Docker world
# ==============================
echo "=== Terminal-Bench Exploration Pipeline ==="
echo ""

if curl -sf "$WORLD_URL/admin/status" > /dev/null 2>&1; then
    echo "Terminal-Bench world already running at $WORLD_URL"
else
    echo "ERROR: Terminal-Bench world not reachable at $WORLD_URL"
    echo "Start the world service first."
    echo "To start locally: cd $EVAL_ROOT && docker compose up -d"
    exit 1
fi

echo ""
echo "World info:"
curl -sf "$WORLD_URL/admin/info" | "$PYTHON_BIN" -m json.tool 2>/dev/null || true
echo ""

# ==============================
# Step 2: Run pipeline
# ==============================
export PYTHONPATH="$PROJECT_ROOT/src/egts"

echo "Running src/egts/data_collection/main.py"
echo "  config: $CONFIG_PATH"
echo ""

"$PYTHON_BIN" src/egts/data_collection/main.py --config "$CONFIG_PATH"
