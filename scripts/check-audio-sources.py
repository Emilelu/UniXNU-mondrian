#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Keep drivers/PongAudio in step with the patch chain that ships it.

The kernel build does not read drivers/PongAudio: it applies patches/xnu/0503,
0504, 0505 and patches/audio/0001, 0003 to the XNU tree. The repository copies
exist so host tests and the iOS 27 migration have something to compile, which
means they can drift silently -- 2026-11-20 the copy of PongAudioAmp.c was 27
lines behind 0001 and had lost the speaker switch drive cc added. Every gate
stayed green: the stub compile only type-checked the older file.

This gate rebuilds bsd/dev from the chain in a throwaway tree and compares the
result byte for byte. Usage:

    python3 scripts/check-audio-sources.py          # report drift, exit 1
    python3 scripts/check-audio-sources.py --write  # copy the chain output over
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRIVERS = os.path.join(ROOT, 'drivers', 'PongAudio')

# Order matters: 0505 anchors on files 0501/0503 create, 0003 on files 0001 adds.
CHAIN = [
    ('xnu', '0503-k60-audio-aw882xx.patch'),
    ('xnu', '0504-k60-audio-pong-audio.patch'),
    ('xnu', '0505-k60-audio-integration.patch'),
    ('audio', '0001-k60-audio-amp-probe.patch'),
    ('audio', '0003-k60-audio-afe-selftest.patch'),
]

# bsd/dev files the chain produces that do not belong to this line's copy.
SKIP = {
    'aw882xx.c': 'codec lane owns the amplifier driver',
    'K60PmicGlinkAudio.h': 'power lane owns the transmission header',
    'pong_audio.c': '0504 is frozen; the AudioReach graph is not carried',
}


def git(dest, *args):
    return subprocess.run(('git',) + args, cwd=dest, capture_output=True, text=True)


def extract(dest):
    """Apply the chain to an empty tree and return the bsd/dev files it made."""
    res = git(dest, 'init', '-q', '.')
    if res.returncode != 0:
        raise SystemExit('cannot init the scratch tree: ' + (res.stderr or res.stdout).strip())
    for sub, name in CHAIN:
        patch = os.path.join(ROOT, 'patches', sub, name)
        if not os.path.exists(patch):
            raise SystemExit('missing patch: ' + patch)
        res = git(dest, 'apply', '--include=bsd/dev/*', '--whitespace=nowarn', patch)
        if res.returncode != 0:
            raise SystemExit('chain broke at %s/%s: %s'
                             % (sub, name, (res.stderr or res.stdout).strip()))
        git(dest, '-c', 'user.email=audio@local', '-c', 'user.name=audio',
            'add', '-A')
        git(dest, '-c', 'user.email=audio@local', '-c', 'user.name=audio',
            'commit', '-qm', 'stage ' + name)
    dev = os.path.join(dest, 'bsd', 'dev')
    if not os.path.isdir(dev):
        raise SystemExit('the chain produced no bsd/dev directory')
    return {name: os.path.join(dev, name) for name in sorted(os.listdir(dev))
            if os.path.isfile(os.path.join(dev, name))}


def lines(path):
    with open(path, 'rb') as handle:
        return handle.read().count(b'\n')


def compare(extracted, drivers):
    """Return (checked, problems) for one extraction and one repository copy."""
    checked = []
    problems = []
    for name in sorted(extracted):
        if name in SKIP:
            continue
        source = extracted[name]
        target = os.path.join(drivers, name)
        if not os.path.exists(target):
            problems.append('%s: the chain makes it, drivers/PongAudio does not carry it' % name)
            continue
        with open(source, 'rb') as handle:
            want = handle.read()
        with open(target, 'rb') as handle:
            have = handle.read()
        if want != have:
            problems.append('%s: the chain makes %d lines, drivers/PongAudio has %d'
                            % (name, lines(source), lines(target)))
            continue
        checked.append((name, lines(source)))
    return checked, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true',
                    help='copy the chain output over drivers/PongAudio')
    ap.add_argument('--keep', action='store_true', help='keep the scratch tree')
    args = ap.parse_args()

    scratch = tempfile.mkdtemp(prefix='audio-sources-')
    try:
        extracted = extract(scratch)
        checked, problems = compare(extracted, DRIVERS)
        if args.write and problems:
            for problem in problems:
                name = problem.split(':', 1)[0]
                if name in extracted:
                    shutil.copyfile(extracted[name], os.path.join(DRIVERS, name))
            checked, problems = compare(extracted, DRIVERS)
            print('wrote %d file(s) into drivers/PongAudio' % len(checked))
        for name, count in checked:
            print('  ok    %s (%d lines)' % (name, count))
        for problem in problems:
            print('  DRIFT ' + problem)
        print('sources: %d file(s) compared against the patch chain' % len(checked))
    finally:
        if not args.keep:
            shutil.rmtree(scratch, ignore_errors=True)
        else:
            print('scratch: ' + scratch)

    if problems:
        print('FAILED: drivers/PongAudio is not what the chain ships; run --write')
        return 1
    print('OK: drivers/PongAudio matches the patch chain')
    return 0


if __name__ == '__main__':
    sys.exit(main())
