#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Self-test for scripts/check-readme.py (P-205 / ★36 rule 7).

The gate reconciles four classes of README drift that check-docs.py cannot see:
dates, ★/P range claims, the bilingual link pair, and the gate-table coverage of
build-strict.sh. These cases pin each reconciliation on a small fixture repo so
a change to one check cannot silently widen or narrow another.

Cases:
  1. a consistent fixture passes;
  2. a README date older than STATUS fails;
  3. an EN date different from the ZH date fails;
  4. a ★/P range claim that lags the real headings fails;
  5. a gate table naming a script that does not exist fails;
  6. a build-strict gate missing from the README table fails;
  7. ZH and EN tables naming different sets fails;
  8. the real repo is self-consistent (regression canary).
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "check-readme.py"

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def load_gate():
    spec = importlib.util.spec_from_file_location("check_readme", GATE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


README_ZH = """# UniXNU-mondrian

[English](README_EN.md)

最后更新：2026-11-15

<!-- GATE-TABLE:BEGIN -->
| scripts/check-build-env.py |
| scripts/eight-step-gate.py |
| scripts/check-docs.py |
<!-- GATE-TABLE:END -->

铁则 ★1–★37 / 坑记录 P-01–P-205
"""

README_EN = """# UniXNU-mondrian

[中文版](README.md)

Last updated: 2026-11-15

<!-- GATE-TABLE:BEGIN -->
| scripts/check-build-env.py |
| scripts/eight-step-gate.py |
| scripts/check-docs.py |
<!-- GATE-TABLE:END -->

Hard rules ★1–★37 / Pitfall log P-01–P-205
"""

STATUS = """本轮更新时间：2026-11-15
"""

HARD_RULES = """## ★37 文档同步
"""

PITFALLS = """## P-205 文档里的日期编号漂移
"""

BUILD_STRICT = """#!/bin/bash
# --- gate-table:BEGIN ---
# runs scripts/check-build-env.py
# runs scripts/eight-step-gate.py
# --- gate-table:END ---
"""


def make_fixture():
    tmp = Path(tempfile.mkdtemp(prefix="k60-readme-test-"))
    (tmp / "docs" / "engineering").mkdir(parents=True)
    (tmp / "scripts").mkdir(parents=True)
    (tmp / "README.md").write_text(README_ZH, encoding="utf-8")
    (tmp / "README_EN.md").write_text(README_EN, encoding="utf-8")
    (tmp / "docs" / "engineering" / "STATUS.md").write_text(STATUS, encoding="utf-8")
    (tmp / "docs" / "engineering" / "HARD-RULES.md").write_text(HARD_RULES, encoding="utf-8")
    (tmp / "docs" / "engineering" / "PITFALLS.md").write_text(PITFALLS, encoding="utf-8")
    (tmp / "scripts" / "build-strict.sh").write_text(BUILD_STRICT, encoding="utf-8")
    for name in ("check-build-env.py", "eight-step-gate.py", "check-docs.py"):
        (tmp / "scripts" / name).write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    return tmp


@case
def a_consistent_fixture_passes():
    gate = load_gate()
    tmp = make_fixture()
    assert gate.run_checks(repo=str(tmp)) == [], "the consistent fixture must pass"


@case
def a_readme_date_older_than_status_fails():
    gate = load_gate()
    tmp = make_fixture()
    p = tmp / "README.md"
    p.write_text(p.read_text(encoding="utf-8").replace("2026-11-15", "2026-11-12"),
                 encoding="utf-8")
    problems = gate.run_checks(repo=str(tmp))
    assert any("早于" in x for x in problems), f"expected a stale-date problem, got {problems}"


@case
def an_en_date_mismatch_fails():
    gate = load_gate()
    tmp = make_fixture()
    p = tmp / "README_EN.md"
    p.write_text(p.read_text(encoding="utf-8").replace("2026-11-15", "2026-11-14"),
                 encoding="utf-8")
    problems = gate.run_checks(repo=str(tmp))
    assert any("README_EN 日期" in x for x in problems), f"expected an EN date problem, got {problems}"


@case
def a_range_claim_lagging_the_headings_fails():
    gate = load_gate()
    tmp = make_fixture()
    (tmp / "docs" / "engineering" / "PITFALLS.md").write_text(
        "## P-206 a newer pitfall\n", encoding="utf-8")
    problems = gate.run_checks(repo=str(tmp))
    assert any("实际最大号是 206" in x for x in problems), f"expected a range problem, got {problems}"


@case
def a_gate_table_naming_a_missing_script_fails():
    gate = load_gate()
    tmp = make_fixture()
    p = tmp / "README.md"
    p.write_text(p.read_text(encoding="utf-8").replace(
        "| scripts/eight-step-gate.py |", "| scripts/no-such-gate.py |"), encoding="utf-8")
    problems = gate.run_checks(repo=str(tmp))
    assert any("文件不存在" in x for x in problems), f"expected a missing-file problem, got {problems}"


@case
def a_build_strict_gate_missing_from_the_table_fails():
    gate = load_gate()
    tmp = make_fixture()
    strict = tmp / "scripts" / "build-strict.sh"
    strict.write_text(strict.read_text(encoding="utf-8").replace(
        "# runs scripts/check-build-env.py\n",
        "# runs scripts/check-build-env.py\n# runs scripts/check-image-args.py\n"),
        encoding="utf-8")
    problems = gate.run_checks(repo=str(tmp))
    assert any("没有出现在 README 门禁表里" in x for x in problems), \
        f"expected a coverage problem, got {problems}"


@case
def a_zh_en_table_mismatch_fails():
    gate = load_gate()
    tmp = make_fixture()
    p = tmp / "README_EN.md"
    p.write_text(p.read_text(encoding="utf-8").replace(
        "| scripts/eight-step-gate.py |", "| scripts/other-gate.py |"), encoding="utf-8")
    problems = gate.run_checks(repo=str(tmp))
    assert any("中英门禁表脚本集不一致" in x for x in problems), \
        f"expected a set mismatch problem, got {problems}"


@case
def the_real_repo_is_self_consistent():
    gate = load_gate()
    problems = gate.run_checks()
    assert problems == [], f"the checked-out repo must pass its own gate: {problems}"


def main() -> int:
    failures = 0
    for fn in CASES:
        try:
            fn()
            print(f"ok   {fn.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 - a broken gate is a failure, not a crash
            failures += 1
            print(f"FAIL {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"TESTS OK {len(CASES) - failures} case(s) ({failures} failure(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
