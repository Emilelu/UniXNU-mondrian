#!/usr/bin/env python3
"""Prove that turning the clamp probe off is behaviourally a no-op.

Lead's question (2026-11-21T19:33): after stacking 0001 and 0003, is the
"switch off" build equivalent to "0003 was never applied"? Three checks answer
it without building a kernel:

  1. delta   - the only textual difference between the stacked file and the
               0001-only file is two insertions: a guard block of preprocessor
               directives plus comments, and one block wrapped in
               `#if K60_BACKLIGHT_PROBE`. Everything else is byte-identical, so
               no brightness code can have changed.
  2. default - the guard does expand to 0 when the build passes no -D, which is
               checked by running the real preprocessor (`cpp -dM`) on the
               guard block, not by grepping for a literal.
  3. drop    - with the guard at 0 the real preprocessor removes the wrapped
               block entirely: no probe token, and the code outside it
               survives.

Usage (needs `git` and a C++ preprocessor; no compilation, no object files):
    python3 docs/research/display/check-switch-inert.py --base <file with 0001>
        --stacked <file with 0001 and 0003>

Exit code 0 = all three checks pass.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# The guard arrives with a blank line and an explanatory block comment in front
# of it; both are part of the same insertion and vanish under -E.
GUARD_RE = re.compile(
    r"\n(?:/\*(?:[^*]|\*(?!/))*\*/\n)?"
    r"#ifndef K60_BACKLIGHT_PROBE\n#define K60_BACKLIGHT_PROBE (\d+)\n#endif\n")
PROBE_BLOCK_RE = re.compile(
    r"\n#if K60_BACKLIGHT_PROBE\n(?P<body>(?:.*\n)*?)#endif\n")


def preprocess(source: str, defines: bool = False) -> str:
    """Run the real preprocessor over a snippet; there are no #includes."""
    binary = shutil.which("clang") or shutil.which("cpp") or shutil.which("gcc")
    if not binary:
        raise SystemExit("no C preprocessor on PATH (clang, cpp or gcc)")
    args = [binary, "-E", "-x", "c++"]
    args += ["-dM"] if defines else ["-P"]
    args += ["-"]
    proc = subprocess.run(args, input=source, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit("preprocessor failed: %s" % proc.stderr.strip()[:400])
    return proc.stdout


def check_delta(base: str, stacked: str) -> list[str]:
    problems = []
    guards = GUARD_RE.findall(stacked)
    blocks = PROBE_BLOCK_RE.findall(stacked)
    if len(guards) != 1:
        problems.append("delta: expected exactly one probe guard block, found %d"
                        % len(guards))
    if len(blocks) != 1:
        problems.append("delta: expected exactly one wrapped probe block, found %d"
                        % len(blocks))
    if problems:
        return problems
    stripped = GUARD_RE.sub("", stacked, count=1)
    stripped = PROBE_BLOCK_RE.sub("", stripped, count=1)
    if stripped != base:
        # Report the first difference so the failure is actionable.
        for number, (left, right) in enumerate(zip(base.split("\n"),
                                                   stripped.split("\n")), 1):
            if left != right:
                problems.append(
                    "delta: line %d differs outside the switch: base %r vs "
                    "stacked %r" % (number, left[:70], right[:70]))
                break
        else:
            problems.append("delta: files differ in length outside the switch")
    return problems


def check_default(stacked: str) -> list[str]:
    guard = GUARD_RE.search(stacked)
    if not guard:
        return ["default: guard block not found, cannot evaluate it"]
    defines = preprocess(guard.group(0), defines=True)
    line = [ln for ln in defines.split("\n")
            if ln.startswith("#define K60_BACKLIGHT_PROBE")]
    if not line:
        return ["default: K60_BACKLIGHT_PROBE is not defined after the guard"]
    value = line[0].split()[-1]
    if value != "0":
        return ["default: K60_BACKLIGHT_PROBE expands to %s, expected 0 when no "
                "-D is passed" % value]
    return []


def check_drop(stacked: str) -> list[str]:
    guard = GUARD_RE.search(stacked)
    block = PROBE_BLOCK_RE.search(stacked)
    if not guard or not block:
        return ["drop: guard or wrapped block missing"]
    snippet = ("\n" + guard.group(0) + block.group(0)
               + "\nvoid keep_the_rest() {}\n")
    out = preprocess(snippet)
    problems = []
    for token in ("probe", "4095"):
        if token in out:
            problems.append("drop: the preprocessor kept %r with the switch at 0"
                            % token)
    if "keep_the_rest" not in out:
        problems.append("drop: the preprocessor also removed the code after the "
                        "block, so the snippet is not representative")
    return problems


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", required=True,
                        help="K60Backlight.cpp with 0001 applied only")
    parser.add_argument("--stacked", required=True,
                        help="K60Backlight.cpp with 0001 and 0003 applied")
    args = parser.parse_args(argv)

    base = Path(args.base).read_text(encoding="utf-8")
    stacked = Path(args.stacked).read_text(encoding="utf-8")

    problems = check_delta(base, stacked) + check_default(stacked) + check_drop(stacked)
    for problem in problems:
        print("FAIL " + problem)
    if problems:
        return 1
    print("OK switch off is inert: same tokens outside the switch, guard "
          "expands to 0, wrapped block dropped by the real preprocessor")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
