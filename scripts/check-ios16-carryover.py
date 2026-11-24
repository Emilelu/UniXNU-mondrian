#!/usr/bin/env python3
'''Iron gate: every ios16 kernel patch must carry a verdict for the 27 line.

Refuses the build while any patch in docs/research/ios27/IOS16-CARRYOVER.toml
still lacks a verdict, or while a patch the inventory cannot find on the 27
side is claimed as carried.
'''
import sys, tomllib, pathlib
REPO = pathlib.Path(__file__).resolve().parents[1]
LEDGER = REPO / 'docs/research/ios27/IOS16-CARRYOVER.toml'
ALLOWED = {'carried', 'deferred', 'not-applicable'}
def main():
    if not LEDGER.exists():
        print(f'FAIL ios16-carryover: {LEDGER.relative_to(REPO)} is missing', file=sys.stderr); return 1
    data = tomllib.loads(LEDGER.read_text())
    rows = data.get('patch', [])
    bad = []
    for row in rows:
        name = row.get('name', '?'); verdict = row.get('verdict', '').strip(); detected = row.get('detected', '')
        if verdict not in ALLOWED:
            bad.append(f'{name}: no verdict (detected {detected})')
        elif verdict == 'carried' and detected in ('partial', 'missing'):
            bad.append(f'{name}: claimed carried but the inventory finds it {detected}')
    if bad:
        for line in bad[:20]: print(f'FAIL ios16-carryover: {line}', file=sys.stderr)
        print(f'FAIL ios16-carryover: {len(bad)} of {len(rows)} patch(es) unclassified', file=sys.stderr)
        return 1
    print(f'OK ios16-carryover: {len(rows)} patch(es) classified')
    return 0
if __name__ == '__main__':
    sys.exit(main())
