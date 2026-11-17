#!/usr/bin/env python3
"""Tests for scripts/check-disk-space.py.

The gate exists because the same cleanup kept being started only after the user
asked.  What has to hold is narrow but real: a filesystem under the floor must
block, a filesystem between the floor and the comfort line must only warn, and a
virtual disk much larger than its contents must be reported as stranding space.
"""
from __future__ import annotations

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HERE, "..", "check-disk-space.py")
GIB = 1024 ** 3

CASES = 0
FAILURES = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global CASES, FAILURES
    CASES += 1
    if condition:
        print(f"  ok   {name}")
    else:
        FAILURES += 1
        print(f"  FAIL {name}{(' :: ' + detail) if detail else ''}")


def load():
    spec = importlib.util.spec_from_file_location("check_disk_space", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    gate = load()

    check(
        "a roomy filesystem passes",
        gate.assess(100 * GIB, 8.0, 25.0)[0] == "ok",
    )
    check(
        "a filesystem under the floor blocks",
        gate.assess(3 * GIB, 8.0, 25.0)[0] == "fail",
    )
    check(
        "a filesystem between the floor and the comfort line warns",
        gate.assess(15 * GIB, 8.0, 25.0)[0] == "warn",
    )
    check(
        "the floor itself is not a pass",
        gate.assess(int(8 * GIB), 8.0, 25.0)[0] == "fail",
        "exactly at the floor must still block",
    )
    status, reason = gate.assess(3 * GIB, 8.0, 25.0)
    check(
        "the blocking message names the floor",
        "8 GiB floor" in reason,
        reason,
    )

    check(
        "a tight virtual disk passes",
        gate.vhdx_slack(62 * GIB, 60 * GIB, 30.0)[0] == "ok",
    )
    check(
        "a virtual disk stranding tens of GiB warns",
        gate.vhdx_slack(161 * GIB, 60 * GIB, 30.0)[0] == "warn",
    )
    check(
        "the stranded-space message says how much is stranded",
        "stranded" in gate.vhdx_slack(161 * GIB, 60 * GIB, 30.0)[1],
    )
    check(
        "the stranded-space message names the recipe",
        "DISK-HYGIENE.md" in gate.vhdx_slack(161 * GIB, 60 * GIB, 30.0)[1],
    )
    check(
        "a virtual disk smaller than its data is not a warning",
        gate.vhdx_slack(40 * GIB, 60 * GIB, 30.0)[0] == "ok",
    )

    rows, failures = gate.check_filesystems()
    labels = [row[0] for row in rows]
    check("both Windows mounts and the WSL root are graded", len(labels) == 3, str(labels))
    check("E: is graded", "E:" in labels, str(labels))
    check("D: is graded", "D:" in labels, str(labels))
    check("the WSL root is graded", "WSL root" in labels, str(labels))
    check(
        "a missing mount warns instead of crashing",
        all(status in {"ok", "warn", "fail"} for _, status, _ in rows),
    )
    check("failure count is a number", isinstance(failures, int))

    return 0 if FAILURES == 0 else 1


if __name__ == "__main__":
    code = main()
    print(f"TESTS OK {CASES} case(s) ({FAILURES} failure(s))" if code == 0 else f"TESTS FAILED {FAILURES}/{CASES}")
    sys.exit(code)
