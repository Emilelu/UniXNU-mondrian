#!/usr/bin/env python3
"""Reproduce scripts/unixnu/patches.py:plan() and apply the result in order.

The plan() source resolves every entry against ctx.profile_roots, and those roots are
(profiles.py:45-48): arch = <framework>/profiles/arch/<arch_name>, soc = the soc feed,
os = <framework>/profiles/os/<os profile>, device = the device repository.
This script mirrors exactly that, so the list it applies is the list a build would apply.
"""
import pathlib
import shutil
import subprocess
import sys

FRAMEWORK = pathlib.Path('/opt/k60/trees/ios27-fw')
DEVICE = pathlib.Path(__file__).resolve().parents[1]
FEED = pathlib.Path('/opt/k60/trees/ios27-out/feeds/xnu-3199e8bc')
SOC = pathlib.Path('/opt/k60/trees/ios27-out/feeds/UniXNU-sm8475-common-6ebb3d7f')
OS_NAME = 'ios-27.0.1-24A446'
ARCH_NAME = 'arm64e'

ROOTS = {
    'arch': FRAMEWORK / 'profiles/arch' / ARCH_NAME,
    'soc': SOC,
    'os': FRAMEWORK / 'profiles/os' / OS_NAME,
    'device': DEVICE,
}


def resolve(reference):
    scope, _, rest = reference.partition(':')
    if scope in ROOTS:
        return (ROOTS[scope] / rest).resolve()
    raise SystemExit(f'unknown scope {scope} in {reference}')


def plan():
    board = (DEVICE / 'board.toml').read_text(encoding='utf-8')
    import tomllib
    series_list = tomllib.loads(board)['kernel']['patch_series']
    result = []
    for reference in series_list:
        series = resolve(reference)
        if not series.is_file():
            raise SystemExit(f'patch series missing: {series}')
        for number, line in enumerate(series.read_text(encoding='utf-8').splitlines(), 1):
            entry = line.strip()
            if not entry or entry.startswith('#'):
                continue
            scope = entry.partition(':')[0]
            if entry.startswith('component:') or scope in ROOTS:
                path = resolve(entry)
            else:
                path = (series.parent / entry).resolve()
            if not path.is_file():
                raise SystemExit(f'{series}:{number}: patch missing: {path}')
            if path in result:
                raise SystemExit(f'patch twice: {path}')
            result.append(path)
    return result


def main():
    patches = plan()
    print(f'plan: {len(patches)} patch(es)')
    for path in patches[:4]:
        print('  ', path)
    work = pathlib.Path('/mnt/e/k60-work/scratch/replay-plan')
    if work.exists():
        shutil.rmtree(work)
    subprocess.run(['git', 'clone', '--quiet', '--shared', str(FEED), str(work)], check=True)
    applied = 0
    failures = []
    for path in patches:
        result = subprocess.run(['git', '-C', str(work), 'apply', '--whitespace=nowarn', str(path)],
                                capture_output=True, text=True)
        if result.returncode:
            failures.append((path.name, (result.stderr or '').strip().splitlines()[:1]))
        else:
            applied += 1
    print(f'applied {applied}, failed {len(failures)} of {len(patches)}')
    for name, error in failures:
        print('  FAIL', name, error)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
