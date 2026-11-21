#!/usr/bin/env python3
"""Judge the zero-copy scanout criterion: the GPU copy must disappear entirely.

Why this exists
---------------
The 120 fps wall in `docs/research/gpu/GPU-27-BUDGET-120FPS.md` is one full-screen
copy per frame. The only way past it is to let the display scan out the
compositor's surface directly, and the criterion for "that happened" is narrow on
purpose: **the copy is gone, not cheaper**. A flight where `gpu=` fell from 5,983
to 1,200 us has not crossed the wall; a flight where `imports=0` and no bench copy
was ever encoded has.

Two shapes of evidence, both already printed by the presenter
(`drivers/PongMetal/PongMetalScanout.h`, the `scanout frames=` rate line):

  * `imports=%llu import=%llu us encode=%llu us submit=%llu us gpu=%llu us sum=%llu us`
  * `Pong Metal: scanout bench n=i/24 import=... gpu=... sum=...`

Dormancy, and why it is not a green light
-----------------------------------------
No flight so far has a single stage line with `imports=0`: every frame still
imports a copy. So today this check can only report dormancy, and it does that
out loud instead of passing quietly (P-290). `--strict` turns dormancy into a
failure, for a branch that claims the direct path already runs.

The day one stage line carries `imports=0` this becomes a criterion with no edit
here, and then all of these must hold at once:

  1. every stage line in the flight has `imports=0` - a mix means some frames
     still copied, which is the fallback, not the direct path;
  2. no `scanout bench` sample at all - the bench loop is itself a copy, so one
     sample means the copy still exists somewhere in that flight;
  3. those stage lines report `gpu=0 us` and `sum=0 us` - the numbers must be
     gone, not smaller;
  4. at least MIN_SAMPLES stage lines, and the frame counter advanced - one line
     is an anecdote, and a frozen counter means the presenter was not serving.

Exit codes follow the other gpu27 checks: 0 holds or dormant, 1 a rule above
failed, 2 the checker could not judge (no log, no stage lines, too few samples).

Usage: python3 scripts/check-gpu27-zero-copy.py LOG [--strict]
"""

import os
import re
import sys

# The rate line is the same shape the judge parses; kept in step with
# judge-gpu27.py so a change to one is caught by the other's fixtures.
STAGE = re.compile(
    r"Pong Metal: scanout frames=(\d+) at [\d.]+ s; last frame: wait=(\d+) us copy=(\d+) us"
    r" done=(\d+) us(?: client=(\d+) us)?; imports=(\d+) import=(\d+) us encode=(\d+) us"
    r" submit=(\d+) us\s*gpu=(\d+) us sum=(\d+) us")
BENCH = re.compile(r"scanout bench n=(\d+)/(\d+) import=(\d+) us encode=(\d+) us "
                   r"submit=(\d+) us\s*gpu=(\d+) us sum=(\d+) us")

MIN_SAMPLES = 8


def read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def parse(text):
    stages = []
    bench = []
    for line in text.splitlines():
        match = STAGE.search(line)
        if match:
            stages.append({
                "frames": int(match.group(1)),
                "imports": int(match.group(6)),
                "gpu": int(match.group(10)),
                "sum": int(match.group(11)),
            })
            continue
        match = BENCH.search(line)
        if match:
            bench.append({"n": int(match.group(1)), "gpu": int(match.group(6))})
    return stages, bench


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if len(argv) > 1 else 2

    path = argv[1]
    strict = "--strict" in argv[2:]
    for arg in argv[2:]:
        if arg not in ("--strict",):
            print("unknown argument %r (try --help)" % arg)
            return 2

    if not os.path.isfile(path):
        print("cannot read %s" % path)
        return 2

    stages, bench = parse(read(path))
    if not stages:
        print("cannot judge: no 'Pong Metal: scanout frames=' line in %s" % path)
        return 2

    direct = [stage for stage in stages if stage["imports"] == 0]
    if not direct:
        print("dormant: all %d stage line(s) still imported a copy (min imports=%d)"
              % (len(stages), min(stage["imports"] for stage in stages)))
        print("the direct scanout path has never run in this log; this check becomes a")
        print("criterion the first time a stage line reports imports=0")
        if strict:
            print("--strict: dormancy counts as a failure here")
            return 1
        return 0

    failures = []
    if len(direct) != len(stages):
        failures.append("only %d of %d stage lines stopped importing a copy; the rest are the "
                        "fallback path" % (len(direct), len(stages)))
    if bench:
        failures.append("%d scanout bench sample(s) present: a copy was still encoded "
                        "(first at n=%d, gpu=%d us)"
                        % (len(bench), bench[0]["n"], bench[0]["gpu"]))
    copied = [stage for stage in direct if stage["gpu"] or stage["sum"]]
    if copied:
        failures.append("%d direct stage line(s) still report a GPU copy (gpu=%d us, sum=%d us)"
                        % (len(copied), copied[0]["gpu"], copied[0]["sum"]))
    if len(direct) < MIN_SAMPLES:
        print("cannot judge: %d direct stage line(s), the rule needs %d"
              % (len(direct), MIN_SAMPLES))
        return 2
    first, last = direct[0]["frames"], direct[-1]["frames"]
    if last <= first:
        print("cannot judge: the frame counter did not advance (%d to %d)" % (first, last))
        return 2

    if failures:
        print("FAIL the copy did not disappear:")
        for line in failures:
            print("  %s" % line)
        return 1

    print("OK the direct path ran: %d stage line(s) with imports=0, no bench copy, "
          "gpu/sum both zero, frames %d to %d" % (len(direct), first, last))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
