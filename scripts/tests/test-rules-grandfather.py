#!/usr/bin/env python3
"""The pitfall-coverage line must be measured, not remembered.

`scripts/check-rules.py` decides which pitfalls need a registered check with
`int(registry.get("grandfather_through", 0))`. The key did not exist for months,
so the default 0 turned "everything after the line" into "everything", and the
registry refused every build over 49 legacy entries (P-256).

Two things can go wrong again, and both are cheap to forbid:

* the number drifts because somebody raises it by hand to silence a red build;
* the key disappears again and the default silently re-decides the rule.

So the first case recomputes the line from the commit that introduced the
coverage, and the second case deletes the key in a scratch copy and asserts the
registry goes red.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RULES = REPO / "docs/engineering/RULES.toml"
PITFALLS = REPO / "docs/engineering/PITFALLS.md"
INTRODUCED = "ad527fd0e"

CASES = []
FAILURES = []


def case(fn):
    CASES.append(fn)
    return fn


def registry() -> dict:
    with RULES.open("rb") as handle:
        return tomllib.load(handle)


def max_pitfall_at(rev: str) -> int:
    text = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{rev}:docs/engineering/PITFALLS.md"],
        capture_output=True, text=True, check=True,
    ).stdout
    numbers = [int(n) for n in re.findall(r"^#{2,3}\s*P-(\d{3})", text, re.M)]
    assert numbers, f"no P-nnn heading at {rev}"
    return max(numbers)


@case
def the_key_exists_and_is_not_zero():
    data = registry()
    assert "grandfather_through" in data, (
        "RULES.toml lost grandfather_through; get(key, 0) re-decides the rule"
    )
    value = data["grandfather_through"]
    assert isinstance(value, int) and value > 0, f"grandfather_through = {value!r}"


@case
def the_line_is_what_the_coverage_commit_saw():
    data = registry()
    expected = max_pitfall_at(INTRODUCED)
    assert data["grandfather_through"] == expected, (
        f"RULES.toml says {data['grandfather_through']}, "
        f"{INTRODUCED} ended at P-{expected}"
    )


@case
def every_pitfall_above_the_line_is_registered():
    data = registry()
    line = data["grandfather_through"]
    registered = {rule["id"] for rule in data["rule"]}
    text = PITFALLS.read_text(encoding="utf-8")
    logged = {f"P-{n}" for n in re.findall(r"^#{2,3}\s*P-(\d{3})", text, re.M)}
    missing = sorted(
        (p for p in logged - registered if int(p.split("-")[1]) > line),
        key=lambda s: int(s.split("-")[1]),
    )
    assert not missing, f"above P-{line} but unregistered: {', '.join(missing)}"


@case
def every_registered_new_pitfall_carries_a_check_or_a_waiver():
    data = registry()
    line = data["grandfather_through"]
    for rule in data["rule"]:
        if rule.get("kind") != "pitfall":
            continue
        number = int(rule["id"].split("-")[1])
        if number <= line:
            continue
        assert rule.get("check") or rule.get("waiver"), (
            f"{rule['id']} neither checks nor waives; the entry is decoration"
        )


@case
def removing_the_key_turns_the_registry_red():
    text = RULES.read_text(encoding="utf-8")
    stripped = re.sub(r"(?m)^grandfather_through\s*=\s*\d+\s*$\n?", "", text)
    assert stripped != text, "could not remove the key"
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / "RULES.toml"
        copy.write_text(stripped, encoding="utf-8")
        with copy.open("rb") as handle:
            data = tomllib.load(handle)
    line = int(data.get("grandfather_through", 0))
    registered = {rule["id"] for rule in data["rule"]}
    logged = {f"P-{n}" for n in re.findall(r"^#{2,3}\s*P-(\d{3})",
                                           PITFALLS.read_text(encoding="utf-8"), re.M)}
    would_fail = [p for p in logged - registered if int(p.split("-")[1]) > line]
    assert would_fail, (
        "without the key the registry would still be green, so the key is not "
        "what decides the rule any more"
    )


def main() -> int:
    for fn in CASES:
        try:
            fn()
        except AssertionError as error:
            FAILURES.append(f"{fn.__name__}: {error}")
            print(f"FAIL {fn.__name__}")
        except Exception as error:                      # noqa: BLE001 - report everything
            FAILURES.append(f"{fn.__name__}: {type(error).__name__}: {error}")
            print(f"ERROR {fn.__name__}: {type(error).__name__}: {error}")
        else:
            print(f"ok   {fn.__name__}")
    print(f"TESTS {'OK' if not FAILURES else 'FAILED'}: "
          f"{len(CASES) - len(FAILURES)}/{len(CASES)}")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    raise SystemExit(main())