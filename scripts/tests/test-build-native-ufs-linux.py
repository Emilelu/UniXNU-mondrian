#!/usr/bin/env python3
"""Tests for scripts/build-native-ufs-linux.py.

The producer is deliberately toolchain-explicit: it names clang-24, llvm-libtool-
darwin-18 and llvm-nm-18 instead of reading a build record. The tests therefore
fabricate a device with stub sources and a defconfig and run the script with
--dry-run: that exercises the flag set, the three config-driven defines, the
include order and the archiver command without a toolchain or a kernel build.
"""
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/build-native-ufs-linux.py'
CASES = []


def case(name, ok, detail=None):
    CASES.append((name, ok, detail))


def make_tree(base):
    for path in (
        '.cache/xnu-work/EXTERNAL_HEADERS',
        '.cache/fakeroot/System/Library/Frameworks/Kernel.framework/Versions/A/PrivateHeaders',
        '.cache/fakeroot/System/Library/Frameworks/Kernel.framework/Versions/A/Headers',
        'build/storage-abi/include',
    ):
        (base / path).mkdir(parents=True, exist_ok=True)
    return base


def make_device(base, names=('NativeUfs.cpp', 'PongUfsTransport.cpp',
                             'verified_root.c', 'xnu_crypto.c'), defconfig=None):
    for name in names:
        path = base / 'drivers/NativeUfs' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('/* stub */\n')
    (base / 'configs').mkdir(parents=True, exist_ok=True)
    (base / 'configs/mondrian_ios27_defconfig').write_text(
        defconfig or 'CONFIG_XNU_NATIVE_UFS=y\n'
                      'CONFIG_XNU_OWNER_DATA_UFS=y\n'
                      'CONFIG_XNU_VERIFIED_ROOT_PROBE=n\n'
                      'CONFIG_XNU_PONG_EARLY_TRACE=y\n')
    return base


def run(args):
    done = subprocess.run([sys.executable, str(SCRIPT)] + args,
                          capture_output=True, text=True)
    done.flat = done.stdout.replace('\\', '/')
    return done


with tempfile.TemporaryDirectory() as tmp:
    base = pathlib.Path(tmp)
    tree = make_tree(base / 'tree')
    device = make_device(base / 'device')
    out = base / 'out'
    done = run(['--device', str(device), '--tree', str(tree), '--out', str(out), '--dry-run'])
    lines = done.flat.splitlines()
    compiles = [line for line in lines if ' -c ' in line]
    case('a dry run prints one compile per C++ source', len(compiles) == 2, done.stdout)
    case('the compile uses clang-24 for the ios27 target',
         all(line.startswith('/opt/unixnu-linux/llvm/bin/clang-24') and
             'arm64-apple-ios27.0' in line for line in compiles), done.stdout)
    case('the compile is a kernel freestanding build',
         all('-mkernel' in line and '-ffreestanding' in line and '-fno-exceptions' in line
             and '-fno-rtti' in line and '-std=gnu++17' in line and '-O2' in line
             for line in compiles))
    case('the three defines come from the defconfig',
         all('-DXNU_PONG_EARLY_TRACE=1' in line and '-DXNU_PONG_UFS_DATA=1' in line
             and '-DNATIVE_VERIFIED_BLOCK=0' in line for line in compiles), done.stdout)
    case('the include order starts with the external headers',
         all(line.index('.cache/xnu-work/EXTERNAL_HEADERS') < line.index('Kernel.framework') for line in compiles))
    case('the storage ABI include is carried', all('build/storage-abi/include' in line for line in compiles))
    case('the driver include is carried', all('drivers/NativeUfs' in line for line in compiles))
    case('the archive command names llvm-libtool-darwin-18',
         any('/usr/bin/llvm-libtool-darwin-18 -static -o' in line for line in lines), done.stdout)
    obj = lambda name: str(out / name).replace('\\', '/')
    case('the archive holds the two C++ objects and not the C ones',
         obj('NativeUfs.o') in done.flat and obj('PongUfsTransport.o') in done.flat
         and 'verified_root.o' not in done.flat)
    case('a dry run says so', 'native-ufs-linux: dry run' in done.stdout)
    case('a quiet tree prints no include note', 'note: include directory absent' not in done.stdout, done.stdout)

    verified = make_device(base / 'verified',
                           defconfig='CONFIG_XNU_OWNER_DATA_UFS=n\n'
                                     'CONFIG_XNU_VERIFIED_ROOT_PROBE=y\n')
    done = run(['--device', str(verified), '--tree', str(tree), '--out', str(out), '--dry-run'])
    case('the verified block adds the two C sources',
         len([line for line in done.flat.splitlines() if ' -c ' in line]) == 4
         and '-DNATIVE_VERIFIED_BLOCK=1' in done.stdout and '-DXNU_PONG_UFS_DATA=0' in done.stdout, done.stdout)
    case('the C sources compile as gnu11',
         any('-std=gnu11' in line and 'xnu_crypto.c' in line for line in done.flat.splitlines()))

    missing = make_device(base / 'thin', names=('NativeUfs.cpp',))
    done = run(['--device', str(missing), '--tree', str(tree), '--dry-run'])
    case('a missing source fails and names it',
         done.returncode != 0 and 'FAIL source not found' in done.stdout and 'PongUfsTransport.cpp' in done.stdout)

    no_config = base / 'noconfig'
    (no_config / 'drivers/NativeUfs').mkdir(parents=True)
    done = run(['--device', str(no_config), '--tree', str(tree), '--dry-run'])
    case('a device without the defconfig fails', done.returncode != 0 and 'defconfig not found' in done.stdout)

failed = [name for name, ok, _ in CASES if not ok]
for name, ok, detail in CASES:
    if not ok:
        print('FAILED CASE: %s' % name)
        if detail:
            print(detail[:1500])
print('TESTS %s %d case(s)' % ('FAILED' if failed else 'OK', len(CASES)))
sys.exit(1 if failed else 0)
