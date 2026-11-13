#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Judge one captured boot against the audio step-8 criteria.

Why this exists: capture.json has no verdict field, and panicMarker reads K60PANIC on
both a healthy boot and a broken one (usblog-20261113-noinitblob was healthy, the
-rev0340 capture was not, and both carry the marker). complete=true is likewise not a
health signal: the broken capture had complete=true and the healthy one had false.
The only evidence that decides this subtask is the PongAudio lines in console.log, so
this script reads those and nothing else.

Exit codes: 0 = probe succeeded, 1 = probe ran but failed, 2 = probe never ran.
"""
import json
import os
import re
import sys

MARK_START = "PongAudio: amp probe start"
MARK_BUS = ("PongAudio: gcc wrapper2", "PongAudio: se15 ready")
MARK_ID = re.compile(r"PongAudio: amp(\d) .*id=0x([0-9a-fA-F]{4})")
MARK_DONE = re.compile(
    r"PongAudio: amp probe done found=(\d+)/(\d+) .*failed=(\d+) timeouts=(\d+)"
    r" .*recovered=(\d+)"
)

# chip ids the probe is allowed to report (PongAudioPlan.h pong_audio_amp_name)
KNOWN = {
    0x2113: "AW88261", 0x2013: "AW88264", 0x2032: "AW88266", 0x2049: "AW88395",
    0x2055: "AW88256", 0x2066: "AW88166", 0x2071: "AW88350", 0x2183: "AW88399",
    0x2308: "AW88230",
}


def read_capture(directory):
    """Return (console lines, capture.json dict). Missing files yield empty values."""
    lines = []
    log_path = os.path.join(directory, "console.log")
    if os.path.isfile(log_path):
        with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
    meta = {}
    meta_path = os.path.join(directory, "capture.json")
    if os.path.isfile(meta_path):
        try:
            # capture-k60-usblog.ps1 writes UTF-8 with a BOM.
            with open(meta_path, "r", encoding="utf-8-sig") as handle:
                meta = json.load(handle)
        except (OSError, ValueError):
            meta = {}
    return lines, meta


def judge(lines, meta):
    """Return (exit code, report lines). Pure: no file access, so it is host-testable."""
    report = []
    report.append("capture.json: state=%s complete=%s stopReason=%s panicMarker=%s openErrors=%s"
                  % (meta.get("state"), meta.get("complete"), meta.get("stopReason"),
                     meta.get("panicMarker"), meta.get("openErrors")))
    starts = [l for l in lines if MARK_START in l]
    buses = [l for l in lines if any(m in l for m in MARK_BUS)]
    text = "\n".join(lines)
    ids = MARK_ID.findall(text)
    dones = MARK_DONE.findall(text)

    report.append("amp probe start      : %d line(s)" % len(starts))
    report.append("gcc/se15 bus ready   : %d line(s)" % len(buses))
    report.append("chip id reads        : %d %s" % (
        len(ids), ", ".join("amp%s=0x%s(%s)" % (n, i, KNOWN.get(int(i, 16), "unknown"))
                            for n, i in ids)))
    report.append("amp probe done       : %d %s" % (len(dones), dones))

    if not starts:
        report.append("VERDICT: probe never ran (no 'amp probe start')")
        return 2, report
    if not dones:
        report.append("VERDICT: probe started but never finished")
        return 1, report

    found, want, failed, timeouts, recovered = (int(x) for x in dones[-1])
    good = found == want and failed == 0 and timeouts == 0 and recovered == 0
    good = good and len(ids) == want and all(int(i, 16) in KNOWN for _, i in ids)
    report.append("VERDICT: %s" % ("SUCCESS - amplifiers identified" if good else "FAILED"))
    return (0 if good else 1), report


def main(argv):
    if len(argv) < 2:
        sys.stderr.write("usage: judge-audio-capture.py <evidence-dir> [...]\n")
        return 2
    worst = 0
    for directory in argv[1:]:
        lines, meta = read_capture(directory)
        code, report = judge(lines, meta)
        print("== %s" % directory)
        for line in report:
            print("   " + line)
        worst = max(worst, code)
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv))
