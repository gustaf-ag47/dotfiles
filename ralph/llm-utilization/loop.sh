#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
MODE=${1:-}
MODEL=${RALPH_MODEL:-openai-codex/gpt-5.6-luna}
RALPH_CLASS=${RALPH_CLASS:-build}
export RALPH_CLASS PI_LLM_CLASS="$RALPH_CLASS"
MAX=${RALPH_MAX_ITERATIONS:-20}
TIMEOUT=${RALPH_ITERATION_TIMEOUT:-1800}
LOCK="$ROOT/.lock"
PLAN="$ROOT/IMPLEMENTATION_PLAN.md"
LOGDIR="$ROOT/logs"
mkdir -p "$LOGDIR"

usage() { echo "usage: $0 plan|build|status" >&2; exit 2; }
[[ "$MODE" == plan || "$MODE" == build || "$MODE" == status ]] || usage

if [[ "$MODE" == status ]]; then
  grep -E '^- \[[ x]\] [A-Z0-9_-]+:' "$PLAN" || cat "$PLAN"
  exit 0
fi

if ! command -v pi >/dev/null; then echo 'pi not found' >&2; exit 1; fi
if ! command -v llm-wait >/dev/null; then echo 'llm-wait not found' >&2; exit 1; fi
if [[ "$MODE" == build && ${BUILD_APPROVED:-0} != 1 ]]; then
  echo 'BUILD is gated. Re-run with BUILD_APPROVED=1.' >&2
  exit 3
fi
if [[ "$MODE" == build && ! -s "$PLAN" ]]; then echo 'missing plan' >&2; exit 1; fi
if [[ "$MODE" == build && $(grep -cE '^- \[[ x]\] [A-Z0-9_-]+:' "$PLAN" || true) -eq 0 ]]; then
  echo 'plan has no tasks; refusing BUILD' >&2; exit 1
fi

exec 9>"$LOCK"
flock -n 9 || { echo 'another Ralph loop is running' >&2; exit 4; }

run_once() {
  local prompt=$1 log=$2
  local -a pi_args=(--no-extensions --no-skills --no-context-files)
  if [[ "$MODE" == plan ]]; then
    pi_args+=(--tools 'read,grep,find,ls,write,edit')
  fi
  llm-wait --until 'any.routable' --model "$MODEL" --max "${RALPH_WAIT_MAX:-30m}"
  timeout --signal=TERM --kill-after=15s "$TIMEOUT" \
    pi --provider "${MODEL%%/*}" --model "$MODEL" --print --no-session \
      "${pi_args[@]}" "$(cat "$prompt")" > >(tee "$log") 2>&1
}

if [[ "$MODE" == plan ]]; then
  run_once "$ROOT/PROMPT_PLAN.md" "$LOGDIR/plan-$(date -u +%Y%m%dT%H%M%SZ).log"
  exit $?
fi

for ((i=1; i<=MAX; i++)); do
  if ! grep -qE '^- \[ \] [A-Z0-9_-]+:' "$PLAN"; then
    echo 'BUILD complete: no unchecked tasks remain.'
    exit 0
  fi
  run_once "$ROOT/PROMPT_BUILD.md" "$LOGDIR/build-${i}-$(date -u +%Y%m%dT%H%M%SZ).log" || {
    echo "BUILD stopped on iteration $i" >&2
    exit 1
  }
done

echo "BUILD stopped after $MAX iterations with unchecked tasks remaining" >&2
exit 1
