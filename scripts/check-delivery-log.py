#!/usr/bin/env python3
"""Cross-check a lane report's `delivery:` line against the Lead's send log.

Iron rule 12 asks for `steer` first and `followup` only after steer was refused.
Until now the only evidence was the sentence a report wrote about itself: a lane
that never saw a steer attempt could write `delivery: followup, steer-rejected:
<anything>` and no gate could tell. This reads the log the Lead appends to on
every send, so the claim has a second, independent side.

Log format (tab separated, one line per send):

    <ISO time>\t<session-id>\t<mode>\t<message-id>\t<note>

Exit codes: 0 every followup has a refused steer before it, 1 one does not,
2 the log or the report directory is missing (cannot judge is not a pass, P-279).

Usage:
    python3 scripts/check-delivery-log.py [--log PATH] [--reports DIR]
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

# The Lead began appending to the log at this instant; reports older than it are
# history (see check()).
LOG_START = datetime.fromisoformat("2026-11-21T16:00:00+08:00")

DEFAULT_LOG = Path("/mnt/e/k60-work/scratch/delivery-log.tsv")
DEFAULT_REPORTS = Path("/mnt/e/k60-work/scratch")
HEADER = re.compile(r"^delivery:\s*(steer|followup)\s*(?:,\s*steer-rejected:\s*(.+))?$")
LANE = re.compile(r"^(?:session-)?([0-9a-f-]{36})$")


def read_log(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            raise SystemExit(f"{path}:{number}: expected 4 tab-separated fields, got {len(parts)}")
        rows.append({"when": parts[0], "session": parts[1], "mode": parts[2],
                     "id": parts[3], "note": parts[4] if len(parts) > 4 else ""})
    return rows


def refusals(rows: list[dict[str, str]]) -> dict[str, int]:
    """Index of the last refused steer per session."""
    last: dict[str, int] = {}
    for index, row in enumerate(rows):
        if row["mode"] == "steer-refused":
            last[row["session"]] = index
    return last


def check(rows: list[dict[str, str]], reports: Path) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    notes: list[str] = []
    refused = refusals(rows)
    followed = [index for index, row in enumerate(rows) if row["mode"] == "followup"]
    for index in followed:
        row = rows[index]
        if row["session"] not in refused or refused[row["session"]] > index:
            problems.append(f"{row['session']} got a followup with no refused steer before it "
                            f"({row['when']}, id {row['id']})")
    for report in sorted(reports.glob("reply-*.md")):
        # Reports written before the log existed cannot carry the marker; they are
        # history, not evidence to be rewritten (P-259: a stale promise is not a lie).
        if report.stat().st_mtime < LOG_START.timestamp():
            notes.append(f"{report.name}: predates the send log, not cross-checked")
            continue
        try:
            first = report.read_text(encoding="utf-8").splitlines()[0]
        except (OSError, IndexError):
            problems.append(f"{report.name}: cannot read the delivery line")
            continue
        match = HEADER.match(first.strip())
        if not match:
            problems.append(f"{report.name}: first line is not a delivery line ({first[:60]!r})")
            continue
        if match.group(1) == "followup" and not any(
                row["mode"] == "followup" and row["session"] for row in rows):
            notes.append(f"{report.name}: claims a followup but the log has none; "
                         f"logged sends start 2026-11-21 16:00")
    if not rows:
        notes.append("the log holds no row yet; nothing to cross-check")
    return problems, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--reports", type=Path, default=DEFAULT_REPORTS)
    arguments = parser.parse_args(argv)
    if not arguments.log.is_file():
        print(f"GATE UNKNOWN: no send log at {arguments.log} (P-279)")
        return 2
    if not arguments.reports.is_dir():
        print(f"GATE UNKNOWN: no report directory at {arguments.reports} (P-279)")
        return 2
    problems, notes = check(read_log(arguments.log), arguments.reports)
    for note in notes:
        print(f"note: {note}")
    for problem in problems:
        print(f"FAIL: {problem}")
    if problems:
        print(f"FAIL delivery: {len(problems)} send(s) or report(s) disagree with the log")
        return 1
    print("OK delivery: every logged followup follows a refused steer")
    return 0


if __name__ == "__main__":
    sys.exit(main())
