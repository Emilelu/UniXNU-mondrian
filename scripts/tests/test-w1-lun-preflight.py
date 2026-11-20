#!/usr/bin/env python3
"""Three-state tests for the PENDING-safe W1 LUN preflight wrapper."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "scripts" / "check-w1-lun-preflight.py"
JUDGE = ROOT / "scripts" / "check-w1-lun-evidence.py"
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


def run(command):
    return subprocess.run(command, capture_output=True, text=True, check=False)


def write_capture(directory, *, hctl="5:0:0:5", descriptor=None, readme=True):
    directory.mkdir(parents=True)
    if readme:
        (directory / "README.txt").write_text("serial=fixture\n", encoding="utf-8")
    if hctl:
        (directory / "device-link.txt").write_text(
            "device -> .../5:0:0:0/5:0:0:%s\n" % hctl.rsplit(":", 1)[1],
            encoding="utf-8")
    if descriptor is not None:
        (directory / "unit-desc.bin").write_bytes(descriptor)


def main():
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        passing = tmp / "pass"
        write_capture(passing, descriptor=bytes([5, 0x02, 5, 1, 0]))
        pending = tmp / "pending"
        write_capture(pending, hctl=None, descriptor=None)
        failing = tmp / "fail"
        write_capture(failing, descriptor=bytes([5, 0x02, 4, 1, 0]))

        for name, expected, token in (
            ("pass", 0, "PREFLIGHT PASS"),
            ("pending", 0, "PREFLIGHT PENDING"),
            ("fail", 1, "PREFLIGHT FAIL"),
        ):
            result = run([sys.executable, str(WRAPPER), "--evidence", str(tmp / name)])
            check(result.returncode == expected,
                  "%s maps to %d" % (name, expected),
                  result.stdout + result.stderr)
            check(token in result.stdout, "%s prints %s" % (name, token), result.stdout)

        missing = run([sys.executable, str(WRAPPER), "--evidence", str(tmp / "absent")])
        check(missing.returncode == 0, "a missing capture is PENDING, not an error",
              missing.stdout + missing.stderr)
        check("PENDING" in missing.stdout, "a missing capture says PENDING", missing.stdout)

        direct = run([sys.executable, str(JUDGE), str(passing)])
        check(direct.returncode == 0, "the judge still returns 0 on PASS", direct.stdout + direct.stderr)
        direct = run([sys.executable, str(JUDGE), str(pending)])
        check(direct.returncode == 2, "the judge still returns 2 on PENDING", direct.stdout + direct.stderr)
        direct = run([sys.executable, str(JUDGE), str(failing)])
        check(direct.returncode == 1, "the judge still returns 1 on FAIL", direct.stdout + direct.stderr)

    print()
    if FAILURES:
        print("K60 W1 PREFLIGHT FAIL %d case(s), %d failure(s)" % (CASES, FAILURES))
        return 1
    print("K60 W1 PREFLIGHT PASS three states, missing capture, judge CLI")
    return 0


if __name__ == "__main__":
    sys.exit(main())
