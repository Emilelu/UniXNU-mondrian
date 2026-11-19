#!/usr/bin/env python3
"""Unit tests for scripts/judge-k60-mode1-console.py.

The cases pin the shapes that decide the read-only A flight: the late read, not
the early d1/d2 enable=0 snapshot; three enabled domains with limits/cap; L3
rows=15; no write lines; SpringBoard; and a complete capture.  A healthy flight
must be PASS even when the limits cap formula is unconfirmed, because the
document treats that as the interpretation focus for the next write test.

Run: python3 scripts/tests/test-judge-k60-mode1-console.py
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
JUDGE = ROOT / "scripts" / "judge-k60-mode1-console.py"
SPRINGBOARD = "KE 24 26 launchd /System/Library/CoreServices/SpringBoard.app/SpringBoard\n"


def domain(dom, enable=1, state=81, limits=0x4, cap=None, rows=14,
           top=1804800, level=13, dcvs=0, vote=11, pdmem=5):
    if cap is None:
        low = state & 0xFF
        cap = top if (limits & 4) == 0 or low == 0 else low * 19200
    return (
        f"K60CpuFreq: d{dom} base=0x17d9{dom}000 enable={enable} state={state} "
        f"({state * 19200}kHz) dcvs={dcvs} limits=0x{limits:x} cap={cap}kHz "
        f"vote={vote} pdmem={pdmem} rows={rows} top={top}kHz level={level} "
        f"mode1=read-only\n")


def l3(rows=15, top=1708800, level=14, vote=13):
    return (f"K60CpuFreq: L3 base=0x17d90000 vote={vote} rows={rows} "
            f"top={top}kHz level={level}\n")


def healthy(limits=0x4, cap0=None, cap1=None, cap2=None):
    early = (domain(0) + domain(1, enable=0, state=0, level=0, vote=0)
             + domain(2, enable=0, state=0, level=0, vote=0))
    late = ("K60CpuFreq: late read begin (mode 1)\n"
            + domain(0, limits=limits, cap=cap0)
            + domain(1, state=33, limits=limits, cap=cap1, rows=17,
                     top=2496000, level=16, vote=16)
            + domain(2, state=41, limits=limits, cap=cap2, rows=20,
                     top=2995200, level=19, vote=19)
            + l3() + "K60CpuFreq: late read end\n")
    return ("K60CpuFreq: mode=1 EPSS domains=3 cpus=8 lut-rows=40\n"
            + early + late + SPRINGBOARD)


def write_case(root, name, text, complete=True, panic=None, bytes_delta=0,
               capture=True, bom=False):
    directory = root / name
    directory.mkdir()
    log = directory / "console.log"
    log.write_text(text, encoding="utf-8", newline="")
    if capture:
        payload = {
            "state": "captured-budget-complete" if complete else "port-not-observed",
            "complete": complete,
            "bytes": log.stat().st_size + bytes_delta,
            "panicMarker": panic,
        }
        (directory / "capture.json").write_text(
            ("\ufeff" if bom else "") + json.dumps(payload), encoding="utf-8")
    return directory


def run(path, *extra):
    proc = subprocess.run(
        [sys.executable, str(JUDGE), str(path), *extra],
        capture_output=True, text=True)
    tail = [line for line in (proc.stdout or "").strip().splitlines() if line.strip()]
    return proc.returncode, proc.stdout or "", (tail[-1] if tail else "")


def main():
    failures = 0
    cases = 0
    root = pathlib.Path(tempfile.mkdtemp())

    def check(label, path, want_rc, words, want_note=None):
        nonlocal failures, cases
        cases += 1
        rc, out, last = run(path)
        problems = []
        if rc != want_rc:
            problems.append("rc=%d want=%d" % (rc, want_rc))
        if "[exit %d]" % want_rc not in out:
            problems.append("exit line does not carry [exit %d]" % want_rc)
        for word in words:
            if word not in out:
                problems.append("missing %r" % word)
        if want_note and want_note not in out:
            problems.append("missing note %r" % want_note)
        if not last.startswith("TOTAL: "):
            problems.append("last line is not TOTAL: %r" % last)
        ok = not problems
        print(("PASS " if ok else "FAIL ") + label)
        if not ok:
            failures += 1
            for problem in problems:
                print("      " + problem)
            for line in out.splitlines():
                print("      " + line)

    check("healthy late read with bit2 cap is PASS",
          write_case(root, "healthy", healthy()), 0,
          ["CAPTURE : PASS", "MODE1 : PASS", "SPRINGBOARD : PASS",
           "TOTAL: 3 PASS / 0 FAIL / 0 INVALID"])

    check("bit2 clear with cap equal to top is PASS",
          write_case(root, "clear", healthy(limits=0x0)), 0,
          ["MODE1 : PASS", "bit2=clear expected=top"])

    check("early-only d1/d2 enable=0 is a late-read failure",
          write_case(root, "early", healthy().replace(
              "K60CpuFreq: late read begin (mode 1)\n", "")
              .replace("K60CpuFreq: late read end\n", "")), 1,
          ["MODE1 : FAIL", "no 'late read begin"])

    check("late d1 still enable=0 is FAIL",
          write_case(root, "late-d1", healthy().replace(
              domain(1, state=33, limits=0x4, rows=17, top=2496000, level=16,
                     vote=16), domain(1, enable=0, state=0, limits=0x4,
                                      rows=17, top=2496000, level=16, vote=0))),
          1, ["MODE1 : FAIL", "d1 enable=0"])

    check("L3 rows other than 15 is FAIL",
          write_case(root, "l3", healthy().replace(l3(), l3(rows=14))), 1,
          ["MODE1 : FAIL", "L3 rows=14"])

    check("a mode-8 apply line is FAIL on a read-only flight",
          write_case(root, "write", healthy()
                     + "K60CpuFreq: mode8 apply d0 level=13 (1804800kHz) readback=ok\n"),
          1, ["MODE1 : FAIL", "write line apply"])

    check("missing SpringBoard is FAIL",
          write_case(root, "nosb", healthy().replace(SPRINGBOARD, "")), 1,
          ["SPRINGBOARD : FAIL"])

    check("panic marker is FAIL",
          write_case(root, "panic", healthy(), panic="panic"), 1,
          ["CAPTURE : FAIL", "panicMarker"])

    check("incomplete capture is FAIL",
          write_case(root, "incomplete", healthy(), complete=False), 1,
          ["CAPTURE : FAIL", "complete is not true"])

    check("byte count mismatch is FAIL",
          write_case(root, "bytes", healthy(), bytes_delta=1), 1,
          ["CAPTURE : FAIL", "bytes="])

    check("a UTF-8 BOM on capture.json is accepted",
          write_case(root, "bom", healthy(), bom=True), 0,
          ["CAPTURE : PASS", "TOTAL: 3 PASS / 0 FAIL / 0 INVALID"])

    check("missing capture.json is INVALID, never PASS",
          write_case(root, "nocapture", healthy(), capture=False), 2,
          ["CAPTURE : INVALID", "capture.json is missing"])

    check("a cap formula mismatch is a NOTE, not a flight failure",
          write_case(root, "capnote", healthy(cap0=1555200 + 19200)), 0,
          ["MODE1 : PASS", "MISMATCH"])

    cases += 1
    proc = subprocess.run([sys.executable, str(JUDGE)], capture_output=True, text=True)
    if proc.returncode != 4 or "no evidence path" not in (proc.stderr or ""):
        failures += 1
        print("FAIL no-argument call exits 4")
        print("      rc=%d stderr=%r" % (proc.returncode, proc.stderr))
    else:
        print("PASS no-argument call exits 4")

    print("TESTS OK %d cases, %d failures" % (cases, failures))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
