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
     is an anecdote, and a frozen counter means the presenter was not serving;
  5. over a window of at least WINDOW_MS, the frame counter advanced at no less
     than WINDOW_MIN_FPS - the direct path has to keep the panel fed, not just
     avoid the copy once.

Rule 5 needs a time on every line, which is what the draft
`patches/proposed/pong-scanout-frame-timestamp.patch` adds as `at=<sec>.<ms>`
(the frame's arrival time, one clock read taken for the wait span). Until that
lands the field is absent, and absence is reported as "no window can be judged"
(exit 2) rather than as a window that held: a missing measurement is never a
passing measurement.

Exit codes follow the other gpu27 checks: 0 holds or dormant, 1 a rule above
failed, 2 the checker could not judge (no log, no stage lines, too few samples,
no timestamp on the lines, or a window shorter than WINDOW_MS).

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
# The frame's arrival stamp is the only field on the line that can be searched
# without knowing its position: the rate prefix prints "at <sec>.<ms> s" (space,
# no equals), the timestamp prints "at=<sec>.<ms>" (P-295: appended last, so no
# group above it moved).
AT = re.compile(r"at=(\d+)\.(\d{1,3})\b")

MIN_SAMPLES = 8
WINDOW_MS = 3000
WINDOW_MIN_FPS = 110


def read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def parse(text):
    stages = []
    bench = []
    for line in text.splitlines():
        match = STAGE.search(line)
        if match:
            stamp = AT.search(line)
            stages.append({
                "frames": int(match.group(1)),
                "imports": int(match.group(6)),
                "gpu": int(match.group(10)),
                "sum": int(match.group(11)),
                "at": None if not stamp else int(stamp.group(1)) * 1000
                      + int(stamp.group(2).ljust(3, "0")),
            })
            continue
        match = BENCH.search(line)
        if match:
            bench.append({"n": int(match.group(1)), "gpu": int(match.group(6))})
    return stages, bench


def judge_window(direct):
    """Rule 5: frames must advance at panel rate across WINDOW_MS.

    Returns (window, verdict, detail) where verdict is "ok", "cannot judge",
    "inconsistent" or "too slow". A line without a stamp is counted, never
    assumed: a flight where only some lines carry one cannot be ordered.
    """
    stamped_lines = [stage for stage in direct if stage["at"] is not None]
    if not stamped_lines:
        return None, "cannot judge", ("none of the %d direct stage line(s) carries an "
                                      "at=<sec>.<ms> stamp" % len(direct))
    if len(stamped_lines) != len(direct):
        return None, "inconsistent", ("%d of %d direct stage line(s) carry no timestamp, so the "
                                      "older ones cannot be placed on the same clock"
                                      % (len(direct) - len(stamped_lines), len(direct)))
    for before, after in zip(stamped_lines, stamped_lines[1:]):
        if after["at"] < before["at"]:
            return None, "inconsistent", ("frames=%d is stamped %d ms, the next line frames=%d is "
                                          "stamped %d ms: time went backwards"
                                          % (before["frames"], before["at"], after["frames"],
                                             after["at"]))
    span_ms = stamped_lines[-1]["at"] - stamped_lines[0]["at"]
    frames = stamped_lines[-1]["frames"] - stamped_lines[0]["frames"]
    if span_ms < WINDOW_MS:
        return None, "cannot judge", ("the stamps span %d ms, rule 5 needs %d ms"
                                      % (span_ms, WINDOW_MS))
    fps = frames * 1000.0 / span_ms
    window = {"span_ms": span_ms, "frames": frames, "fps": fps}
    if fps < WINDOW_MIN_FPS:
        return window, "too slow", ("%d frames in %d ms is %.0f/s, below the %d/s the panel "
                                    "needs" % (frames, span_ms, fps, WINDOW_MIN_FPS))
    return window, "ok", ""


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

    window, verdict, detail = judge_window(direct)
    if verdict == "inconsistent":
        print("FAIL the direct stage lines disagree about time:")
        print("  %s" % detail)
        return 1
    if verdict == "cannot judge":
        print("cannot judge the window: %s" % detail)
        print("carry patches/proposed/pong-scanout-frame-timestamp.patch (at=<sec>.<ms>)")
        print("with the next image; without it rule 5 cannot be checked either way")
        return 2
    if verdict == "too slow":
        print("FAIL the direct path did not keep the panel fed:")
        print("  %s" % detail)
        return 1

    print("OK the direct path ran: %d stage line(s) with imports=0, no bench copy, "
          "gpu/sum both zero, frames %d to %d, %d frames in %d ms (%.0f/s over %d ms)"
          % (len(direct), first, last, window["frames"], window["span_ms"],
             window["fps"], window["span_ms"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
