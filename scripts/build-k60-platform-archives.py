#!/usr/bin/env python3
"""route-a-15: build our K60 ArmDTPlatform and ArmCpu archives against the
darwin24 tree, then link them into the kernel.

Our 16.6.1 kernel reached a video console because its link line carried
`-Wl,-force_load,$ARM_DT_ARCHIVE` (and optionally $ARMCPU_ARCHIVE) from
`$PONG_NATIVE_DRIVER_SOURCE` - the K60 driver sources. The darwin24 build so far
linked neither, which is why the loader reports "0 staged kext(s)" and the kernel
never reaches a console.

pong's own entries (build-xnu-ipados18.sh):
  250:  python3 "$PONG_NATIVE_DRIVER_SOURCE/scripts/build-pong-armcpu-macos.py" \
  807:  ARM_DT_ARCHIVE=$ROOT/build/armdt-platform/libArmDTPlatform.a
  813:  ARMCPU_ARCHIVE=$ROOT/build/armcpu/libArmCpu.a
"""
from pathlib import Path
import argparse
import os
import subprocess
import sys

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--tree', type=Path, required=True,
                help='resolved kernel tree; archives land in <tree>/build/<subdir>/')
ap.add_argument('--driver', type=Path, default=None,
                help='device repository carrying scripts/build-pong-*-macos.py '
                     '(defaults to the repository beside the tree)')
ap.add_argument('--fakeroot', type=Path, default=None,
                help='SDK root the kernel build made (default <tree>/.cache/fakeroot)')
ap.add_argument('--log-dir', type=Path, default=None)
ap.add_argument('--triple', default=os.environ.get('DARWIN_TRIPLE', 'arm64-apple-ios27.0'))
ap.add_argument('--darwin', default=os.environ.get('XNU_DARWIN', '26.0.0'))
ap.add_argument('--version', dest='xnu_version',
                default=os.environ.get('XNU_VERSION', '12377.121.6'))
_args = ap.parse_args()

TREE = _args.tree.resolve()
DRIVER = (_args.driver or Path(__file__).resolve().parents[1]).resolve()
FAKEROOT = (_args.fakeroot or TREE / '.cache/fakeroot').resolve()
LOGDIR = (_args.log_dir or TREE.parent / 'logs').resolve()
LOGDIR.mkdir(parents=True, exist_ok=True)
# The vendor recipes want the XNU source root (the directory that owns bsd/).
# unixnu resolves a kernel tree as <out>/<profile>/<defconfig>/tree with the
# sources unpacked under .cache/xnu-work, so accept either layout and hand the
# recipes the place bsd/ actually lives. Output still goes to <tree>/build.
XNU = TREE if (TREE / 'bsd').is_dir() else TREE / '.cache/xnu-work'
if not (XNU / 'bsd').is_dir():
    sys.exit(f'{TREE}: neither it nor .cache/xnu-work is an XNU source root (no bsd/)')
if not (DRIVER / 'scripts' / 'build-pong-platform-macos.py').is_file():
    sys.exit(f'{DRIVER}: no scripts/build-pong-platform-macos.py')

toolchain = Path('/opt/unixnu-linux')
clt = toolchain / 'CommandLineTools/usr'
xct = toolchain / 'XcodeDefault.xctoolchain/usr'

env = dict(os.environ)
env.update(
    PATH=f'{clt}/bin:{toolchain}/bin:{toolchain}/llvm/bin:{os.environ.get("PATH","")}',
    LC_ALL='C', PLATFORM='iPhoneOS', JOBS='8',
    CLT_PREFIX=str(clt), XCTOOLCHAIN_PREFIX=str(xct),
    XNU_TOOLCHAIN_BIN=f'{clt}/bin {xct}/bin',
    HOST_CC=f'{clt}/bin/xnu-host-cc', MIGCOM=f'{clt}/libexec/migcom',
    UNIXNU_SDKROOT=str(FAKEROOT), UNIXNU_SDK_VERSION='18.0',
    CROSS_CLANG=str(toolchain / 'llvm/bin/clang'),
    DARWIN_TRIPLE=_args.triple,
    CROSS_EXTRA_FLAGS='-mllvm -disable-atexit-based-global-dtor-lowering',
    CCC_OVERRIDE_OPTIONS='# +-Wno-missing-designated-field-initializers +-Wno-unused-but-set-global',
    XNU_DARWIN=_args.darwin, XNU_VERSION=_args.xnu_version,
    # The vendor recipes hardcode arm64-apple-ios16.0; the 27 line builds arm64e.
    K60_PLATFORM_TARGET_TRIPLE=_args.triple,
    PONG_NATIVE_DRIVER_SOURCE=str(DRIVER),
    PONG_HARDWARE_DTB=str(TREE / 'build/xnu/ios-dst/hardware.dtb'),
)

# The recipes read <tree>/.cache/fakeroot, where <tree> is whatever they are
# handed. We hand them the XNU source root, but unixnu keeps the fakeroot one
# level up at <out tree>/.cache/fakeroot, so bridge the two with a symlink
# instead of duplicating 36 MB of SDK headers.
XNU_FAKEROOT = XNU / '.cache/fakeroot'
if XNU_FAKEROOT.is_symlink() or XNU_FAKEROOT.exists():
    pass
else:
    XNU_FAKEROOT.parent.mkdir(parents=True, exist_ok=True)
    XNU_FAKEROOT.symlink_to(FAKEROOT)
    print(f'linked {XNU_FAKEROOT} -> {FAKEROOT}')

SCRIPTS = [
    ('armdt-platform', 'build-pong-platform-macos.py', 'libArmDTPlatform.a'),
    ('armcpu', 'build-pong-armcpu-macos.py', 'libArmCpu.a'),
]

results = []
for subdir, script, libname in SCRIPTS:
    path = DRIVER / 'scripts' / script
    print('=' * 70)
    print(script, '->', path)
    if not path.exists():
        print('  MISSING script')
        results.append((libname, None, 'missing script'))
        continue
    log = LOGDIR / f'{subdir}.log'
    r = subprocess.run([sys.executable, str(path), '--tree', str(XNU),
                        '--skip-image-verification'],
                       cwd=str(DRIVER), env=env,
                       stdout=open(log, 'wb'), stderr=subprocess.STDOUT)
    print('  rc =', r.returncode)
    text = Path(log).read_text(errors='replace')
    if r.returncode != 0:
        errs = [l for l in text.splitlines()
                if 'error:' in l or 'Error' in l or 'No such file' in l]
        for l in errs[:15]:
            print('   ', l[:200])
        if not errs:
            print('\n'.join(text.splitlines()[-15:]))
        results.append((libname, None, f'rc={r.returncode}'))
        continue
    lib = TREE / 'build' / subdir / libname
    # The recipe writes under the tree it was handed; take that copy whenever it
    # exists, otherwise a stale archive from an earlier run satisfies the check
    # below and the freshly built one is silently ignored.
    strayed_now = XNU / 'build' / subdir / libname
    if strayed_now.is_file():
        lib.parent.mkdir(parents=True, exist_ok=True)
        strayed_now.replace(lib)
        print('  TAKEN', strayed_now, '->', lib, lib.stat().st_size, 'bytes')
    if lib.exists():
        print('  BUILT', lib, lib.stat().st_size, 'bytes')
        results.append((libname, lib, 'ok'))
    else:
        # The recipes write under the tree they are handed; move the archive to
        # where the kernel build's fileset step looks for it.
        strayed = XNU / 'build' / subdir / libname
        if strayed.is_file():
            lib.parent.mkdir(parents=True, exist_ok=True)
            strayed.replace(lib)
            print('  MOVED', strayed, '->', lib, lib.stat().st_size, 'bytes')
            results.append((libname, lib, 'ok'))
            continue
        # The script may write elsewhere; look for it.
        found = list((TREE / 'build').rglob(libname))
        print('  expected', lib, 'not found; rglob:', found)
        results.append((libname, found[0] if found else None,
                        'ok-but-relocated' if found else 'missing output'))

print()
print('=' * 70)
print('summary:')
for libname, lib, status in results:
    print(f'  {libname}: {status}' + (f'  {lib}' if lib else ''))
