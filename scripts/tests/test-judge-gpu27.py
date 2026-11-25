#!/usr/bin/env python3
"""Tests for scripts/judge-gpu27.py.

The point of this judge is that a good bench is not a 120 Hz reading, so the tests are built
around that: one fixture holds 24 real bench samples whose sum median is 5,907 us (inside the
6,000 us budget) together with the real composition statistic showing 20 frames a second, and
the judge has to fail it and say why. A second fixture turns the two draft fields into
failures (heavy drops, a client interval over one frame), a third is a dead GPU (INVALID), and
a fourth is synthetic so the gate can be shown to return PASS at all - a judge that only ever fails passes
its own negative cases by accident (P-290 family).

Run: python3 scripts/tests/test-judge-gpu27.py
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
JUDGE = os.path.join(REPO, "scripts", "judge-gpu27.py")
FIXTURES = os.path.join(HERE, "fixtures", "gpu27")

CASES = [
    {
        "fixture": "gpu27-bench-good-wall-present.log",
        "exit": 1,
        "state": "FAIL",
        "must_say": [
            "the bench fits the budget while the compositor still copies every frame",
            "13183 us each in the driver",
            "gpu median 2470 us",
        ],
        "why": "a bench inside the budget must not pass while the compositor copies the frame",
    },
    {
        "fixture": "gpu27-invalid-devicelost.log",
        "exit": 3,
        "state": "INVALID",
        "must_say": ["DeviceLost appeared"],
        "why": "a run that died measured nothing (P-244)",
    },
    {
        "fixture": "gpu27-stage-only-instrumented.log",
        "exit": 0,
        "state": "PASS",
        "must_say": ["gpu median 2222 us", "sum median 4444 us", "client=8333"],
        "why": "with no bench the copy has to come out of the stage line, where the optional "
               "client= group shifts the later groups: reading submit (111) as gpu passes "
               "silently, so the numbers are pinned",
    },
    {
        "fixture": "gpu27-instrumented-drops-and-gap.log",
        "exit": 1,
        "state": "FAIL",
        "must_say": [
            "dropped=200 of offers=800 (25.0%)",
            "client frame took 14000 us, over the 8333 us budget",
            "drawLayer() did not copy a frame",
        ],
        "why": "inside the copy budget is not enough: refused frames and a slow client "
               "still miss 120 Hz, and the two draft fields have to be read, not just printed",
    },
    {
        "fixture": "gpu27-synthetic-pass.log",
        "exit": 0,
        "state": "PASS",
        "must_say": ["drawLayer() did not copy a frame", "gpu median 2450 us"],
        "why": "the judge must be able to pass, or its negative cases prove nothing",
    },
]


def run(fixture):
    path = os.path.join(FIXTURES, fixture)
    finished = subprocess.run([sys.executable, JUDGE, path],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              universal_newlines=True)
    return finished.returncode, finished.stdout


def main():
    failures = []
    for case in CASES:
        code, output = run(case["fixture"])
        if code != case["exit"]:
            failures.append("%s: exit %d, wanted %d (%s)"
                            % (case["fixture"], code, case["exit"], case["why"]))
        if "verdict: %s" % case["state"] not in output:
            failures.append("%s: no 'verdict: %s'" % (case["fixture"], case["state"]))
        for needle in case["must_say"]:
            if needle not in output:
                failures.append("%s: output does not say %r" % (case["fixture"], needle))

    # An unreadable target is not a FAIL: it is the "nothing was measured" state.
    missing = os.path.join(FIXTURES, "there-is-no-such-flight.log")
    finished = subprocess.run([sys.executable, JUDGE, missing],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              universal_newlines=True)
    if finished.returncode != 2:
        failures.append("a missing file returned %d, wanted 2" % finished.returncode)

    # --json has to carry the same verdict as the prose, or a gate reading it would drift.
    code, output = run(CASES[0]["fixture"])
    finished = subprocess.run([sys.executable, JUDGE,
                               os.path.join(FIXTURES, CASES[0]["fixture"]), "--json"],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              universal_newlines=True)
    if '"state": "FAIL"' not in finished.stdout:
        failures.append("--json did not report the FAIL state")

    for failure in failures:
        print("FAIL: %s" % failure)
    if failures:
        return 1
    print("TESTS OK: %d cases, plus a missing file and the json form" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
