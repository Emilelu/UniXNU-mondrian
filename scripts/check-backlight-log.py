#!/usr/bin/env python3
"""Judge a K60 console log against the brightness service criteria.

Why this exists: brightness-9 and brightness-10 differ by one kernel argument,
and the question they answer is whether publishing backlight-control is what
made backboardd crash on brightness-4 (int-236).  Reading that out of a raw
console log by hand invites the wrong answer, because the same log carries a
"published level" line in three different shapes across builds, the counters
are printed only when a debugger asks, and a crash shows up as "sig=11" far
away from the backlight lines.

The criteria are the ones written down in
docs/research/display/HANDOFF-20261114.md and STATS-INDEX.md:

  control=0 (the default image)
    1. the service published a level,
    2. it did NOT claim backlight-control (and, when the build prints it,
       conformance=0),
    3. native_backlight_stats[0] == 3 (4 means it published as
       AppleARMBacklight) and native_backlight_request[4]/[5] are 0,
    4. backboardd did not take a SIGSEGV (sig=11 count 0),
    5. the first frame was presented.

  control=1 (kernel argument k60_backlight_control=1)
    same, but conformance/control must be 1 and stats[0] must be 4.  A log
    without those fields is a FAIL here, not a warning: no pre-gate build could
    have published control, so the two disagree means the wrong image flew.

brightness-13 onwards print the counters inside the published line
("stats=stage,requests,level,readback req=goal,ms,conformance,control"), so the
verdict no longer needs a debugger.  A log without them is therefore a FAIL on
any image built from brightness-13 on: the image is older than its label claims.
brightness-9 is deliberately kept as the old-form comparison and is judged with
--old-form, which downgrades the missing counters to a warning again.

brightness-17 onwards also print one line per CoreBrightness request:

    K60 BACKLIGHT: brightness level 1024 -> level 1024 dbv 0x80a
    K60 BACKLIGHT: brightness-nits 0.00000 -> level 0 dbv 0x0

Pass --min-dbv and --max-dbv to judge the 12-bit range from those lines.  The
bounds are checked over requests whose DBV is non-zero, so the startup
brightness-nits 0 request (panel off) does not count as the dimmest point.
Missing requests are a FAIL in that mode: the publication layer passing does
not prove a user ever moved the slider.

Exit status: 0 pass, 1 fail, 2 the log does not carry the verdict (no
backlight line at all, or an old-form log whose counters are absent).

Usage:
    python3 scripts/check-backlight-log.py <console.log|evidence dir> [--control=1] [--old-form] [--json]
    python3 scripts/check-backlight-log.py <console.log|evidence dir> --min-dbv=0x14 --max-dbv=0xfff
    python3 scripts/check-backlight-log.py --selftest
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PUBLISHED = re.compile(
    r"K60 BACKLIGHT: published level (\d+) dbv 0x([0-9a-fA-F]+)"
    r"(?: conformance=(\d+))?(?: control=(\d+))?")
CONFORMANCE = re.compile(
    r"K60 BACKLIGHT: conformance AppleARMBacklight=(\d+) control=(\d+)")
COUNTER = re.compile(r"(?:native_)?(backlight_stats|backlight_request)\[(\d+)\]\s*[=:]\s*(-?\d+)")
# brightness-13 and later: counters carried inside the published line, so one
# grep of the log is the whole evidence.
INLINE = re.compile(
    r"stats=(-?\d+),(-?\d+),(-?\d+),(-?\d+)"
    r" req=(-?\d+),(-?\d+),(-?\d+),(-?\d+)")
SIGSEGV = re.compile(r"sig=11|SIGSEGV|signal 11")
REQUEST = re.compile(
    r"K60 BACKLIGHT: brightness(?:-nits)?[^\n]*?-> level (\d+) dbv 0x([0-9a-fA-F]+)")


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
    found = {"level": None, "dbv": None, "conformance": None, "control": None,
             "stats": {}, "request": {}, "sig11": 0, "first_frame": False,
             "springboard": 0, "lines": text.count("\n") + 1, "inline": False,
             "brightness_requests": []}
    match = PUBLISHED.search(text)
    if match:
        found["level"] = int(match.group(1))
        found["dbv"] = int(match.group(2), 16)
        # brightness-4 printed "... dbv 0xff control 1" with no conformance field.
        if match.group(3) is not None:
            found["conformance"] = int(match.group(3))
            found["control"] = int(match.group(4) or 0)
        elif match.group(4) is not None:
            found["control"] = int(match.group(4))
    separate = CONFORMANCE.search(text)
    if separate:
        found["conformance"] = int(separate.group(1))
        found["control"] = int(separate.group(2))
    inline = INLINE.search(text)
    if inline:
        values = [int(v) for v in inline.groups()]
        found["stats"].update({0: values[0], 1: values[1], 2: values[2], 3: values[3]})
        found["request"].update({0: values[4], 1: values[5], 4: values[6], 5: values[7]})
        found["inline"] = True
    for kind, index, value in COUNTER.findall(text):
        bucket = "stats" if kind == "backlight_stats" else "request"
        found[bucket][int(index)] = int(value)
    found["brightness_requests"] = [
        (int(level), int(dbv, 16)) for level, dbv in REQUEST.findall(text)]
    found["sig11"] = len(SIGSEGV.findall(text))
    found["first_frame"] = "first frame presented" in text
    found["springboard"] = sum(1 for line in text.splitlines() if "SpringBoard" in line)
    return found


def judge(found: dict, expect: int, old_form: bool = False,
          min_dbv: int | None = None, max_dbv: int | None = None) -> tuple[int, list[str]]:
    """Return (exit status, report lines).

    old_form marks a pre-brightness-13 log (brightness-9 is kept as the old-form
    comparison image), where the counters were never printed.  Every later image
    carries them in the published line, so there their absence means the log is
    older than the image claims - a failure, not an unknown.
    """
    lines: list[str] = []
    failures = 0
    unknown = 0
    if found["level"] is None:
        return 2, ["FAIL the log carries no 'K60 BACKLIGHT: published level' line",
                   "     -> the service never ran; check boot-arg k60_backlight and",
                   "        whether pong_panel_bringup() succeeded"]
    lines.append("service published level %d at dbv 0x%02x" % (found["level"], found["dbv"]))
    control = found["control"]
    conformance = found["conformance"]
    if control is None:
        # A log without the field comes from a build that predates the gate, and
        # no such build can carry k60_backlight_control=1. Judging it as control=1
        # therefore means the wrong image was flown, which is a failure, not an
        # unknown. On the default image the same absence is only a warning.
        if expect:
            failures += 1
            lines.append("FAIL no control field, but this image claims control=1: "
                         "the log is from an older build (wrong image?)")
        else:
            lines.append("WARN the published line has no control field (older build)")
            unknown += 1
    elif control != expect:
        failures += 1
        lines.append("FAIL control=%d but this image should publish control=%d" % (control, expect))
    else:
        lines.append("control=%d as expected" % control)
    if conformance is None:
        if expect:
            failures += 1
            lines.append("FAIL no conformance field, but this image claims control=1: "
                         "an older build cannot have published it")
        else:
            lines.append("WARN no conformance field: rebuild, brightness-9 and later print it")
            unknown += 1
    elif conformance != expect:
        failures += 1
        lines.append("FAIL conformance=%d, expected %d" % (conformance, expect))
    else:
        lines.append("conformance=%d as expected" % conformance)

    stage = found["stats"].get(0)
    want_stage = 4 if expect else 3
    if stage is None:
        if old_form:
            lines.append("WARN old-form log: no counters printed (brightness-9 shape)")
            unknown += 1
        else:
            failures += 1
            lines.append("FAIL the published line carries no counters: brightness-13 and "
                         "later print stats=/req=, so this log is from an older image")
    elif stage != want_stage:
        failures += 1
        lines.append("FAIL stats[0]=%d, expected %d (see STATS-INDEX.md)" % (stage, want_stage))
    else:
        lines.append("stats[0]=%d as expected" % stage)

    for index in (4, 5):
        value = found["request"].get(index)
        if value is None:
            continue
        if value != expect:
            failures += 1
            lines.append("FAIL request[%d]=%d, expected %d" % (index, value, expect))
        else:
            lines.append("request[%d]=%d as expected" % (index, value))

    if found["sig11"]:
        failures += 1
        lines.append("FAIL backboardd took %d SIGSEGV (sig=11) - int-236 shape"
                     % found["sig11"])
    else:
        lines.append("no SIGSEGV in the log")

    if not found["first_frame"]:
        failures += 1
        lines.append("FAIL 'first frame presented' never appeared")
    else:
        lines.append("first frame presented")

    if min_dbv is not None or max_dbv is not None:
        requests = [(level, dbv) for level, dbv in found["brightness_requests"] if dbv > 0]
        if len(requests) < 3:
            failures += 1
            lines.append("FAIL only %d non-zero brightness request line(s); "
                         "the 12-bit range test needs at least 3" % len(requests))
        else:
            observed = [dbv for _, dbv in requests]
            lo, hi = min(observed), max(observed)
            if min_dbv is not None and lo != min_dbv:
                failures += 1
                lines.append("FAIL dimmest request reached dbv 0x%x, expected 0x%x"
                             % (lo, min_dbv))
            elif min_dbv is not None:
                lines.append("dimmest request reached dbv 0x%x as expected" % lo)
            if max_dbv is not None and hi != max_dbv:
                failures += 1
                lines.append("FAIL brightest request reached dbv 0x%x, expected 0x%x"
                             % (hi, max_dbv))
            elif max_dbv is not None:
                lines.append("brightest request reached dbv 0x%x as expected" % hi)

    lines.append("SpringBoard lines: %d" % found["springboard"])
    if failures:
        return 1, lines
    if unknown:
        return 2, lines
    return 0, lines


def selftest() -> int:
    """Fixtures shaped like the logs already on disk."""
    cases = [
        ("brightness-13 default, healthy",
         "K60 BACKLIGHT: published level 2047 dbv 0xff conformance=0 control=0"
         " stats=3,0,2047,255 req=0,0,0,0 (no AppleARMBacklight conformance)\n"
         "K60 DISPLAY: first frame presented\n"
         "KE 24 26 launchd /System/Library/CoreServices/SpringBoard.app/SpringBoard\n"
         "K60RV 2 SpringBoard[26] mem=4608\n",
         0, 0, False),
        ("brightness-4: control published, backboardd crashed, no frame",
         "K60 BACKLIGHT: published level 2047 dbv 0xff control 1\n"
         "backboardd[55] exited: sig=11\n"
         "backboardd[55] exited: sig=11\n"
         "KE 24 26 launchd /System/Library/CoreServices/SpringBoard.app/SpringBoard\n",
         1, 0, True),
        ("brightness-14 with conformance, crashed",
         "K60 BACKLIGHT: published level 2047 dbv 0xff conformance=1 control=1"
         " stats=4,0,2047,255 req=0,0,1,1\n"
         "backboardd[55] exited: sig=11\n"
         "K60 DISPLAY: first frame presented\n",
         1, 1, False),
        ("brightness-14 that passed",
         "K60 BACKLIGHT: published level 1200 dbv 0x78 conformance=1 control=1"
         " stats=4,0,1200,120 req=0,0,1,1\n"
         "K60 DISPLAY: first frame presented\n",
         0, 1, False),
        ("service never ran", "K60 PANEL: bring-up complete (0x11/0x29/0x51)\n", 2, 0, False),
        ("brightness-9 old form, healthy but counters absent",
         "K60 BACKLIGHT: published level 2047 dbv 0xff conformance=0 control=0"
         " (no AppleARMBacklight conformance)\n"
         "K60 DISPLAY: first frame presented\n", 2, 0, True),
        ("brightness-13 log whose counters are missing",
         "K60 BACKLIGHT: published level 2047 dbv 0xff conformance=0 control=0\n"
         "K60 DISPLAY: first frame presented\n", 1, 0, False),
        ("control=1 image judged against an old build log",
         "K60 BACKLIGHT: published level 2047 dbv 0xff control 1\n"
         "K60 DISPLAY: first frame presented\n",
         1, 1, True),
        ("inline counters say stage 4 on a control=0 image",
         "K60 BACKLIGHT: published level 2047 dbv 0xff conformance=0 control=0"
         " stats=4,0,2047,255 req=0,0,0,0\n"
         "K60 DISPLAY: first frame presented\n", 1, 0, False),
        ("inline counters say control was published on a control=0 image",
         "K60 BACKLIGHT: published level 2047 dbv 0xff conformance=0 control=0"
         " stats=3,0,2047,255 req=0,0,0,1\n"
         "K60 DISPLAY: first frame presented\n", 1, 0, False),
    ]
    bad = 0
    for name, text, want, expect, old_form in cases:
        status, report = judge(parse(text), expect, old_form)
        if status != want:
            bad += 1
            print("FAIL %s: status %d, wanted %d" % (name, status, want))
            for line in report:
                print("     " + line)
        else:
            print("ok   %s -> %d" % (name, status))
    range_cases = [
        ("12-bit range reaches 0x14 and 0xfff",
         "K60 BACKLIGHT: published level 2047 dbv 0xfff conformance=1 control=1"
         " stats=4,0,2047,2047 req=0,0,1,1\n"
         "K60 BACKLIGHT: brightness level 2047 -> level 2047 dbv 0xfff\n"
         "K60 BACKLIGHT: brightness level 1024 -> level 1024 dbv 0x80a\n"
         "K60 BACKLIGHT: brightness level 1 -> level 1 dbv 0x14\n"
         "K60 DISPLAY: first frame presented\n",
         0),
        ("12-bit range bottom stayed at 0x1",
         "K60 BACKLIGHT: published level 2047 dbv 0xfff conformance=1 control=1"
         " stats=4,0,2047,2047 req=0,0,1,1\n"
         "K60 BACKLIGHT: brightness level 2047 -> level 2047 dbv 0xfff\n"
         "K60 BACKLIGHT: brightness level 1024 -> level 1024 dbv 0x80a\n"
         "K60 BACKLIGHT: brightness level 1 -> level 1 dbv 0x1\n"
         "K60 DISPLAY: first frame presented\n",
         1),
        ("12-bit range has no user requests",
         "K60 BACKLIGHT: published level 2047 dbv 0xfff conformance=1 control=1"
         " stats=4,0,2047,2047 req=0,0,1,1\n"
         "K60 DISPLAY: first frame presented\n",
         1),
    ]
    for name, text, want in range_cases:
        status, report = judge(parse(text), 1, False, 0x14, 0xfff)
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
    print("check-backlight-log: %d fixtures passed" % (len(cases) + len(range_cases)))
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    expect = 0
    if "--control=1" in argv or "--expect-control=1" in argv:
        expect = 1
    old_form = "--old-form" in argv
    min_dbv = None
    max_dbv = None
    for arg in argv[1:]:
        if arg.startswith("--min-dbv="):
            min_dbv = int(arg.split("=", 1)[1], 0)
        elif arg.startswith("--max-dbv="):
            max_dbv = int(arg.split("=", 1)[1], 0)
    target = None
    for arg in argv[1:]:
        if arg.startswith("--"):
            continue
        target = Path(arg)
        break
    if target is None:
        print("usage: check-backlight-log.py <console.log|dir> [--control=1] [--old-form] [--json] [--min-dbv=0x14 --max-dbv=0xfff]")
        return 2
    found = parse(read_log(target))
    status, report = judge(found, expect, old_form, min_dbv, max_dbv)
    if "--json" in argv:
        print(json.dumps({"status": status, "found": found, "report": report}, indent=2))
    else:
        for line in report:
            print(line)
        verdict = {0: "PASS", 1: "FAIL", 2: "INCONCLUSIVE"}[status]
        print("check-backlight-log: %s (control=%d image)" % (verdict, expect))
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv))
