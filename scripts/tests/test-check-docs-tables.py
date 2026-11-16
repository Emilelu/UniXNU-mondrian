#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Self-test for the Markdown table checker in scripts/check-docs.py.

Cases:
  1. plain rows split into cells;
  2. escaped pipes stay in one cell;
  3. pipes inside code spans stay in one cell;
  4. a trailing backslash inside a code span does not swallow the delimiter;
  5. a row with the wrong cell count is rejected;
  6. a matching table passes.
"""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "check-docs.py"


def load_gate():
    spec = importlib.util.spec_from_file_location("check_docs", GATE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def cells(module, line):
    return module._table_cells(line)


def check_fixture(text):
    gate = load_gate()
    with tempfile.TemporaryDirectory(prefix="k60-doc-table-") as tmp:
        root = Path(tmp)
        (root / "docs").mkdir()
        (root / "docs" / "sample.md").write_text(text, encoding="utf-8")
        gate.REPO = str(root)
        return gate.check_tables(verbose=False)


def main() -> int:
    failures = 0
    gate = load_gate()

    def check(name, actual, expected):
        nonlocal failures
        if actual != expected:
            failures += 1
            print(f"FAIL {name}: expected {expected!r}, got {actual!r}")
        else:
            print(f"ok   {name}")

    check("plain", cells(gate, "| a | b |"), ["a", "b"])
    check("escaped pipe", cells(gate, r"| a \| b | c |"), [r"a \| b", "c"])
    check("code span pipe", cells(gate, "| `a|b` | c |"), ["`a|b`", "c"])
    check("code span trailing backslash", cells(gate, "| `E:\\k60-work\\` | 1 |"),
          ["`E:\\k60-work\\`", "1"])

    problems, _ = check_fixture("| a | b |\n|---|---|\n| 1 |\n")
    check("bad row rejected", len(problems), 1)
    problems, _ = check_fixture("| a | b |\n|---|---|\n| 1 | 2 |\n")
    check("good table passes", problems, [])

    print(f"TESTS {'OK' if failures == 0 else 'FAILED'} ({failures} failure(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
