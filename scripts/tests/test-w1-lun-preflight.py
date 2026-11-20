#!/usr/bin/env python3
"""Three-state tests for the PENDING-safe W1 LUN preflight wrapper.

The three states use committed fixture directories, not temporary synthetic
captures, so the exact bytes and paths reviewed by a human are the ones tested.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "scripts" / "check-w1-lun-preflight.py"
JUDGE = ROOT / "scripts" / "check-w1-lun-evidence.py"
FIXTURES = ROOT / "scripts" / "tests" / "fixtures"
CASES = 0
FAILURES = 0


def check(condition, label, detail=""):
    global CASES, FAILURES
    CASES += 1
    if condition:
        print("ok   %s" % label)
    else:
        FAILURES += 1
        print("FAIL %s%s" % (label, (": " + detail) if detail else ""))


def run(script, *args):
    return subprocess.run([sys.executable, str(script), *args],
                          capture_output=True, text=True, check=False)


def main():
    pass_dir = FIXTURES / "w1-lun-pass"
    pending_dir = FIXTURES / "w1-lun-pending"
    fail_dir = FIXTURES / "w1-lun-fail"

    check((pass_dir / "unit-desc.bin").read_bytes() == bytes([5, 2, 5, 1, 0]),
          "pass fixture descriptor is IDN 0x02 index 5 enabled")
    check((fail_dir / "unit-desc.bin").read_bytes() == bytes([5, 2, 4, 1, 0]),
          "fail fixture descriptor is IDN 0x02 index 4")
    check(not (pending_dir / "unit-desc.bin").exists()
          and not (pending_dir / "device-link.txt").exists(),
          "pending fixture has neither leg")

    result = run(WRAPPER, "--evidence", str(pass_dir))
    check(result.returncode == 0 and "K60 W1 LUN PREFLIGHT PASS" in result.stdout,
          "pass fixture maps to exit 0", result.stdout + result.stderr)

    result = run(WRAPPER, "--evidence", str(pending_dir))
    check(result.returncode == 0 and "K60 W1 LUN PREFLIGHT PENDING" in result.stdout,
          "pending fixture maps to exit 0", result.stdout + result.stderr)

    result = run(WRAPPER, "--evidence", str(fail_dir))
    check(result.returncode == 1 and "K60 W1 LUN PREFLIGHT FAIL" in result.stdout,
          "fail fixture maps to exit 1", result.stdout + result.stderr)

    result = run(WRAPPER, "--evidence", str(FIXTURES / "w1-lun-absent"))
    check(result.returncode == 0 and "PENDING no capture" in result.stdout,
          "missing capture is PENDING and non-blocking", result.stdout + result.stderr)

    for label, path, expected in (("pass", pass_dir, 0), ("pending", pending_dir, 2),
                                  ("fail", fail_dir, 1)):
        result = run(JUDGE, str(path), "--expect-lun", "5")
        check(result.returncode == expected,
              "judge CLI keeps %s at %d" % (label, expected),
              str(result.returncode) + " " + result.stdout + result.stderr)

    source = WRAPPER.read_text(encoding="utf-8")
    check("in-line build preflight" in source, "wrapper says it is the in-line entry")
    check("flight ledger" in source, "wrapper says it does not write the flight ledger")

    print("K60 W1 PREFLIGHT PASS three fixture states, missing capture, judge CLI")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
