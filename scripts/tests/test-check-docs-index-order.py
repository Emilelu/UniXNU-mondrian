#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Self-test for the INDEX reading-order checker in scripts/check-docs.py.

Cases:
  1. a Chinese numeral heading matches six numbered rows;
  2. an Arabic numeral heading does the same;
  3. a declared count that differs from the table is rejected;
  4. non-sequential row numbers are rejected;
  5. a missing reading-order section is rejected.
"""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "check-docs.py"


def load_gate():
    spec = importlib.util.spec_from_file_location("check_docs_index", GATE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def problems_for(text):
    gate = load_gate()
    with tempfile.TemporaryDirectory(prefix="k60-doc-index-") as tmp:
        root = Path(tmp)
        (root / "docs").mkdir()
        (root / "docs" / "INDEX.md").write_text(text, encoding="utf-8")
        gate.REPO = str(root)
        problems, _ = gate.check_index_reading_order(verbose=False)
        return problems


def table(order):
    rows = "\n".join("| %s | doc-%s | why |" % (n, n) for n in order)
    return "| 顺序 | 文档 | 为什么先读 |\n|---|---|---|\n" + rows + "\n"


def main() -> int:
    failures = 0

    def check(name, actual, expected):
        nonlocal failures
        if actual != expected:
            failures += 1
            print(f"FAIL {name}: expected {expected!r}, got {actual!r}")
        else:
            print(f"ok   {name}")

    check("chinese six", problems_for("## 0. 先读这六份\n\n" + table(range(1, 7))), [])
    check("arabic six", problems_for("## 0. 先读这6份\n\n" + table(range(1, 7))), [])
    check("wrong count",
          len(problems_for("## 0. 先读这五份\n\n" + table(range(1, 7)))), 1)
    check("bad order",
          len(problems_for("## 0. 先读这六份\n\n" + table([1, 0, 2, 3, 4, 5]))), 1)
    check("missing section",
          len(problems_for("# no reading order\n")), 1)

    print(f"TESTS {'OK' if failures == 0 else 'FAILED'} ({failures} failure(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
