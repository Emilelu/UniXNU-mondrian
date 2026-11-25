#!/usr/bin/env python3
"""A lane's report must say how it reached the Lead.

Iron rule 12 says: try `steer` first, fall back to `followup` only when steer is
rejected.  Nothing checked that, so on 2026-11-21 two lanes reported arriving by
`followup` with no evidence that steer had been tried at all.

A log we do not control cannot prove intent, but every lane already writes a
reply markdown.  So the marker lives there, on the first non-empty line:

    delivery: steer
    delivery: followup, steer-rejected: 目标当前离线

Missing marker, unknown value, or a followup without a rejection reason all fail.
Exit codes: 0 every report declares a lawful delivery, 1 problems, 2 no reports.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
DEFAULT_DIR = Path("/mnt/e/iOS Port/Work/scratch")

# Reports written before the marker existed cannot declare it.  They are reported
# as notes instead of failures, and the cutoff is a constant so the exemption
# cannot grow with the calendar.
GRANDFATHER = datetime(2026, 11, 21, 15, 0, 0).timestamp()

LINE = re.compile(r"^delivery:\s*(steer|followup)\s*(?:,\s*steer-rejected:\s*(.+))?$")
REJECTED = re.compile(r"steer-rejected:\s*\S")


def first_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip().strip("`")
        if stripped:
            return stripped
    return ""


def check(reports: dict[str, str], mtimes: dict[str, float] | None = None) -> list[str]:
    problems: list[str] = []
    for name, text in sorted(reports.items()):
        if mtimes and mtimes.get(name, 0) < GRANDFATHER:
            continue
        line = first_line(text)
        match = LINE.match(line)
        if not match:
            problems.append(f"{name}: first line is not `delivery: steer` or `delivery: followup, steer-rejected: …` (has {line[:60]!r})")
            continue
        mode, reason = match.group(1), match.group(2)
        if mode == "followup" and not (reason and REJECTED.search(line)):
            problems.append(f"{name}: followup without a rejection reason; iron-12 asks for steer first")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--pattern", default="reply-*-20261*.md")
    arguments = parser.parse_args(argv)
    if not arguments.dir.is_dir():
        print(f"GATE UNKNOWN: no reply directory at {arguments.dir} (P-279)")
        return 2
    reports: dict[str, str] = {}
    mtimes: dict[str, float] = {}
    for path in sorted(arguments.dir.glob(arguments.pattern)):
        try:
            reports[path.name] = path.read_text(encoding="utf-8", errors="replace")
            mtimes[path.name] = path.stat().st_mtime
        except OSError as error:
            print(f"note: cannot read {path.name}: {error}")
    old = sorted(name for name, when in mtimes.items() if when < GRANDFATHER)
    if old:
        print(f"note: {len(old)} report(s) predate the marker and were not judged")
    if not reports:
        print(f"GATE UNKNOWN: no reports matched {arguments.pattern} in {arguments.dir}")
        return 2
    problems = check(reports, mtimes)
    for problem in problems:
        print(f"FAIL: {problem}")
    if problems:
        print(f"FAIL delivery: {len(problems)} report(s) do not declare a lawful delivery")
        return 1
    print(f"OK delivery: {len(reports)} report(s) declare steer-first")
    return 0


if __name__ == "__main__":
    sys.exit(main())
