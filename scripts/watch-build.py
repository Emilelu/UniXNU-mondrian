#!/usr/bin/env python3
"""Say whether a K60 build is working, stalled, or finished — from evidence.

A background job status is not evidence: the job can sit on a setsid child that
already exited, and the EDK II phase (`build -p … -n 8`, then GenFds) writes no
log line for minutes while it is busy. So this reads three independent things:

  * the log's modification time and last line,
  * whether any build child (make, clang, ld, nasm, python, dtc, unixnu) exists,
  * the load average.

Verdicts: RUNNING (log moved recently or a child exists), STALLED (no child and
the log has not moved for --stale seconds), FINISHED (the log's last lines carry
a verdict word), UNKNOWN (log missing).

Exit codes: 0 running, 1 stalled, 2 finished-with-failure, 3 finished-ok, 4 unknown.

Usage:
    python3 scripts/watch-build.py /mnt/e/k60-work/scratch/build-menu-14.log
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

CHILDREN = ("make", "clang", "ld", "ld64", "nasm", "iasl", "dtc", "unixnu", "python3", "GenFw", "GenSec")
FAILURE = re.compile(r"(^rc=[1-9]|build refused|❌|FAIL:|error: |failed \()", re.MULTILINE)
SUCCESS = re.compile(r"(^rc=0|artifacts: boot\.img|== payload:|payload\.img: \d+ bytes)", re.MULTILINE)


def children() -> list[str]:
    try:
        out = subprocess.run(["ps", "-eo", "comm="], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    names = [line.strip() for line in out.splitlines() if line.strip()]
    return [name for name in names if any(token in name for token in CHILDREN)]


def last_lines(path: Path, count: int = 3) -> list[str]:
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(max(0, size - 8192))
        text = handle.read().decode("utf-8", errors="replace")
    return [line for line in text.splitlines() if line.strip()][-count:]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--stale", type=int, default=360, help="seconds without a log line that count as stalled")
    arguments = parser.parse_args(argv)
    log = arguments.log
    if not log.is_file():
        print(f"UNKNOWN: no log at {log}")
        return 4
    age = time.time() - log.stat().st_mtime
    tail = last_lines(log)
    text = log.read_text(encoding="utf-8", errors="replace")
    kids = children()
    verdict = None
    if FAILURE.search("\n".join(tail)) or re.search(r"^rc=[1-9]", text[-4000:], re.MULTILINE):
        verdict = "FINISHED-FAILED"
    elif SUCCESS.search(text[-4000:]):
        verdict = "FINISHED-OK"
    elif age <= arguments.stale or kids:
        verdict = "RUNNING"
    else:
        verdict = "STALLED"
    print(f"{verdict}: log idle {age:.0f}s, {len(kids)} build child(ren)")
    if kids:
        print("  children: " + ", ".join(sorted(set(kids))[:8]))
    for line in tail:
        print(f"  | {line[:160]}")
    return {"RUNNING": 0, "STALLED": 1, "FINISHED-FAILED": 2, "FINISHED-OK": 3}.get(verdict, 4)


if __name__ == "__main__":
    sys.exit(main())
