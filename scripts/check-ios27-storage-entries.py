#!/usr/bin/env python3
"""Report whether the kernel collection carries a fileset entry for NativeUfs.

Route B keeps the UFS driver out of the kernel image's own link: the driver
becomes its own fileset entry, so its imports of the public IOStorageFamily
classes resolve against a sibling entry at prelink time instead of against
com.apple.kernel. Whether that happened is visible in the product: the outer
MH_FILESET lists one entry per kext, and the driver's bundle has to be one of
them. This checker answers that question for any kernel collection.

It reads the same structures as check-ios27-storage-exports.py
(LC_FILESET_ENTRY 0x80000035, entry_id relative to the load command) and
reports, for each name it was given, which entry carries it. An absent entry is
a state, not an error: without --require-entry the exit code stays 0.
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_MATCHES = ('NativeUfs', 'native-ufs')


def exports_module():
    spec = importlib.util.spec_from_file_location('storage_exports', HERE / 'check-ios27-storage-exports.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def entries(path):
    module = exports_module()
    parsed = module.parse_file(path)
    image = parsed['image']
    if image['filetype'] != module.MH_FILESET:
        raise ValueError('filetype %d is not a fileset (MH_FILESET 12)' % image['filetype'])
    return image, [entry['name'] for entry in parsed['entries']]


def match(names, patterns):
    hits = []
    for name in names:
        lowered = name.lower()
        for pattern in patterns:
            if pattern.lower() in lowered:
                hits.append((pattern, name))
                break
    return hits


def main():
    parser = argparse.ArgumentParser(description='Say whether the kernel carries a NativeUfs fileset entry.')
    parser.add_argument('--kernelcache', type=Path, required=True)
    parser.add_argument('--match', action='append', dest='matches')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--require-entry', action='store_true')
    args = parser.parse_args()
    patterns = args.matches or list(DEFAULT_MATCHES)
    report = {'kernel': str(args.kernelcache), 'matches': patterns, 'hardware_verified': False}
    try:
        image, names = entries(args.kernelcache)
    except Exception as error:
        print('FAILED: %s: %s' % (args.kernelcache, error))
        report['failures'] = [str(error)]
        if args.out:
            args.out.write_text(json.dumps(report, indent=2) + '\n')
        print('ios27-storage-entries: FAILED')
        return 1
    hits = match(names, patterns)
    report.update({
        'filetype': image['filetype'],
        'entry_count': len(names),
        'entries': names,
        'matched': [{'pattern': pattern, 'entry': name} for pattern, name in hits],
        'verdict': 'present' if hits else 'absent',
    })
    print('kernel: %s' % args.kernelcache)
    print('filetype: %d MH_FILESET' % image['filetype'])
    print('entries: %d' % len(names))
    for name in names:
        print('  %s' % name)
    if hits:
        for pattern, name in hits:
            print('matched %s in %s' % (pattern, name))
    else:
        print('no entry matches %s' % ', '.join(patterns))
    if args.out:
        args.out.write_text(json.dumps(report, indent=2) + '\n')
    if hits:
        print('ios27-storage-entries: present')
        return 0
    print('ios27-storage-entries: absent')
    return 1 if args.require_entry else 0


if __name__ == '__main__':
    sys.exit(main())
