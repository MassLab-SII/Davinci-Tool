#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${ROOT_DIR}"

# ------------------------------------------------------------------
# Load .env with bash (handles ${VAR:-default} correctly for synthesis)
# ------------------------------------------------------------------
if [ -f "${ROOT_DIR}/.env" ]; then
  set -a; source "${ROOT_DIR}/.env"; set +a
fi

# ==============================
# Override synthesis model endpoints here if needed.
# Defaults come from .env (*_MODEL_BASE_URL / *_MODEL_API_KEY).
# Uncomment and edit to split across endpoints.
# ==============================
# export JUDGE_MODEL_BASE_URL="https://your-endpoint/v1"
# export JUDGE_MODEL_API_KEY="your_api_key"
# export WRITER_MODEL_BASE_URL="https://your-endpoint/v1"
# export WRITER_MODEL_API_KEY="your_api_key"

# ------------------------------------------------------------------
# Cleanup: ensure Ctrl+C kills the current child pipeline process
# ------------------------------------------------------------------
_current_child_pid=""
_cleanup() {
  if [[ -n "${_current_child_pid}" ]] && kill -0 "${_current_child_pid}" 2>/dev/null; then
    echo ""
    echo "=== Shutting down current pipeline (pid=${_current_child_pid}) ==="
    kill -TERM "${_current_child_pid}" 2>/dev/null || true
    sleep 2
    if kill -0 "${_current_child_pid}" 2>/dev/null; then
      echo "Force-killing pipeline (SIGKILL)..."
      kill -KILL "${_current_child_pid}" 2>/dev/null || true
    fi
    echo "Pipeline stopped."
  fi
  exit 130
}
trap _cleanup INT TERM

# ==============================
# Configuration
# ==============================
PYTHON_BIN="python"
CONFIG_PATH="configs/egts/synthesis.yaml"
INPUT_MODE="raw"
LIMIT="0"            # 0 means all; or pass a number to cap per world
BASE_OUTPUT_DIR="output/exploration_worlds/deepseekv4"

# Edit this list to choose which worlds to synthesize.
# Names must match the keys in EXP_NAME_OVERRIDES or follow the
# convention exp_<world> where hyphens become underscores.
SYNTHESIS_WORLDS=(
  "tool_sandbox"
  "stabletoolbench"
  "apibank"
  "terminal-bench"
  "webshop"
  "miniwob"
  "scienceworld"
  "discoveryworld"
  "mcpmark_filesystem"
  "mcpmark_github"
  "mcpmark_postgres"
  "mcpmark_playwright"
  "appworld"
  "toolathlon"
)

# Override exp_name for worlds where the config doesn't follow the
# exp_<world_with_underscores> convention.
declare -A EXP_NAME_OVERRIDES=(
  [mcpmark_github]="exp_mcpmark_github_test"
)

# ------------------------------------------------------------------
# Setup
# ------------------------------------------------------------------
LOG_ROOT="${MULTI_SYNTH_LOG_ROOT:-${ROOT_DIR}/output/multi_synthesis_runs/$(date +%Y%m%d_%H%M%S)}"
mkdir -p "${LOG_ROOT}"

export PYTHONPATH="$ROOT_DIR/src/egts"

_timestamp() {
  date +%H:%M:%S
}

echo "=== EGTS Multi-World Synthesis ==="
echo "start:    $(date)"
echo "root:     ${ROOT_DIR}"
echo "log root: ${LOG_ROOT}"
echo "worlds:   ${#SYNTHESIS_WORLDS[@]} total"
echo "config:   ${CONFIG_PATH}"
echo ""

_success_count=0
_failed_count=0
_skipped_count=0

# ------------------------------------------------------------------
# Main loop — sequential (synthesis is API-rate-limited)
# ------------------------------------------------------------------
for world in "${SYNTHESIS_WORLDS[@]}"; do
  exp_name="${EXP_NAME_OVERRIDES[${world}]:-exp_${world//-/_}}"
  input_dir="${BASE_OUTPUT_DIR}/${exp_name}"
  output_file="${input_dir}/synthesized_review_train_data.json"
  meta_file="${input_dir}/synthesis_progress.json"
  log_path="${LOG_ROOT}/${world}.log"

  echo "[$(_timestamp)] SYNTH  ${world}  exp=${exp_name}  input=${input_dir}"

  # Skip worlds that haven't been collected yet
  if [[ ! -d "${input_dir}" ]]; then
    echo "[$(_timestamp)] SKIP   ${world}  reason=input_dir_not_found: ${input_dir}"
    _skipped_count=$((_skipped_count + 1))
    continue
  fi

  raw_count=$(find "${input_dir}" -maxdepth 4 -name "raw_context.json" 2>/dev/null | wc -l)
  if [[ "${raw_count}" -eq 0 ]]; then
    echo "[$(_timestamp)] SKIP   ${world}  reason=no_raw_episodes"
    _skipped_count=$((_skipped_count + 1))
    continue
  fi

  echo "[$(_timestamp)]        ${world}  raw_episodes=${raw_count}"

  ARGS=(
    src/egts/data_synthesis/pipeline.py
    --config "${CONFIG_PATH}"
    --input "${input_dir}"
    --input-mode "${INPUT_MODE}"
    --output "${output_file}"
    --meta "${meta_file}"
  )

  if [[ "${LIMIT}" != "0" ]]; then
    ARGS+=(--limit "${LIMIT}")
  fi

  set +e
  "${PYTHON_BIN}" "${ARGS[@]}" >"${log_path}" 2>&1 &
  _current_child_pid=$!
  wait "${_current_child_pid}"
  exit_code=$?
  _current_child_pid=""
  set -e

  if [[ ${exit_code} -eq 0 ]]; then
    echo "[$(_timestamp)] OK     ${world}  log=${log_path}"
    _success_count=$((_success_count + 1))
  else
    echo "[$(_timestamp)] FAIL   ${world}  exit=${exit_code}  log=${log_path}"
    _failed_count=$((_failed_count + 1))
  fi
done

echo ""
echo "=== Multi-World Synthesis Finished ==="
echo "end:      $(date)"
echo "success:  ${_success_count}"
echo "failed:   ${_failed_count}"
echo "skipped:  ${_skipped_count}"
echo "total:    $((${_success_count} + ${_failed_count} + ${_skipped_count}))"
echo "logs:     ${LOG_ROOT}"
exit ${_failed_count}
