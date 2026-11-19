#!/usr/bin/env python3
"""Guard the power policy modules that must survive the iOS27 move.

The CPU/GPU/boost/sleep/vote/rail plans and the thermal trip map are pure C:
no IOKit, no XNU, no MMIO.
This check fails if one of them grows a platform include or symbol, and it
compiles every module freestanding so an accidental libc/IOKit dependency is
caught before the iOS27 tree inherits it.
"""
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
POWER = REPO / "drivers" / "PongPower"
MODULES = [
    "K60CpuFreqPlan.c",
    "K60GpuFreqPlan.c",
    "K60BoostPlan.c",
    "K60SleepPlan.c",
    "K60PowerVotePlan.c",
    "K60RailPlan.c",
    "K60ThermalMap.c",
    "K60ChargeAuth.c",
]
HEADERS = [name[:-2] + ".h" for name in MODULES]
FORBIDDEN_INCLUDE = re.compile(
    r'^\s*#\s*include\s*[<"](?:IOKit|kern|mach|sys|libkern|os|pexpert|arm|architecture)/',
    re.MULTILINE,
)
FORBIDDEN_SYMBOL = re.compile(
    r'\b(?:IOService|IOPMrootDomain|IOLog|ml_arm_sleep|'
    r'arm64_platform_sleep_hook|psci_smp_cpu_off|processor_exit_reason)\b'
)

errors = []
for name in HEADERS + MODULES:
    path = POWER / name
    if not path.exists():
        errors.append(f"missing {path.relative_to(REPO)}")
        continue
    text = path.read_text(encoding="utf-8")
    for match in FORBIDDEN_INCLUDE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        errors.append(f"{path.relative_to(REPO)}:{line}: platform include")
    for match in FORBIDDEN_SYMBOL.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        errors.append(f"{path.relative_to(REPO)}:{line}: platform symbol {match.group(0)}")

if errors:
    print("POWER PORTABILITY FAILED", file=sys.stderr)
    for error in errors:
        print(f"  {error}", file=sys.stderr)
    sys.exit(1)

for name in MODULES:
    path = POWER / name
    cmd = [
        "cc", "-std=c11", "-ffreestanding", "-fno-builtin",
        "-Wall", "-Wextra", "-Werror", "-I", str(POWER),
        "-fsyntax-only", str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        print(f"POWER PORTABILITY FAILED: {name}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

print(f"POWER PORTABILITY OK ({len(MODULES)} modules, freestanding C11)")
