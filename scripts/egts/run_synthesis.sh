#!/usr/bin/env bash
set -euo pipefail

# ==============================
# Edit parameters here
# ==============================
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON_BIN="python"   # or: /path/to/python
CONFIG_PATH="configs/egts/synthesis.yaml"
INPUT_DIR="output/exploration_worlds/deepseekv4/exp_tool_sandbox"   # empty => pipeline default path
INPUT_MODE="raw"      # auto | raw | synthesized
LIMIT="0"            # 0 means all
# OUTPUT_FILE="output/synthesis/filesystem/exp_glm47/data_synthesis_ds31/synthesized_review_records.json"        # empty => pipeline default path
# META_FILE="output/synthesis/filesystem/exp_glm47/data_synthesis_ds31/synthesis_progress.json"          # empty => pipeline default path
OUTPUT_FILE="output/exploration_worlds/deepseekv4/exp_tool_sandbox/synthesized_review_train_data.json"        # empty => pipeline default path
META_FILE="output/exploration_worlds/deepseekv4/exp_tool_sandbox/synthesis_progress.json"    
# ==============================
# Run
# ==============================
export PYTHONPATH="$PROJECT_ROOT/src/egts"

echo "Running src/egts/data_synthesis/pipeline.py"
echo "  config: $CONFIG_PATH"
echo "  input:  $INPUT_DIR"
echo "  mode:   $INPUT_MODE"
echo "  limit:  $LIMIT"

ARGS=(
  src/egts/data_synthesis/pipeline.py
  --config "$CONFIG_PATH"
  --input "$INPUT_DIR"
  --input-mode "$INPUT_MODE"
)

if [[ "$LIMIT" != "0" ]]; then
  ARGS+=(--limit "$LIMIT")
fi

if [[ -n "$OUTPUT_FILE" ]]; then
  ARGS+=(--output "$OUTPUT_FILE")
fi

if [[ -n "$META_FILE" ]]; then
  ARGS+=(--meta "$META_FILE")
fi

"$PYTHON_BIN" "${ARGS[@]}"
