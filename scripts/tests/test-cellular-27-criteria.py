#!/usr/bin/env python3
"""Host-only regression for scripts/check-cellular-27-criteria.py.

The judge self-test already runs each positive criterion and its deliberately
broken input.  This wrapper exists so the repository's ordinary test run has
one stable line to look for.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def main() -> int:
    judge = ROOT / "scripts/check-cellular-27-criteria.py"
    if not judge.is_file():
        print("missing %s" % judge)
        return 1
    proc = subprocess.run(
        [sys.executable, str(judge), "--self-test"],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=600,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0 or "CELLULAR 27 CRITERIA SELF-TEST PASS 7/7" not in output:
        print(output)
        print("K60 CELLULAR 27 CRITERIA FAILED rc=%d" % proc.returncode)
        return 1
    print("K60 CELLULAR 27 CRITERIA PASS 7/7")
    return 0


if __name__ == "__main__":
    sys.exit(main())
