#!/usr/bin/env python3
"""Replay the four patch layers in build order on a throwaway clone of the pinned XNU feed.

This is not a build: it clones nothing from the network (`--shared` against the local feed),
applies patches with `git apply`, and reports the first one that fails. It answers the
question a compile cannot answer cheaply: "does the whole series still apply in order?"
"""
import argparse
import pathlib
import shutil
import subprocess
import sys

FEED = pathlib.Path('/opt/k60/trees/ios27-out/feeds/xnu-3199e8bc')
FRAMEWORK = pathlib.Path('/opt/k60/trees/ios27-fw')
SELF = pathlib.Path(__file__).resolve().parents[1]

LAYERS = (
    ('arch', FRAMEWORK / 'patches/xnu'),
    ('soc', pathlib.Path('/opt/k60/trees/ios27-out/feeds/UniXNU-sm8475-common-6ebb3d7f/patches')),
    ('os', FRAMEWORK / 'profiles/os/ios-27.0.1-24A446/patches'),
    ('device', SELF / 'patches/xnu-12377'),
)


def series_of(directory):
    path = directory / 'series'
    if not path.is_file():
        return []
    entries = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        line = line.split('#', 1)[0].strip()
        if line.endswith('.patch'):
            entries.append(line)
    return entries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', default='/mnt/e/k60-work/scratch/replay-27')
    args = parser.parse_args()
    work = pathlib.Path(args.work)
    if work.exists():
        shutil.rmtree(work)
    subprocess.run(['git', 'clone', '--quiet', '--shared', str(FEED), str(work)], check=True)
    applied = failed = 0
    for name, directory in LAYERS:
        entries = series_of(directory)
        print(f'{name}: {len(entries)} patch(es) from {directory}')
        for entry in entries:
            patch = directory / entry
            if not patch.is_file():
                print(f'  MISSING {name}/{entry}')
                failed += 1
                continue
            result = subprocess.run(['git', '-C', str(work), 'apply', '--whitespace=nowarn', str(patch)],
                                    capture_output=True, text=True)
            if result.returncode == 0:
                applied += 1
            else:
                failed += 1
                print(f'  FAIL {name}/{entry}')
                print('    ' + (result.stderr or result.stdout).strip().splitlines()[0])
    print(f'applied {applied}, failed {failed}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
