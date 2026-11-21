#!/usr/bin/env python3
"""Tests for scripts/check-gpu27-flip-asserts.py.

The checker is dormant today, and a dormant gate is only worth having if it
fails the moment it stops being dormant. These tests build a throwaway lane
tree in four states - no series line, in series and in step, in series with one
number drifted, and assertions carried with no series line at all - and require
the checker to say which state it is in instead of passing quietly.

Run: python3 scripts/tests/test-check-gpu27-flip-asserts.py
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
CHECKER = os.path.join(REPO, "scripts", "check-gpu27-flip-asserts.py")

# The real draft, copied verbatim: the point of the check is that the header and
# this file agree, so the test must not paraphrase it.
LANE = os.environ.get("K60_GPU27_REPO") or os.path.join(os.path.dirname(REPO), "k60-gpu-27")
PATCH_SOURCE = os.path.join(LANE, "patches", "proposed", "pong-scanout-v2-layout-asserts.patch")

BLOCK = """#define PONG_SCANOUT_V2_LAYOUT 0
#if PONG_SCANOUT_V2_LAYOUT
static_assert(sizeof(PongScanoutFrame)==56,"v2 frame");
static_assert(offsetof(PongScanoutFrame,token)==44,"v2 token sits where reserved was");
static_assert(offsetof(PongScanoutFrame,evict)==48,"v2 evict");
static_assert(offsetof(PongScanoutFrame,target)==52,"v2 target");
#endif
"""

BASE = """enum {PongScanoutVersion=1};
struct PongScanoutFrame {uint64_t sequence,address,bytes,stride;uint32_t width,height,format,reserved;};
static_assert(sizeof(PongScanoutFrame)==48,"v1 frame");
static_assert(offsetof(PongScanoutFrame,reserved)==44,"v1 reserved");
"""


def run(args):
    finished = subprocess.run([sys.executable, CHECKER] + args,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              universal_newlines=True)
    return finished.returncode, finished.stdout


def build(block="", series=False, patch=True):
    room = tempfile.mkdtemp(prefix="gpu27-flip-")
    drivers = os.path.join(room, "drivers", "PongAdreno")
    proposed = os.path.join(room, "patches", "proposed")
    xnu = os.path.join(room, "patches", "xnu")
    for path in (drivers, proposed, xnu):
        os.makedirs(path)
    with open(os.path.join(drivers, "PongScanoutWire.h"), "w", encoding="utf-8") as handle:
        handle.write(BASE + block)
    if patch:
        shutil.copyfile(PATCH_SOURCE, os.path.join(proposed, os.path.basename(PATCH_SOURCE)))
    if series:
        with open(os.path.join(xnu, "series"), "w", encoding="utf-8") as handle:
            handle.write("0600-k60-display-composition.patch\n"
                         "pong-scanout-assert-offsets.patch\n"
                         "pong-scanout-v2-layout-asserts.patch\n")
    return room


def main():
    if not os.path.isfile(PATCH_SOURCE):
        print("SKIP the real draft is missing at %s" % PATCH_SOURCE)
        return 0

    failures = []

    # 0. the lane as it stands: no series line, no block - dormant, and that is a pass.
    code, output = run([])
    if code != 0:
        failures.append("the real lane is not dormant-and-passing: %d\n%s" % (code, output))
    elif "dormant" not in output:
        failures.append("the real lane passed without saying it was dormant:\n%s" % output)

    # 1. in series and in step.
    room = build(block=BLOCK, series=True)
    try:
        code, output = run(["--lane-root=" + room])
        if code != 0:
            failures.append("in-step copies returned %d, wanted 0\n%s" % (code, output))
        elif "sha256" not in output:
            failures.append("in-step copies passed without a digest:\n%s" % output)
    finally:
        shutil.rmtree(room, ignore_errors=True)

    # 2. one number drifted - the case the whole check exists for.
    room = build(block=BLOCK.replace("target)==52", "target)==56"), series=True)
    try:
        code, output = run(["--lane-root=" + room])
        if code != 1:
            failures.append("a drifted offset returned %d, wanted 1\n%s" % (code, output))
        if "header only" not in output:
            failures.append("a drifted offset was not shown:\n%s" % output)
    finally:
        shutil.rmtree(room, ignore_errors=True)

    # 3. the claim without the record: block in the header, no series line.
    room = build(block=BLOCK, series=False)
    try:
        code, output = run(["--lane-root=" + room])
        if code != 1:
            failures.append("a claim without a series line returned %d, wanted 1\n%s" % (code, output))
        if "without the record" not in output:
            failures.append("a claim without a series line was not named:\n%s" % output)
    finally:
        shutil.rmtree(room, ignore_errors=True)

    # 4. half a block.
    half = BLOCK.replace('static_assert(offsetof(PongScanoutFrame,evict)==48,"v2 evict");\n', "")
    room = build(block=half, series=True)
    try:
        code, output = run(["--lane-root=" + room])
        if code != 1:
            failures.append("half a block returned %d, wanted 1\n%s" % (code, output))
        if "3 of 4" not in output:
            failures.append("half a block was not counted:\n%s" % output)
    finally:
        shutil.rmtree(room, ignore_errors=True)

    # 5. the draft itself missing - cannot run, not a pass.
    room = build(block=BLOCK, series=True, patch=False)
    try:
        code, output = run(["--lane-root=" + room])
        if code != 2:
            failures.append("a missing draft returned %d, wanted 2\n%s" % (code, output))
    finally:
        shutil.rmtree(room, ignore_errors=True)

    # 6. --strict turns the dormant lane into a failure.
    code, output = run(["--strict"])
    if code != 1:
        failures.append("--strict on the dormant lane returned %d, wanted 1\n%s" % (code, output))

    if failures:
        for failure in failures:
            print("FAIL %s" % failure)
        print("TESTS FAILED: %d" % len(failures))
        return 1
    print("TESTS OK: 7 cases (dormant, in step, drifted, claim without record, half, missing draft, strict)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
