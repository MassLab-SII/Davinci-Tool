#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${ROOT_DIR}"

# ------------------------------------------------------------------
# Load .env
# ------------------------------------------------------------------
# Save user pre-exports so .env MODEL defaults don't clobber them.
_USER_EXPLORATION_MODEL_BASE_URL="${EXPLORATION_MODEL_BASE_URL:-}"
_USER_EXPLORATION_MODEL_API_KEY="${EXPLORATION_MODEL_API_KEY:-}"
_USER_EXPLORATION_MODEL_NAME="${EXPLORATION_MODEL_NAME:-}"
_USER_WRITER_MODEL_BASE_URL="${WRITER_MODEL_BASE_URL:-}"
_USER_WRITER_MODEL_API_KEY="${WRITER_MODEL_API_KEY:-}"
_USER_WRITER_MODEL_NAME="${WRITER_MODEL_NAME:-}"
_USER_JUDGE_MODEL_BASE_URL="${JUDGE_MODEL_BASE_URL:-}"
_USER_JUDGE_MODEL_API_KEY="${JUDGE_MODEL_API_KEY:-}"
_USER_JUDGE_MODEL_NAME="${JUDGE_MODEL_NAME:-}"

if [ -f "${ROOT_DIR}/.env" ]; then
  set -a; source "${ROOT_DIR}/.env"; set +a
fi

# ==============================
# Model endpoints
# ==============================
# Priority: user pre-export > .env value
export EXPLORATION_MODEL_BASE_URL="${_USER_EXPLORATION_MODEL_BASE_URL:-${EXPLORATION_MODEL_BASE_URL:-}}"
export EXPLORATION_MODEL_API_KEY="${_USER_EXPLORATION_MODEL_API_KEY:-${EXPLORATION_MODEL_API_KEY:-}}"
export EXPLORATION_MODEL_NAME="${_USER_EXPLORATION_MODEL_NAME:-${EXPLORATION_MODEL_NAME:-}}"
export WRITER_MODEL_BASE_URL="${_USER_WRITER_MODEL_BASE_URL:-${WRITER_MODEL_BASE_URL:-}}"
export WRITER_MODEL_API_KEY="${_USER_WRITER_MODEL_API_KEY:-${WRITER_MODEL_API_KEY:-}}"
export WRITER_MODEL_NAME="${_USER_WRITER_MODEL_NAME:-${WRITER_MODEL_NAME:-}}"
export JUDGE_MODEL_BASE_URL="${_USER_JUDGE_MODEL_BASE_URL:-${JUDGE_MODEL_BASE_URL:-}}"
export JUDGE_MODEL_API_KEY="${_USER_JUDGE_MODEL_API_KEY:-${JUDGE_MODEL_API_KEY:-}}"
export JUDGE_MODEL_NAME="${_USER_JUDGE_MODEL_NAME:-${JUDGE_MODEL_NAME:-}}"

# ==============================
# Configuration
# ==============================
PYTHON_BIN="${PYTHON_BIN:-python}"
BASE_INPUT_DIR="${BASE_INPUT_DIR:-output/exploration_worlds/deepseekv4}"
BASE_OUTPUT_DIR="${BASE_OUTPUT_DIR:-output/replay_synthesis_prod}"
LIMIT="${LIMIT:-0}"          # 0 = all; global default (overridden by WORLD_LIMITS)
BATCH_SIZE="${MULTI_SYNTH_BATCH_SIZE:-2}"

# Per-world limits — override the global LIMIT for specific worlds.
# Worlds not listed here use the global LIMIT value.
# Example: WORLD_LIMITS=([tool_sandbox]=50 [apibank]=100)
declare -A WORLD_LIMITS=()

# Resume from checkpoint (default: on).  Set to "false" or pass --no-resume
# to force re-processing all episodes.
RESUME="${RESUME:-true}"

# Pipeline mode:
#   replay  — uses data_collection/replay_from_raw.py (replay synthesis from raw episodes, needs MCP servers running)
#   legacy  — uses data_synthesis/pipeline.py (old synthesis pipeline, no MCP needed)
PIPELINE_MODE="${PIPELINE_MODE:-replay}"

# Worlds to process.
# For replay mode, each world's MCP server must be running.
# For legacy mode, no server needed.
SYNTHESIS_WORLDS=(
  # "tool_sandbox"
  # "stabletoolbench"
  # "terminal-bench"
  "mcpmark_filesystem"
  "mcpmark_github"
  "mcpmark_postgres"
  "mcpmark_playwright"
  # "webshop"
  # "miniwob"
  # "scienceworld"
  # "discoveryworld"
  # "apibank"
  # "toolathlon"
  # "appworld"
)

# Override exp_name for worlds where the config doesn't follow the
# exp_<world_with_underscores> convention.
declare -A EXP_NAME_OVERRIDES=(
  [mcpmark_github]="exp_mcpmark_github"
)

# Config mapping — which YAML config to use for each world in replay mode.
# Falls back to "configs/egts/${world}.yaml" if not specified here.
declare -A WORLD_CONFIGS=(
  [tool_sandbox]="configs/egts/tool_sandbox.yaml"
  [stabletoolbench]="configs/egts/stabletoolbench.yaml"
  [apibank]="configs/egts/apibank.yaml"
  [terminal-bench]="configs/egts/terminal-bench.yaml"
  [webshop]="configs/egts/webshop.yaml"
  [miniwob]="configs/egts/miniwob.yaml"
  [scienceworld]="configs/egts/scienceworld.yaml"
  [discoveryworld]="configs/egts/discoveryworld.yaml"
  [mcpmark_filesystem]="configs/egts/mcpmark_filesystem.yaml"
  [mcpmark_github]="configs/egts/mcpmark_github.yaml"
  [mcpmark_postgres]="configs/egts/mcpmark_postgres.yaml"
  [mcpmark_playwright]="configs/egts/mcpmark_playwright.yaml"
  [toolathlon]="configs/egts/toolathlon.yaml"
  [appworld]="configs/egts/appworld.yaml"
)

# ------------------------------------------------------------------
# Signal / cleanup
# ------------------------------------------------------------------
_stopped=false
declare -A PIDS=()
declare -A PGIDS=()
declare -A LOGS=()
RUNNING=()
PENDING=("${SYNTHESIS_WORLDS[@]}")
_success_count=0
_failed_count=0
_skipped_count=0

cleanup() {
  if ${_stopped}; then return; fi
  _stopped=true
  PENDING=()

  echo ""
  echo "=== Shutting down ${#RUNNING[@]} running job(s) ==="

  for world in "${RUNNING[@]}"; do
    local pgid="${PGIDS[${world}]:-}"
    if [[ -n "${pgid}" ]] && kill -0 "-${pgid}" 2>/dev/null; then
      echo "  Sending SIGTERM to ${world} (pgid=${pgid})..."
      kill -TERM "-${pgid}" 2>/dev/null || true
    fi
  done

  local deadline=$(($(date +%s) + 8))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    local alive=0
    for world in "${RUNNING[@]}"; do
      local pgid="${PGIDS[${world}]:-}"
      if [[ -n "${pgid}" ]] && kill -0 "-${pgid}" 2>/dev/null; then
        alive=1 && break
      fi
    done
    if [ "$alive" -eq 0 ]; then
      echo "All jobs stopped gracefully."
      return
    fi
    sleep 0.5
  done

  echo "Force-killing remaining jobs (SIGKILL)..."
  for world in "${RUNNING[@]}"; do
    local pgid="${PGIDS[${world}]:-}"
    if [[ -n "${pgid}" ]] && kill -0 "-${pgid}" 2>/dev/null; then
      kill -KILL "-${pgid}" 2>/dev/null || true
    fi
  done
  echo "Force-kill complete."
}

trap cleanup INT TERM

# ------------------------------------------------------------------
# Setup
# ------------------------------------------------------------------
LOG_ROOT="${MULTI_SYNTH_LOG_ROOT:-${ROOT_DIR}/output/multi_replay_runs/$(date +%Y%m%d_%H%M%S)}"
mkdir -p "${LOG_ROOT}"

export PYTHONPATH="$ROOT_DIR/src/egts"

_timestamp() {
  date +%H:%M:%S
}

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

# Resolve the effective limit for a world: WORLD_LIMITS[world] > LIMIT > 0
_resolve_limit() {
  local world="$1"
  local wl="${WORLD_LIMITS[${world}]:-}"
  if [[ -n "${wl}" ]]; then
    echo "${wl}"
  else
    echo "${LIMIT}"
  fi
}

launch_replay() {
  local world="$1"
  local exp_name="${EXP_NAME_OVERRIDES[${world}]:-exp_${world//-/_}}"
  local input_dir="${BASE_INPUT_DIR}/${exp_name}"
  local output_dir="${BASE_OUTPUT_DIR}/${exp_name}"
  local config_file="${WORLD_CONFIGS[${world}]:-configs/egts/${world}.yaml}"
  local log_path="${LOG_ROOT}/${world}.log"
  local eff_limit
  eff_limit=$(_resolve_limit "${world}")
  LOGS["${world}"]="${log_path}"

  # Pre-flight: input dir must exist with raw episodes
  if [[ ! -d "${input_dir}" ]]; then
    echo "[$(_timestamp)] SKIP   ${world}  reason=input_dir_not_found: ${input_dir}"
    _skipped_count=$((_skipped_count + 1))
    return 1
  fi

  local raw_count
  raw_count=$(find "${input_dir}" -maxdepth 4 -name "trajectory.json" 2>/dev/null | wc -l)
  if [[ "${raw_count}" -eq 0 ]]; then
    echo "[$(_timestamp)] SKIP   ${world}  reason=no_raw_episodes"
    _skipped_count=$((_skipped_count + 1))
    return 1
  fi

  # Pre-flight: config file must exist
  if [[ ! -f "${config_file}" ]]; then
    echo "[$(_timestamp)] SKIP   ${world}  reason=config_not_found: ${config_file}"
    _skipped_count=$((_skipped_count + 1))
    return 1
  fi

  echo "[$(_timestamp)] START  ${world}  exp=${exp_name}  raw=${raw_count}  cfg=${config_file}  limit=${eff_limit}  running=${#RUNNING[@]}  pending=${#PENDING[@]}"

  mkdir -p "${output_dir}"

  local ARGS=(
    src/egts/data_collection/replay_from_raw.py
    --input "${input_dir}"
    --config "${config_file}"
    --output "${output_dir}"
  )

  if [[ "${eff_limit}" != "0" ]]; then
    ARGS+=(--limit "${eff_limit}")
  fi

  if [[ "${RESUME}" != "true" ]]; then
    ARGS+=(--no-resume)
  fi

  setsid "${PYTHON_BIN}" "${ARGS[@]}" >"${log_path}" 2>&1 &
  local pid=$!
  PIDS["${world}"]=${pid}
  PGIDS["${world}"]=${pid}
  RUNNING+=("${world}")
}

launch_legacy() {
  local world="$1"
  local exp_name="${EXP_NAME_OVERRIDES[${world}]:-exp_${world//-/_}}"
  local input_dir="${BASE_INPUT_DIR}/${exp_name}"
  local output_file="${input_dir}/synthesized_review_train_data.json"
  local meta_file="${input_dir}/synthesis_progress.json"
  local config_path="configs/egts/synthesis.yaml"
  local log_path="${LOG_ROOT}/${world}.log"
  local eff_limit
  eff_limit=$(_resolve_limit "${world}")
  LOGS["${world}"]="${log_path}"

  if [[ ! -d "${input_dir}" ]]; then
    echo "[$(_timestamp)] SKIP   ${world}  reason=input_dir_not_found: ${input_dir}"
    _skipped_count=$((_skipped_count + 1))
    return 1
  fi

  local raw_count
  raw_count=$(find "${input_dir}" -maxdepth 4 -name "raw_context.json" 2>/dev/null | wc -l)
  if [[ "${raw_count}" -eq 0 ]]; then
    echo "[$(_timestamp)] SKIP   ${world}  reason=no_raw_episodes"
    _skipped_count=$((_skipped_count + 1))
    return 1
  fi

  echo "[$(_timestamp)] START  ${world}  exp=${exp_name}  raw=${raw_count}  mode=legacy  running=${#RUNNING[@]}  pending=${#PENDING[@]}"

  local ARGS=(
    src/egts/data_synthesis/pipeline.py
    --config "${config_path}"
    --input "${input_dir}"
    --input-mode raw
    --output "${output_file}"
    --meta "${meta_file}"
  )

  if [[ "${eff_limit}" != "0" ]]; then
    ARGS+=(--limit "${eff_limit}")
  fi

  setsid "${PYTHON_BIN}" "${ARGS[@]}" >"${log_path}" 2>&1 &
  local pid=$!
  PIDS["${world}"]=${pid}
  PGIDS["${world}"]=${pid}
  RUNNING+=("${world}")
}

launch_synthesis() {
  if [[ "${PIPELINE_MODE}" == "legacy" ]]; then
    launch_legacy "$1"
  else
    launch_replay "$1"
  fi
}

reap_synthesis() {
  local world="$1"
  local pid="${PIDS[${world}]}"

  wait "${pid}" 2>/dev/null && local exit_code=$? || local exit_code=$?

  if [[ ${exit_code} -eq 0 ]]; then
    echo "[$(_timestamp)] OK     ${world}  log=${LOGS[${world}]}"
    _success_count=$((_success_count + 1))
  else
    echo "[$(_timestamp)] FAIL   ${world}  exit=${exit_code}  log=${LOGS[${world}]}"
    _failed_count=$((_failed_count + 1))
  fi

  local new_running=()
  for w in "${RUNNING[@]}"; do
    if [[ "$w" != "${world}" ]]; then
      new_running+=("$w")
    fi
  done
  RUNNING=("${new_running[@]}")
}

# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
echo "=== EGTS Multi-World Synthesis (Parallel) ==="
echo "start:       $(date)"
echo "root:        ${ROOT_DIR}"
echo "log root:    ${LOG_ROOT}"
echo "pipeline:    ${PIPELINE_MODE}"
echo "input base:  ${BASE_INPUT_DIR}"
echo "output base: ${BASE_OUTPUT_DIR}"
echo "worlds:      ${#SYNTHESIS_WORLDS[@]} total"
echo "batch:       ${BATCH_SIZE} concurrent"
echo "limit:       ${LIMIT} (0=all, global default)"
if [[ ${#WORLD_LIMITS[@]} -gt 0 ]]; then
  echo "per-world limits:"
  for w in "${!WORLD_LIMITS[@]}"; do
    printf "  %-30s %s\n" "${w}" "${WORLD_LIMITS[${w}]}"
  done
fi
echo ""

# Pre-filter: remove worlds that would be skipped
_filtered_pending=()
for world in "${PENDING[@]}"; do
  exp_name="${EXP_NAME_OVERRIDES[${world}]:-exp_${world//-/_}}"
  input_dir="${BASE_INPUT_DIR}/${exp_name}"
  if [[ ! -d "${input_dir}" ]]; then
    echo "[$(_timestamp)] SKIP   ${world}  reason=input_dir_not_found: ${input_dir}"
    _skipped_count=$((_skipped_count + 1))
    continue
  fi

  if [[ "${PIPELINE_MODE}" == "legacy" ]]; then
    raw_count=$(find "${input_dir}" -maxdepth 4 -name "raw_context.json" 2>/dev/null | wc -l)
  else
    raw_count=$(find "${input_dir}" -maxdepth 4 -name "trajectory.json" 2>/dev/null | wc -l)
  fi
  if [[ "${raw_count}" -eq 0 ]]; then
    echo "[$(_timestamp)] SKIP   ${world}  reason=no_raw_episodes"
    _skipped_count=$((_skipped_count + 1))
    continue
  fi

  if [[ "${PIPELINE_MODE}" == "replay" ]]; then
    config_file="${WORLD_CONFIGS[${world}]:-configs/egts/${world}.yaml}"
    if [[ ! -f "${config_file}" ]]; then
      echo "[$(_timestamp)] SKIP   ${world}  reason=config_not_found: ${config_file}"
      _skipped_count=$((_skipped_count + 1))
      continue
    fi
  fi

  _filtered_pending+=("${world}")
done
PENDING=("${_filtered_pending[@]}")

echo ""

if [[ ${#PENDING[@]} -eq 0 ]]; then
  echo "No worlds to process. Exiting."
  exit 0
fi

# Launch initial batch
while [[ ${#RUNNING[@]} -lt ${BATCH_SIZE} && ${#PENDING[@]} -gt 0 ]]; do
  launch_synthesis "${PENDING[0]}"
  PENDING=("${PENDING[@]:1}")
done
echo ""

# Dynamic dispatch loop
while [[ ${#RUNNING[@]} -gt 0 ]]; do
  if ${_stopped}; then break; fi

  finished=""
  for world in "${RUNNING[@]}"; do
    pid="${PIDS[${world}]}"
    if ! kill -0 "${pid}" 2>/dev/null; then
      finished="${world}"
      break
    fi
  done

  if [[ -n "${finished}" ]]; then
    reap_synthesis "${finished}"

    if [[ ${#PENDING[@]} -gt 0 ]]; then
      launch_synthesis "${PENDING[0]}"
      PENDING=("${PENDING[@]:1}")
      echo ""
    fi
  else
    sleep 2
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

# Quality summary for replay mode
if [[ "${PIPELINE_MODE}" == "replay" ]]; then
  echo ""
  echo "=== Per-World Quality Summary (Replay) ==="
  for world in "${SYNTHESIS_WORLDS[@]}"; do
    exp_name="${EXP_NAME_OVERRIDES[${world}]:-exp_${world//-/_}}"
    summary_file="${BASE_OUTPUT_DIR}/${exp_name}/replay_synthesis_summary.json"
    if [[ -f "${summary_file}" ]]; then
      python3 -c "
import json, sys
try:
    with open('${summary_file}') as f:
        d = json.load(f)
    total = d.get('total', 0)
    acc = d.get('accepted', 0)
    q = d.get('quality_distribution', {})
    hq = q.get('high_quality', 0)
    ar = q.get('acceptable', 0)
    rj = q.get('reject', 0)
    rate = f'{acc}/{total} ({100*acc/max(1,total):.0f}%)'
    print(f'  ${world:25s}  accepted={rate:>12s}  high={hq}  acceptable={ar}  reject={rj}')
except Exception as e:
    print(f'  ${world:25s}  (could not read: {e})')
" 2>/dev/null || echo "  ${world:25s}  (no summary file)"
    else
      printf "  %-25s  (not yet processed)\n" "${world}"
    fi
  done
else
  echo ""
  echo "=== Per-World Quality Summary (Legacy) ==="
  for world in "${SYNTHESIS_WORLDS[@]}"; do
    exp_name="${EXP_NAME_OVERRIDES[${world}]:-exp_${world//-/_}}"
    progress_file="${BASE_INPUT_DIR}/${exp_name}/synthesis_progress.json"
    if [[ -f "${progress_file}" ]]; then
      python3 -c "
import json, sys
try:
    with open('${progress_file}') as f:
        d = json.load(f)
    total = d.get('total_episodes', '?')
    accepted = d.get('accepted', '?')
    quality = d.get('quality_distribution', {})
    high_q = quality.get('high_quality', 0)
    acc = quality.get('acceptable', 0)
    rej = quality.get('reject', 0)
    rate = f'{accepted}/{total}' if total != '?' else '?'
    print(f'  ${world:25s}  accepted={rate:>10s}  high={high_q}  acceptable={acc}  reject={rej}')
except Exception as e:
    print(f'  ${world:25s}  (could not read: {e})')
" 2>/dev/null || echo "  ${world:25s}  (no progress file)"
    else
      printf "  %-25s  (not yet synthesized)\n" "${world}"
    fi
  done
fi

exit ${_failed_count}
