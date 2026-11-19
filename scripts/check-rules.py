#!/usr/bin/env python3
"""Run every check registered in docs/engineering/RULES.toml.

A rule written in prose is a wish. A rule with an executable check is a gate.
This runner is the single place that turns the prose in ``AGENTS.md``, the
pitfall log and the process documents into something that can stop a build.

Usage:
    python3 scripts/check-rules.py            # run everything, exit non-zero on failure
    python3 scripts/check-rules.py --list     # show the registry
    python3 scripts/check-rules.py --only P-155
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RULES = REPO / "docs" / "engineering" / "RULES.toml"
PITFALLS = REPO / "docs" / "engineering" / "PITFALLS.md"
AGENTS = REPO / "AGENTS.md"

PITFALL_HEADING = re.compile(r"^#{2,3}\s*P-(\d{3})", re.MULTILINE)
HARD_HEADING = re.compile(r"^##\s*★(\d+)", re.MULTILINE)
# `### 铁则 9` is the original Chinese heading; `### Iron rule 9` is the English
# rewrite. Both are accepted so translating AGENTS.md does not turn the coverage
# check vacuous - a heading the regex misses used to mean "no rule declared",
# which passes silently instead of failing loudly.
IRON_HEADING = re.compile(r"^###\s*(?:铁则|Iron[ _]rule)\s*(\d+)", re.MULTILINE)


def load_registry() -> dict:
    return tomllib.loads(RULES.read_text(encoding="utf-8"))


def iron_rules_in_agents() -> set[str]:
    """Return the iron rule ids AGENTS.md actually declares."""
    if not AGENTS.is_file():
        return set()
    text = AGENTS.read_text(encoding="utf-8", errors="replace")
    return {f"iron-{n}" for n in IRON_HEADING.findall(text)}


def pitfalls_in_log() -> set[str]:
    if not PITFALLS.is_file():
        return set()
    text = PITFALLS.read_text(encoding="utf-8", errors="replace")
    return {f"P-{n}" for n in PITFALL_HEADING.findall(text)}


def hard_rules_in_doc() -> set[str]:
    hard = REPO / "docs" / "engineering" / "HARD-RULES.md"
    if not hard.is_file():
        return set()
    text = hard.read_text(encoding="utf-8", errors="replace")
    return {f"hard-{n}" for n in HARD_HEADING.findall(text)}


def run_check(command: str) -> tuple[bool, str]:
    # text=True alone decodes with the host locale (GBK on this machine), so a
    # check that prints UTF-8 or a stray non-ASCII byte kills the whole registry
    # with UnicodeDecodeError instead of reporting that check as failed. The
    # registry must be able to *report* a broken check, never die of one.
    # The children are Python too, and on this host the default codec is GBK:
    # a check that prints Chinese dies with UnicodeEncodeError inside itself and
    # reports as a failure of the thing it was checking. Force UTF-8 down the
    # whole tree so the registry grades verdicts, not console encodings.
    child_env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    result = subprocess.run(command, shell=True, cwd=str(REPO), env=child_env,
                            capture_output=True, text=True, check=False,
                            encoding="utf-8", errors="replace")
    output = ((result.stdout or "") + (result.stderr or "")).strip().splitlines()
    tail = output[-1] if output else "(no output)"
    return result.returncode == 0, tail


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--repo", help="repository to check (default: the one holding this script)")
    parser.add_argument("--only", action="append", default=[])
    args = parser.parse_args()

    if args.repo:
        global REPO, RULES, PITFALLS, AGENTS
        REPO = Path(args.repo).resolve()
        RULES = REPO / "docs" / "engineering" / "RULES.toml"
        PITFALLS = REPO / "docs" / "engineering" / "PITFALLS.md"
        AGENTS = REPO / "AGENTS.md"

    if not RULES.is_file():
        print(f"❌ 缺少登记表 {RULES.relative_to(REPO)}")
        return 1
    registry = load_registry()
    rules = registry.get("rule", [])

    if args.list:
        for rule in rules:
            mode = rule.get("check") or f"waiver: {rule.get('waiver', '')[:60]}"
            print(f"{rule['id']:<8} {rule['kind']:<8} {mode}")
        return 0

    registered = {rule["id"] for rule in rules}
    problems: list[str] = []

    # Coverage: every declared iron rule must be registered. An empty set means
    # the heading format changed and the rest of this block proves nothing, so
    # that case is a failure rather than a pass.
    declared = iron_rules_in_agents()
    if not declared:
        problems.append("AGENTS.md declares no iron rule heading "
                        "(expected '### 铁则 N' or '### Iron rule N'); "
                        "coverage would be vacuous")
    for rule_id in sorted(declared - registered):
        problems.append(f"AGENTS.md 声明了 {rule_id} 但 RULES.toml 没有登记检查")

    # Same trap for the pitfall log: a translated or reordered file whose
    # headings stop matching would otherwise report "no new pitfalls".
    logged = pitfalls_in_log()
    if PITFALLS.is_file() and not logged:
        problems.append("PITFALLS.md contains no 'P-nnn' heading; the pitfall "
                        "coverage check would be vacuous")

    # Coverage: every pitfall newer than the grandfather line must be registered.
    grand = int(registry.get("grandfather_through", 0))
    for pitfall in sorted(logged - registered):
        if int(pitfall.split("-")[1]) > grand:
            problems.append(f"{pitfall} 没有登记检查也没有 waiver（PITFALLS.md 里的新坑必须有门禁）")

    # Coverage: every ★N hard rule must be registered.
    for rule_id in sorted(hard_rules_in_doc() - registered):
        problems.append(f"{rule_id} 在 HARD-RULES.md 里但没有登记检查也没有 waiver")

    # Every registered rule must be actionable.
    for rule in rules:
        if not rule.get("check") and not rule.get("waiver"):
            problems.append(f"{rule['id']} 既没有 check 也没有 waiver")

    selected = [rule for rule in rules
                if not args.only or rule["id"] in args.only]
    failures: list[tuple[str, str]] = []
    waived: list[str] = []
    cache: dict[str, tuple[bool, str]] = {}
    for rule in selected:
        command = rule.get("check")
        if not command:
            waived.append(rule["id"])
            continue
        if command not in cache:
            cache[command] = run_check(command)
        ok, tail = cache[command]
        mark = "✅" if ok else "❌"
        print(f"{mark} {rule['id']:<8} {tail}")
        if not ok:
            failures.append((rule["id"], tail))

    executed = len(cache)
    print()
    print(f"登记 {len(rules)} 条，本轮涉及 {len(selected)} 条，"
          f"实际执行 {executed} 个不同命令，失败 {len(failures)} 条，waiver {len(waived)} 条")
    if problems:
        print("❌ 覆盖缺口：")
        for problem in problems:
            print(f"   - {problem}")
    if failures or problems:
        print("结论: ❌ 规范与铁则门禁未通过")
        return 1
    print("结论: ✅ 规范与铁则门禁全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
