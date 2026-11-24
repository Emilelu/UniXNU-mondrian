#!/usr/bin/env python3
"""Check that every live branch is registered with an owner and a purpose.

Fails when a non-archive remote branch that is ahead of main has no entry in
docs/engineering/BRANCH-REGISTRY.toml.  Entries whose purpose/merge_plan are
still TBD are reported as a warning count so the build log keeps showing the
debt until the owning line fills it in.
"""
import subprocess
import sys
import tomllib
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = REPO / 'docs/engineering/BRANCH-REGISTRY.toml'


def main():
    if not REGISTRY.exists():
        print('FAIL branch-registry: %s is missing' % REGISTRY.relative_to(REPO), file=sys.stderr)
        return 1
    data = tomllib.loads(REGISTRY.read_text())
    rows = data.get('branch', [])
    known = {r.get('name') for r in rows}
    refs = subprocess.run(['git', 'for-each-ref', '--format=%(refname:short)', 'refs/remotes/origin'],
                          cwd=REPO, capture_output=True, text=True).stdout.splitlines()
    missing = []
    for ref in refs:
        name = ref.replace('origin/', '').strip()
        if not name or 'HEAD' in name or name.startswith('archive/'):
            continue
        ahead = subprocess.run(['git', 'rev-list', '--count', 'origin/main..' + ref],
                               cwd=REPO, capture_output=True, text=True).stdout.strip() or '0'
        if ahead == '0':
            continue
        if name not in known:
            missing.append(name)
    if missing:
        for name in missing:
            print('FAIL branch-registry: %s has no entry' % name, file=sys.stderr)
        print('FAIL branch-registry: %d branch(es) unregistered' % len(missing), file=sys.stderr)
        return 1
    tbd = [r.get('name') for r in rows if r.get('purpose') in ('TBD', '') or r.get('merge_plan') in ('TBD', '')]
    if tbd:
        print('WARN branch-registry: %d of %d entr(ies) still need a purpose/merge_plan from their line:' % (len(tbd), len(rows)))
        for name in tbd[:12]:
            print('  - ' + name)
        if len(tbd) > 12:
            print('  ... %d more' % (len(tbd) - 12))
    print('OK branch-registry: %d entr(ies), %d TBD' % (len(rows), len(tbd)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
