#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Dry-run the seven Wi-Fi 27 criteria on green and red fixtures.

The checker is the same program the TOML command names.  For each step a
fixture carries every required fact, then all but one; the first run must
print the expected line and exit 0, the second must name the missing fact and
exit 1.  A missing fixture must exit 2.  ``--case <step>-red`` runs one red
case, which is the command recorded in the lane TOML.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts/check-wifi27-criteria.py"
LEDGER = ROOT / "docs/research/eight-step/wifi-27.toml"


def load_checker():
    spec = importlib.util.spec_from_file_location("check_wifi27_criteria", CHECKER)
    if spec is None or spec.loader is None:
        raise SystemExit("FAIL checker: cannot import %s" % CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expected_line(step: str) -> str:
    data = tomllib.loads(LEDGER.read_text(encoding="utf-8"))
    return data["hardware"]["wifi"]["step"][step]["criteria"]["expected"]


def negative_line(step: str) -> str:
    data = tomllib.loads(LEDGER.read_text(encoding="utf-8"))
    return data["hardware"]["wifi"]["step"][step]["criteria"]["negative_expected"]


def run_fixture(step: str, present: list[str], directory: Path):
    fixture = directory / ("%s.json" % step)
    fixture.write_text(json.dumps({"present": present}), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(CHECKER), "--step", step, "--fixture", str(fixture)],
        capture_output=True,
        text=True,
    )


def red_case(step: str, required: tuple[str, ...], directory: Path):
    present = list(required)
    removed = present.pop(0)
    proc = run_fixture(step, present, directory)
    want = negative_line(step)
    if proc.returncode != 1:
        return False, "rc=%d want 1; stdout=%r stderr=%r" % (proc.returncode, proc.stdout.strip(), proc.stderr.strip())
    if proc.stdout.strip() != want:
        return False, "stdout=%r want %r" % (proc.stdout.strip(), want)
    return True, want


def green_case(step: str, required: tuple[str, ...], directory: Path):
    proc = run_fixture(step, list(required), directory)
    want = expected_line(step)
    if proc.returncode != 0:
        return False, "rc=%d want 0; stdout=%r stderr=%r" % (proc.returncode, proc.stdout.strip(), proc.stderr.strip())
    if proc.stdout.strip() != want:
        return False, "stdout=%r want %r" % (proc.stdout.strip(), want)
    return True, want


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", help="<step>-red; run only that red fixture")
    args = parser.parse_args(argv)
    checker = load_checker()
    steps = list(checker.STEPS)
    failures = 0

    with tempfile.TemporaryDirectory(prefix="wifi27-criteria-") as tmp:
        directory = Path(tmp)
        if args.case:
            if not args.case.endswith("-red"):
                print("FAIL case: %s: expected <step>-red" % args.case)
                return 1
            step = args.case[:-4]
            if step not in checker.REQUIRED:
                print("FAIL case: %s: unknown step" % args.case)
                return 1
            ok, detail = red_case(step, checker.REQUIRED[step], directory)
            if ok:
                print("PASS %s: %s" % (args.case, detail))
                return 0
            print("FAIL %s: %s" % (args.case, detail))
            return 1

        for step in steps:
            ok, detail = green_case(step, checker.REQUIRED[step], directory)
            if ok:
                print("PASS %s green: %s" % (step, detail))
            else:
                failures += 1
                print("FAIL %s green: %s" % (step, detail))
            ok, detail = red_case(step, checker.REQUIRED[step], directory)
            if ok:
                print("PASS %s red: %s" % (step, detail))
            else:
                failures += 1
                print("FAIL %s red: %s" % (step, detail))

        missing = directory / "absent.json"
        proc = subprocess.run(
            [sys.executable, str(CHECKER), "--step", steps[0], "--fixture", str(missing)],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 2 and "FAIL fixture:" in proc.stderr:
            print("PASS fixture missing: rc=2")
        else:
            failures += 1
            print("FAIL fixture missing: rc=%d stderr=%r" % (proc.returncode, proc.stderr.strip()))

    if failures:
        print("%d failure(s)" % failures)
        return 1
    print("%d/%d criteria have green and red dry-runs" % (len(steps), len(steps)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
