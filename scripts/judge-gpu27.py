#!/usr/bin/env python3
"""Judge a 27-line GPU flight for one question: is the panel being fed at 120 Hz?

单看 bench 不能判 120fps. The bench repeats one copy inside one offer with nothing on the
device animating, so it answers "how fast is the copy" and nothing else. A flight can hold a
5,907 us bench and still show 20 frames a second, because the frame also pays the kernel
compositor's full-screen CPU copy (measured 13,183 us each, usblog-20261119-151837:3341).
Reaching 120 Hz therefore needs two independent facts, and this judge refuses to pass on one:

  A. the copy fits the budget      - bench or steady stage medians (GPU_BUDGET_US, SUM_BUDGET_US)
  B. nothing else writes the frame - the compositor's "us each in the driver" statistic must be
                                     gone and the panel must be fed at PANEL_MIN per second

Three states, deliberately named rather than inferred from the exit code alone:

  PASS      both A and B hold, and no field that is present contradicts them
  FAIL      either half is missing, or a present field contradicts the other half
  INVALID   the run measured nothing: DeviceLost, a fault, or no frame at all (P-236, P-244)

Exit codes match the rest of scripts/judge-*.py: 0 PASS, 1 FAIL, 3 INVALID, 2 unreadable.

Fields this judge knows about but which the 16.6.1 image does not print yet (they are the
instrumentation ask in docs/research/gpu/GPU-27-JUDGE-DRAFT.md): `scanout version=`,
`abi=kernel=<v>/<sizeof> client=<v>`, `gpuonly=`, `offers=`/`dropped=`, `client=<us>`.
An absent field is reported as unmeasured, never assumed good; a present field that
disagrees is a FAIL.

Usage: judge-gpu27.py <evidence dir | console.log> [--json]
"""

import json
import os
import re
import statistics
import sys

# The kernel composer's own statistic. Its presence is the single most useful signal in the
# log: while it prints, drawLayer() is still copying every frame on the CPU.
DRIVER = re.compile(
    r"MiniIOMobileFramebuffer:\s*(\d+)\s*frames in\s*(\d+)\s*ms\s*\((\d+)\s*a second\),"
    r"\s*(\d+)\s*us each in the driver, after\s*(\d+)\s*us waiting for the GPU")
BENCH = re.compile(
    r"scanout bench n=(\d+)/(\d+) import=(\d+) us encode=(\d+) us submit=(\d+) us"
    r"\s*gpu=(\d+) us sum=(\d+) us status=(0x[0-9a-fA-F]+)")
STAGE = re.compile(
    r"Pong Metal: scanout frames=(\d+) at [\d.]+ s; last frame: wait=(\d+) us copy=(\d+) us"
    r" done=(\d+) us; imports=(\d+) import=(\d+) us encode=(\d+) us submit=(\d+) us"
    r"\s*gpu=(\d+) us sum=(\d+) us")
PANEL = re.compile(r"te\s*(\d+)/s")
PANEL_PERIOD = re.compile(r"period\s*(\d+)\s*us")
VOTE = "GPU level vote from gperf"
SCANOUT_VERSION = re.compile(r"scanout version=(\d+)")
ABI = re.compile(r"abi=kernel=(\d+)/(\d+) client=(\d+)")
GPU_ONLY = re.compile(r"gpuonly=([01])")
OFFERS = re.compile(r"offers=(\d+) dropped=(\d+)")
CLIENT = re.compile(r"client=(\d+) us")
DEVICE_LOST = "DeviceLost"
FAULTS = ("CP/SMMU fault", "GPU copy not retired", "panic(", "K60KEXC", "crashed: backboardd")

GPU_BUDGET_US = 3000          # card l, S3
SUM_BUDGET_US = 6000          # card l, S4
BENCH_MIN_SAMPLES = 8         # card l allows the bench to stand in for five presented frames
STAGE_MIN_LINES = 20          # steady stage lines needed before a median means anything
PANEL_MIN = 110               # judge-gpu-perf.py: below this the panel itself dropped
FRAME_BUDGET_US = 8333        # 120 Hz
BENCH_OK_BUT_UI_SLOW = (
    "the bench fits the budget while the compositor still copies every frame on the CPU")


def read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError as error:
        print("cannot read %s: %s" % (path, error))
        return None


def median(values):
    return int(statistics.median(values)) if values else None


def collect(text):
    facts = {
        "driver_lines": [],
        "bench": [],
        "stage": [],
        "panel_hz": None,
        "panel_period_us": None,
        "vote": 0,
        "scanout_version": None,
        "abi": None,
        "gpuonly": None,
        "offers": None,
        "client_us": None,
        "device_lost": text.count(DEVICE_LOST),
        "faults": {needle: text.count(needle) for needle in FAULTS if text.count(needle)},
    }
    for match in DRIVER.finditer(text):
        facts["driver_lines"].append({
            "frames": int(match.group(1)),
            "ms": int(match.group(2)),
            "per_second": int(match.group(3)),
            "driver_us": int(match.group(4)),
            "waiting_us": int(match.group(5)),
        })
    for match in BENCH.finditer(text):
        facts["bench"].append({
            "n": int(match.group(1)),
            "import_us": int(match.group(3)),
            "encode_us": int(match.group(4)),
            "submit_us": int(match.group(5)),
            "gpu_us": int(match.group(6)),
            "sum_us": int(match.group(7)),
            "status": match.group(8),
        })
    for match in STAGE.finditer(text):
        facts["stage"].append({
            "wait_us": int(match.group(2)),
            "copy_us": int(match.group(3)),
            "gpu_us": int(match.group(8)),
            "sum_us": int(match.group(9)),
        })
    if PANEL.search(text):
        facts["panel_hz"] = max(int(v) for v in PANEL.findall(text))
    if PANEL_PERIOD.search(text):
        facts["panel_period_us"] = median([int(v) for v in PANEL_PERIOD.findall(text)])
    facts["vote"] = text.count(VOTE)
    match = SCANOUT_VERSION.search(text)
    if match:
        facts["scanout_version"] = int(match.group(1))
    match = ABI.search(text)
    if match:
        facts["abi"] = {"kernel": int(match.group(1)), "size": int(match.group(2)),
                        "client": int(match.group(3))}
    match = GPU_ONLY.search(text)
    if match:
        facts["gpuonly"] = int(match.group(1))
    match = OFFERS.search(text)
    if match:
        facts["offers"] = {"offers": int(match.group(1)), "dropped": int(match.group(2))}
    match = CLIENT.search(text)
    if match:
        facts["client_us"] = int(match.group(1))
    return facts


def medians(facts):
    out = {}
    if len(facts["bench"]) >= BENCH_MIN_SAMPLES:
        out["source"] = "bench"
        rows = facts["bench"]
        out["import_us"] = median([r["import_us"] for r in rows])
        out["encode_us"] = median([r["encode_us"] for r in rows])
        out["submit_us"] = median([r["submit_us"] for r in rows])
        out["gpu_us"] = median([r["gpu_us"] for r in rows])
        out["sum_us"] = median([r["sum_us"] for r in rows])
        out["failed"] = sum(1 for r in rows if r["status"] != "0x0")
        out["samples"] = len(rows)
    elif len(facts["stage"]) >= STAGE_MIN_LINES:
        out["source"] = "stage"
        rows = facts["stage"]
        out["gpu_us"] = median([r["gpu_us"] for r in rows])
        out["sum_us"] = median([r["sum_us"] for r in rows])
        out["copy_us"] = median([r["copy_us"] for r in rows])
        out["wait_us"] = median([r["wait_us"] for r in rows])
        out["failed"] = 0
        out["samples"] = len(rows)
    else:
        out["source"] = None
        out["samples"] = len(facts["bench"]) + len(facts["stage"])
    return out


def judge(facts, stats):
    """Return (state, reasons). state is PASS, FAIL or INVALID."""
    invalid = []
    if facts["device_lost"]:
        invalid.append("DeviceLost appeared %d times (P-244)" % facts["device_lost"])
    if facts["faults"]:
        invalid.append("fault lines: " + ", ".join(sorted(facts["faults"])))
    if not facts["driver_lines"] and not facts["bench"] and not facts["stage"]:
        invalid.append("no frame was ever presented and no bench ran (P-236)")
    if stats["source"] is None:
        invalid.append("neither %d bench samples nor %d steady stage lines: no median is"
                       " meaningful" % (BENCH_MIN_SAMPLES, STAGE_MIN_LINES))
    if invalid:
        return "INVALID", invalid

    fails = []
    # A. the copy fits the budget
    if stats.get("gpu_us") is not None and stats["gpu_us"] >= GPU_BUDGET_US:
        fails.append("gpu median %d us is not below %d us" % (stats["gpu_us"], GPU_BUDGET_US))
    if stats.get("sum_us") is not None and stats["sum_us"] >= SUM_BUDGET_US:
        fails.append("sum median %d us is not below %d us" % (stats["sum_us"], SUM_BUDGET_US))
    if stats.get("failed"):
        fails.append("%d copies reported a non-zero status" % stats["failed"])

    # B. nothing else writes the frame
    wall = [row for row in facts["driver_lines"] if row["per_second"] < PANEL_MIN]
    if wall:
        worst = max(wall, key=lambda row: row["driver_us"])
        # The bench half alone is exactly the trap this judge exists for, so name it.
        bench_fits = (stats.get("sum_us") is not None and stats["sum_us"] < SUM_BUDGET_US)
        fails.append("%s: %d/%d frames a second, %d us each in the driver"
                     % (BENCH_OK_BUT_UI_SLOW if bench_fits else "the panel was starved",
                        worst["per_second"], worst["frames"], worst["driver_us"]))
    if facts["panel_hz"] is not None and facts["panel_hz"] < PANEL_MIN:
        fails.append("panel dropped to %d Hz" % facts["panel_hz"])
    if facts["gpuonly"] == 0:
        fails.append("gpuonly=0: CPU composition is still allowed to run")

    # Fields that exist only when the image was instrumented. Present and wrong is a FAIL;
    # absent is reported as unmeasured by the caller, never counted as good.
    if facts["abi"] is not None:
        abi = facts["abi"]
        if abi["kernel"] != abi["client"] or abi["size"] not in (416, 3104):
            fails.append("abi=kernel=%d/%d client=%d does not agree"
                         % (abi["kernel"], abi["size"], abi["client"]))
    if facts["scanout_version"] is not None and facts["scanout_version"] not in (1, 2):
        fails.append("scanout version=%d is not a layout this line knows"
                     % facts["scanout_version"])
    if facts["offers"] is not None and facts["offers"]["dropped"]:
        fails.append("dropped=%d: frames were offered and refused"
                     % facts["offers"]["dropped"])
    if facts["client_us"] is not None and facts["client_us"] > FRAME_BUDGET_US:
        fails.append("client frame took %d us, over the %d us budget"
                     % (facts["client_us"], FRAME_BUDGET_US))

    return ("FAIL", fails) if fails else ("PASS", [])


def main(argv):
    if len(argv) < 2:
        print("usage: judge-gpu27.py <evidence dir | console.log> [--json]")
        return 2
    target = argv[1]
    as_json = "--json" in argv[2:]
    path = os.path.join(target, "console.log") if os.path.isdir(target) else target
    text = read(path)
    if text is None:
        return 2

    facts = collect(text)
    stats = medians(facts)
    state, reasons = judge(facts, stats)

    unmeasured = [name for name, value in (
        ("scanout version", facts["scanout_version"]),
        ("abi", facts["abi"]),
        ("gpuonly", facts["gpuonly"]),
        ("offers/dropped", facts["offers"]),
        ("client us", facts["client_us"]),
        ("panel hz", facts["panel_hz"]),
    ) if value is None]

    if as_json:
        print(json.dumps({
            "state": state,
            "reasons": reasons,
            "unmeasured": unmeasured,
            "stats": stats,
            "driver_lines": facts["driver_lines"],
            "bench_samples": len(facts["bench"]),
            "stage_lines": len(facts["stage"]),
        }, ensure_ascii=False, indent=2))
        return {"PASS": 0, "FAIL": 1, "INVALID": 3}[state]

    print("== 1. validity ==")
    print("  bench samples      : %d" % len(facts["bench"]))
    print("  steady stage lines : %d" % len(facts["stage"]))
    print("  compositor stats   : %d" % len(facts["driver_lines"]))
    print("  DeviceLost         : %d" % facts["device_lost"])

    print("\n== 2. the copy (A) ==")
    if stats["source"]:
        print("  source: %s (%d samples)" % (stats["source"], stats["samples"]))
        print("  gpu median %s us (budget %d) | sum median %s us (budget %d)"
              % (stats.get("gpu_us"), GPU_BUDGET_US, stats.get("sum_us"), SUM_BUDGET_US))
    else:
        print("  no sample set large enough for a median")

    print("\n== 3. the frame writer (B) ==")
    if not facts["driver_lines"]:
        print("  the compositor statistic did not print: drawLayer() did not copy a frame")
    for row in facts["driver_lines"]:
        print("  %d frames in %d ms (%d a second), %d us each in the driver, "
              "%d us waiting for the GPU"
              % (row["frames"], row["ms"], row["per_second"], row["driver_us"],
                 row["waiting_us"]))
    if facts["panel_hz"] is not None:
        print("  panel: %d Hz, period %s us" % (facts["panel_hz"], facts["panel_period_us"]))

    print("\n== 4. instrumented fields ==")
    print("  scanout version=%s | abi=%s | gpuonly=%s | offers=%s | client=%s"
          % (facts["scanout_version"], facts["abi"], facts["gpuonly"],
             facts["offers"], facts["client_us"]))
    if unmeasured:
        print("  unmeasured (absent, not assumed good): %s" % ", ".join(unmeasured))

    print("\nverdict: %s" % state)
    for reason in reasons:
        print("  - %s" % reason)
    if state == "PASS" and unmeasured:
        print("  note: %d field(s) unmeasured; the copy and the writer both hold, which is"
              " what 120 Hz needs, but the wire and the client were not observable here"
              % len(unmeasured))
    if state == "FAIL" and any("bench fits the budget" in reason for reason in reasons):
        # Printed in English on purpose: this console is a GBK code page and CJK output
        # arrives as mojibake. The Chinese phrasing of the same rule lives in the docstring.
        print("  read: a bench alone cannot judge 120 fps - it repeats one copy with nothing"
              " animating, and this panel was fed by the CPU compositor instead")
    return {"PASS": 0, "FAIL": 1, "INVALID": 3}[state]


if __name__ == "__main__":
    sys.exit(main(sys.argv))
