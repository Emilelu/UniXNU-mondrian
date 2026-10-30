#!/usr/bin/env python3
"""Run the K60 prelink on a kernel that was built somewhere else.

"unixnu build kernel" rebuilds XNU, which needs macOS.  This runs only the
prelink step, with the roots and slide from [kernel.prelink], through the same
auto-slide wrapper the CI preflight installs.  The kernel comes from the CI
artifact (upload_kernel) or from any other machine; the 20G81 kernelcache is the
one "unixnu ipsw" extracts.

[kernel.prelink] lives in the OS profile for this format 2 device
(profiles/os/<os_profile>/profile.toml), so the profile is read by default and a
board.toml [kernel.prelink] table, when present, overrides it field by field.
The profile's slide is "0" because the auto-slide wrapper derives the real slide
from the component extents.

    python3 scripts/k60-prelink-local.py --kernel mach.development.pong.unstripped \\
        --prelinked out/ipsw/20G81/kernelcache.decompressed --output kernel.macho
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / 'scripts/emit_prelink_autoslide.py'


def prelink_table(board, profile):
    """[kernel.prelink] for this device: the OS profile's table, overridden by the board's."""
    merged = dict(profile.get('kernel', {}).get('prelink', {}))
    merged.update(board.get('kernel', {}).get('prelink', {}))
    return merged


def default_profile(board):
    name = board.get('board', {}).get('os_profile')
    if not name:
        return None
    return ROOT.parent / 'UniXNU' / 'profiles' / 'os' / name / 'profile.toml'


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--kernel', required=True, type=Path, help='native kernel Mach-O (mach.*.unstripped)')
    parser.add_argument('--prelinked', required=True, type=Path, help='20G81 kernelcache.decompressed')
    parser.add_argument('--output', required=True, type=Path, help='prelinked kernel to write')
    parser.add_argument('--kit', type=Path, default=Path.home() / 'hackios/UniXNU/kits/XnuPrelink',
                        help='XnuPrelink checkout (default: %(default)s)')
    parser.add_argument('--board', type=Path, default=ROOT / 'board.toml')
    parser.add_argument('--profile', type=Path,
                        help='OS profile with [kernel.prelink] (default: <board os_profile> of ../UniXNU)')
    parser.add_argument('--early-security-init', action='append', default=[],
                        metavar='BUNDLE=ORIGINAL_VA',
                        help='initializer the prelinker runs before lockdown')
    args = parser.parse_args()

    for path in (args.kernel, args.prelinked, args.kit / 'emit_prelink.py'):
        if not path.exists():
            sys.exit(f'not found: {path}')
    if args.output.exists():
        sys.exit(f'refusing to overwrite {args.output}')

    board = tomllib.loads(args.board.read_text())
    profile_path = args.profile or default_profile(board)
    if profile_path is None:
        sys.exit(f'{args.board} has no [board] os_profile; pass --profile')
    if not profile_path.exists():
        sys.exit(f'not found: {profile_path} (pass --profile for the OS profile)')
    prelink = prelink_table(board, tomllib.loads(profile_path.read_text()))
    if not prelink.get('roots'):
        sys.exit(f'no [kernel.prelink] roots in {profile_path} or {args.board}')
    roots = prelink['roots']
    slide = prelink.get('slide', '0')

    with tempfile.TemporaryDirectory() as scratch:
        kit = Path(scratch) / 'XnuPrelink'
        shutil.copytree(args.kit, kit, ignore=shutil.ignore_patterns('.git', '__pycache__'))
        shutil.copyfile(kit / 'emit_prelink.py', kit / 'emit_prelink_orig.py')
        shutil.copyfile(WRAPPER, kit / 'emit_prelink.py')
        command = [sys.executable, str(kit / 'emit_prelink.py'), '--kernel', str(args.kernel),
                   '--prelinked', str(args.prelinked), f'--slide={slide}', '--output', str(args.output)]
        for root in roots:
            command += ['--root', root]
        for initializer in args.early_security_init:
            command += ['--early-security-init', initializer]
        print(f'prelink: {len(roots)} roots, slide {slide}', flush=True)
        result = subprocess.run(command, cwd=kit)
    if result.returncode:
        sys.exit(f'prelink failed ({result.returncode})')
    print(f'prelink: {args.output} ({args.output.stat().st_size} bytes)')


if __name__ == '__main__':
    main()
