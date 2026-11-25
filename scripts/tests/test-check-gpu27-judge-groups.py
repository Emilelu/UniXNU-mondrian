#!/usr/bin/env python3
"""Tests for scripts/check-gpu27-judge-groups.py.

The checker only earns its keep if it can fail. These tests build two broken
copies of the fixture directory - one where the field is missing from the
fixture that is supposed to carry it, one where a neighbour's value sits in the
pinned slot (the exact shape of the group shift it was written for) - and
require the checker to name the problem instead of passing.

Run: python3 scripts/tests/test-check-gpu27-judge-groups.py
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
CHECKER = os.path.join(REPO, "scripts", "check-gpu27-judge-groups.py")
FIXTURES = os.path.join(HERE, "fixtures", "gpu27")
WITH_CLIENT = "gpu27-stage-only-instrumented.log"
PLAIN = "gpu27-stage-only-plain.log"


def run(args):
    finished = subprocess.run([sys.executable, CHECKER] + args,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              universal_newlines=True)
    return finished.returncode, finished.stdout


def copy_fixtures():
    room = tempfile.mkdtemp(prefix="gpu27-groups-")
    target = os.path.join(room, "cases")
    shutil.copytree(FIXTURES, target)
    return room, target


def rewrite(path, old, new):
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    assert old in text, "fixture no longer contains %r" % old
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text.replace(old, new))


def main():
    failures = []

    code, output = run([])
    if code != 0:
        failures.append("the real fixture tree did not pass: %d\n%s" % (code, output))

    # 1. the field is gone from the fixture that is supposed to carry it.
    room, target = copy_fixtures()
    try:
        rewrite(os.path.join(target, WITH_CLIENT), " client=8333 us;", ";")
        code, output = run(["--fixtures=" + target])
        if code != 1:
            failures.append("a missing client field returned %d, wanted 1" % code)
        if "still unmeasured" not in output:
            failures.append("a missing client field was not named:\n%s" % output)
    finally:
        shutil.rmtree(room, ignore_errors=True)

    # 2. a neighbour's value in the pinned slot - the group shift itself.
    room, target = copy_fixtures()
    try:
        rewrite(os.path.join(target, WITH_CLIENT), "gpu=2222 us", "gpu=111 us")
        code, output = run(["--fixtures=" + target])
        if code != 1:
            failures.append("a shifted group returned %d, wanted 1" % code)
        if "gpu_us" not in output:
            failures.append("a shifted group was not named:\n%s" % output)
    finally:
        shutil.rmtree(room, ignore_errors=True)

    # 3. a machine without the evidence store: skip, unless --strict is asked.
    room, target = copy_fixtures()
    try:
        missing = os.path.join(room, "no-such-log.txt")
        code, output = run(["--fixtures=" + target, "--real-log=" + missing])
        if code != 0:
            failures.append("a missing real log without --strict returned %d, wanted 0" % code)
        if "SKIP the real-log pin" not in output:
            failures.append("a missing real log was not reported as SKIP:\n%s" % output)
        code, output = run(["--fixtures=" + target, "--real-log=" + missing, "--strict"])
        if code != 1:
            failures.append("a missing real log with --strict returned %d, wanted 1" % code)
    finally:
        shutil.rmtree(room, ignore_errors=True)

    if failures:
        for failure in failures:
            print("FAIL %s" % failure)
        return 1
    print("TESTS OK: 3 cases (missing field, shifted group, missing real log)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
