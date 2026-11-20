#!/usr/bin/env python3
"""Judge the K60 EPSS mode-1 A flight from its console and capture evidence.

Why this exists: docs/research/power/01-EPSS-PROBE.md section 8 defines the
next read-only boot as a fixed acceptance test, but the evidence is a 130-160 KB
console log plus capture.json.  Reading it by eye is exactly where an early
d1/d2 enable=0 snapshot gets mistaken for a failure, or a mode-8 write line is
missed in a log that was supposed to be read-only.  This judge turns the three
A criteria into PASS/FAIL/INVALID and prints the evidence line for each.

Criteria:
  CAPTURE      capture.json complete, bytes matches the file, no panic marker
  MODE1        one mode=1 header, a late read block, d0/d1/d2 all enable=1 with
               limits/cap/rows/top/level, L3 rows=15, and no write lines
  SPRINGBOARD  a launchd SpringBoard launch line

The capture's d1/d2 early-read lines are deliberately ignored: the late read
after the secondary CPUs start is the one the document requires.  The limits
bit2 / cap formula is printed as a NOTE, not counted as a criterion, because
the document keeps it as the interpretation focus for the next write test.

Exit status: 0 PASS, 1 FAIL, 2 INVALID, 4 usage error (never a verdict).
Usage:
    python3 scripts/judge-k60-mode1-console.py <evidence-dir|console.log>
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

HEADER_RE = re.compile(
    r"K60CpuFreq: mode=1 EPSS domains=3 cpus=8 lut-rows=40")
LATE_BEGIN_RE = re.compile(r"K60CpuFreq: late read begin \(mode 1\)")
LATE_END_RE = re.compile(r"K60CpuFreq: late read end")
DOMAIN_RE = re.compile(
    r"K60CpuFreq: d(?P<domain>[0-2]) base=0x[0-9a-fA-F]+ "
    r"enable=(?P<enable>\d+) state=(?P<state>\d+) \((?P<state_khz>\d+)kHz\) "
    r"dcvs=(?P<dcvs>\d+) limits=0x(?P<limits>[0-9a-fA-F]+) "
    r"cap=(?P<cap>\d+)kHz vote=(?P<vote>\d+) pdmem=(?P<pdmem>\d+) "
    r"rows=(?P<rows>\d+) top=(?P<top>\d+)kHz level=(?P<level>\d+) "
    r"mode1=read-only")
LEGACY_DOMAIN_RE = re.compile(
    r"K60CpuFreq: d(?P<domain>[0-2]) base=0x[0-9a-fA-F]+ .*mode1=read-only")
L3_RE = re.compile(
    r"K60CpuFreq: L3 base=0x[0-9a-fA-F]+ vote=(?P<vote>\d+) "
    r"rows=(?P<rows>\d+) top=(?P<top>\d+)kHz level=(?P<level>\d+)")
SPRINGBOARD_RE = re.compile(
    r"(?:KE \d+ \d+ launchd .*SpringBoard|SpringBoard\[)")
WRITE_PATTERNS = [
    ("apply", re.compile(r"K60CpuFreq: mode(?:[23678]|10) apply d[0-2] ")),
    ("vote", re.compile(r"K60CpuFreq: mode(?:[23678]|10) vote (?:d[0-2]|L3) ")),
    ("pdmem", re.compile(r"K60CpuFreq: mode(?:[23678]|10) d[0-2] pdmem=\d+->\d+")),
    ("restore", re.compile(r"K60CpuFreq: mode(?:[23678]|10) restore domains=")),
    ("l3-readback", re.compile(r"K60CpuFreq: mode10 L3 level=.*readback=ok")),
]
X0_KHZ = 19200
LIMITS_BIT = 4


def _criterion(verdict, evidence=None, notes=None):
    return verdict, list(evidence or []), list(notes or [])


def _capture_criterion(capture, on_disk):
    if capture is None:
        return _criterion("INVALID", notes=[
            "capture.json is missing, so capture completion cannot be proven"])
    notes = []
    verdict = "PASS"
    if capture.get("complete") is not True:
        verdict = "FAIL"
        notes.append("capture.json complete is not true (state=%r)" % capture.get("state"))
    declared = capture.get("bytes")
    if not isinstance(declared, int) or declared <= 0:
        verdict = "FAIL"
        notes.append("capture.json bytes is not a positive integer: %r" % (declared,))
    elif declared != on_disk:
        verdict = "FAIL"
        notes.append("capture.json bytes=%d but console.log is %d bytes" % (declared, on_disk))
    panic = capture.get("panicMarker")
    if panic not in (None, ""):
        verdict = "FAIL"
        notes.append("panicMarker=%r" % (panic,))
    if capture.get("state") == "port-not-observed":
        verdict = "FAIL"
        notes.append("capture state is port-not-observed")
    if verdict == "PASS":
        notes.append("complete=true bytes=%d panicMarker=null" % on_disk)
    return _criterion(verdict, notes=notes)


def _late_block(lines):
    begin = None
    for index, line in enumerate(lines):
        if LATE_BEGIN_RE.search(line):
            begin = index
    if begin is None:
        return None, None, "no 'late read begin (mode 1)' line"
    end = None
    for index in range(begin + 1, len(lines)):
        if LATE_END_RE.search(lines[index]):
            end = index
            break
    if end is None:
        return None, None, "late read begin has no matching 'late read end'"
    return begin, end, None


def _cap_formula(limits, state, cap, top):
    if limits & LIMITS_BIT:
        low = state & 0xFF
        expected = top if low == 0 else low * X0_KHZ
        rule = "bit2=set expected=%dkHz (state&0xff=%d * %d)" % (
            expected, low, X0_KHZ)
    else:
        expected = top
        rule = "bit2=clear expected=top=%dkHz" % top
    return expected, rule


def _mode1_criterion(lines):
    evidence = []
    notes = []
    headers = [i + 1 for i, line in enumerate(lines) if HEADER_RE.search(line)]
    if not headers:
        return _criterion("FAIL", notes=["no 'mode=1 EPSS domains=3 cpus=8 lut-rows=40' header"])
    evidence.extend(headers[:1])
    if len(headers) > 1:
        notes.append("mode=1 header appears %d times; judging the last late read" % len(headers))

    begin, end, error = _late_block(lines)
    if error:
        return _criterion("FAIL", evidence, notes + [error])
    evidence.append(begin + 1)
    block = [(i + 1, lines[i]) for i in range(begin + 1, end)]
    verdict = "PASS"

    domains = {}
    legacy = {}
    for number, line in block:
        match = DOMAIN_RE.search(line)
        if match:
            domains[int(match.group("domain"))] = (number, match)
            continue
        old = LEGACY_DOMAIN_RE.search(line)
        if old:
            legacy[int(old.group("domain"))] = (number, line)
    for domain in range(3):
        if domain not in domains:
            verdict = "FAIL"
            if domain in legacy:
                notes.append("d%d line at :%d is the pre-limits format (no limits/cap); "
                             "rebuild with the current probe" % (domain, legacy[domain][0]))
            else:
                notes.append("d%d line is missing or unparsable in the late read" % domain)
            continue
        number, match = domains[domain]
        evidence.append(number)
        enable = int(match.group("enable"))
        state = int(match.group("state"))
        cap = int(match.group("cap"))
        rows = int(match.group("rows"))
        top = int(match.group("top"))
        level = int(match.group("level"))
        limits = int(match.group("limits"), 16)
        if enable != 1:
            verdict = "FAIL"
            notes.append("d%d enable=%d at :%d (late read requires 1)" % (domain, enable, number))
        if enable == 1 and state == 0:
            verdict = "FAIL"
            notes.append("d%d is enabled but state=0 at :%d" % (domain, number))
        if rows <= 0 or top <= 0 or level >= rows:
            verdict = "FAIL"
            notes.append("d%d rows=%d top=%d level=%d at :%d" % (
                domain, rows, top, level, number))
        if cap <= 0 or cap > top:
            verdict = "FAIL"
            notes.append("d%d cap=%d is outside 1..%d at :%d" % (domain, cap, top, number))
        expected, rule = _cap_formula(limits, state, cap, top)
        notes.append("CAP formula: d%d limits=0x%x state=%d %s cap=%d -> %s" % (
            domain, limits, state, rule, cap,
            "match" if cap == expected else "MISMATCH"))
        if cap != expected:
            notes.append("  cap is unconfirmed; do not judge a write test by it until 0x308 ownership is clear")

    l3s = [(number, L3_RE.search(line)) for number, line in block if L3_RE.search(line)]
    if not l3s:
        verdict = "FAIL"
        notes.append("L3 line is missing from the late read")
    else:
        number, match = l3s[-1]
        evidence.append(number)
        rows = int(match.group("rows"))
        top = int(match.group("top"))
        level = int(match.group("level"))
        if rows != 15:
            verdict = "FAIL"
            notes.append("L3 rows=%d at :%d, expected 15" % (rows, number))
        if top <= 0 or level >= rows:
            verdict = "FAIL"
            notes.append("L3 top=%d level=%d rows=%d at :%d" % (top, level, rows, number))

    seen_writes = []
    for name, pattern in WRITE_PATTERNS:
        for index, line in enumerate(lines):
            if pattern.search(line):
                seen_writes.append((name, index + 1, line.strip()))
                break
    if seen_writes:
        verdict = "FAIL"
        for name, number, line in seen_writes:
            evidence.append(number)
            notes.append("write line %s at :%d: %s" % (name, number, line))

    if verdict == "PASS":
        notes.append("three domains enable=1 after the late read, L3 rows=15, no write lines")
    return _criterion(verdict, evidence, notes)


def _springboard_criterion(lines):
    hits = [i + 1 for i, line in enumerate(lines) if SPRINGBOARD_RE.search(line)]
    if not hits:
        return _criterion("FAIL", notes=["no launchd SpringBoard launch line"])
    return _criterion("PASS", hits[:1], ["SpringBoard launch line present"])


def _print_criteria(results):
    for name, (verdict, evidence, notes) in results:
        where = ", ".join(":%d" % n for n in evidence) if evidence else "none"
        print("%s : %s (evidence %s)" % (name, verdict, where))
        for note in notes:
            print("  - " + note)


class _ArgumentParser(argparse.ArgumentParser):
    """argparse exits 2 for a usage error, but 2 means INVALID here.

    A typo in a flag would then be indistinguishable from "the capture carried
    nothing to judge", which is the one distinction this exit table exists for.
    """

    def error(self, message):
        self.print_usage(sys.stderr)
        print("%s: error: %s" % (self.prog, message), file=sys.stderr)
        raise SystemExit(4)

def main():
    parser = _ArgumentParser(
        description="Judge the K60 EPSS mode-1 A flight from console and capture evidence.")
    parser.add_argument("target", nargs="?",
                        help="evidence directory or console.log path")
    parser.add_argument("--log", help="console.log path (alternative to target)")
    args = parser.parse_args()
    target = args.log or args.target
    if not target:
        parser.print_usage(sys.stderr)
        print("k60-mode1: no evidence path", file=sys.stderr)
        return 4

    path = pathlib.Path(target)
    if path.is_dir():
        log_path = path / "console.log"
        capture_path = path / "capture.json"
    else:
        log_path = path
        capture_path = path.with_name("capture.json")
    if not log_path.is_file():
        print("k60-mode1: no console.log at %s -- INVALID, not a usage error" % log_path, file=sys.stderr)
        return 2

    data = log_path.read_bytes()
    text = data.decode("utf-8", "replace")
    lines = text.splitlines()
    capture = None
    capture_error = None
    if capture_path.is_file():
        try:
            capture = json.loads(capture_path.read_text(
                encoding="utf-8-sig", errors="replace"))
        except (OSError, ValueError) as error:
            capture_error = str(error)

    if capture_error:
        capture_result = _criterion("INVALID", notes=["capture.json is unreadable: %s" % capture_error])
    else:
        capture_result = _capture_criterion(capture, len(data))
    results = [
        ("CAPTURE", capture_result),
        ("MODE1", _mode1_criterion(lines)),
        ("SPRINGBOARD", _springboard_criterion(lines)),
    ]
    evaluated = [result[0] for _name, result in results]
    if "FAIL" in evaluated:
        verdict, code = "FAIL", 1
    elif "INVALID" in evaluated:
        verdict, code = "INVALID", 2
    else:
        verdict, code = "PASS", 0

    print("k60-mode1: %s (mode-1 A) (%s, %d bytes on disk) [exit %d]" % (
        verdict, log_path.name, len(data), code))
    _print_criteria(results)
    print("TOTAL: %d PASS / %d FAIL / %d INVALID" % (
        evaluated.count("PASS"), evaluated.count("FAIL"), evaluated.count("INVALID")))
    return code


if __name__ == "__main__":
    sys.exit(main())
