#!/usr/bin/env python3
"""Run the W1 LUN judge from a build preflight without making absence fatal.

W1 needs a read-only capture from a running Android/device, so a fresh tree
cannot have the evidence yet.  A preflight that exits non-zero for that state
is permanently red, and a permanently red gate is ignored.  The judge keeps its
three-state CLI (0 PASS, 2 PENDING, 1 FAIL); this wrapper maps PENDING to 0 and
leaves only a contradictory or malformed capture as a build failure.

This is the in-line build preflight entry.  It only reads the judge's verdict;
it does not add or update an entry in the flight ledger.

By default the newest `w1-lun-*` directory under the K60 evidence root is used.
Set K60_W1_EVIDENCE to one capture directory, or K60_W1_EVIDENCE_ROOT to a
different root.  A missing capture is a PENDING result, not an error.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
JUDGE = HERE / "check-w1-lun-evidence.py"
DEFAULT_ROOTS = (Path("/mnt/e/k60-work/evidence"), Path("E:/k60-work/evidence"))


def evidence_root(explicit):
    if explicit:
        return Path(explicit)
    configured = os.environ.get("K60_W1_EVIDENCE_ROOT")
    if configured:
        return Path(configured)
    for candidate in DEFAULT_ROOTS:
        if candidate.is_dir():
            return candidate
    return DEFAULT_ROOTS[0]


def capture_dir(root):
    """Return one capture directory, or None when there is nothing to judge."""
    if root.is_dir() and (root / "device-link.txt").is_file():
        return root
    if root.is_dir() and (root / "unit-desc.bin").is_file():
        return root
    if not root.is_dir():
        return None
    candidates = [path for path in root.glob("w1-lun-*") if path.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def main(argv=None):
    parser = argparse.ArgumentParser(description="PENDING-safe W1 LUN build preflight")
    parser.add_argument("--evidence", help="capture directory; overrides discovery")
    parser.add_argument("--expect-lun", type=int, default=5,
                        help="hypothesis to test; default 5")
    parser.add_argument("--judge", default=str(JUDGE), help="judge script (tests only)")
    args = parser.parse_args(argv)

    root = evidence_root(args.evidence)
    capture = Path(args.evidence) if args.evidence else capture_dir(root)
    if capture is None or not capture.is_dir():
        print("K60 W1 LUN PREFLIGHT PENDING no capture under %s (does not block)" % root)
        return 0

    command = [sys.executable, str(args.judge), str(capture),
               "--expect-lun", str(args.expect_lun)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    output = (result.stdout + result.stderr).strip()
    if output:
        print(output)
    if result.returncode == 0:
        print("K60 W1 LUN PREFLIGHT PASS %s" % capture)
        return 0
    if result.returncode == 2:
        print("K60 W1 LUN PREFLIGHT PENDING %s (does not block)" % capture)
        return 0
    print("K60 W1 LUN PREFLIGHT FAIL %s (judge exited %d)" % (capture, result.returncode))
    return 1


if __name__ == "__main__":
    sys.exit(main())
