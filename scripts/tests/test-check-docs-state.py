#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Self-test for the docs/state INDEX coverage in scripts/check-docs.py.

Cases:
  1. every docs/state snapshot is mentioned in docs/INDEX.md;
  2. a docs/state snapshot missing from docs/INDEX.md fails.
"""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "check-docs.py"


def load_gate():
    spec = importlib.util.spec_from_file_location("check_docs_state", GATE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def check_fixture(index_text, files):
    gate = load_gate()
    with tempfile.TemporaryDirectory(prefix="k60-doc-state-") as tmp:
        root = Path(tmp)
        state = root / "docs" / "state"
        state.mkdir(parents=True)
        (root / "docs" / "INDEX.md").write_text(index_text, encoding="utf-8")
        for name, text in files.items():
            (state / name).write_text(text, encoding="utf-8")
        gate.REPO = str(root)
        return gate.check_index_coverage(verbose=False)


def main() -> int:
    failures = 0

    def check(name, actual, expected):
        nonlocal failures
        if actual != expected:
            failures += 1
            print(f"FAIL {name}: expected {expected!r}, got {actual!r}")
        else:
            print(f"ok   {name}")

    problems, counted = check_fixture(
        "| [STATE](state/STATE.md) |\n",
        {"STATE.md": "# State\n"},
    )
    check("state snapshot indexed", (problems, counted), ([], 1))

    problems, _ = check_fixture(
        "| [OTHER](state/OTHER.md) |\n",
        {"STATE.md": "# State\n", "OTHER.md": "# Other\n"},
    )
    check("state snapshot missing", any("state/STATE.md" in p for p in problems), True)

    print(f"TESTS {'OK' if failures == 0 else 'FAILED'} ({failures} failure(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
