#!/usr/bin/env bash
set -euo pipefail

# ==============================
# Edit parameters here
# ==============================
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON_BIN="${PYTHON_BIN:-python}"
INPUT_DIR="output/exploration_worlds/deepseekv4/exp_tool_sandbox"
OUTPUT_FILE="sft_trajs2data_skill_guided.jsonl"
FRAMEWORK="axolotl"          # llamafactory | axolotl
DIFFICULTY="medium,hard,expert"             # easy | medium | hard | expert | medium,hard,expert | all
PROGRESS_FILE=""             # empty => default (<output>.progress.json)
META_FILE=""                 # optional synthesis meta json for quality backfill

# Quality profile:
# - legacy: keep all (backward-compatible)
# - high_and_acceptable: keep high_quality + acceptable, exclude fallback
# - high_only: keep only high_quality, exclude fallback
# - custom: use QUALITY_TIER / MIN_QUALITY_SCORE / EXCLUDE_FALLBACK below
QUALITY_PROFILE="high_only"     # legacy | high_and_acceptable | high_only | custom

# Custom quality filters (effective when QUALITY_PROFILE=custom)
QUALITY_TIER=""              # e.g. "high_quality,acceptable"
MIN_QUALITY_SCORE="-1"       # negative => disabled; e.g. "0.70"
EXCLUDE_FALLBACK="false"     # true | false

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

# ==============================
# Run
# ==============================
export PYTHONPATH="$PROJECT_ROOT/src/egts"

echo "Running src/egts/data_synthesis/trajectory_to_sft.py"
echo "  input:      $INPUT_DIR"
echo "  output:     $OUTPUT_FILE"
echo "  framework:  $FRAMEWORK"
echo "  difficulty: $DIFFICULTY"
echo "  q_profile:  $QUALITY_PROFILE"
echo "  q_tier:     ${QUALITY_TIER:-<none>}"
echo "  q_min:      $MIN_QUALITY_SCORE"
echo "  q_no_fb:    $EXCLUDE_FALLBACK"
if [[ -n "$META_FILE" ]]; then
  echo "  q_meta:     $META_FILE"
fi

ARGS=(
  -m data_synthesis.trajectory_to_sft
  --input "$INPUT_DIR"
  --output "$OUTPUT_FILE"
  --framework "$FRAMEWORK"
  --difficulty "$DIFFICULTY"
  --exclude-fallback "$EXCLUDE_FALLBACK"
)

if [[ -n "$PROGRESS_FILE" ]]; then
  ARGS+=(--progress "$PROGRESS_FILE")
fi

if [[ -n "$QUALITY_TIER" ]]; then
  ARGS+=(--quality-tier "$QUALITY_TIER")
fi

if [[ "$MIN_QUALITY_SCORE" != "-1" ]]; then
  ARGS+=(--min-quality-score "$MIN_QUALITY_SCORE")
fi

if [[ -n "$META_FILE" ]]; then
  ARGS+=(--meta "$META_FILE")
fi

"$PYTHON_BIN" "${ARGS[@]}"
