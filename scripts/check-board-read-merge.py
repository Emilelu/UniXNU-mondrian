#!/usr/bin/env python3
"""A gate that reads board.toml must merge os_overrides first (P-305 family).

Twice in one day a checker compared the base table against a 27 image or a 27
board and reported differences that the merged contract does not have: 66 phantom
GAPs in audit-ios27-conformance.py and three phantom missing arguments in
check-image-args.py. Both were "read the top level of board.toml", which is only
correct for a board without os_overrides.

This gate is deliberately a reading, not a proof: it looks for scripts that parse
board.toml and do not mention any merge path. It cannot tell whether a given read
is of a merged value, so by default it reports and exits 0; --strict exits 1.
"""
import argparse
import pathlib
import re
import sys

MERGE_HINTS = ('os_overrides', 'profiles.merge', 'effective(', 'merge_board', 'profile_merge')
READS = re.compile(r'tomllib\.loads|tomllib\.load')
BOARD = re.compile(r'board\.toml')


def board_has_overrides(board):
    text = board.read_text(encoding='utf-8', errors='replace')
    return bool(re.search(r'^\[os_overrides', text, re.MULTILINE))


ALLOW = pathlib.Path(__file__).resolve().parent / 'BOARD-READ-MERGE.toml'


def allowed():
    """Scripts reviewed as deliberately reading the base table.

    The gate cannot tell which key a read touches, so the review is recorded once
    here with a reason instead of leaving every reader permanently red (P-290).
    """
    if not ALLOW.is_file():
        return {}
    import tomllib
    data = tomllib.loads(ALLOW.read_text(encoding='utf-8'))
    return {entry['script']: entry.get('why', '') for entry in data.get('reviewed', [])}


def suspects(scripts):
    found = []
    for path in sorted(scripts.glob('*.py')):
        try:
            text = path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        if not BOARD.search(text) or not READS.search(text):
            continue
        if any(hint in text for hint in MERGE_HINTS):
            continue
        found.append(path.name)
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default=str(pathlib.Path(__file__).resolve().parents[1]))
    parser.add_argument('--strict', action='store_true')
    options = parser.parse_args()

    repo = pathlib.Path(options.repo)
    board = repo / 'board.toml'
    if not board.is_file():
        print(f'note board-merge: no board.toml under {repo}; nothing to judge', file=sys.stderr)
        return 0
    if not board_has_overrides(board):
        print('ok board-merge: this board declares no os_overrides, so the base table is the contract')
        return 0

    reviewed = allowed()
    names = [name for name in suspects(repo / 'scripts') if name not in reviewed]
    if not names:
        print('ok board-merge: every script that parses board.toml names a merge path')
        return 0
    print(f'note board-merge: {len(names)} script(s) parse board.toml without naming a merge path: '
          + ', '.join(names))
    print(f'     {len(reviewed)} script(s) are reviewed in {ALLOW.name}; new readers are the problem')
    print('     this board declares os_overrides, so the contract is the merged table (P-305)')
    return 1 if options.strict else 0


if __name__ == '__main__':
    sys.exit(main())
