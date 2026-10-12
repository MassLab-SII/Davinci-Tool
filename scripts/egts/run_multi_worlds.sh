#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${ROOT_DIR}"

# Maximum number of worlds to run concurrently.
# Tune this to stay within your model API's concurrency limit.
BATCH_SIZE=3

# Edit this list to choose which executable worlds to collect in parallel.
# Supported names are the keys in RUNNERS below.
EXECUTABLE_WORLDS=(
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

# Optional per-world config override. Leave unset to use each runner's default.
declare -A CONFIG_OVERRIDES=()

declare -A RUNNERS=(
  [apibank]="scripts/egts/run_apibank.sh"
  [appworld]="scripts/egts/run_appworld.sh"
  [discoveryworld]="scripts/egts/run_discoveryworld.sh"
  [mcpmark_filesystem]="scripts/egts/run_mcpmark_filesystem.sh"
  [mcpmark_github]="scripts/egts/run_mcpmark_github.sh"
  [mcpmark_playwright]="scripts/egts/run_mcpmark_playwright.sh"
  [mcpmark_postgres]="scripts/egts/run_mcpmark_postgres.sh"
  [miniwob]="scripts/egts/run_miniwob.sh"
  [scienceworld]="scripts/egts/run_scienceworld.sh"
  [stabletoolbench]="scripts/egts/run_stabletoolbench.sh"
  [terminal-bench]="scripts/egts/run_terminal_bench.sh"
  [tool_sandbox]="scripts/egts/run_tool_sandbox.sh"
  [toolathlon]="scripts/egts/run_toolathlon.sh"
  [webshop]="scripts/egts/run_webshop.sh"
)

LOG_ROOT="${MULTI_WORLD_LOG_ROOT:-${ROOT_DIR}/output/multi_world_runs/$(date +%Y%m%d_%H%M%S)}"
mkdir -p "${LOG_ROOT}"

# ------------------------------------------------------------------
# Dynamic state
# ------------------------------------------------------------------
declare -A PIDS=()      # world -> child PID
declare -A PGIDS=()     # world -> process group ID
declare -A LOGS=()      # world -> log path
RUNNING=()              # names of currently-running worlds (ordered)
PENDING=("${EXECUTABLE_WORLDS[@]}")
_stopped=false
_failed_count=0
_success_count=0

# ------------------------------------------------------------------
# Signal / cleanup
# ------------------------------------------------------------------
cleanup() {
  if ${_stopped}; then return; fi
  _stopped=true

  # Stop launching new worlds
  PENDING=()

  echo ""
  echo "=== Shutting down ${#RUNNING[@]} running world(s) ==="

  for world in "${RUNNING[@]}"; do
    local pgid="${PGIDS[${world}]:-}"
    if [[ -n "${pgid}" ]] && kill -0 "-${pgid}" 2>/dev/null; then
      kill -TERM "-${pgid}" 2>/dev/null || true
    fi
  done

  # Wait up to 5s for graceful shutdown
  local deadline=$(($(date +%s) + 5))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    local alive=0
    for world in "${RUNNING[@]}"; do
      local pgid="${PGIDS[${world}]:-}"
      if [[ -n "${pgid}" ]] && kill -0 "-${pgid}" 2>/dev/null; then
        alive=1 && break
      fi
    done
    if [ "$alive" -eq 0 ]; then
      echo "All worlds stopped gracefully."
      return
    fi
    sleep 0.3
  done

  echo "Force-killing remaining worlds (SIGKILL)..."
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
# Helpers
# ------------------------------------------------------------------
_timestamp() {
  date +%H:%M:%S
}

launch_world() {
  local world="$1"
  local runner="${RUNNERS[${world}]:-}"
  if [[ -z "${runner}" ]]; then
    echo "[$(_timestamp)] ERROR: unknown world '${world}'" >&2
    return 1
  fi
  if [[ ! -f "${runner}" ]]; then
    echo "[$(_timestamp)] ERROR: runner not found '${world}': ${runner}" >&2
    return 1
  fi

  local log_path="${LOG_ROOT}/${world}.log"
  LOGS["${world}"]="${log_path}"

  local config_override="${CONFIG_OVERRIDES[${world}]:-}"
  if [[ -n "${config_override}" ]]; then
    setsid bash "${runner}" "${config_override}" >"${log_path}" 2>&1 &
  else
    setsid bash "${runner}" >"${log_path}" 2>&1 &
  fi
  local pid=$!
  PIDS["${world}"]=${pid}
  PGIDS["${world}"]=${pid}
  RUNNING+=("${world}")

  echo "[$(_timestamp)] START  ${world}  pid=${pid}  running=${#RUNNING[@]}  pending=${#PENDING[@]}"
}

reap_world() {
  local world="$1"
  local pid="${PIDS[${world}]}"

  # Reap zombie
  wait "${pid}" 2>/dev/null && local exit_code=$? || local exit_code=$?

  if [[ ${exit_code} -eq 0 ]]; then
    echo "[$(_timestamp)] OK     ${world}  log=${LOGS[${world}]}"
    _success_count=$((_success_count + 1))
  else
    echo "[$(_timestamp)] FAIL   ${world}  exit=${exit_code}  log=${LOGS[${world}]}"
    _failed_count=$((_failed_count + 1))
  fi

  # Remove from RUNNING array
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
echo "=== EGTS Multi-World Collection ==="
echo "start:    $(date)"
echo "root:     ${ROOT_DIR}"
echo "log root: ${LOG_ROOT}"
echo "worlds:   ${#EXECUTABLE_WORLDS[@]} total"
echo "batch:    ${BATCH_SIZE} concurrent"
echo ""

# Launch initial batch
while [[ ${#RUNNING[@]} -lt ${BATCH_SIZE} && ${#PENDING[@]} -gt 0 ]]; do
  launch_world "${PENDING[0]}"
  PENDING=("${PENDING[@]:1}")
done
echo ""

# Dynamic dispatch loop
while [[ ${#RUNNING[@]} -gt 0 ]]; do
  if ${_stopped}; then
    break
  fi

  # Poll for finished children
  finished=""
  for world in "${RUNNING[@]}"; do
    pid="${PIDS[${world}]}"
    if ! kill -0 "${pid}" 2>/dev/null; then
      finished="${world}"
      break
    fi
  done

  if [[ -n "${finished}" ]]; then
    reap_world "${finished}"

    # Immediately launch next pending world (unless we're shutting down)
    if [[ ${#PENDING[@]} -gt 0 ]]; then
      launch_world "${PENDING[0]}"
      PENDING=("${PENDING[@]:1}")
    fi
  else
    sleep 1
  fi
done

echo ""
echo "=== Multi-World Collection Finished ==="
echo "end:      $(date)"
echo "success:  ${_success_count}"
echo "failed:   ${_failed_count}"
echo "total:    $((${_success_count} + ${_failed_count}))"
echo "logs:     ${LOG_ROOT}"
exit ${_failed_count}
