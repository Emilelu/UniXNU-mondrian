#!/usr/bin/env python3
"""Judge a K60 console log against the pre-registered 120 Hz flight criteria.

This is the log-side companion to scripts/check-panel-timing.py.  The static
checker proves the image contains the eleven-packet timing@2 switch, the
first-GPU-frame trigger and the INTF1 vsync_count update.  This checker proves
the image, once booted, actually produced the pre-registered evidence:

  * "K60 PANEL: 120 Hz switch at the first GPU frame"
  * "K60 PANEL: timing switch to 120 Hz: 11 packets, rc 0"
  * after the UI frame, INTF1 TE rate 110-130/s
  * before the switch, INTF1 TE rate 55-65/s (supporting)
  * first frame presented, at least 100 SpringBoard lines, zero sig=11
  * no K60 PANEL DCS failure after the switch starts
  * K60 BACKLIGHT published level ... conformance=1 control=1

Why the line counter: INTF_LINE_COUNT (0xb0) is the panel scan line counter;
one wrap is one frame, and the official DisplayTimingProbe reference measures
the shortest interval between two wraps (DisplayTimingProbe.cpp:45-70).
INTF_TEAR_INT_COUNT_VAL (0x298) high 16 bits is a read-pointer frame count and
was observed wrapping to 55->1 in the 120hz-4 log, so it is not a TE rate.
INTF_FRAME_COUNT (0xac) counts DPU command-FIFO commits, so a static UI can
legitimately show a low frame rate while the panel itself runs at 120 Hz.  All
three are recorded in the log; only the line-counter period decides the rate.

Exit status: 0 PASS, 1 FAIL, 2 INCONCLUSIVE (switch happened but no post-UI
TE observation, or the log has no K60 PANEL line at all).

Usage:
    python3 scripts/check-120hz-log.py <console.log|evidence dir> [--json]
    python3 scripts/check-120hz-log.py --selftest
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REQUESTED = "K60 PANEL: 120 Hz switch at the first GPU frame"
SWITCH = re.compile(r"K60 PANEL: timing switch to 120 Hz: (\d+) packets, rc (\d+)")
INTF = re.compile(
    r"K60 PANEL: INTF1 (.+?) te (\d+)/s frames (\d+)/s over (\d+) ms"
    r" \(te (\d+)->(\d+) frames (\d+)->(\d+)\)")
BACKLIGHT = re.compile(
    r"K60 BACKLIGHT: published level (\d+) dbv 0x([0-9a-fA-F]+)"
    r" conformance=(\d+) control=(\d+)")
DCS_FAIL = re.compile(r"K60 PANEL: DCS .*failed", re.I)
SIGSEGV = re.compile(r"sig=11|SIGSEGV|signal 11")


def read_log(target: Path) -> str:
    if target.is_dir():
        for name in ("console.log", "console.txt", "log.txt"):
            candidate = target / name
            if candidate.is_file():
                return candidate.read_text(errors="replace")
        raise SystemExit("no console.log under " + str(target))
    if not target.is_file():
        raise SystemExit("no such file: " + str(target))
    return target.read_text(errors="replace")


def parse(text: str) -> dict:
    found: dict = {
        "panel_lines": text.count("K60 PANEL:"),
        "switch_requested": text.count(REQUESTED),
        "switch_done": None,
        "switch_done_index": None,
        "intf": [],
        "backlight": None,
        "dcs_fail": 0,
        "sig11": len(SIGSEGV.findall(text)),
        "first_frame": text.count("K60 DISPLAY: first frame presented"),
        "springboard": sum(1 for line in text.splitlines() if "SpringBoard" in line),
        "lines": text.count("\n") + 1,
    }
    match = SWITCH.search(text)
    if match:
        found["switch_done"] = (int(match.group(1)), int(match.group(2)))
        found["switch_done_index"] = match.start()
    for match in INTF.finditer(text):
        found["intf"].append({
            "phase": match.group(1),
            "te": int(match.group(2)),
            "frames": int(match.group(3)),
            "ms": int(match.group(4)),
            "te0": int(match.group(5)),
            "te1": int(match.group(6)),
            "frames0": int(match.group(7)),
            "frames1": int(match.group(8)),
            "index": match.start(),
        })
    match = BACKLIGHT.search(text)
    if match:
        found["backlight"] = {
            "level": int(match.group(1)),
            "dbv": int(match.group(2), 16),
            "conformance": int(match.group(3)),
            "control": int(match.group(4)),
        }
    if found["switch_done_index"] is not None:
        found["dcs_fail"] = len(DCS_FAIL.findall(text[found["switch_done_index"]:]))
    return found


def judge(found: dict) -> tuple[int, list[str]]:
    lines: list[str] = []
    failures = 0
    unknown = 0

    if not found["panel_lines"]:
        return 2, ["FAIL the log carries no K60 PANEL line: wrong image or capture"]
    lines.append("K60 PANEL lines: %d" % found["panel_lines"])

    if not found["switch_requested"]:
        failures += 1
        lines.append("FAIL missing 'K60 PANEL: 120 Hz switch at the first GPU frame'")
    else:
        lines.append("first-GPU-frame switch request present")
    if found["switch_done"] is None:
        failures += 1
        lines.append("FAIL missing 'K60 PANEL: timing switch to 120 Hz: ... packets, rc ...'")
    else:
        packets, rc = found["switch_done"]
        if packets != 11:
            failures += 1
            lines.append("FAIL timing switch sent %d packets, expected 11" % packets)
        else:
            lines.append("timing switch sent 11 packets")
        if rc != 0:
            failures += 1
            lines.append("FAIL timing switch rc %d, expected 0" % rc)
        else:
            lines.append("timing switch rc 0")

    ui = [row for row in found["intf"] if row["phase"] == "after the UI frame"]
    before = [row for row in found["intf"] if row["phase"] == "before the switch"]
    after = [row for row in found["intf"] if row["phase"] == "after the switch"]
    for label, rows in (("before the switch", before), ("after the switch", after)):
        if rows:
            row = rows[-1]
            lines.append("%s: te %d/s frames %d/s over %d ms%s" % (
                label, row["te"], row["frames"], row["ms"],
                " (supporting)" if label == "after the switch" else ""))
        else:
            lines.append("WARN no '%s' INTF1 rate line" % label)
    if before:
        if not 55 <= before[-1]["te"] <= 65:
            failures += 1
            lines.append("FAIL before-switch TE %d/s outside 55-65/s" % before[-1]["te"])
        else:
            lines.append("before-switch TE %d/s in 55-65/s" % before[-1]["te"])
    if not ui:
        unknown += 1
        lines.append("INCONCLUSIVE no 'after the UI frame' INTF1 rate line: "
                     "the switch has no post-UI TE evidence")
    else:
        row = ui[-1]
        lines.append("after the UI frame: te %d/s frames %d/s over %d ms" % (
            row["te"], row["frames"], row["ms"]))
        if not 110 <= row["te"] <= 130:
            failures += 1
            lines.append("FAIL after-UI TE %d/s outside 110-130/s" % row["te"])
        else:
            lines.append("after-UI TE %d/s in 110-130/s" % row["te"])
        lines.append("after-UI frame counter %d/s (DPU commits; not the panel rate)" % row["frames"])

    if found["first_frame"]:
        lines.append("first frame presented: %d" % found["first_frame"])
    else:
        failures += 1
        lines.append("FAIL 'K60 DISPLAY: first frame presented' never appeared")
    if found["springboard"] >= 100:
        lines.append("SpringBoard lines: %d" % found["springboard"])
    else:
        failures += 1
        lines.append("FAIL SpringBoard lines: %d, expected at least 100" % found["springboard"])
    if found["sig11"]:
        failures += 1
        lines.append("FAIL sig=11 count: %d, expected 0" % found["sig11"])
    else:
        lines.append("sig=11 count: 0")
    if found["dcs_fail"]:
        failures += 1
        lines.append("FAIL %d K60 PANEL DCS failure(s) after the switch" % found["dcs_fail"])
    else:
        lines.append("no K60 PANEL DCS failure after the switch")

    if found["backlight"] is None:
        failures += 1
        lines.append("FAIL missing 'K60 BACKLIGHT: published level ... conformance=1 control=1'")
    else:
        row = found["backlight"]
        lines.append("backlight: level %d dbv 0x%x conformance=%d control=%d" % (
            row["level"], row["dbv"], row["conformance"], row["control"]))
        if row["conformance"] != 1 or row["control"] != 1:
            failures += 1
            lines.append("FAIL backlight conformance/control must both be 1")
        else:
            lines.append("backlight conformance=1 control=1")
        lines.append("NOTE the user must still move the slider through both endpoints")

    if failures:
        return 1, lines
    if unknown:
        return 2, lines
    return 0, lines


def selftest() -> int:
    def healthy() -> str:
        sb = "\n".join("KE 24 26 launchd /System/Library/CoreServices/SpringBoard.app/SpringBoard" for _ in range(100))
        return (
            "K60 PANEL: 120 Hz switch at the first GPU frame\n"
            "K60 PANEL: INTF1 before the switch te 60/s frames 0/s over 200 ms (te 29->41 frames 2724->2724)\n"
            "K60 PANEL: timing switch to 120 Hz: 11 packets, rc 0\n"
            "K60 PANEL: INTF1 after the switch te 121/s frames 3/s over 500 ms (te 20->80 frames 2725->2726)\n"
            "K60 PANEL: INTF1 after the UI frame te 120/s frames 120/s over 500 ms (te 52->112 frames 2955->3015)\n"
            "K60 BACKLIGHT: published level 2047 dbv 0xfff conformance=1 control=1 stats=4,0,2047,2047 req=0,0,1,1\n"
            "K60 DISPLAY: first frame presented (swap 2, 1440x3200 canvas on 1440x3200 panel)\n"
            + sb + "\n")
    cases = [
        ("healthy 120 Hz", healthy(), 0),
        ("old 120hz-3 log: 12/s and no first-frame switch", healthy()
         .replace("K60 PANEL: 120 Hz switch at the first GPU frame\n", "")
         .replace("K60 PANEL: INTF1 after the UI frame te 120/s frames 120/s",
                  "K60 PANEL: INTF1 after the UI frame te 12/s frames 2/s"), 1),
        ("switch but still 12/s", healthy().replace(
            "K60 PANEL: INTF1 after the UI frame te 120/s",
            "K60 PANEL: INTF1 after the UI frame te 12/s"), 1),
        ("no post-UI observation", healthy().replace(
            "K60 PANEL: INTF1 after the UI frame te 120/s frames 120/s over 500 ms (te 52->112 frames 2955->3015)\n", ""), 2),
        ("backlight control missing", healthy().replace(
            "conformance=1 control=1", "conformance=0 control=0"), 1),
        ("DCS failure after switch", healthy().replace(
            "K60 PANEL: timing switch to 120 Hz: 11 packets, rc 0\n",
            "K60 PANEL: timing switch to 120 Hz: 11 packets, rc 0\nK60 PANEL: DCS 0x51 failed: -5\n"), 1),
        ("no panel line", "K60 DISPLAY: first frame presented\n", 2),
    ]
    bad = 0
    for name, text, want in cases:
        status, report = judge(parse(text))
        if status != want:
            bad += 1
            print("FAIL %s: status %d, wanted %d" % (name, status, want))
            for line in report:
                print("     " + line)
        else:
            print("ok   %s -> %d" % (name, status))
    if bad:
        print("%d fixture(s) disagreed" % bad)
        return 1
    print("check-120hz-log: %d fixtures passed" % len(cases))
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    target = None
    for arg in argv[1:]:
        if arg.startswith("--"):
            continue
        target = Path(arg)
        break
    if target is None:
        print("usage: check-120hz-log.py <console.log|dir> [--json]")
        return 2
    found = parse(read_log(target))
    status, report = judge(found)
    if "--json" in argv:
        print(json.dumps({"status": status, "found": found, "report": report}, indent=2))
    else:
        for line in report:
            print(line)
        verdict = {0: "PASS", 1: "FAIL", 2: "INCONCLUSIVE"}[status]
        print("check-120hz-log: %s" % verdict)
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv))
