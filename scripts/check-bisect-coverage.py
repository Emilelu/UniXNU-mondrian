#!/usr/bin/env python3
"""Refuse a bisect whose images exist but were never flown (P-218).

A bisect over N hunks has 2**N - 1 non-empty subsets.  The mistake P-218 records
is not arithmetic: it is flying "the next one" turn after turn while a built,
unflown image sits in the artifacts directory holding the decisive cell.  So the
check is a set difference, not a coverage percentage:

    built = every boot.img that has a build-manifest.json
    flown = every image an evidence directory recorded in boot.json
    stale = built - flown

**The flight record is `boot.json`, not the ledger.**  `record-boot.py` refuses a
log with fewer than 100 SpringBoard lines, so the ledger only contains flights
that reached the desktop.  A silent image — exactly the ones a bisect cares most
about — leaves no ledger row, and using the ledger as the "flown" set reports
every silent image as never flown.  `flash.sh` writes `boot.json` on every
flight, including `port-not-observed`, so that is the honest record.

Exit 0 clean, 1 stale images found, 2 the inputs could not be read.
"""
import argparse
import json
import os
import sys

ARTIFACTS = '/mnt/e/iOS Port/Work/artifacts'
EVIDENCE = '/mnt/e/iOS Port/Work/evidence'


def built_images(artifacts, prefix=''):
    """Yield (name, boot_img_sha256, mtime) for every built image."""
    if not os.path.isdir(artifacts):
        return
    for name in sorted(os.listdir(artifacts)):
        if prefix and not name.startswith(prefix):
            continue
        directory = os.path.join(artifacts, name)
        manifest = os.path.join(directory, 'build-manifest.json')
        boot = os.path.join(directory, 'boot.img')
        if not (os.path.isfile(manifest) and os.path.isfile(boot)):
            continue
        try:
            with open(manifest, encoding='utf-8-sig') as handle:
                data = json.load(handle)
        except (ValueError, OSError):
            continue
        sha = (data.get('components') or {}).get('boot_img') or ''
        if not sha:
            continue
        yield name, sha, os.stat(boot).st_mtime


def flown_images(evidence):
    """Every (artifact directory name, sha256) a flight recorded.

    `boot.json` is written by `flash.sh` before the console is read, so it exists
    for silent images too.  Both the full path and the hash are returned: the
    path identifies the artifact directory, the hash survives a rename.
    """
    names = set()
    hashes = set()
    if not os.path.isdir(evidence):
        return names, hashes
    for entry in sorted(os.listdir(evidence)):
        path = os.path.join(evidence, entry, 'boot.json')
        if not os.path.isfile(path):
            continue
        try:
            # PowerShell writes these files with a UTF-8 BOM; `utf-8-sig` strips
            # it, and without that every row parses as a ValueError and the
            # whole evidence directory looks empty (the P-218 failure mode again).
            with open(path, encoding='utf-8-sig') as handle:
                row = json.load(handle)
        except (ValueError, OSError):
            continue
        sha = (row.get('imageSha256') or '').strip().lower()
        if len(sha) == 64:
            hashes.add(sha)
        image = (row.get('image') or '').strip().replace('\\', '/')
        if image:
            parts = [p for p in image.split('/') if p]
            if len(parts) >= 2:
                names.add(parts[-2])
    return names, hashes


def stale_images(artifacts, evidence, prefix='', since=0.0):
    flown_names, flown_hashes = flown_images(evidence)
    stale = []
    for name, sha, mtime in built_images(artifacts, prefix):
        if mtime < since:
            continue
        if name in flown_names or sha.lower() in flown_hashes:
            continue
        stale.append((name, sha, mtime))
    return stale


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', default=ARTIFACTS)
    parser.add_argument('--evidence', default=EVIDENCE)
    parser.add_argument('--prefix', default='', help='only images whose directory starts with this')
    parser.add_argument('--since', type=float, default=0.0, help='unix time; ignore older images')
    args = parser.parse_args(argv)

    if not os.path.isdir(args.artifacts):
        print('❌ artifacts directory not found: %s' % args.artifacts)
        return 2

    stale = stale_images(args.artifacts, args.evidence, args.prefix, args.since)
    if not stale:
        print('✅ bisect coverage: every built image under %r has a flight recorded'
              % (args.prefix or '<all>'))
        return 0

    print('❌ %d built image(s) were never flown (P-218):' % len(stale))
    for name, sha, _ in stale:
        print('   %-28s %s' % (name, sha))
    print('   A built-but-unflown image can hold the decisive cell; fly it or delete it.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
