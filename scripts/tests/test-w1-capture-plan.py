#!/usr/bin/env python3
"""Host-only tests for the W1 capture-plan printer.

The printer is deliberately inert: it may call cat/printf, but it must never
invoke adb, fastboot, dd, or a block-device write.  The emitted plan is checked
with bash -n but is never executed.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRINTER = ROOT / "scripts" / "w1-capture-plan.sh"
PLAN = None
FAILURES = 0


def check(condition, label, detail=""):
    global FAILURES
    if condition:
        print("ok   %s" % label)
    else:
        FAILURES += 1
        print("FAIL %s%s" % (label, (": " + detail) if detail else ""))


def main():
    global PLAN
    outer = subprocess.run(["bash", "-n", str(PRINTER)], capture_output=True,
                           text=True, check=False)
    check(outer.returncode == 0, "printer parses", outer.stderr)

    result = subprocess.run(["bash", str(PRINTER)], capture_output=True,
                            text=True, check=False)
    check(result.returncode == 0, "printer exits 0", result.stderr)
    PLAN = result.stdout
    check("#!/usr/bin/env bash" in PLAN, "plan starts with a shell shebang")
    check("adb shell readlink -f /dev/block/by-name/modemst1" in PLAN,
          "plan resolves modemst1")
    check('readlink -f /sys/class/block/$SDF/device' in PLAN,
          "plan reads the H:C:T:L device link")
    check("desc -t 2 -i 5 -s 0 -r -D" in PLAN and "UFS_TOOL" in PLAN,
          "plan reads Unit Descriptor index 5")
    check("check-w1-lun-evidence.py" in PLAN, "plan includes the W1 judge")
    check("check-capture-bundle.py" in PLAN and "AUTOCHECK" in PLAN,
          "plan advertises the local-only composed auto-check")
    check("K60_EFS_BLOCKS" in PLAN and "K60_CONSOLE" in PLAN,
          "auto-check documents optional full-block and console inputs")
    check("--require-efs-bytes" in PLAN and "whole 4 KiB" in PLAN,
          "console auto-check requires the whole 4 KiB")
    check('README.txt' in PLAN and 'adb get-serialno' in PLAN,
          "plan records capture provenance for the W1 judge")
    check(PLAN.count("# EXPECT") >= 8, "every evidence command has EXPECT")
    check(PLAN.count("# IF") >= 6, "every evidence command has IF")
    check("# LEG A" in PLAN and "# LEG B" in PLAN and "# LEG C" in PLAN,
          "plan labels all three legs")
    check(PLAN.rstrip().endswith("run on a device with adb root; Lead runs this, not the lane"),
          "plan ends with the exact ownership sentence")

    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(PLAN)
        plan_path = handle.name
    try:
        emitted = subprocess.run(["bash", "-n", plan_path], capture_output=True,
                                 text=True, check=False)
        check(emitted.returncode == 0, "emitted plan parses", emitted.stderr)
    finally:
        os.unlink(plan_path)

    with tempfile.TemporaryDirectory() as temp:
        marker = Path(temp) / "adb-was-called"
        fake = Path(temp) / "adb"
        fake.write_text("#!/bin/sh\nprintf called > %s\nexit 99\n" % marker,
                        encoding="utf-8")
        fake.chmod(0o755)
        env = dict(os.environ)
        env["PATH"] = temp + os.pathsep + env.get("PATH", "")
        inert = subprocess.run(["bash", str(PRINTER)], capture_output=True,
                               text=True, check=False, env=env)
        check(inert.returncode == 0 and not marker.exists(),
              "printer does not invoke adb", inert.stderr)

    check(not any(line.strip().startswith("fastboot") for line in PLAN.splitlines()),
          "plan does not run fastboot")
    check("dd if=" not in PLAN, "plan does not include dd")
    check(">/dev/block" not in PLAN, "plan does not write a block device")
    if FAILURES:
        print("K60 W1 CAPTURE PLAN FAIL %d check(s)" % FAILURES)
        return 1
    print("K60 W1 CAPTURE PLAN PASS commands, ranges, legs, inert printer")
    return 0


if __name__ == "__main__":
    sys.exit(main())
