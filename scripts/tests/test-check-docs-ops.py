#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Self-test for the docs/ops snapshot-banner checker in scripts/check-docs.py.

Cases:
  1. a documented snapshot with a banner passes;
  2. a snapshot without the banner fails;
  3. a snapshot missing from docs/ops/README.md fails.
"""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "check-docs.py"


def load_gate():
    spec = importlib.util.spec_from_file_location("check_docs_ops", GATE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def check_fixture(readme, files):
    gate = load_gate()
    with tempfile.TemporaryDirectory(prefix="k60-doc-ops-") as tmp:
        root = Path(tmp)
        ops = root / "docs" / "ops"
        ops.mkdir(parents=True)
        (ops / "README.md").write_text(readme, encoding="utf-8")
        for name, text in files.items():
            (ops / name).write_text(text, encoding="utf-8")
        gate.REPO = str(root)
        return gate.check_ops_snapshots(verbose=False)


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

    valid = "| [a.md](a.md) | [b.md](b.md) |\n"
    problems, counted = check_fixture(valid, {
        "a.md": "# A\n\n> 上游快照，不是本项目权威\n",
        "b.md": "# B\n\n> 状态快照，不是当前状态\n",
    })
    check("valid snapshots", (problems, counted), ([], 2))

    problems, _ = check_fixture(valid, {
        "a.md": "# A\n\n> 上游快照，不是本项目权威\n",
        "b.md": "# B\n\n没有横幅\n",
    })
    check("missing banner", any("缺少" in p for p in problems), True)

    problems, _ = check_fixture("| [a.md](a.md) |\n", {
        "a.md": "# A\n\n> 上游快照，不是本项目权威\n",
        "b.md": "# B\n\n> 状态快照，不是当前状态\n",
    })
    check("missing index row", any("未登记" in p for p in problems), True)

    print(f"TESTS {'OK' if failures == 0 else 'FAILED'} ({failures} failure(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
