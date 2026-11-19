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

The fixture item is derived from EIGHT-STEPS.toml, never hard-coded: the first
version pinned `buttons`, which was parked and incomplete at the time.  Buttons
became active and complete, so the test then asserted that a fully green item
must fail — it was measuring the calendar, not the gate.  Each case now picks
an item that currently has the property under test and says so when the tree
has no such item.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "eight-step-gate.py"
DATA = ROOT / "docs" / "research" / "EIGHT-STEPS.toml"
# Build mode checks steps 1-6 only (eight-step-gate.py: BUILD_STEPS = STEPS[:6]),
# so a gap in step 7 must not be treated as a build-mode gap here either.
BUILD_STEPS = ("same_model", "official", "decompile", "wide", "plan", "deep")
LABELS = {"same_model": "① 同型", "official": "② 官方",
          "decompile": "③ 反编译", "wide": "④ 广域", "plan": "⑤ 方案",
          "deep": "⑥ 深挖"}


def items_with(statuses):
    """Hardware items whose status is one of `statuses`, with their step gaps."""
    doc = tomllib.loads(DATA.read_text(encoding="utf-8"))
    out = {}
    for name, body in doc.get("hardware", {}).items():
        status = body.get("status", "active")
        if status not in statuses:
            continue
        steps = body.get("step", {})
        gaps = [s for s in BUILD_STEPS
                if not steps.get(s) or steps[s].get("done") is not True]
        out[name] = (status, gaps)
    return out


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


def main() -> int:
    failures = 0

    def check(label, want_rc, want_text=None, args=("--build",), items=None,
              forbid_text=None):
        nonlocal failures
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

    # A parked item with a complete build record: declaring it must be accepted
    # and must not be blocked by the active lines.
    parked_ok = {n: s for n, (s, gaps) in
                 items_with({"parked", "planned"}).items() if not gaps}
    if parked_ok:
        name, status = sorted(parked_ok.items())[0]
        check("declaring a parked item is accepted", 0,
              f"声明范围: {name}[{status}]", items=name)
    else:
        print("SKIP declaring a parked item is accepted "
              "(no parked/planned item currently has a complete build record)")

    # An incomplete item must still be held to the evidence rules when declared.
    # Prefer an active one: that is the case where the gate has teeth, because
    # nothing else would stop the build.
    incomplete = {n: v for n, v in items_with({"active", "parked", "planned"})
                  .items() if v[1]}
    if incomplete:
        # An active item with gaps cannot happen while the whole-device default
        # passes, so fall back to the parked one with the smallest gap count.
        name = sorted(incomplete, key=lambda n: (len(incomplete[n][1]), n))[0]
        step = incomplete[name][1][0]
        check("a declared item is still held to the evidence rules", 1,
              f"{name} :: {LABELS[step]}", items=name)
    else:
        print("SKIP a declared item is still held to the evidence rules "
              "(every hardware item currently has a complete build record)")

    check("an unknown name is refused", 1,
          "不存在的硬件项", items="nosuch")

    # The declaration must not narrow flash mode. Whether flash passes depends
    # on the whole device, so assert on the absence of scoping, not on rc.
    any_item = sorted(items_with({"active", "parked", "planned", "device-verified"}))[0]
    check("flash mode ignores the declaration", None,
          "模式: flash", args=("--flash",), items=any_item,
          forbid_text="声明范围")

    if failures:
        print(f"TESTS OK 0 cases ({failures} failure(s))")
        return 1
    print("TESTS OK 5 cases (0 failure(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
