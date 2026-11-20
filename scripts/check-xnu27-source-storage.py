#!/usr/bin/env python3
"""Report what the source storage closure still needs on the iOS 27 line.

The Data gate chain (scripts/check-bluetooth-data-gate-chain.py) ends in
XNU_OWNER_ROOT_TRUST, which the generic builder only accepts with a real block
storage backend: XNU_NATIVE_VIRTIO_BLOCK (no virtio-mmio block device on this
board) or XNU_SOURCE_STORAGE. The 16.6.1 line answers that with drivers/NativeUfs
compiled into libNativeUfs.a; the 27 line carries the same sources but selects
none of them. This checker reads the repository and prints the six pieces the
closure needs, each with the file and line that decides it, so the work order
does not have to be re-derived from the builder every time.

It is a reporter: gaps are the expected state today, and it exits 0 unless an
input is missing. --require turns any gap into a failure, for the gate that runs
after the closure lands.
"""
import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

PROFILE = 'ios-27.0.1-24A446'


def read(path):
    path = Path(path)
    if not path.is_file():
        raise SystemExit(f'FAIL {path} not found')
    return path.read_text(errors='replace')


def line_of(text, needle):
    for number, line in enumerate(text.splitlines(), 1):
        if needle in line:
            return f'{number}'
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'), help='the device checkout')
    parser.add_argument('--board', type=Path, help='board.toml (default <root>/board.toml)')
    parser.add_argument('--builder', type=Path, help='the generic builder (default <root>/scripts/build-xnu-generic.sh)')
    parser.add_argument('--defconfig', type=Path, help='the 27 defconfig (default from board.toml)')
    parser.add_argument('--framework', type=Path, help='the framework checkout (default <root>/../UniXNU)')
    parser.add_argument('--profile', default=PROFILE)
    parser.add_argument('--require', action='store_true', help='exit 1 when a piece is missing')
    parser.add_argument('--out', type=Path, help='write report.json here')
    args = parser.parse_args()

    root = args.root.resolve()
    board_path = args.board or root / 'board.toml'
    board = tomllib.loads(read(board_path))
    overrides = board.get('os_overrides', {})
    if args.profile not in overrides:
        raise SystemExit(f'FAIL {board_path} has no os_overrides."{args.profile}"')
    profile = overrides[args.profile]
    components = profile.get('components', {}).get('include', [])
    kernel = profile.get('kernel', {})
    defconfig_path = args.defconfig or (root / 'configs' / kernel.get('defconfig', ''))
    builder_path = args.builder or root / 'scripts/build-xnu-generic.sh'

    pieces = []

    def add(name, ok, evidence):
        pieces.append({'piece': name, 'ok': ok, 'evidence': evidence})

    sources = [root / 'drivers/NativeUfs/NativeUfs.cpp', root / 'drivers/NativeUfs/PongUfsTransport.cpp']
    missing = [str(path.relative_to(root)) for path in sources if not path.is_file()]
    add('the block storage driver sources', not missing,
        'drivers/NativeUfs/NativeUfs.cpp and PongUfsTransport.cpp' if not missing
        else 'missing ' + ', '.join(missing))

    line = line_of(read(board_path), 'include = ["ArmDTPlatform", "ArmCpu", "XnuPrelink"]')
    add('the 27 profile selects the component', 'NativeUfs' in components,
        f'{board_path.name}:{line} include = {components}')

    defconfig = read(defconfig_path)
    number = line_of(defconfig, 'CONFIG_XNU_NATIVE_UFS')
    value = 'absent'
    if number:
        for line_text in defconfig.splitlines():
            if line_text.strip().startswith('CONFIG_XNU_NATIVE_UFS'):
                value = line_text.split('=', 1)[1].strip()
    add('the defconfig builds it', value == 'y',
        f'{defconfig_path.name}:{number} CONFIG_XNU_NATIVE_UFS={value}')

    builder = read(builder_path)
    native = line_of(builder, 'build/native-ufs/libNativeUfs.a')
    sheng = line_of(builder, 'build/sheng-ufs/libPongUfs.a')
    add('the builder links this branch archive', native is not None,
        f'{builder_path.name}:{native} libNativeUfs.a' if native
        else f'{builder_path.name}:{sheng} links build/sheng-ufs/libPongUfs.a, which this branch does not build')

    series_path = root / kernel.get('patch_series', ['device:patches/xnu-12377/series'])[-1].split(':', 1)[-1]
    series = read(series_path).splitlines()
    personality, scans = None, 0
    for entry in series:
        entry = entry.strip()
        if not entry or entry.startswith('#'):
            continue
        scans += 1
        patch = root / 'patches/xnu-12377' / entry
        if not patch.is_file():
            continue
        text = patch.read_text(errors='replace')
        if 'KernelConfigTables' in text and 'NativeUfs' in text:
            personality = entry
            break
    add('a patch installs the IOKit personality', personality is not None,
        f'{personality} adds NativeUfs to KernelConfigTables.cpp' if personality
        else f'none of the {scans} entries in {series_path.relative_to(root)} mention NativeUfs beside KernelConfigTables')

    framework = args.framework or root.parent / 'UniXNU'
    kit = framework / 'kits/VerifiedRoot'
    storage = framework / 'scripts/build-sheng-source-storage.py'
    policies = list((framework / 'scripts/policies').glob(args.profile + '/*.bin'))
    add('the policy bundle the root trust verifies',
        bool(policies) and kit.is_dir() and storage.is_file(),
        f'{kit} and {storage} present, policies {len(policies)}'
        if policies else f'no signed policy bundle under {framework}/scripts/policies/{args.profile} '
        f'(the kit and the builder are {kit.is_dir() and storage.is_file()})')

    for piece in pieces:
        print(('  OK   ' if piece['ok'] else '  GAP  ') + piece['piece'])
        print(f'         {piece["evidence"]}')
    gaps = [piece for piece in pieces if not piece['ok']]
    ordered = [
        'CONFIG_XNU_CRYPTO_BOOTSTRAP=prelinked (see scripts/check-xnu27-crypto-provider.py)',
        'select NativeUfs in the 27 profile components and build drivers/NativeUfs',
        'link build/native-ufs/libNativeUfs.a from the generic builder',
        'carry the KernelConfigTables personality patch in the 27 series',
        'sign the OS/SystemOS root policies and hand them to the payload',
        'turn on BOOT_MANIFEST, CACHE_STARTUP, CACHE_MOUNT, ROOT_AUDIT, ROOT_TRUST',
    ]
    print(f'xnu27-source-storage: {len(gaps)} gap(s)')
    if gaps:
        print('order to close them:')
        for index, step in enumerate(ordered, 1):
            print(f'  {index}. {step}')

    report = {'root': str(root), 'profile': args.profile, 'pieces': pieces,
              'gaps': [piece['piece'] for piece in gaps], 'order': ordered,
              'hardware_verified': False}
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return 1 if (args.require and gaps) else 0


if __name__ == '__main__':
    sys.exit(main())
