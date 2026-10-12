#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT_ENV_FILE="$PROJECT_ROOT/.env"
CONFIG_PATH="configs/egts/mcpmark_github.yaml"

cd "$PROJECT_ROOT"

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

if [ -z "${GITHUB_TOKENS:-}" ] || [ -z "${GITHUB_EVAL_ORG:-}" ]; then
  echo "ERROR: Missing MCPMark GitHub configuration."
  echo "Set GITHUB_TOKENS and GITHUB_EVAL_ORG in $PROJECT_ENV_FILE or the current shell."
  exit 1
fi

export PYTHONPATH="$PROJECT_ROOT/src/egts"
export MCPMARK_TASK_SUITE="${MCPMARK_TASK_SUITE:-standard}"

echo "=== MCPMark GitHub EGTS Exploration ==="
echo "config: $CONFIG_PATH"
echo "task suite: $MCPMARK_TASK_SUITE"
echo "eval org: $GITHUB_EVAL_ORG"

WORLD_URL="http://127.0.0.1:30008"
if curl -sf "${WORLD_URL}/admin/status" > /dev/null 2>&1; then
    echo "World reachable at ${WORLD_URL}"
else
    echo "ERROR: World not reachable at ${WORLD_URL}"
    echo "Start the world service first (default port 30008)."
    exit 1
fi

echo ""
exec python src/egts/data_collection/main.py --config "$CONFIG_PATH"

