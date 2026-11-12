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
import re
import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RULES = REPO / "docs" / "engineering" / "RULES.toml"
PITFALLS = REPO / "docs" / "engineering" / "PITFALLS.md"
AGENTS = REPO / "AGENTS.md"

PITFALL_HEADING = re.compile(r"^#{2,3}\s*P-(\d{3})")
HARD_HEADING = re.compile(r"^##\s*★(\d+)", re.MULTILINE)


def load_registry() -> dict:
    return tomllib.loads(RULES.read_text(encoding="utf-8"))


def iron_rules_in_agents() -> set[str]:
    """Return the iron rule ids AGENTS.md actually declares."""
    if not AGENTS.is_file():
        return set()
    text = AGENTS.read_text(encoding="utf-8", errors="replace")
    return {f"iron-{n}" for n in re.findall(r"^###\s*铁则\s*(\d+)", text, re.MULTILINE)}


def pitfalls_in_log() -> set[str]:
    if not PITFALLS.is_file():
        return set()
    text = PITFALLS.read_text(encoding="utf-8", errors="replace")
    return {f"P-{n}" for n in PITFALL_HEADING.findall(text, re.MULTILINE)}


def hard_rules_in_doc() -> set[str]:
    hard = REPO / "docs" / "engineering" / "HARD-RULES.md"
    if not hard.is_file():
        return set()
    text = hard.read_text(encoding="utf-8", errors="replace")
    return {f"hard-{n}" for n in HARD_HEADING.findall(text)}


def run_check(command: str) -> tuple[bool, str]:
    result = subprocess.run(command, shell=True, cwd=str(REPO),
                            capture_output=True, text=True, check=False)
    output = (result.stdout + result.stderr).strip().splitlines()
    tail = output[-1] if output else "(no output)"
    return result.returncode == 0, tail


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--only", action="append", default=[])
    args = parser.parse_args()

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

    # Coverage: every declared iron rule must be registered.
    for rule_id in sorted(iron_rules_in_agents() - registered):
        problems.append(f"AGENTS.md 声明了 {rule_id} 但 RULES.toml 没有登记检查")

    # Coverage: every pitfall newer than the grandfather line must be registered.
    grand = int(registry.get("grandfather_through", 0))
    for pitfall in sorted(pitfalls_in_log() - registered):
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
