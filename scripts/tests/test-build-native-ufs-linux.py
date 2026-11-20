#!/usr/bin/env python3
"""Tests for scripts/build-native-ufs-linux.py.

The script takes its compile flags from a build record, so the tests fabricate a
record and three stub sources and run it with --dry-run: that exercises record
discovery, the argument rewrite, the include and define set, and the archiver
selection without needing a toolchain or a kernel build.
"""
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/build-native-ufs-linux.py'
CASES = []


def case(name, ok, detail=None):
    CASES.append((name, ok, detail))


def make_tree(base, target='arm64e-apple-darwin'):
    record_dir = base / 'tree/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT'
    record_dir.mkdir(parents=True)
    record = record_dir / 'KernelConfigTables.cpo.json'
    record.write_text(json.dumps({
        'directory': str(record_dir),
        'arguments': ['/opt/llvm/bin/clang-24', '-c',
                      str(base / 'tree/iokit/KernelConfigTables.cpp'),
                      '-o', str(record_dir / 'KernelConfigTables.cpo'),
                      '-target', target, '-std=gnu++17'],
    }))
    return record


def make_device(base, names=('NativeUfs.cpp', 'PongUfsTransport.cpp', 'verified_root.c')):
    for name in names:
        path = base / 'drivers/NativeUfs' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('/* stub */\n')
    return base


def run(args):
    return subprocess.run([sys.executable, str(SCRIPT)] + args,
                          capture_output=True, text=True)


with tempfile.TemporaryDirectory() as tmp:
    base = pathlib.Path(tmp)
    record = make_tree(base)
    device = make_device(base / 'device')
    out = base / 'out'
    done = run(['--device', str(device), '--tree', str(base / 'tree'),
                '--out', str(out), '--dry-run'])
    lines = done.stdout.splitlines()
    compiles = [line for line in lines if '/opt/llvm/bin/clang-24' in line]
    case('a dry run prints one command per source', len(compiles) == 3, done.stdout)
    case('every command defines the two switches',
         all('XNU_NATIVE_UFS=1' in line and 'XNU_SOURCE_STORAGE=1' in line for line in compiles))
    case('every command carries the driver include directories',
         all('drivers/NativeUfs' in line for line in compiles))
    case('every command keeps the recorded target',
         all('arm64e-apple-darwin' in line for line in compiles))
    case('the recorded source is gone from the command',
         all('iokit/KernelConfigTables.cpp' not in line for line in compiles))
    case('the archive command names llvm-ar or ar',
         any('ar rcs' in line or 'llvm-ar rcs' in line for line in lines), done.stdout)
    case('the archive holds the three objects',
         all(str(out / name) in done.stdout for name in
             ('NativeUfs.o', 'PongUfsTransport.o', 'verified_root.o')))
    case('a dry run says so', 'native-ufs-linux: dry run' in done.stdout)
    case('a tree without the storage ABI says so', 'note:' in done.stdout, done.stdout)

    (base / 'tree/build/storage-abi/include').mkdir(parents=True)
    done = run(['--device', str(device), '--tree', str(base / 'tree'),
                '--out', str(out), '--dry-run'])
    case('the storage ABI include is used when the tree has one',
         'build/storage-abi/include' in done.stdout)
    case('a tree with the storage ABI stays quiet', 'note:' not in done.stdout, done.stdout)

    done = run(['--device', str(device), '--tree', str(base / 'empty'), '--dry-run'])
    case('a tree without a record fails', done.returncode != 0 and 'no build/xnu/ios-obj' in done.stdout + done.stderr)

    thin = make_device(base / 'thin', names=('NativeUfs.cpp',))
    done = run(['--device', str(thin), '--tree', str(base / 'tree'), '--dry-run'])
    case('a missing source fails and names it',
         done.returncode != 0 and 'PongUfsTransport.cpp not found' in done.stdout + done.stderr)

    done = run(['--device', str(device), '--tree', str(base / 'tree'),
                '--record', str(record), '--out', str(out), '--dry-run'])
    case('an explicit record is accepted', done.returncode == 0 and len(compiles) == 3)

    broken = base / 'broken.json'
    broken.write_text('{"directory": "/tmp"}')
    done = run(['--device', str(device), '--tree', str(base / 'tree'),
                '--record', str(broken), '--dry-run'])
    case('a record without arguments fails', done.returncode != 0)

    wrong = base / 'wrong.json'
    wrong.write_text(json.dumps({'directory': str(base), 'arguments': ['/opt/llvm/bin/clang-24', '-c', 'unrelated.cpp']}))
    done = run(['--device', str(device), '--tree', str(base / 'tree'),
                '--record', str(wrong), '--dry-run'])
    case('a record that does not name the IOKit object fails',
         done.returncode != 0 and 'does not name iokit/KernelConfigTables.cpp' in done.stdout + done.stderr)

failed = [name for name, ok, _ in CASES if not ok]
for name, ok, detail in CASES:
    if not ok and detail:
        print('--- %s\n%s' % (name, detail))
print('TESTS %s %d case(s)' % ('FAILED' if failed else 'OK', len(CASES)))
sys.exit(1 if failed else 0)
