#!/usr/bin/env python3
"""Compare our component sources against the Pong reference tree.

The branch sync in k60-sync-refs.sh only reports moved git branches. It says
nothing about the component sources we keep a local copy of under drivers/,
which is where a Darwin 24 fix can sit already written in the reference tree
while our copy stays on the Darwin 22 order. The ArmCpu start order was such
a fix: it sat in UniXNU-pong's drivers/ArmCpu/ArmCpu.cpp behind a
PONG_DARWIN_MAJOR >= 24 guard, and the unit only found it after a panic
named the assertion.

Prints, per shared component, the files that differ and how large the
difference is, so a reviewer can decide what to take. Read-only.
"""
import argparse
import difflib
import subprocess
import sys
from pathlib import Path

DEVICE = Path(__file__).resolve().parents[1]
REFERENCE = Path('/home/emilelu/hackios/UniXNU-pong')

# Files that are expected to differ: the licence and the bundle metadata are
# per-repository, and the DarwinBoot component is a different major version.
SKIP_SUFFIX = ('.plist',)
SKIP_NAMES = ('LICENSE', 'LICENSE.txt')


def summarise(ours: Path, theirs: Path) -> str:
    """Return a one-line description of the difference between two files."""
    a = ours.read_text(errors='replace').splitlines()
    b = theirs.read_text(errors='replace').splitlines()
    diff = list(difflib.unified_diff(a, b, lineterm='', n=0))
    changed = sum(1 for line in diff
                  if (line.startswith('+') or line.startswith('-'))
                  and not line.startswith(('+++', '---')))
    added = sum(1 for line in diff if line.startswith('+') and not line.startswith('+++'))
    removed = sum(1 for line in diff if line.startswith('-') and not line.startswith('---'))
    return f'{changed} changed lines ({added}+ {removed}-)'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, default=REFERENCE,
                        help='reference tree to compare against')
    parser.add_argument('--component', action='append',
                        help='only this component (repeatable)')
    args = parser.parse_args()

    reference = args.reference.resolve()
    if not (reference / 'drivers').is_dir():
        print(f'no drivers directory under {reference}', file=sys.stderr)
        return 1

    ours_root = DEVICE / 'drivers'
    ours_root.mkdir(parents=True, exist_ok=True)

    components = sorted(p.name for p in ours_root.iterdir() if p.is_dir())
    if args.component:
        components = [c for c in components if c in args.component]

    differences = 0
    for name in components:
        ours = ours_root / name
        theirs = reference / 'drivers' / name
        if not theirs.is_dir():
            print(f'{name}: not in the reference tree')
            continue

        ours_files = sorted(p for p in ours.rglob('*')
                            if p.is_file() and p.suffix not in SKIP_SUFFIX
                            and p.name not in SKIP_NAMES)
        differing = []
        for path in ours_files:
            other = theirs / path.relative_to(ours)
            if not other.is_file():
                differing.append((path.relative_to(ours), 'only in this repository'))
            elif path.read_bytes() != other.read_bytes():
                differing.append((path.relative_to(ours), summarise(path, other)))

        extra = sorted(p.relative_to(theirs) for p in theirs.rglob('*')
                       if p.is_file() and p.suffix not in SKIP_SUFFIX
                       and p.name not in SKIP_NAMES
                       and not (ours / p.relative_to(theirs)).is_file())

        if not differing and not extra:
            print(f'{name}: identical')
            continue

        differences += len(differing) + len(extra)
        print(f'{name}: {len(differing)} differing file(s), {len(extra)} only in the reference')
        for rel, note in differing:
            print(f'    {rel}: {note}')
        for rel in extra:
            print(f'    {rel}: only in the reference tree')

    print()
    if differences:
        print(f'{differences} difference(s). Read each one before quoting the reference code.')
    else:
        print('every shared component matches the reference tree.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
