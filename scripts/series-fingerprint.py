#!/usr/bin/env python3
"""series-fingerprint.py -- one series fingerprint, one implementation (P-214).

Three tools ask "which patch series is this?" and until now each answered with
its own hash:

  * scripts/build-strict.sh wrote ``sha256(<bytes of patches/xnu/series>)`` into
    ``build-manifest.json``;
  * scripts/porting-gate.py and scripts/record-boot.py computed
    ``sha256(name + str(size) for every entry)`` and truncated it to 16 hex.

Both are stable, both look like a fingerprint, and they never agree.  The damage
appeared the day record-boot started preferring the manifest (P-211): the ledger
gained rows in the *file* namespace while the gate kept comparing in the
*names+sizes* namespace, so "the series that last booted" could never equal "the
series in the tree" and iron-4 blocked every merge.  The ledger looked healthy
and the gate looked strict; only the units were different.

This script is the single implementation.  The names+sizes form is kept because
it is the one the ledger already uses and because it also catches a patch whose
name stayed but whose content changed size.

Usage:
    python3 scripts/series-fingerprint.py [--json] [series-file] [patches-dir]

Default arguments are the repository this script lives in.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys


def fingerprint(series: pathlib.Path, patches: pathlib.Path) -> tuple[str, int]:
    """sha256(names + sizes)[:16] and the number of entries.

    Matches porting-gate.py and record-boot.py byte for byte: the name is hashed
    as-is (no separator), then the decimal size when the file exists.
    """
    digest = hashlib.sha256()
    names = [line.strip() for line in series.read_text(encoding='utf-8', errors='ignore').splitlines()
             if line.strip()]
    for name in names:
        digest.update(name.encode())
        candidate = patches / name
        if candidate.exists():
            digest.update(str(candidate.stat().st_size).encode())
    return digest.hexdigest()[:16], len(names)


def main(argv: list[str] | None = None) -> int:
    repo = pathlib.Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description='one series fingerprint, one implementation (P-214)')
    parser.add_argument('series', nargs='?', default=str(repo / 'patches/xnu/series'))
    parser.add_argument('patches', nargs='?', default=str(repo / 'patches/xnu'))
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)

    series = pathlib.Path(args.series)
    patches = pathlib.Path(args.patches)
    if not series.is_file():
        print(f'series-fingerprint: no series file at {series}', file=sys.stderr)
        return 2
    value, count = fingerprint(series, patches)
    if args.json:
        print(json.dumps({'fingerprint': value, 'count': count}))
    else:
        print(f'{value} {count}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
