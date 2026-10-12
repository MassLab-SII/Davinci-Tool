#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${ROOT_DIR}"

# ==============================
# Configuration
# ==============================
PYTHON_BIN="python"
FRAMEWORK="axolotl"               # axolotl | llamafactory

# Quality profile (same as convert.sh):
#   legacy               – keep all records
#   high_and_acceptable  – high_quality + acceptable, exclude fallback
#   high_only            – high_quality only, exclude fallback
#   custom               – use QUALITY_TIER / MIN_QUALITY_SCORE / EXCLUDE_FALLBACK below
QUALITY_PROFILE="${QUALITY_PROFILE:-high_only}"

# Custom quality filters (effective when QUALITY_PROFILE=custom)
QUALITY_TIER=""
MIN_QUALITY_SCORE="-1"
EXCLUDE_FALLBACK="false"

case "$QUALITY_PROFILE" in
  legacy)
    QUALITY_TIER=""
    MIN_QUALITY_SCORE="-1"
    EXCLUDE_FALLBACK="false"
    ;;
  high_and_acceptable)
    QUALITY_TIER="high_quality,acceptable"
    MIN_QUALITY_SCORE="0.70"
    EXCLUDE_FALLBACK="true"
    ;;
  high_only)
    QUALITY_TIER="high_quality"
    MIN_QUALITY_SCORE="0.85"
    EXCLUDE_FALLBACK="true"
    ;;
  custom)
    ;;
  *)
    echo "Unknown QUALITY_PROFILE: $QUALITY_PROFILE"
    echo "Expected one of: legacy | high_and_acceptable | high_only | custom"
    exit 1
    ;;
esac

# Difficulty filter: easy | medium | hard | expert | medium,hard,expert | all
DIFFICULTY="${DIFFICULTY:-all}"

# Source: where synthesis output lives
# SOURCE mode: "legacy" (exploration → synthesis pipeline) or "replay" (replay synthesis pipeline)
SOURCE="${SOURCE:-replay}"

case "$SOURCE" in
  legacy)
    BASE_INPUT_DIR="${BASE_INPUT_DIR:-output/exploration_worlds/deepseekv4}"
    ;;
  replay)
    BASE_INPUT_DIR="${BASE_INPUT_DIR:-output/replay_synthesis_prod}"
    ;;
  *)
    echo "Unknown SOURCE: $SOURCE (expected: legacy | replay)"
    exit 1
    ;;
esac

# Target: axolotl training data directory
OUTPUT_DIR="${OUTPUT_DIR:-${ROOT_DIR}/output/sft}"

# Worlds to convert. Leave empty to auto-discover all worlds with synthesis output.
# Names use underscores: stabletoolbench, mcpmark_filesystem, etc.
CONVERT_WORLDS=(
  "stabletoolbench"
  "tool_sandbox"
  "apibank"          # DROPPED: banking APIs, no benchmark overlap
  "terminal-bench"
  "webshop"          # DROPPED: shopping-specific, only 5 tools, too narrow
  "miniwob"          # DROPPED: web UI DOM interaction, mismatched paradigm
  "scienceworld"     # DROPPED: exploration game, teaches random actions
  "discoveryworld"   # DROPPED: exploration game, 50-200 step random walks
  "appworld"
  "toolathlon"
  "mcpmark_filesystem"
  "mcpmark_github"
  "mcpmark_playwright"
  "mcpmark_postgres"
)

# Override exp_name for worlds where the synthesis output directory doesn't
# follow the exp_<world_with_underscores> convention.
declare -A EXP_NAME_OVERRIDES=(
  [terminal-bench]="exp_terminal_bench"
)

# Conversion runs per batch (conversion is fast, I/O-bound; use moderate concurrency)
BATCH_SIZE="${CONVERT_BATCH_SIZE:-4}"

# ==============================
# Setup
# ==============================
export PYTHONPATH="$ROOT_DIR/src/egts"

_timestamp() {
  date +%H:%M:%S
}

echo "=== EGTS Batch SFT Conversion ==="
echo "start:       $(date)"
echo "root:        ${ROOT_DIR}"
echo "source:      ${SOURCE}"
echo "input base:  ${BASE_INPUT_DIR}"
echo "output dir:  ${OUTPUT_DIR}"
echo "framework:   ${FRAMEWORK}"
echo "quality:     ${QUALITY_PROFILE}"
echo "difficulty:  ${DIFFICULTY}"
echo ""

# ==============================
# Auto-discover worlds with synthesis output
# ==============================
if [[ ${#CONVERT_WORLDS[@]} -eq 0 ]]; then
  echo "Auto-discovering worlds with synthesis output (source=${SOURCE})..."
  CONVERT_WORLDS=()
  for exp_dir in "${BASE_INPUT_DIR}"/exp_*/; do
    [[ -d "$exp_dir" ]] || continue
    exp_name=$(basename "$exp_dir")
    # Check for synthesis output (depends on SOURCE)
    has_output=false
    if [[ "${SOURCE}" == "replay" ]]; then
      [[ -f "${exp_dir}/trajs2data_replay_synthesis/replay_data.jsonl" ]] && has_output=true
    else
      [[ -f "${exp_dir}/synthesized_review_train_data.json" ]] || \
      [[ -f "${exp_dir}/synthesized_review_records.json" ]] && has_output=true
    fi
    if $has_output; then
      # Map exp_name back to world name
      world_name="${exp_name#exp_}"
      CONVERT_WORLDS+=("${world_name}")
      if [[ "${SOURCE}" == "replay" ]]; then
        record_count=$(wc -l < "${exp_dir}/trajs2data_replay_synthesis/replay_data.jsonl" 2>/dev/null | awk '{print $1}')
        echo "  ${world_name}  (${exp_name})  records=${record_count}"
      else
        raw_count=$(find "$exp_dir" -maxdepth 4 -name "raw_context.json" 2>/dev/null | wc -l)
        echo "  ${world_name}  (${exp_name})  raw_episodes=${raw_count}"
      fi
    fi
  done
  echo "Discovered ${#CONVERT_WORLDS[@]} world(s) with synthesis output."
  echo ""
fi

if [[ ${#CONVERT_WORLDS[@]} -eq 0 ]]; then
  echo "No worlds to convert. Exiting."
  exit 0
fi

mkdir -p "${OUTPUT_DIR}"

# ==============================
# Temp directory for intermediate JSONL files
# ==============================
TEMP_DIR=$(mktemp -d -t egts_convert_XXXXXX)
cleanup_temp() {
  rm -rf "${TEMP_DIR}"
}
trap cleanup_temp EXIT

# ==============================
# Signal / cleanup for parallel mode
# ==============================
_stopped=false
declare -A PIDS=()
declare -A PGIDS=()
RUNNING=()
PENDING=("${CONVERT_WORLDS[@]}")
_success_count=0
_failed_count=0

cleanup() {
  if ${_stopped}; then return; fi
  _stopped=true
  PENDING=()

  echo ""
  echo "=== Shutting down ${#RUNNING[@]} running conversion job(s) ==="

  for world in "${RUNNING[@]}"; do
    local pgid="${PGIDS[${world}]:-}"
    if [[ -n "${pgid}" ]] && kill -0 "-${pgid}" 2>/dev/null; then
      kill -TERM "-${pgid}" 2>/dev/null || true
    fi
  done
  sleep 2
  for world in "${RUNNING[@]}"; do
    local pgid="${PGIDS[${world}]:-}"
    if [[ -n "${pgid}" ]] && kill -0 "-${pgid}" 2>/dev/null; then
      kill -KILL "-${pgid}" 2>/dev/null || true
    fi
  done
  echo "Shutdown complete."
}

trap cleanup INT TERM

# ==============================
# Convert a single world
# ==============================
convert_world() {
  local world="$1"
  local exp_name="${EXP_NAME_OVERRIDES[${world}]:-exp_${world//-/_}}"
  local input_dir="${BASE_INPUT_DIR}/${exp_name}"
  local jsonl_tmp="${TEMP_DIR}/${world}.jsonl"
  local progress_file="${TEMP_DIR}/${world}.progress.json"

  # Find synthesis output file (depends on SOURCE)
  local synth_file=""
  if [[ "${SOURCE}" == "replay" ]]; then
    # Replay: replay_data.jsonl in trajs2data_replay_synthesis/
    local replay_jsonl="${input_dir}/trajs2data_replay_synthesis/replay_data.jsonl"
    if [[ -f "${replay_jsonl}" ]]; then
      synth_file="${replay_jsonl}"
    fi
  else
    # Legacy: synthesized_review_train_data.json or synthesized_review_records.json
    if [[ -f "${input_dir}/synthesized_review_train_data.json" ]]; then
      synth_file="${input_dir}/synthesized_review_train_data.json"
    elif [[ -f "${input_dir}/synthesized_review_records.json" ]]; then
      synth_file="${input_dir}/synthesized_review_records.json"
    else
      # Search recursively
      synth_file=$(find "${input_dir}" -maxdepth 4 -name "synthesized_review_train_data.json" -o -name "synthesized_review_records.json" 2>/dev/null | head -1)
    fi
  fi

  if [[ -z "${synth_file}" ]]; then
    echo "[$(_timestamp)] SKIP   ${world}  reason=no_synthesis_output"
    return 1
  fi

  echo "[$(_timestamp)] START  ${world}  synth=$(basename "${synth_file}")"

  # Step 1: Run converter → JSONL
  local ARGS=(
    -m data_synthesis.trajectory_to_sft
    --input "${synth_file}"
    --output "${jsonl_tmp}"
    --framework "${FRAMEWORK}"
    --progress "${progress_file}"
    --difficulty "${DIFFICULTY}"
    --exclude-fallback "${EXCLUDE_FALLBACK}"
  )

  if [[ -n "${QUALITY_TIER}" ]]; then
    ARGS+=(--quality-tier "${QUALITY_TIER}")
  fi
  if [[ "${MIN_QUALITY_SCORE}" != "-1" ]]; then
    ARGS+=(--min-quality-score "${MIN_QUALITY_SCORE}")
  fi

  set +e
  "${PYTHON_BIN}" "${ARGS[@]}" 2>&1
  local exit_code=$?
  set -e

  if [[ ${exit_code} -ne 0 ]]; then
    echo "[$(_timestamp)] FAIL   ${world}  stage=convert  exit=${exit_code}"
    return 1
  fi

  # Count converted records from JSONL
  local data_num
  data_num=$(wc -l < "${jsonl_tmp}" | awk '{print $1}')
  if [[ "${data_num}" -eq 0 ]]; then
    echo "[$(_timestamp)] SKIP   ${world}  reason=zero_records_after_filter"
    return 1
  fi

  # Step 2: Convert JSONL → JSON array, save to output
  local output_file="${OUTPUT_DIR}/${world}.json"
  python3 -c "
import json, sys
records = []
with open('${jsonl_tmp}', 'r') as f:
    for line in f:
        line = line.strip()
        if line:
            records.append(json.loads(line))
with open('${output_file}', 'w') as f:
    json.dump(records, f, indent=2, ensure_ascii=False)
print(f'Wrote {len(records)} records to ${output_file}')
"

  local file_size
  file_size=$(du -h "${output_file}" | cut -f1)
  echo "[$(_timestamp)] OK     ${world}  records=${data_num}  size=${file_size}  output=${output_file}"
  return 0
}

# ==============================
# Main — sequential or parallel
# ==============================
if [[ "${BATCH_SIZE}" -le 1 ]]; then
  # Sequential mode (simpler, better logging)
  for world in "${CONVERT_WORLDS[@]}"; do
    if convert_world "${world}"; then
      _success_count=$((_success_count + 1))
    else
      _failed_count=$((_failed_count + 1))
    fi
    echo ""
  done
else
  # Parallel mode (reuses pattern from run_multi_world_synthesis_parallel.sh)
  launch_convert() {
    local world="$1"
    convert_world "${world}" &
    local pid=$!
    PIDS["${world}"]=${pid}
    PGIDS["${world}"]=${pid}
    RUNNING+=("${world}")
  }

  reap_convert() {
    local world="$1"
    local pid="${PIDS[${world}]}"
    local exit_code
    wait "${pid}" 2>/dev/null
    exit_code=$?
    if [[ ${exit_code} -eq 0 ]]; then
      _success_count=$((_success_count + 1))
    else
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

  # Launch initial batch
  while [[ ${#RUNNING[@]} -lt ${BATCH_SIZE} && ${#PENDING[@]} -gt 0 ]]; do
    launch_convert "${PENDING[0]}"
    PENDING=("${PENDING[@]:1}")
  done
  echo ""

  # Dynamic dispatch
  while [[ ${#RUNNING[@]} -gt 0 ]]; do
    if ${_stopped}; then break; fi
    finished=""
    for world in "${RUNNING[@]}"; do
      if ! kill -0 "${PIDS[${world}]}" 2>/dev/null; then
        finished="${world}"
        break
      fi
    done
    if [[ -n "${finished}" ]]; then
      reap_convert "${finished}"
      if [[ ${#PENDING[@]} -gt 0 ]]; then
        launch_convert "${PENDING[0]}"
        PENDING=("${PENDING[@]:1}")
        echo ""
      fi
    else
      sleep 1
    fi
  done
fi

# ==============================
# Summary
# ==============================
echo ""
echo "=== Batch Conversion Finished ==="
echo "end:      $(date)"
echo "success:  ${_success_count}"
echo "failed:   ${_failed_count}"
echo "total:    $((${_success_count} + ${_failed_count}))"
echo ""

# List output files
echo "=== Output Files ==="
for f in "${OUTPUT_DIR}"/*.json; do
  if [[ -f "$f" ]]; then
    name=$(basename "$f")
    size=$(du -h "$f" | cut -f1)
    records=$(python3 -c "import json; print(len(json.load(open('$f'))))" 2>/dev/null || echo "?")
    printf "  %-50s  records=%s  size=%s\n" "$name" "$records" "$size"
  fi
done

echo ""
echo "output dir: ${OUTPUT_DIR}"
exit ${_failed_count}
