#!/usr/bin/env python3
"""Registry hygiene: rule ids must be unique, and a rule that names a pitfall in
its source must use that pitfall's id.

Both were violated on 2026-11-14: the line-endings rule was registered as
hard-34, which HARD-RULES.md already used for the protocol/model rule. Because
check-rules.py keeps `registered = {rule["id"] for rule in rules}` as a set, the
duplicate was invisible in the coverage check, and `--only hard-34` quietly ran
two different checks.
"""
import os
import sys
import tomllib
from collections import Counter
from pathlib import Path

REPO = Path(os.environ.get("K60_REPO") or Path(__file__).resolve().parents[1])
RULES = REPO / "docs" / "engineering" / "RULES.toml"
HARD = REPO / "docs" / "engineering" / "HARD-RULES.md"


def main() -> int:
    if not RULES.is_file():
        print(f"skip: {RULES} does not exist")
        return 0

    registry = tomllib.loads(RULES.read_text(encoding="utf-8"))
    rules = registry.get("rule", [])
    failures: list[str] = []

    ids = [rule.get("id", "") for rule in rules]
    dupes = sorted(i for i, n in Counter(ids).items() if n > 1)
    if dupes:
        failures.append(f"duplicate rule id(s): {dupes}")

    for rule in rules:
        rule_id = rule.get("id", "")
        if not rule_id:
            failures.append("a rule has no id")
            continue
        source = rule.get("source", "")
        if source.startswith("docs/engineering/PITFALLS.md:P-"):
            pitfall = source.split(":")[-1]
            if rule_id != pitfall:
                failures.append(
                    f"{rule_id} names {pitfall} in its source but uses a different id"
                )
        if rule_id.startswith("P-") and source and "PITFALLS.md" not in source:
            failures.append(f"{rule_id} is a pitfall id but its source is {source}")

    # A hard-NN id must match the ★NN heading it claims to come from.
    hard_ids = set()
    if HARD.is_file():
        import re

        hard_ids = {f"hard-{n}" for n in re.findall(r"^##\s*★(\d+)", HARD.read_text(
            encoding="utf-8", errors="replace"), re.M)}
    for rule in rules:
        rule_id = rule.get("id", "")
        source = rule.get("source", "")
        if rule_id.startswith("hard-") and source.startswith("docs/engineering/HARD-RULES.md:★"):
            if hard_ids and rule_id not in hard_ids:
                failures.append(
                    f"{rule_id} claims {source} but HARD-RULES.md has no ★{rule_id.split('-')[1]}"
                )

    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        print(f"结论: ❌ registry has {len(failures)} problem(s)")
        return 1

    print(f"✅ registry: {len(rules)} rules, {len(set(ids))} unique id(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
