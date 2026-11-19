#!/bin/bash
# Offline only: no device access, no MMIO, no physical memory.
#
# Runs the pure-logic suites behind the official power page: the CPU and GPU
# frequency plans, the boost rules, the sleep wake path, the peripheral vote
# bookkeeping and the cross-module pin of the numbers section 5 states.
# Each suite must print exactly its recorded check count, so a test that stops
# compiling its new cases fails here instead of passing silently.
#
# usage: run-k60-power-host.sh [OUTPUT_DIR]
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../.." && pwd)
OUT=${1:-}
if [ -n "$OUT" ]; then mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd); else OUT=$(mktemp -d); fi
cd "$REPO"
CFLAGS=(-std=c11 -O1 -Wall -Wextra -Werror -I drivers/PongPower)
total=0
run() {
  local name=$1 expected=$2
  shift 2
  cc "${CFLAGS[@]}" "$@" -o "$OUT/$name"
  local out
  out=$("$OUT/$name")
  printf '%s\n' "$out"
  if ! printf '%s\n' "$out" | grep -q "TESTS OK $expected checks"; then
    echo "power-host: $name did not report $expected checks" >&2
    exit 1
  fi
  total=$((total + expected))
}
run cpufreq 154 scripts/tests/test-k60-cpufreq-plan.c drivers/PongPower/K60CpuFreqPlan.c
run gpu-freq 123 scripts/tests/test-k60-gpu-freq-plan.c drivers/PongPower/K60GpuFreqPlan.c
run boost 40 scripts/tests/test-k60-boost-plan.c drivers/PongPower/K60BoostPlan.c
run sleep 73 scripts/tests/test-k60-sleep-plan.c drivers/PongPower/K60SleepPlan.c
run vote 58 scripts/tests/test-k60-power-vote-plan.c drivers/PongPower/K60PowerVotePlan.c
run conformance 27 scripts/tests/test-k60-power-conformance.c \
  drivers/PongPower/K60BoostPlan.c drivers/PongPower/K60SleepPlan.c \
  drivers/PongPower/K60PowerVotePlan.c
echo "power-host: OK ($total checks in 6 suites; binaries in $OUT)"
