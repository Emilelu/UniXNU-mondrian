#!/usr/bin/env python3
"""Structural test for docs/research/thermal/CRITERIA.toml and its reader.

CRITERIA.toml is the machine-readable half of LEVEL-MAP.md section 5.3, and
scripts/check-thermal-log.py is the reader. A criterion with a typo in its kind,
a profile nobody can select, or a duplicate id would silently weaken the boot
verdict, so this test reads the file and fails on those. It also runs the reader
self-test, which proves the criteria can actually fail.

Usage: python3 scripts/tests/test-k60-thermal-log.py
"""
import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CRITERIA = REPO / "docs" / "research" / "thermal" / "CRITERIA.toml"
READER = REPO / "scripts" / "check-thermal-log.py"
KINDS = {"count", "each", "coverage", "pair"}
SEVERITIES = {"required", "advisory"}
LEVELS = {"50000": "1/3", "75000": "2/3", "85000": "3/3"}

failures = []
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        failures.append(message)


def main():
    with open(CRITERIA, "rb") as handle:
        document = tomllib.load(handle)
    criteria = document.get("criterion", [])
    check(document.get("version") == 1, "version must be 1")
    check(bool(document.get("log", {}).get("evidence_root")), "log.evidence_root missing")
    check(len(criteria) >= 20, "only %d criteria; the verdict needs the full table" % len(criteria))

    ids = [criterion.get("id") for criterion in criteria]
    check(all(ids), "a criterion has no id")
    check(len(set(ids)) == len(ids), "duplicate criterion id(s)")

    profiles = {criterion.get("profile", "*") for criterion in criteria}
    for profile in profiles:
        check(profile == "*" or profile == "cold" or profile.startswith("bias-"),
              "unknown profile %r" % profile)
    for wanted in ("cold", "bias-50000", "bias-75000", "bias-85000"):
        check(wanted in profiles, "profile %r has no criterion" % wanted)
    for bias, level in LEVELS.items():
        wanted = [criterion for criterion in criteria
                  if criterion.get("profile") == "bias-" + bias
                  and level in criterion.get("pattern", "")]
        check(bool(wanted), "bias-%s has no criterion expecting level %s" % (bias, level))

    for criterion in criteria:
        name = criterion.get("id")
        check(bool(criterion.get("title")), "%s: no title" % name)
        check(criterion.get("kind", "count") in KINDS, "%s: unknown kind" % name)
        check(criterion.get("severity", "required") in SEVERITIES, "%s: unknown severity" % name)
        check(bool(criterion.get("why")), "%s: no why; a failure would not say where to look" % name)
        check(bool(criterion.get("pattern")), "%s: no pattern" % name)
        if criterion.get("kind") == "each":
            check(bool(criterion.get("must")), "%s: each needs must" % name)
        if criterion.get("kind") == "coverage":
            check(len(criterion.get("expected", [])) == 32,
                  "%s: expected list is not the 32 zone labels" % name)
        if criterion.get("kind") == "pair":
            check(bool(criterion.get("level_pattern")), "%s: pair needs level_pattern" % name)
        if criterion.get("kind", "count") == "count":
            check("min" in criterion or "max" in criterion, "%s: count needs min or max" % name)

    result = subprocess.run([sys.executable, str(READER), "--self-test"],
                            capture_output=True, text=True)
    check(result.returncode == 0,
          "reader self-test failed: %s" % (result.stdout + result.stderr).strip())
    result = subprocess.run([sys.executable, str(READER), "--list-profiles"],
                            capture_output=True, text=True)
    check(result.returncode == 0, "reader --list-profiles failed")

    if failures:
        print("FAILED: %d problem(s)" % len(failures))
        for problem in failures:
            print("  - " + problem)
        return 1
    print("TESTS OK %d" % checks)
    return 0


if __name__ == "__main__":
    sys.exit(main())
