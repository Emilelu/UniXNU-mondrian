#!/bin/bash
# Offline only: no device access, no MMIO, no physical memory.
#
# Runs the pure-logic suites behind the official power page: the CPU and GPU
# frequency plans, the boost rules, the sleep wake path, the ArmCpuSleep
# interface, the peripheral vote bookkeeping, the rail ordering model, the
# thermal trip map, the charge-auth protocol state machine, the HMAC vectors and
# the cross-module pin of the numbers section 5 states.
# Each suite must print exactly its recorded check count, so a test that stops
# compiling its new cases fails here instead of passing silently. The python half
# (carry manifest, the three console judges, the ios27 preflight, the SMCCC text
# gate, the ADSP image and MDT readers) runs after the C suites and must exit 0,
# so a judge that stops matching its own fixtures cannot pass unseen.
#
# usage: run-k60-power-host.sh [OUTPUT_DIR]
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../.." && pwd)
OUT=${1:-}
if [ -n "$OUT" ]; then mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd); else OUT=$(mktemp -d); fi
cd "$REPO"
python3 scripts/check-power-portability.py
CFLAGS=(-std=c11 -O1 -Wall -Wextra -Werror -I drivers/PongPower)
if [ "${K60_POWER_SANITIZE:-0}" != "0" ]; then
  CFLAGS+=(-g -fsanitize=address,undefined -fno-omit-frame-pointer)
fi
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
run cpufreq 203 scripts/tests/test-k60-cpufreq-plan.c drivers/PongPower/K60CpuFreqPlan.c
run gpu-freq 140 scripts/tests/test-k60-gpu-freq-plan.c drivers/PongPower/K60GpuFreqPlan.c
run boost 40 scripts/tests/test-k60-boost-plan.c drivers/PongPower/K60BoostPlan.c
run sleep 73 scripts/tests/test-k60-sleep-plan.c drivers/PongPower/K60SleepPlan.c
run vote 58 scripts/tests/test-k60-power-vote-plan.c drivers/PongPower/K60PowerVotePlan.c
run armcpu-sleep 1038 scripts/tests/test-armcpu-sleep.c
run conformance 134 scripts/tests/test-k60-power-conformance.c \
  drivers/PongPower/K60BoostPlan.c drivers/PongPower/K60SleepPlan.c \
  drivers/PongPower/K60PowerVotePlan.c drivers/PongPower/K60RailPlan.c
run thermal 125 scripts/tests/test-k60-thermal-map.c \
  drivers/PongPower/K60ThermalMap.c drivers/PongPower/K60RailPlan.c
run charge-auth 99 scripts/tests/test-k60-charge-auth.c drivers/PongPower/K60ChargeAuth.c
run charge-hmac 5 scripts/tests/test-k60-charge-hmac.c
echo "power-host: OK ($total checks in 10 suites; portability preflight passed; binaries in $OUT)"

# The python half of the line is a suite too: the judges and the carry manifest
# rotted silently the last time nothing ran them (P-170, the charge-auth suites
# shipped in the tree and no runner referenced them). The ADSP python suites
# (SMCCC, image, MDT) live in run-k60-handoff-host.sh, which is their entry.
python_suites=0
run_py() {
  local name=$1
  shift
  local out
  if ! out=$("$@" 2>&1); then
    printf '%s\n' "$out" | tail -20 >&2
    echo "power-python: $name failed" >&2
    exit 1
  fi
  python_suites=$((python_suites + 1))
  printf '  %-14s %s\n' "$name" "$(printf '%s\n' "$out" | tail -1)"
}
run_py carry python3 scripts/tests/test-power-carry.py
run_py handoff-judge python3 scripts/tests/test-judge-k60-handoff-console.py
run_py sleep-judge python3 scripts/tests/test-judge-k60-sleep-console.py
run_py mode1-judge python3 scripts/tests/test-judge-k60-mode1-console.py
run_py ios27-preflight python3 scripts/tests/test-check-ios27-power-preflight.py
echo "power-python: OK ($python_suites suites)"