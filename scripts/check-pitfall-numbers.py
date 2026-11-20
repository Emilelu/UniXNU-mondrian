#!/usr/bin/env python3
"""Pitfall numbers are handed out once: no id may name two different pitfalls.

Two things go wrong without this check, and both happened on 2026-11-20:

  * a lane appends the next number it remembers and collides with an entry that
    landed on main while it was working (P-260/261/262 here were three of those);
  * a RULES.toml row is registered for an id that PITFALLS.md no longer carries,
    so the rule points at a section nobody can read.

The first failure is invisible inside one branch, because the branch simply does
not contain main's entry. `--against` takes the other tree's PITFALLS.md and
reports the same number carrying two different titles across the two.
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PITFALLS = "docs/engineering/PITFALLS.md"
RULES = "docs/engineering/RULES.toml"
HEADING = re.compile(r"^(#{2,3})[ \t]+(P-[0-9]+)(?=$|[ \t—:：-])(.*)$")
TITLE_PREFIX = re.compile(r"^[-—:：★\s]+")
# A section may grow a "更正 / 追加实测 / 补充" sub-heading that repeats its own
# number; that is a continuation of the same pitfall, not a second one.
CONTINUATION = ("更正", "追加", "补充", "续", "实测", "update", "correction", "addendum")
RULE_ID = re.compile(r'^id = "(P-\d+)"', re.M)
RULE_SOURCE = re.compile(r'^source = "docs/engineering/PITFALLS\.md:(P-\d+)"', re.M)


def headings(text: str) -> list[tuple[str, str, int]]:
    """(number, title, heading level) for every pitfall section.

    Two shapes are in the file: "## P-274 — title" on one line, and the older
    "## P-212" with the title on the next non-empty line. Matching only the
    first shape let a bare heading be parsed as P-21 with the title "2",
    because \\d+ backtracks until the rest of the line can satisfy (.+).
    """
    lines = text.splitlines()
    rows: list[tuple[str, str, int]] = []
    for index, line in enumerate(lines):
        m = HEADING.match(line)
        if not m:
            continue
        title = TITLE_PREFIX.sub("", m.group(3)).strip()
        if not title:
            for follow in lines[index + 1:]:
                if follow.strip():
                    if not follow.lstrip().startswith("#"):
                        title = follow.strip()
                    break
        rows.append((m.group(2), title, len(m.group(1))))
    return rows


def read(path: Path, problems: list[str], label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        problems.append(f"cannot read {label}: {error}")
        return ""


def canonical_titles(text: str, label: str, problems: list[str]) -> dict[str, str]:
    seen: dict[str, str] = {}
    for number, title, _level in headings(text):
        if number not in seen:
            seen[number] = title
        elif not title.lower().startswith(CONTINUATION):
            problems.append(
                f"{label}: {number} names two different pitfalls: {seen[number]!r} and {title!r}"
                if seen[number] != title else f"{label}: {number} appears twice with the same title")
    if not seen:
        problems.append(f"{label} carries no '## P-NNN' heading; this check would pass vacuously")
    return seen


def verify(root: Path, against: Path | None = None) -> list[str]:
    problems: list[str] = []
    text = read(root / PITFALLS, problems, PITFALLS)
    rules = read(root / RULES, problems, RULES)
    if problems:
        return problems
    seen = canonical_titles(text, PITFALLS, problems)

    ids = RULE_ID.findall(rules)
    sources = RULE_SOURCE.findall(rules)
    if not ids:
        problems.append(f"{RULES} registers no rule id; the cross-check would pass vacuously")
    for number in ids:
        if number not in seen:
            problems.append(f"RULES.toml registers {number}, but {PITFALLS} has no such section")
    for number in sources:
        if number not in seen:
            problems.append(f"RULES.toml points at {PITFALLS}:{number}, which does not exist")

    if against is not None:
        other_text = read(against, problems, str(against))
        other = canonical_titles(other_text, str(against), problems)
        for number, title in seen.items():
            if number in other and other[number] != title:
                problems.append(
                    f"{number} is a different pitfall on the other tree: ours {title!r}, "
                    f"there {other[number]!r} - renumber before merging")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--against", metavar="PITFALLS.md",
                        help="another tree's PITFALLS.md (for example main's) to catch merge collisions")
    args = parser.parse_args(argv)
    root = Path(args.root)
    problems = verify(root, Path(args.against) if args.against else None)
    if problems:
        print(f"❌ pitfall-numbers: {len(problems)} problem(s)")
        for problem in problems:
            print(f"   - {problem}")
        return 1
    entries = headings((root / PITFALLS).read_text(encoding="utf-8"))
    numbers = {int(number.split("-")[1]) for number, _title, _level in entries}
    highest = max(numbers)
    print(f"✅ pitfall-numbers: {len(numbers)} pitfall(s), highest P-{highest:03d}; "
          f"no number names two pitfalls, every registered id has a section")
    return 0


if __name__ == "__main__":
    sys.exit(main())
