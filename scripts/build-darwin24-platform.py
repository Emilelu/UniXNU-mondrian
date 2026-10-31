#!/usr/bin/env python3
"""route-a-15: rebuild the darwin24 kernel WITH the K60 platform archives.

This is the change that should finally give the kernel a platform expert:
  libArmDTPlatform.a  - ArmDTPlatform : IODTPlatformExpert for our DTB
  libArmCpu.a         - pong_cpu_start and the CPU start protocol

Both were just built against this darwin24 tree (27,808 B and 34,600 B).
pong's link lines (build-xnu-ipados18.sh 806-816, 966-975) force-load both.
"""
from pathlib import Path
import os
import subprocess
import sys

TREE = Path('/tmp/k60build/out/route-a18/Pong-iPadOS18-native')
WORK = TREE / '.cache' / 'xnu-work'
FAKEROOT = TREE / '.cache/fakeroot'
LOGDIR = TREE.parent / 'logs'
LOGDIR.mkdir(parents=True, exist_ok=True)

ARM_DT = TREE / 'build/armdt-platform/libArmDTPlatform.a'
ARM_CPU = TREE / 'build/armcpu/libArmCpu.a'

for lib in (ARM_DT, ARM_CPU):
    if not lib.exists():
        raise SystemExit(f'missing archive: {lib}')
    print(f'{lib.name}: {lib.stat().st_size} bytes')

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
    MEMORY_SIZE=str(os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')),
    SYSCTL_HW_PHYSICALCPU=str(os.cpu_count()),
    SYSCTL_HW_LOGICALCPU=str(os.cpu_count()),
)

# The platform driver is selected by IOPlatformExpert matching, so the kernel has
# to see it at link time. Keep the console switches from the previous build.
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
    'start.o_SFLAGS_ADD=-DXNU_NATIVE_ARCH_TIMER=1',
    'arm_init.o_CFLAGS_ADD=-DXNU_PONG_RAMOOPS_CONSOLE=1 -mstrict-align -mgeneral-regs-only -march=armv8.1-a',
    'serial_console.o_CFLAGS_ADD=-DXNU_PONG_RAMOOPS_CONSOLE=1',
    'pe_init.o_CFLAGS_ADD=-DXNU_DT_PANIC_REGION=1',
    f'LD_KERNEL_ARCHIVES=-L{FAKEROOT}/usr/local/lib/kernel -lfirehose_kernel '
    f'-Wl,-force_load,{ARM_DT} -Wl,-force_load,{ARM_CPU}',
    f'LD_KERNEL_LIBS={FAKEROOT}/usr/local/lib/kernel/libcc_kext.a',
    f'OBJROOT={TREE}/build/xnu/ios-obj',
    f'SYMROOT={TREE}/build/xnu/ios-sym',
    f'DSTROOT={TREE}/build/xnu/ios-dst',
]

log = LOGDIR / 'build-platform.log'
# make does not track command-line variable changes, so the previous link (without
# the platform archives) stays in place unless its output is removed.
stale = TREE / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/mach.development.pong.unstripped.noctf'
if stale.exists():
    print('removing the stale link output:', stale.name, stale.stat().st_size, 'bytes')
    stale.unlink()
print('linking with ArmDTPlatform + ArmCpu ...')
r = subprocess.run(cmd, cwd=str(TREE), env=env,
                   stdout=open(log, 'wb'), stderr=subprocess.STDOUT)
print('rc =', r.returncode)
text = Path(log).read_text(errors='replace')
if r.returncode != 0:
    errs = [l for l in text.splitlines()
            if 'error:' in l or 'Undefined' in l or 'duplicate symbol' in l
            or 'referenced from' in l]
    print(f'{len(errs)} diagnostic lines')
    for l in errs[:25]:
        print(' ', l[:220])
    if not errs:
        print('\n'.join(text.splitlines()[-20:]))
    sys.exit(1)

art = TREE / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/mach.development.pong.unstripped.noctf'
print('ARTIFACT:', art, art.stat().st_size)
print(subprocess.run(['sha256sum', str(art)], capture_output=True, text=True).stdout.strip())

# Prove the platform driver really landed in the binary.
data = art.read_bytes()
for needle, label in ((b'ArmDTPlatform', 'ArmDTPlatform class name'),
                      (b'pong_cpu_start', 'pong_cpu_start symbol'),
                      (b'PONG DIAGNOSTIC v92', 'ramoops console')):
    print(f'  {label}: {"FOUND" if needle in data else "absent"}')
