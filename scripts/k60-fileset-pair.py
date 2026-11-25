#!/usr/bin/env python3
"""Add reviewed data pairings to a fileset map, so prelink can resolve them.

The kit pairs Apple's collection to our kernel by matching, and anything it
cannot pair ends up in `missing` -- for data references there is no stub, so an
unpaired global silently keeps a stale address. The kit already accepts a
`data` table in its map (`fileset_emit.emit_images` folds `payload['data']` into
the same pairs dict as `payload['functions']`); it simply has nothing to put
there for the globals it could not match. This tool takes the reviewed
`[[pairing]]` entries from docs/engineering/IOS27-PRELINK-ALLOWLIST.toml, checks
that the native kernel really defines the claimed symbol at the claimed address,
and folds them in.

Two things are deliberate:

  * the signature is recomputed with the kit's own `expected_signature`, because
    a hand-edited map is otherwise either rejected or silently ignored;
  * `--check` verifies the map is consistent without writing, so a build can
    prove the state it is about to use.
"""

import argparse
import json
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

KIT = Path('/opt/k60/trees/ios27-fw/kits/XnuPrelink')
NM = '/usr/bin/llvm-nm-18'


def symbols(path, nm=NM):
    """Address -> names, from the native kernel's own symbol table."""
    out = subprocess.run([nm, '-n', '--defined-only', str(path)],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit('cannot read %s with %s: %s'
                         % (path, nm, out.stderr.strip() or 'no output'))
    table = {}
    for line in out.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3:
            table.setdefault(int(parts[0], 16), []).append(parts[2])
    return table


def reviewed(allowlist):
    document = tomllib.loads(Path(allowlist).read_text(encoding='utf-8'))
    rows = []
    for entry in document.get('pairing', []):
        missing = [key for key in ('address', 'target', 'reason', 'review') if not entry.get(key)]
        if missing:
            raise SystemExit('%s: [[pairing]] has no %s' % (allowlist, ', '.join(missing)))
        rows.append(entry)
    return rows


def signature(payload):
    sys.path.insert(0, str(KIT))
    from fileset_names import expected_signature
    return expected_signature(payload)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('map', help='kernel.map.json written by emit_prelink.py')
    parser.add_argument('--allowlist', required=True,
                        help='docs/engineering/IOS27-PRELINK-ALLOWLIST.toml')
    parser.add_argument('--native', required=True,
                        help='the native kernel the map was built against')
    parser.add_argument('--check', action='store_true',
                        help='verify only; exit 1 if the map is out of date')
    arguments = parser.parse_args(argv)

    payload = json.loads(Path(arguments.map).read_text(encoding='utf-8'))
    table = symbols(arguments.native)
    pairs = payload.setdefault('data', {})

    added = unchanged = 0
    problems = []
    for entry in reviewed(arguments.allowlist):
        address = int(entry['address'], 16)
        target = int(entry['target'], 16)
        names = table.get(target)
        if not names:
            problems.append('%s: the native kernel defines nothing at %s'
                            % (entry['address'], entry['target']))
            continue
        # The name in `reason` is documentation; the address is what binds. Check
        # that some name at that address shares a token with the claim, so a
        # shuffled target fails instead of quietly pointing somewhere else.
        claim = entry.get('symbol') or entry['reason'].split()[0].split('::')[0]
        if not any(claim.split('/')[0].strip('_') in name for name in names):
            problems.append('%s: %s holds %s, not %s'
                            % (entry['address'], entry['target'], ', '.join(names), claim))
            continue
        key = hex(address)
        value = {'native': hex(target)}
        if pairs.get(key) == value:
            unchanged += 1
        else:
            pairs[key] = value
            added += 1

    if problems:
        for problem in problems:
            print('FAIL ' + problem)
        return 1

    stale = payload.get('matcher_signature') != signature(payload)
    if stale:
        payload['matcher_signature'] = signature(payload)

    if arguments.check:
        print('map %s: %d pairing(s) present, %d to add, signature %s'
              % (arguments.map, unchanged, added, 'stale' if stale else 'current'))
        return 1 if (added or stale) else 0

    if added or stale:
        with tempfile.NamedTemporaryFile('w', delete=False,
                                         dir=str(Path(arguments.map).parent),
                                         encoding='utf-8') as handle:
            json.dump(payload, handle, indent=2)
            handle.write('\n')
            temporary = Path(handle.name)
        temporary.replace(arguments.map)
    print('map %s: %d pairing(s) kept, %d added, signature %s'
          % (arguments.map, unchanged, added, 'rewritten' if stale else 'unchanged'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
