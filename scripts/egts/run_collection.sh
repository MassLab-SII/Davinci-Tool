#!/usr/bin/env bash
set -euo pipefail

# ==============================
# Edit parameters here
# ==============================
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON_BIN="python"   # or: /path/to/python
CONFIG_PATH="configs/egts/tool_sandbox.yaml"
# ==============================
# Run
# ==============================
export PYTHONPATH="$PROJECT_ROOT/src/egts"

echo "Running src/egts/data_collection/main.py"
echo "  config: $CONFIG_PATH"

"$PYTHON_BIN" -m data_collection.main --config "$CONFIG_PATH"
