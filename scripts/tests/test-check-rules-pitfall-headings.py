#!/usr/bin/env python3
"""The pitfall-heading scan must see headings that are not at offset zero.

P-254 records the failure this test exists for: the regex was compiled without
re.MULTILINE and the call site passed re.MULTILINE as findall's *position*
argument, so a scan over the real log returned nothing and the coverage check
reported itself vacuous. Both halves are asserted here, because either one alone
reproduces the bug.
"""
import importlib.util
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"ok   {name}")
    else:
        failures.append(f"{name}: {detail}")
        print(f"FAIL {name}: {detail}")


def load() -> object:
    spec = importlib.util.spec_from_file_location("check_rules", REPO / "scripts" / "check-rules.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = load()

    # 1. The pattern itself must be multiline: a heading on line 2 has to match.
    sample = "## P-001 first\n## P-254 second\n"
    check("the real pattern is multiline",
          module.PITFALL_HEADING.findall(sample) == ["001", "254"],
          f"got {module.PITFALL_HEADING.findall(sample)}")
    check("the real pattern is compiled with re.MULTILINE",
          bool(module.PITFALL_HEADING.flags & re.MULTILINE),
          f"flags={module.PITFALL_HEADING.flags}")

    # 2. The call site must not smuggle an integer in as the scan position.
    source = (REPO / "scripts" / "check-rules.py").read_text(encoding="utf-8")
    check("pitfalls_in_log passes only the text",
          "PITFALL_HEADING.findall(text, re.MULTILINE)" not in source,
          "re.MULTILINE is findall's pos argument, not a flag")

    # 3. On the real log the scan must find the recent three-digit pitfalls.
    logged = module.pitfalls_in_log()
    check("the real pitfall log yields headings", len(logged) > 100, f"got {len(logged)}")
    check("a heading added after line one is found", "P-254" in logged,
          "P-254 is this very entry; if it is missing the scan stopped early")
    check("the newest registered pitfall is visible", "P-253" in logged,
          f"P-253 missing from {len(logged)} headings")

    print()
    if failures:
        print(f"TESTS FAILED ({len(failures)})")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"TESTS OK ({len(logged)} headings in the real log)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
