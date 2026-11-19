#!/usr/bin/env python3
"""Judge the flight that asks whether the GPU was running at a level that fits the work.

Three layers, in this order (P-236):

  1. validity   - did anything render, and did the GPU stay alive? A zero-frame run measures
                  nothing and a DeviceLost run is dead rather than slow (P-244).
  2. path       - is this the image that carries the vote at all? `GPU level vote from gperf`
                  has to appear, otherwise "no vote" would read as "the vote did not help".
  3. numbers    - medians of the four measured stages, compared against the flight that ran
                  before the vote existed (card j: gpu 5,983 us, copy 8,406 us).

Exit codes: 0 = the criteria hold, 1 = they do not, 3 = invalid, 2 = unreadable.
"""

import os
import re
import statistics
import sys

COMPOSITOR = re.compile(r"MiniIOMobileFramebuffer:\s*(\d+)\s*frames in\s*(\d+)\s*ms")
COMMITS = re.compile(r"Pong Metal: c(\d+)/0 d(\d+)")
VOTE = re.compile(
    r"GPU level vote from gperf: .*status=(0x[0-9a-fA-F]+|0)\b.*a=(\d+) b=(\d+)"
    r"|GPU level vote from gperf")
VOTE_LOOSE = "GPU level vote from gperf"
STAGE = re.compile(
    r"Pong Metal: scanout frames=(\d+) at [\d.]+ s; last frame: wait=(\d+) us copy=(\d+) us"
    r" done=(\d+) us; imports=(\d+) import=(\d+) us encode=(\d+) us submit=(\d+) us"
    r" gpu=(\d+) us sum=(\d+) us")
# The bench repeats the same copy inside one offer, so its samples do not depend on whether
# anything on the device was animating. When it ran, it is the sample set worth taking a median
# of; the ordinary stage lines stay as the fallback for an image without the bench.
BENCH = re.compile(
    r"scanout bench n=(\d+)/(\d+) import=(\d+) us encode=(\d+) us submit=(\d+) us"
    r" gpu=(\d+) us sum=(\d+) us status=(0x[0-9a-fA-F]+)")
PANEL = re.compile(r"(?:after the UI frame|panel after UI)[^\n]*?te\s*(\d+)/s")
DEVICE_LOST = "DeviceLost"
FAULTS = ("CP/SMMU fault", "GPU copy not retired", "panic(", "K60KEXC", "crashed: backboardd")

GPU_BEFORE_US = 5983
COPY_BEFORE_US = 8406
GPU_TARGET_US = 3000
COPY_TARGET_US = 6000
PANEL_MIN = 110
STEADY_FRAMES = 20


def read(path):
    try:
        with open(path, "rb") as handle:
            return handle.read().decode("utf-8", "replace")
    except OSError as error:
        print("judge: cannot read %s (%s)" % (path, error))
        return None


def median(values):
    return int(statistics.median(values)) if values else None


def judge(text):
    lines = text.splitlines()
    compositor = [int(n) for n, _ in COMPOSITOR.findall(text)]
    commits = [int(n) for n, _ in COMMITS.findall(text)]
    votes = [line for line in lines if VOTE_LOOSE in line]
    stages = [tuple(int(x) for x in m) for m in STAGE.findall(text)]
    panel = [int(x) for x in PANEL.findall(text)]
    lost = text.count(DEVICE_LOST)
    faults = {needle: text.count(needle) for needle in FAULTS}

    bench = [(int(n), int(total), int(i), int(e), int(s), int(g), int(sm), int(st, 16))
             for n, total, i, e, s, g, sm, st in BENCH.findall(text)]
    steady = [row for row in stages if row[0] >= STEADY_FRAMES]
    out = {
        "compositor_frames": max(compositor) if compositor else 0,
        "client_commits": max(commits) if commits else 0,
        "vote_lines": len(votes),
        "stage_lines": len(stages),
        "steady_lines": len(steady),
        "device_lost": lost,
        "faults": faults,
        "panel_hz": panel[-1] if panel else None,
        "import_mismatch": sum(1 for row in stages if row[4] != row[0]),
        "bench_lines": len(bench),
        "bench_failed": sum(1 for row in bench if row[7] != 0),
    }
    if bench:
        ok = [row for row in bench if row[7] == 0]
        if ok:
            out.update(
                import_us=median([r[2] for r in ok]),
                encode_us=median([r[3] for r in ok]),
                submit_us=median([r[4] for r in ok]),
                gpu_us=median([r[5] for r in ok]),
                sum_us=median([r[6] for r in ok]),
                copy_us=None,
            )
    elif steady:
        out.update(
            import_us=median([r[5] for r in steady]),
            encode_us=median([r[6] for r in steady]),
            submit_us=median([r[7] for r in steady]),
            gpu_us=median([r[8] for r in steady]),
            sum_us=median([r[9] for r in steady]),
            copy_us=median([r[2] for r in steady]),
        )
    return out, votes


def main():
    if len(sys.argv) < 2:
        print("usage: judge-gpu-perf.py <evidence dir | console.log>")
        return 2
    target = sys.argv[1]
    path = target
    if os.path.isdir(target):
        path = os.path.join(target, "console.log")
    text = read(path)
    if text is None:
        return 2

    facts, votes = judge(text)
    print("== 1. validity (P-236, P-244) ==")
    print("  compositor frames : %d" % facts["compositor_frames"])
    print("  client commits    : %d" % facts["client_commits"])
    print("  stage lines       : %d (%d steady, frames >= %d)"
          % (facts["stage_lines"], facts["steady_lines"], STEADY_FRAMES))
    print("  bench samples     : %d (%d failed)" % (facts["bench_lines"], facts["bench_failed"]))
    print("  DeviceLost        : %d" % facts["device_lost"])
    for needle, count in facts["faults"].items():
        print("  %-18s: %d" % (needle, count))

    invalid = []
    # A bench flight is allowed to be idle: the whole point of repeating the copy is that the
    # measurement no longer depends on something on the device happening to animate. What the
    # bench cannot survive is never having been offered a frame at all.
    if facts["bench_lines"] >= 8:
        if facts["compositor_frames"] < 1:
            invalid.append("no frame was ever offered, so the bench could not have run")
    else:
        if facts["compositor_frames"] < 5:
            invalid.append("the compositor did not present (P-236)")
        if facts["client_commits"] < 5:
            invalid.append("the client committed fewer than five command buffers")
    if facts["device_lost"]:
        invalid.append("DeviceLost appeared %d times (P-244)" % facts["device_lost"])
    if facts["steady_lines"] < 20 and facts["bench_lines"] < 8:
        invalid.append("neither 20 steady stage lines nor 8 bench samples: no median is meaningful")
    if invalid:
        print("  verdict: INVALID - " + "; ".join(invalid))
        print("\nNothing below is a measurement of the vote.")
        return 3

    print("\n== 2. path ==")
    print("  'GPU level vote from gperf' lines : %d" % facts["vote_lines"])
    for line in votes[:2]:
        print("    %s" % line.strip())
    if not facts["vote_lines"]:
        print("  verdict: FAIL - the image or the boot line did not carry gperf=13")
        return 1

    print("\n== 3. numbers (steady medians, us) ==")
    print("  source: %s" % ("bench repeats" if facts["bench_lines"] >= 8 else "stage lines"))
    print("  import %s | encode %s | submit %s | gpu %s | sum %s | copy %s"
          % (facts["import_us"], facts["encode_us"], facts["submit_us"],
             facts["gpu_us"], facts["sum_us"], facts["copy_us"]))
    print("  before the vote (card j): gpu %d, copy %d" % (GPU_BEFORE_US, COPY_BEFORE_US))
    print("  imports == frames on every steady line: %s"
          % ("yes" if facts["import_mismatch"] == 0 else "NO (%d lines)" % facts["import_mismatch"]))
    if facts["panel_hz"] is not None:
        print("  panel te : %d/s" % facts["panel_hz"])

    problems = []
    if facts["gpu_us"] is None or facts["gpu_us"] >= GPU_TARGET_US:
        problems.append("gpu median %s us is not below %d us" % (facts["gpu_us"], GPU_TARGET_US))
    if facts["copy_us"] is not None and facts["copy_us"] >= COPY_TARGET_US:
        problems.append("copy median %s us is not below %d us" % (facts["copy_us"], COPY_TARGET_US))
    if facts["bench_lines"] == 0 and facts["import_mismatch"]:
        problems.append("imports != frames on %d steady lines" % facts["import_mismatch"])
    if facts["bench_failed"]:
        problems.append("%d bench copies failed" % facts["bench_failed"])
    if facts["panel_hz"] is not None and facts["panel_hz"] < PANEL_MIN:
        problems.append("panel dropped to %d Hz" % facts["panel_hz"])
    if any(facts["faults"].values()):
        problems.append("a fault line appeared")

    if problems:
        print("\n  verdict: FAIL - " + "; ".join(problems))
        if facts["gpu_us"] is not None and facts["gpu_us"] >= 5000:
            print("  F3: the clock is not the limiter; next is fencing, vblank queueing or a"
                  " real GPU frequency read-back")
        return 1
    print("\n  verdict: PASS - the vote landed and both stage medians moved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
