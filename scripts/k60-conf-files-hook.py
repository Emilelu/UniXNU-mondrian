#!/usr/bin/env python3
"""Append this tree's driver entries to bsd/conf/files (seam 1, P-266).

Why a hook and not a patch: `bsd/conf/files` is re-seeded from the feed on every
build, so a hunk against it cannot survive (P-171). The builder calls this after
the tree exists; it only names files that are actually on disk, and it prints
what it added so the log answers "did my driver get compiled" without a rebuild.

Entries live in `patches/xnu-12377/conf-files.txt`, one `path<TAB>tag` per line.
Adding a driver means adding a line, not editing a hunk.
"""
import argparse
import os
import sys
from pathlib import Path

LIST = Path('patches/xnu-12377/conf-files.txt')
ANCHOR = 'bsd/dev/unix_startup.c'


def entries(path):
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        if len(parts) != 2:
            raise SystemExit(f'{path}: expected "path<TAB>tag", got {line!r}')
        yield parts[0], parts[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tree_arg', nargs='?', default=None,
                        help='the assembled tree, as a positional (how the builder calls this)')
    parser.add_argument('--tree', default=None, help='the assembled tree')
    parser.add_argument('--list', default=None, help='override the entry list')
    options = parser.parse_args()

    root = Path(options.tree or options.tree_arg or '.').resolve()
    names = Path(options.list).resolve() if options.list else root / LIST
    conf = root / '.cache/xnu-work/bsd/conf/files'
    if not conf.is_file():
        print(f'error: no bsd/conf/files under {root}', file=sys.stderr)
        return 2

    text = conf.read_text(encoding='utf-8')
    if ANCHOR not in text:
        print(f'error: {ANCHOR} is not in bsd/conf/files; refusing to guess a location', file=sys.stderr)
        return 2

    added, skipped, missing = [], [], []
    for source, tag in entries(names):
        if not (root / '.cache/xnu-work' / source).is_file():
            missing.append(source)
            continue
        needle = f'{source}\t\t\t{tag}'
        if needle in text:
            skipped.append(source)
            continue
        added.append(needle)

    if missing:
        print(f'note conf-files: {len(missing)} entr(ies) name a file that is not in this tree: '
              + ', '.join(missing))
    if added:
        text = text.rstrip('\n') + '\n' + '\n'.join(added) + '\n'
        conf.write_text(text, encoding='utf-8')
    print(f'ok conf-files: added {len(added)}, already present {len(skipped)}, absent {len(missing)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
