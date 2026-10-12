#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT_ENV_FILE="$PROJECT_ROOT/.env"
CONFIG_PATH="configs/egts/mcpmark_github.yaml"
INPUT_DIR="${INPUT_DIR:-output/exploration_worlds/exp_mcpmark_github}"
LIMIT_ARGS=()

cd "$PROJECT_ROOT"

if [ -f "$PROJECT_ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$PROJECT_ENV_FILE"
  set +a
fi

if [ -z "${WRITER_MODEL_BASE_URL:-}" ] || [ -z "${WRITER_MODEL_API_KEY:-}" ]; then
  echo "ERROR: Missing writer model configuration."
  echo "Set WRITER_MODEL_BASE_URL and WRITER_MODEL_API_KEY in $PROJECT_ENV_FILE or the current shell."
  exit 1
fi

if [ -n "${LIMIT:-}" ]; then
  LIMIT_ARGS=(--limit "$LIMIT")
fi

export PYTHONPATH="$PROJECT_ROOT/src/egts"

echo "=== MCPMark GitHub EGTS Experience Backfill ==="
echo "config: $CONFIG_PATH"
echo "input_dir: $INPUT_DIR"
if [ -n "${LIMIT:-}" ]; then
  echo "limit: $LIMIT"
fi
echo ""

python scripts/egts/backfill_experience_store.py \
  --config "$CONFIG_PATH" \
  --input-dir "$INPUT_DIR" \
  "${LIMIT_ARGS[@]}"
