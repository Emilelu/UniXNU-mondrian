#!/usr/bin/env python3
"""Check that every field judge-gpu27.py parses is exercised in both shapes.

Why this exists
---------------
The judge gained an optional `client=` group in the stage line, and the group
inserted at position 5 shifted every later group by one. The judge then read
`submit` as `gpu`: on the real card j flight it printed "gpu median 967 us"
where the flight card says 5,983 us, and a copy five times over budget looked
comfortable. Nothing failed loudly, no fixture caught it, because every fixture
that reached the stage path also carried bench samples and the bench wins the
source choice (P-295, "measuring the wrong group measures everything wrong").

So the rule this script enforces is narrow and mechanical:

  * each optional or added field has a fixture that carries it and a fixture
    that does not, and the judge's `unmeasured` list has to change between
    them - a field that is always present proves nothing about absence, and a
    field that is never parsed would just look "absent" forever;
  * the absolute values on the pinned fixtures are checked, not just the exit
    code, so a shifted group cannot pass by being plausible;
  * both data sources are covered, because a stage-only flight is the case that
    broke;
  * one real flight log is re-judged and compared against the medians its
    flight card published (docs/research/gpu/FLIGHT-CARD-20261119j.md). A
    synthetic fixture can only prove the parser agrees with itself.

Exit codes follow judge-gpu27.py: 0 all checks hold, 1 a check failed, 2 the
checker could not run. A missing real log is reported as SKIP and only fails
with --strict, so a machine without the evidence store can still run the
fixture half.

Usage: python3 scripts/check-gpu27-judge-groups.py [--strict] [--real-log=PATH]
                                                   [--fixtures=DIR] [--judge=PATH]
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
JUDGE = os.path.join(REPO, "scripts", "judge-gpu27.py")
FIXTURES = os.path.join(REPO, "scripts", "tests", "fixtures", "gpu27")

# The real flight the bench samples and the composition statistic were taken
# from (docs/research/gpu/FLIGHT-CARD-20261119j.md): 34 stage samples, 24 bench
# samples, and a flight card that published gpu 5,983 us and sum 8,281 us as the
# medians. Those two numbers are the absolute pin.
REAL_LOG = "E:/iOS Port/Work/evidence/usblog-20261119-151837/console.log"
REAL_EXPECT = {"source": "stage", "gpu_us": 5983, "sum_us": 8281}

# fixture carrying the field, fixture not carrying it, and the name the judge
# uses in `unmeasured`. The pinned values are the numbers written in the fixture
# on purpose and chosen to differ from the neighbouring fields, so reading the
# wrong group cannot pass.
GROUPS = [
    {
        "field": "client us",
        "with": "gpu27-stage-only-instrumented.log",
        "without": "gpu27-stage-only-plain.log",
        "pin": {"source": "stage", "gpu_us": 2222, "sum_us": 4444},
        "why": "the optional group sits inside the stage line; stage-only is the path that"
               " broke, so both shapes are pinned here",
    },
    {
        "field": "offers/dropped",
        "with": "gpu27-instrumented-drops-and-gap.log",
        "without": "gpu27-stage-only-plain.log",
        "why": "the draft prints these only on the PONG SCANOUT line, never on the stage line",
    },
    {
        "field": "scanout version",
        "with": "gpu27-instrumented-drops-and-gap.log",
        "without": "gpu27-stage-only-plain.log",
        "why": "the wire version is the field a 48/56 byte mismatch is diagnosed from",
    },
]

# Bench and stage are two different readers of the same numbers; the bench one
# was never broken by the group shift, so it stays covered as the control.
BENCH_PIN = {"fixture": "gpu27-bench-good-wall-present.log",
             "pin": {"source": "bench", "gpu_us": 2470}}


def judge(fixture, judge_path):
    finished = subprocess.run([sys.executable, judge_path, fixture, "--json"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True)
    if not finished.stdout.strip():
        return None, "judge printed nothing (%s)" % finished.stderr.strip()[:120]
    try:
        report = json.loads(finished.stdout)
    except ValueError as error:
        return None, "judge output is not json: %s" % error
    return report, None


def check(fixtures, judge_path, real_log, strict):
    failures = []
    notes = []

    for group in GROUPS:
        for shape in ("with", "without"):
            path = os.path.join(fixtures, group[shape])
            if not os.path.isfile(path):
                failures.append("%s: fixture %s is missing" % (group["field"], group[shape]))
        with_path = os.path.join(fixtures, group["with"])
        without_path = os.path.join(fixtures, group["without"])
        if not (os.path.isfile(with_path) and os.path.isfile(without_path)):
            continue

        carried, error = judge(with_path, judge_path)
        if error:
            failures.append("%s: %s" % (group["field"], error))
            continue
        absent, error = judge(without_path, judge_path)
        if error:
            failures.append("%s: %s" % (group["field"], error))
            continue

        if group["field"] in carried["unmeasured"]:
            failures.append("%s: still unmeasured in %s, so the parser never sees it"
                            % (group["field"], group["with"]))
        if group["field"] not in absent["unmeasured"]:
            failures.append("%s: reported as measured in %s, where the field is absent"
                            % (group["field"], group["without"]))
        for key, want in group.get("pin", {}).items():
            got = carried["stats"].get(key)
            if got != want:
                failures.append("%s: %s in %s is %r, the fixture pins %r"
                                % (group["field"], key, group["with"], got, want))

    bench_path = os.path.join(fixtures, BENCH_PIN["fixture"])
    if not os.path.isfile(bench_path):
        failures.append("bench control fixture %s is missing" % BENCH_PIN["fixture"])
    else:
        report, error = judge(bench_path, judge_path)
        if error:
            failures.append("bench control: %s" % error)
        else:
            for key, want in BENCH_PIN["pin"].items():
                got = report["stats"].get(key)
                if got != want:
                    failures.append("bench control: %s is %r, the fixture pins %r"
                                    % (key, got, want))

    if real_log and os.path.isfile(real_log):
        report, error = judge(real_log, judge_path)
        if error:
            failures.append("real log: %s" % error)
        else:
            for key, want in REAL_EXPECT.items():
                got = report["stats"].get(key)
                if got != want:
                    failures.append("real log: %s is %r, the flight card published %r"
                                    % (key, got, want))
            if not report.get("state"):
                failures.append("real log: the judge returned no state")
    else:
        notes.append("SKIP the real-log pin: %s is not on this machine" % (real_log or "no path"))
        if strict:
            failures.append("--strict was given and the real log is missing, so the absolute"
                            " values were never re-checked against a flight")

    return failures, notes


def main(argv):
    strict = "--strict" in argv
    fixtures = FIXTURES
    judge_path = JUDGE
    real_log = os.environ.get("K60_GPU27_REAL_LOG", REAL_LOG)
    for argument in argv[1:]:
        if argument.startswith("--fixtures="):
            fixtures = argument.split("=", 1)[1]
        elif argument.startswith("--judge="):
            judge_path = argument.split("=", 1)[1]
        elif argument.startswith("--real-log="):
            real_log = argument.split("=", 1)[1]

    if not os.path.isfile(judge_path):
        print("cannot run: %s is missing" % judge_path)
        return 2

    failures, notes = check(fixtures, judge_path, real_log, strict)

    for group in GROUPS:
        print("  %-16s %s / %s" % (group["field"], group["with"], group["without"]))
    print("  %-16s %s" % ("bench control", BENCH_PIN["fixture"]))
    print("  %-16s %s" % ("real log", real_log if os.path.isfile(real_log) else "(missing)"))
    for note in notes:
        print("note %s" % note)
    if failures:
        for failure in failures:
            print("FAIL %s" % failure)
        return 1
    print("OK every parsed field is exercised with and without, and the pinned values hold")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
