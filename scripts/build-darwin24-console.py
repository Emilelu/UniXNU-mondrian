#!/usr/bin/env python3
"""route-a-18: rebuild the darwin24 kernel with pong's console/trace switches.

Our previous build passed none of pong's 33 EXTRA_MAKE_ARGS, so every
XNU_* feature compiled out (all defaults are 0) - including the ramoops console
mirror in serial_console.c, which is the only channel this board has while the
video console needs platform kexts we have not ported.

This build adds, copied from build-xnu-ipados18.sh lines 708-731:
  XNU_PONG_RAMOOPS_CONSOLE=1   mirror console_write into the K60 carveout
  XNU_PONG_EARLY_TRACE=1       early trace in start.S / arm_init / startup
  XNU_NATIVE_ARCH_TIMER=1      architectural timer (no platform timer kext)
  XNU_DT_PANIC_REGION=1        keep the panic log in a DT-visible region
plus the matching per-object flags.
"""
from pathlib import Path
import os
import subprocess
import sys

TREE = Path('/tmp/k60build/out/route-a18/Pong-iPadOS18-native')
WORK = TREE / '.cache' / 'xnu-work'
FAKEROOT = TREE / '.cache/fakeroot'
LOGDIR = TREE.parent / 'logs'
SUPPORT = TREE / 'build/route-a18-support/libRouteA18Support.a'
PATCH243 = Path('/home/emilelu/hackios/UniXNU-mondrian/patches/xnu-ipados18/'
                '0243-k60-ramoops-physical-base.patch')

toolchain = Path('/opt/unixnu-linux')
clt = toolchain / 'CommandLineTools/usr'
xct = toolchain / 'XcodeDefault.xctoolchain/usr'

# Ensure the K60 ramoops base patch is in the tree.
hdr = WORK / 'osfmk/arm64/pong_ramoops_console.h'
if '0xA7000000ULL' not in hdr.read_text():
    subprocess.run(['git', '-C', str(WORK), 'apply', str(PATCH243)], check=True)
    print('applied 0243 (K60 ramoops base)')

# Force these objects to rebuild with the new macros: make does not track
# command-line variable changes.
stamp_dir = TREE / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG'
if stamp_dir.exists():
    for name in ('start.o', 'arm_init.o', 'arm_vm_init.o', 'machine_routines.o',
                 'startup.o', 'serial_console.o', 'debug.o', 'counter_test.o',
                 'pe_init.o', 'IOStartIOKit.o', 'OSRuntime.o'):
        for path in stamp_dir.rglob(name):
            path.unlink(missing_ok=True)

env = dict(os.environ)
env.update(
    PATH=f'{clt}/bin:{toolchain}/bin:{os.environ.get("PATH","")}',
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
    MEMORY_SIZE=str(os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')),
    SYSCTL_HW_PHYSICALCPU=str(os.cpu_count()),
    SYSCTL_HW_LOGICALCPU=str(os.cpu_count()),
)

RAMOOPS = 1
EARLY = 1
cmd = [
    'make', '-C', str(WORK), 'build', 'SDKROOT=iphoneos',
    'ARCH_CONFIGS=ARM64', 'MACHINE_CONFIGS=PONG', 'KERNEL_CONFIGS=DEVELOPMENT',
    'ARCH_STRING_FOR_CURRENT_MACHINE_CONFIG=arm64',
    'LARGE_MEMORY_DEFINE=-UARM_LARGE_MEMORY',
    'ARM64_LINK_ADDR=0xfffffff007004000', 'ARM64_PLKSEG_ADDR=0xfffffff004004000',
    'DEPLOYMENT_TARGET_FLAGS=-miphoneos-version-min=18.0 -DXNU_TARGET_OS_IOS',
    'DEPLOYMENT_LINKER_FLAGS=-Wl,-ios_version_min,18.0',
    'RC_DARWIN_KERNEL_VERSION=24.6.0', 'RC_ProjectSourceVersion=11417.140.69',
    'BUILD_LTO=0', 'BUILD_STATIC_LINK=0', 'BUILD_DSYM=0', 'BOUND_CHECKS=0',
    'BUILD_WERROR=0', 'MAKEJOBS=-j8',
    # console / trace switches, verbatim from pong's script
    f'start.o_SFLAGS_ADD=-DXNU_NATIVE_ARCH_TIMER=1 -DXNU_PONG_EARLY_TRACE={EARLY}',
    f'arm_init.o_CFLAGS_ADD=-DXNU_PONG_EARLY_TRACE={EARLY} '
    f'-DXNU_PONG_RAMOOPS_CONSOLE={RAMOOPS} -mstrict-align -mgeneral-regs-only -march=armv8.1-a',
    f'arm_vm_init.o_CFLAGS_ADD=-DXNU_PONG_EARLY_TRACE={EARLY}',
    f'machine_routines.o_CFLAGS_ADD=-DXNU_PONG_EARLY_TRACE={EARLY}',
    f'startup.o_CFLAGS_ADD=-DXNU_PONG_EARLY_TRACE={EARLY}',
    f'serial_console.o_CFLAGS_ADD=-DXNU_PONG_EARLY_TRACE={EARLY} '
    f'-DXNU_PONG_RAMOOPS_CONSOLE={RAMOOPS}',
    f'debug.o_CFLAGS_ADD=-DXNU_PONG_EARLY_TRACE={EARLY}',
    f'counter_test.o_CFLAGS_ADD=-DXNU_PONG_EARLY_TRACE={EARLY}',
    f'IOStartIOKit.cpo_CFLAGS_ADD=-DXNU_PONG_EARLY_TRACE={EARLY}',
    f'OSRuntime.cpo_CFLAGS_ADD=-DXNU_PONG_EARLY_TRACE={EARLY}',
    'pe_init.o_CFLAGS_ADD=-DXNU_DT_PANIC_REGION=1 '
    f'-DXNU_PONG_EARLY_TRACE={EARLY}',
    f'LD_KERNEL_ARCHIVES=-L{FAKEROOT}/usr/local/lib/kernel -lfirehose_kernel',
    f'LD_KERNEL_LIBS={FAKEROOT}/usr/local/lib/kernel/libcc_kext.a',
    f'OBJROOT={TREE}/build/xnu/ios-obj',
    f'SYMROOT={TREE}/build/xnu/ios-sym',
    f'DSTROOT={TREE}/build/xnu/ios-dst',
]

log = LOGDIR / 'build-console.log'
LOGDIR.mkdir(parents=True, exist_ok=True)
print('building with RAMOOPS_CONSOLE=1 EARLY_TRACE=1 ...')
r = subprocess.run(cmd, cwd=str(TREE), env=env,
                   stdout=open(log, 'wb'), stderr=subprocess.STDOUT)
print('rc =', r.returncode)
text = Path(log).read_text(errors='replace')
if r.returncode != 0:
    errs = [l for l in text.splitlines() if 'error:' in l and 'Wno-' not in l]
    print(f'{len(errs)} error lines')
    for l in errs[:20]:
        print(' ', l[:220])
    if not errs:
        print('\n'.join(text.splitlines()[-20:]))
    sys.exit(1)

art = stamp_dir / 'mach.development.pong.unstripped.noctf'
print('ARTIFACT:', art, art.stat().st_size)
print(subprocess.run(['sha256sum', str(art)], capture_output=True, text=True).stdout.strip())
