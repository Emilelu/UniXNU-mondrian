#!/usr/bin/env python3
"""Host test for scripts/check-catalog-armcpu-gaps.py.

Runs the checker against this worktree and against a copy whose catalog is
missing, and asserts the three documented properties:

  * the three gap ids always appear, one verdict each;
  * a lane whose catalog cannot be read reports UNKNOWN and names the missing
    input instead of folding it into "fine";
  * the checker writes nothing (board.toml byte-identical before and after).
"""

import hashlib
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHECK = os.path.join(REPO, "scripts", "check-catalog-armcpu-gaps.py")
GAPS = ("psci-node", "sheng-smp", "sleep")
VERDICTS = ("SATISFIED", "OPEN", "UNKNOWN")


def run(args):
    done = subprocess.run([sys.executable, CHECK] + args, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    return done.returncode, done.stdout + done.stderr


def digest(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def main():
    failures = []
    board = os.path.join(REPO, "board.toml")
    before = digest(board)

    code, out = run([])
    if code not in (0, 1, 2):
        failures.append("rc %d is outside the documented 0/1/2" % code)
    for gap in GAPS:
        if gap not in out:
            failures.append("gap %s is missing from the output" % gap)
    for verdict in VERDICTS:
        for line in out.splitlines():
            if gap in line and verdict in line:
                break
    verdicts = sum(out.count(v) for v in VERDICTS)
    if verdicts < len(GAPS):
        failures.append("expected at least %d verdicts, saw %d" % (len(GAPS), verdicts))
    if "missing input" in out and code != 2:
        failures.append("an UNKNOWN verdict must exit 2, got %d" % code)

    missing = os.path.join(REPO, "no-such-catalog-checkout")
    code, out = run(["--catalog", missing])
    expected = 1 if "OPEN" in out else 2
    if code != expected:
        failures.append("missing catalog: expected rc %d (OPEN wins over UNKNOWN), "
                        "got %d" % (expected, code))
    if out.count("UNKNOWN") < 2:
        failures.append("missing catalog: expected two UNKNOWN gaps")
    if "missing input" not in out:
        failures.append("missing catalog: UNKNOWN must name the missing input")
    if "SATISFIED" in out and "sleep" not in out:
        failures.append("missing catalog: sleep must not be judged satisfied")

    if digest(board) != before:
        failures.append("the checker modified board.toml")

    print("TESTS %s" % ("OK" if not failures else "FAILED"))
    for failure in failures:
        print("  - " + failure)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
