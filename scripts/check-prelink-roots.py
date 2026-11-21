"""Judge the prelink root list we hand to the kit.

`dependency_closure()` raises `Missing prelink dependency` for a root the kernelcache
does not carry, and `profiles.merge()` replaces lists, so the device layer has to
repeat the OS profile's set. Both make a hand-edited list unsafe, hence this check:

  1. no duplicate entries;
  2. every included root exists in the kernelcache we prelink against;
  3. no bundle is both a root and an exclusion;
  4. the list still covers every root the OS profile declares (P-306).

Exit codes: 0 conformant, 1 violations, 2 cannot judge (missing input).
"""

import argparse
import os
import plistlib
import struct
import sys
import tomllib

DEFAULT_CACHE = '/home/emilelu/kc24A446/ipsw/24A446/kernelcache.decompressed'
LC_SEGMENT_64 = 0x19


def read_roots(board):
    with open(board, 'rb') as fh:
        doc = tomllib.load(fh)
    roots = doc.get('kernel', {}).get('prelink', {}).get('roots') or []
    return [str(r) for r in roots]


def read_profile_roots(framework, profile):
    path = os.path.join(framework, 'profiles', 'os', profile, 'profile.toml')
    if not os.path.isfile(path):
        return None, path
    with open(path, 'rb') as fh:
        doc = tomllib.load(fh)
    return [str(r) for r in (doc.get('kernel', {}).get('prelink', {}).get('roots') or [])], path


def kernelcache_bundles(path):
    """Bundle identifiers inside __PRELINK_INFO, or None when unreadable."""
    try:
        data = open(path, 'rb').read()
    except OSError:
        return None
    if struct.unpack_from('<I', data, 0)[0] != 0xFEEDFACF:
        return None
    ncmds = struct.unpack_from('<I', data, 16)[0]
    at = 32
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from('<II', data, at)
        if cmd == LC_SEGMENT_64 and data[at + 8:at + 24].split(b'\0', 1)[0] == b'__PRELINK_INFO':
            fileoff, filesize = struct.unpack_from('<QQ', data, at + 40)
            blob = data[fileoff:fileoff + filesize].split(b'\0', 1)[0]
            doc = plistlib.loads(blob)
            return {e['CFBundleIdentifier'] for e in doc['_PrelinkInfoDictionary']}
        at += cmdsize
    return None


def judge(roots, profile_roots, bundles):
    problems = []
    seen, duplicates = set(), []
    for root in roots:
        if root in seen:
            duplicates.append(root)
        seen.add(root)
    problems += ['duplicate entry: %s' % r for r in sorted(set(duplicates))]

    included = {r for r in roots if not r.startswith('!')}
    excluded = {r[1:] for r in roots if r.startswith('!')}
    problems += ['both a root and an exclusion: %s' % b for b in sorted(included & excluded)]

    if bundles is not None:
        problems += ['not in the kernelcache: %s' % r for r in sorted(included - bundles)]

    if profile_roots is not None:
        covered = included | excluded
        missing = [r for r in profile_roots if not r.startswith('!') and r not in covered]
        problems += ['the OS profile declares it, the board list dropped it: %s' % r for r in
                     sorted(missing)]
    return problems, len(included), len(excluded)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board', default='board.toml')
    parser.add_argument('--framework', default='../UniXNU')
    parser.add_argument('--kernelcache', default=os.environ.get('K60_KERNELCACHE', DEFAULT_CACHE))
    parser.add_argument('--strict-kernelcache', action='store_true',
                        help='a missing kernelcache is a failure, not "cannot judge"')
    args = parser.parse_args(argv)

    try:
        roots = read_roots(args.board)
    except OSError as exc:
        print('FAIL: cannot read %s: %s' % (args.board, exc))
        return 2
    if not roots:
        print('FAIL: no [kernel.prelink].roots in %s; the kit would fall back to its own default' % args.board)
        return 1

    with open(args.board, 'rb') as fh:
        profile = tomllib.load(fh).get('board', {}).get('os_profile', '')
    profile_roots, profile_path = read_profile_roots(args.framework, profile)
    if profile_roots is None:
        print('note: no %s; the OS profile layer was not compared' % profile_path)

    bundles = kernelcache_bundles(args.kernelcache)
    if bundles is None:
        print('note: cannot read the kernelcache at %s; root membership was not judged (P-279: '
              'unreadable is not the same as absent)' % args.kernelcache)
        if args.strict_kernelcache:
            return 2

    problems, included, excluded = judge(roots, profile_roots, bundles)
    for problem in problems:
        print('FAIL: %s' % problem)
    if problems:
        print('FAILED %d problem(s) in the prelink root list' % len(problems))
        return 1
    print('OK prelink roots: %d included, %d excluded%s'
          % (included, excluded,
             '' if profile_roots is None else ', covers the OS profile\'s %d' % len(profile_roots)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
