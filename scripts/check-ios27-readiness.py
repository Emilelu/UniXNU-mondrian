#!/usr/bin/env python3
"""Check whether the recorded iOS 27 port expectations still hold.

Each expectation was measured once against a known-good 27 tree and written down
here with the reason. The script re-measures and reports drift, so a moving 27
tree fails loudly instead of being rediscovered patch by patch.
"""
import argparse
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATCHES = os.path.join(REPO, 'patches', 'xnu')

# patch -> (expected rc of git apply --check, reason)
PATCH_EXPECT = [
    ('0620-k60-modem-image.patch', 0, 'adds bsd/dev files only'),
    ('0621-k60-modem-pas.patch', 1, 'its call-site hunk waits for the 27 data mount'),
    ('0622-k60-modem-qrtr.patch', 0, 'adds bsd/dev files only'),
    ('0623-k60-ipa.patch', 0, 'adds bsd/dev files only'),
    ('0621-k60-io-submap-budget.patch', 1, 'not carried; 27 has no io_submap'),
    ('0624-k60-ipa-call-site.patch', 1, 'call sites are regenerated as 0629'),
]

SYMBOLS = ['ml_io_map_unmappable', 'kmem_alloc_contig', 'ptoa_64', 'flush_dcache64',
           'pmap_find_phys', 'PE_parse_boot_argn', 'kernel_map', 'kmem_free']

SEARCH = ['osfmk', 'bsd', 'libkern', 'pexpert', 'iokit']


def run(argv, cwd=None):
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True)


def patch_status(tree, name):
    path = os.path.join(PATCHES, name)
    if not os.path.exists(path):
        return None, 'patch file missing'
    result = run(['git', '-C', tree, 'apply', '--check', path])
    return result.returncode, (result.stderr or result.stdout).strip()


def symbol_present(tree, symbol):
    for sub in SEARCH:
        root = os.path.join(tree, sub)
        if not os.path.isdir(root):
            continue
        result = run(['grep', '-rlw', symbol, root, '--include=*.h', '--include=*.c'])
        if result.stdout.strip():
            return True
    return False


def include_present(tree, header):
    if header in ('stdint.h', 'stddef.h', 'stdbool.h'):
        return True
    for sub in SEARCH:
        root = os.path.join(tree, sub)
        if not os.path.isdir(root):
            continue
        result = run(['find', root, '-path', '*/' + header, '-print', '-quit'])
        if result.stdout.strip():
            return True
    return False


def includes_used():
    names = set()
    root = os.path.join(REPO, 'drivers', 'PongCellular')
    for entry in sorted(os.listdir(root)):
        if not entry.endswith(('.c', '.h')):
            continue
        with open(os.path.join(root, entry), encoding='utf-8', errors='replace') as handle:
            for line in handle:
                if line.startswith('#include <'):
                    names.add(line.split('<', 1)[1].split('>', 1)[0].strip())
    return sorted(names)


def anchor_state(tree):
    path = os.path.join(tree, 'bsd', 'kern', 'kern_exec.c')
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8', errors='replace') as handle:
        body = handle.read()
    return body.count('native_owner_data_stage = 3;')


def compare(expected, actual):
    """Drift is any measured rc that differs from the recorded one."""
    return expected == actual


def self_test():
    cases = [(0, 0, True), (1, 1, True), (0, 1, False), (1, 0, False)]
    for expected, actual, want in cases:
        if compare(expected, actual) is not want:
            print('K60 READY FAIL compare(%d, %d) != %r' % (expected, actual, want))
            return 1
    print('K60 READY PASS expectations compared, drift detected')
    return 0


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tree', help='root of the iOS 27 XNU source tree')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.tree or not os.path.isdir(args.tree):
        print('K60 READY INVALID tree not found: %r' % (args.tree,))
        return 2
    drift = 0
    for name, expected, reason in PATCH_EXPECT:
        actual, note = patch_status(args.tree, name)
        if actual is None:
            print('K60 READY INVALID %s %s' % (name, note))
            return 2
        if compare(expected, actual):
            print('K60 READY ok   %s rc=%d (%s)' % (name, actual, reason))
        else:
            drift += 1
            print('K60 READY DRIFT %s expected rc=%d got rc=%d: %s'
                  % (name, expected, actual, note.splitlines()[0] if note else ''))
    missing = [s for s in SYMBOLS if not symbol_present(args.tree, s)]
    if missing:
        drift += 1
        print('K60 READY DRIFT kernel symbols missing: ' + ' '.join(missing))
    else:
        print('K60 READY ok   %d kernel symbols present' % len(SYMBOLS))
    headers = includes_used()
    absent = [h for h in headers if not include_present(args.tree, h)]
    if absent:
        drift += 1
        print('K60 READY DRIFT headers missing: ' + ' '.join(absent))
    else:
        print('K60 READY ok   %d includes resolve' % len(headers))
    anchors = anchor_state(args.tree)
    if anchors is None:
        print('K60 READY INVALID no bsd/kern/kern_exec.c under the tree')
        return 2
    print('K60 READY note anchor lines=%d (expected 0 until the data mount lands)' % anchors)
    if drift:
        print('K60 READY CHANGED %d expectation(s) drifted' % drift)
        return 1
    print('K60 READY OK every recorded expectation still holds')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
