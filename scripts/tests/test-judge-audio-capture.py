#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Host test for scripts/judge-audio-capture.py.

The judge replaced a human reading capture.json, which is exactly the step that got
the verdict wrong twice (panicMarker reads K60PANIC on a healthy boot too). These cases
pin the three outcomes and the two traps.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "judge-audio-capture.py")

spec = importlib.util.spec_from_file_location("judge_audio_capture", TOOL)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

fails = 0


def expect(cond, what):
    global fails
    if not cond:
        print("FAIL " + what)
        fails += 1


HEALTHY = [
    "K60PANIC: restart windows ready",
    "PongAudio: amp probe start (amplifiers are read-only; AMPS.md A1-A7)",
    "PongAudio: amp gcc clk core halt=0x00000002 running=1",
    "PongAudio: amp se15 ready config=0x03000021 status=0x00000000 level=2",
    "PongAudio: amp0 addr=0x34 id=0x2113 chip=AW88261",
    "PongAudio: amp1 addr=0x35 id=0x2113 chip=AW88261",
    "PongAudio: amp probe done found=2/2 transfers=26 failed=0 timeouts=0 stray=0 recovered=0",
]
SILENT = [
    "PongAudio: amp probe start (amplifiers are read-only; AMPS.md A1-A7)",
    "PongAudio: amp0 addr=0x34 no answer after 3 reads result=3 err=3 irq=0x00000000",
    "PongAudio: amp probe done found=0/2 transfers=6 failed=6 timeouts=3 stray=0 recovered=2",
]
STARTED_ONLY = [
    "PongAudio: amp probe start (amplifiers are read-only; AMPS.md A1-A7)",
    "PongAudio: se15 no DFS level",
]
ABSENT = ["K60PANIC: restart windows ready", "no audio here"]


def cases():
    code, report = mod.judge(HEALTHY, {"state": "captured-truncated", "complete": False,
                                       "panicMarker": "K60PANIC"})
    expect(code == 0, "healthy capture is SUCCESS even with panicMarker set and complete=false")
    expect(any("SUCCESS" in l for l in report), "healthy report names SUCCESS")
    expect(any("amp0=0x2113(AW88261)" in l for l in report), "known chip id is named")
    expect(any("bus ready" in l and l.strip().endswith("2 line(s)") for l in report),
           "the two real bus lines are recognised")

    code, _ = mod.judge(SILENT, {"state": "captured", "complete": True,
                                 "panicMarker": "K60PANIC"})
    expect(code == 1, "complete=true does not rescue a silent amplifier")

    code, report = mod.judge(STARTED_ONLY, {})
    expect(code == 1, "started but unfinished is a failure")
    expect(any("never finished" in l for l in report), "unfinished report says so")

    code, report = mod.judge(ABSENT, {})
    expect(code == 2, "no probe line means the probe never ran")
    expect(any("never ran" in l for l in report), "absent report says so")

    # an unknown id must not be accepted just because the count matches
    odd = list(HEALTHY)
    odd[4] = "PongAudio: amp0 addr=0x34 id=0x1234 chip=unknown"
    code, _ = mod.judge(odd, {})
    expect(code == 1, "unknown chip id fails even at found=2/2")

    # one amplifier identified is not success either
    half = [l for l in HEALTHY if "amp1 addr" not in l]
    code, _ = mod.judge(half, {})
    expect(code == 1, "found=2/2 with one id read fails")

    expect(mod.KNOWN[0x2113] == "AW88261", "chip table matches PongAudioPlan.h")
    expect(len(mod.KNOWN) == 9, "nine known ids")


def bom_case():
    """capture.json is written with a BOM; reading it as plain utf-8 used to fail."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "capture.json"), "w", encoding="utf-8-sig") as handle:
            handle.write('{"state": "captured", "complete": true}')
        with open(os.path.join(tmp, "console.log"), "w", encoding="utf-8") as handle:
            handle.write("\n".join(HEALTHY))
        lines, meta = mod.read_capture(tmp)
        expect(meta.get("state") == "captured", "BOM-prefixed capture.json parses")
        expect(len(lines) == len(HEALTHY), "console.log is read whole")
    code, _ = mod.judge(*mod.read_capture("/nonexistent-evidence-dir"))
    expect(code == 2, "a missing directory is not a success")


def severity_case():
    """Two runs are combined by need, not by numeric max: failure outranks absent."""
    expect(mod.severity(1) > mod.severity(2), "a failed run outranks a run that never started")
    expect(mod.severity(2) > mod.severity(0), "a run that never started outranks success")
    expect(mod.severity(0) == 0, "success is the least severe")


def main():
    cases()
    bom_case()
    severity_case()
    if fails:
        print("TESTS FAILED %d case(s)" % fails)
        return 1
    print("TESTS OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
