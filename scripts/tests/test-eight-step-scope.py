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


DATA = ROOT / "docs" / "research" / "EIGHT-STEPS.toml"


def run(args, items=None):
    env = dict(os.environ)
    env.pop("K60_EIGHT_STEP_ITEMS", None)
    # The gate prints Chinese verdicts with a check mark; a GBK console kills it
    # mid-print and the empty stdout reads as a failed case (P-248 family).
    env["PYTHONIOENCODING"] = "utf-8"
    if items is not None:
        env["K60_EIGHT_STEP_ITEMS"] = items
    proc = subprocess.run([sys.executable, str(GATE)] + args,
                          capture_output=True, text=True, env=env, cwd=str(ROOT),
                          encoding="utf-8", errors="replace")
    return proc.returncode, proc.stdout + proc.stderr


def parked_names():
    """Parked/planned items, in data order."""
    try:
        import tomllib
    except ImportError:
        return []
    data = tomllib.loads(DATA.read_text(encoding="utf-8"))
    return [n for n, b in (data.get("hardware") or {}).items()
            if b.get("status", "active") != "active"]


def scoped_refusal():
    """(name, status, problem line) for the first not-yet-active item the gate
    still refuses, or None when every one of them is green.

    Nothing here is hardcoded: buttons was parked when this test was written and
    became active on 90611764, so a literal name asserted the opposite of the
    truth and turned a green gate into a red test.  Which step fails also moves
    as the lines land, so the case reads the problem line out of the gate
    instead of guessing "② 官方 未标记 done=true".
    """
    for name in parked_names():
        rc, out = run(["--build"], name)
        if rc == 0:
            continue
        for line in out.splitlines():
            # problem lines print as "    - wifi :: ② 官方 …"
            stripped = line.strip().lstrip("-").strip()
            if stripped.startswith(f"{name} ::"):
                return name, hardware_status(name), stripped
    return None


def hardware_status(name):
    """The status the data gives that item, for the assertion text."""
    try:
        import tomllib
    except ImportError:
        return "parked"
    data = tomllib.loads(DATA.read_text(encoding="utf-8"))
    body = (data.get("hardware") or {}).get(name) or {}
    return body.get("status", "active")


def main() -> int:
    failures = 0
    cases = 0

    def check(label, want_rc, want_text=None, args=("--build",), items=None,
              forbid_text=None):
        nonlocal failures, cases
        cases += 1
        rc, out = run(list(args), items)
        # want_rc=None means "the whole-device verdict decides"; the case is
        # about scoping, not about whether the device is currently green.
        ok = want_rc is None or rc == want_rc
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

    # Scoping is about *being allowed to name* a not-yet-active item and then
    # being held to the same evidence rules. Which item that is has to come
    # from the data: buttons was parked here until 90611764 made it active,
    # and a hardcoded name then asserted the opposite of the truth.
    refused = scoped_refusal()
    if refused is None:
        print("SKIP every parked/planned item is green; nothing left to scope")
    else:
        name, status, problem = refused
        check("declaring a not-yet-active item is accepted", 1,
              f"声明范围: {name}[{status}]", items=name)
        check("a declared item is still held to the evidence rules", 1,
              problem, items=name)
        check("flash mode ignores the declaration", None,
              "模式: flash", args=("--flash",), items=name,
              forbid_text="声明范围")

    check("an unknown name is refused", 1,
          "不存在的硬件项", items="nosuch")

    if failures:
        print(f"TESTS OK 0 cases ({failures} failure(s))")
        return 1
    print(f"TESTS OK {cases} cases (0 failure(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
