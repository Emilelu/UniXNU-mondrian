#!/usr/bin/env python3
"""P-250: two patches may share a number only when one carries a letter suffix.

Merging the power line appended its ``patches/xnu/series`` tail verbatim, so the
result held two entries numbered 0624 -- the branch's platform-sleep-boot-complete
and main's quiet-managed-page-report -- and 0622/0623 each pointed at two different
files.  The build applies patches by filename, so nothing broke.  That is exactly
why the defect survived: a build proves the files exist, never that a number means
one thing.  A reader (or a future rebase) cannot tell which 0624 a document means.

Two historical collisions are deliberate and stay: 0334/0334b and 0502/0502b.  The
``-b`` suffix marks the second patch of one logical change, so the rule is not
"numbers are unique" but "a repeated number must be disambiguated by a letter suffix
on exactly one of the two".  A third pair, two bare 0392 entries for unrelated
changes, was the defect this gate found on its first run.

Usage:
    python3 scripts/check-series-numbering.py            # every series file
    python3 scripts/check-series-numbering.py --series P # one file
"""
from __future__ import annotations

import argparse
import collections
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# "0334b-k60-autoreset.patch" -> number 0334, suffix "b"
ENTRY_RE = re.compile(r'^(?P<num>\d{4})(?P<suffix>[a-z]*)-(?P<rest>.+)\.patch$')


def series_files(root: str) -> list[str]:
    found = []
    for base, _dirs, files in os.walk(os.path.join(root, 'patches')):
        if 'series' in files:
            found.append(os.path.join(base, 'series'))
    return sorted(found)


def entries(series: str) -> list[tuple[str, str, str]]:
    """Return (number, suffix, filename) for each real entry in a series file."""
    out = []
    with open(series, encoding='utf-8') as handle:
        for line in handle:
            name = line.strip()
            if not name or name.startswith('#'):
                continue
            base = os.path.basename(name)
            match = ENTRY_RE.match(base)
            if not match:
                continue
            out.append((match.group('num'), match.group('suffix'), base))
    return out


def collisions(rows: list[tuple[str, str, str]]) -> list[str]:
    """Report numbers used twice without a distinguishing letter suffix."""
    problems = []
    grouped = collections.defaultdict(list)
    for num, suffix, name in rows:
        grouped[num].append((suffix, name))
    for num in sorted(grouped):
        group = grouped[num]
        if len(group) < 2:
            continue
        suffixed = [s for s, _ in group if s]
        # Exactly one member of a pair must carry a suffix: two bare entries are
        # ambiguous, and so are two suffixed ones (nothing says which is first).
        if len(group) == 2 and len(suffixed) == 1:
            continue
        names = ', '.join(name for _, name in group)
        problems.append(f'{num}: {len(group)} entries, {len(suffixed)} suffixed ({names})')
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--series', action='append', default=None,
                    help='series file to check (default: every patches/*/series)')
    ap.add_argument('--root', default=ROOT)
    args = ap.parse_args()

    paths = args.series or series_files(args.root)
    if not paths:
        print('❌ no series file found (P-250)')
        return 1

    failures = 0
    for path in paths:
        rows = entries(path)
        problems = collisions(rows)
        label = os.path.relpath(path, args.root)
        if problems:
            failures += len(problems)
            print(f'❌ {label}: {len(problems)} ambiguous patch number(s) (P-250)')
            for problem in problems:
                print(f'   - {problem}')
        else:
            numbers = len({num for num, _, _ in rows})
            print(f'✅ {label}: {len(rows)} entries, {numbers} distinct numbers')

    if failures:
        print('   修法：给后加进来的那一条顺延到空号（如 0624 -> 0626），')
        print('   同一次改动里同时改文件名、series 和所有文档引用。')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
