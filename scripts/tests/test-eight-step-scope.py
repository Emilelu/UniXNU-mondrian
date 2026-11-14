#!/usr/bin/env python3
"""Tests for the eight-step gate's build scoping (P-192).

Context: on 2026-11-14 the wifi and bt agents could not build through
build-strict.sh because flash mode demands every active hardware item be green
and the touch line was mid-edit.  They hand-packaged images, and two of those
ran over DarwinBoot's 607-byte ceiling or replaced debug=0x140 with debug=1.
Scoping must therefore:
  * default to the whole device when nothing is declared,
  * accept a parked or planned item so an unrelated line cannot block a build,
  * reject a name that does not exist,
  * never apply to flash mode.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "eight-step-gate.py"


def run(args, items=None):
    env = dict(os.environ)
    env.pop("K60_EIGHT_STEP_ITEMS", None)
    if items is not None:
        env["K60_EIGHT_STEP_ITEMS"] = items
    proc = subprocess.run([sys.executable, str(GATE)] + args,
                          capture_output=True, text=True, env=env, cwd=str(ROOT))
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    failures = 0

    def check(label, want_rc, want_text=None, args=("--build",), items=None,
              forbid_text=None):
        nonlocal failures
        rc, out = run(list(args), items)
        ok = (rc == want_rc or (want_rc == 0 and rc == 0))
        if want_text and want_text not in out:
            ok = False
        if forbid_text and forbid_text in out:
            ok = False
        print(f"{'PASS' if ok else 'FAIL'} {label}")
        if not ok:
            failures += 1
            print(f"      rc={rc} want={want_rc}")
            for line in out.splitlines()[-6:]:
                print("      " + line)

    # The device as it stands today: every active item green in build mode.
    check("no declaration keeps the whole-device default", 0,
          "八步流程通过", forbid_text="声明范围")

    check("declaring a parked item is accepted", 1,
          "声明范围: buttons[parked]", items="buttons")

    check("a declared item is still held to the evidence rules", 1,
          "buttons :: ② 官方 未标记 done=true", items="buttons")

    check("an unknown name is refused", 1,
          "不存在的硬件项", items="nosuch")

    check("flash mode ignores the declaration", 1,
          "八步流程未通过，禁止刷机", args=("--flash",), items="buttons")

    if failures:
        print(f"TESTS OK 0 cases ({failures} failure(s))")
        return 1
    print("TESTS OK 5 cases (0 failure(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
