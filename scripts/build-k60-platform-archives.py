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
import os
import subprocess
import sys

TREE = Path('/tmp/k60build/out/route-a18/Pong-iPadOS18-native')
DRIVER = Path('/tmp/k60build/pong-driver')
FAKEROOT = TREE / '.cache/fakeroot'
LOGDIR = TREE.parent / 'logs'
LOGDIR.mkdir(parents=True, exist_ok=True)

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
    DARWIN_TRIPLE='arm64-apple-ios18.0',
    CROSS_EXTRA_FLAGS='-mllvm -disable-atexit-based-global-dtor-lowering',
    CCC_OVERRIDE_OPTIONS='# +-Wno-missing-designated-field-initializers +-Wno-unused-but-set-global',
    XNU_DARWIN='24.6.0', XNU_VERSION='11417.140.69',
    PONG_NATIVE_DRIVER_SOURCE=str(DRIVER),
    PONG_HARDWARE_DTB=str(TREE.parent / 'Pong-iPadOS18-native' /
                          'build/xnu/ios-dst' / 'hardware.dtb'),
)

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
    r = subprocess.run([sys.executable, str(path), '--tree', str(TREE),
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
    if lib.exists():
        print('  BUILT', lib, lib.stat().st_size, 'bytes')
        results.append((libname, lib, 'ok'))
    else:
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
