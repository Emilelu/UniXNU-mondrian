#!/usr/bin/env python3
"""Build drivers/NativeUfs into libNativeUfs.a on a Linux host.

The 16.6.1 line compiles this driver with scripts/build-pong-ufs-probe-macos.py,
which runs under xcrun, and the framework compiles its own storage runtime with
xcrun ar (scripts/build-sheng-source-storage.py:240). Neither path exists on the
Linux host that builds iOS 27, so the Data gate's storage backend had no recipe
here at all: board.toml cannot select NativeUfs and build-xnu-generic.sh cannot
link an archive nobody produces.

This script closes that half of the gap without touching either file. It takes
the compile flags from the tree's own build record for an IOKit object, so the
driver sees exactly the headers, target and defines the kernel build uses, then
compiles the three translation units and archives them with llvm-ar. The record
is a build artifact, not a source of truth: pass --record to point at another
one, and --dry-run to print the commands without running them.

It reports; it does not wire anything up. Selecting the component in board.toml
and linking the archive from the 27 builder stay with the people who own those
two files.
"""
import argparse
import json
import pathlib
import shutil
import subprocess
import sys

SOURCES = [
    ('NativeUfs.cpp', 'NativeUfs.o'),
    ('PongUfsTransport.cpp', 'PongUfsTransport.o'),
    ('verified_root.c', 'verified_root.o'),
]
DEFINES = ['XNU_NATIVE_UFS=1', 'XNU_SOURCE_STORAGE=1']


def record_arguments(record):
    data, _ = json.JSONDecoder().raw_decode(record.read_text())
    if 'arguments' not in data or 'directory' not in data:
        raise SystemExit('FAIL %s has no arguments/directory; pass --record' % record)
    return data['arguments'], pathlib.Path(data['directory'])


def find_record(tree):
    pattern = 'build/xnu/ios-obj/*/iokit/DEVELOPMENT/KernelConfigTables.cpo.json'
    found = sorted(pathlib.Path(tree).glob(pattern))
    if not found:
        raise SystemExit('FAIL no %s under %s; build the kernel once or pass --record' % (pattern, tree))
    return found[0]


def rewrite(arguments, source, output):
    """Swap the recorded source and object for ours, keeping every other flag."""
    argv = list(arguments)
    swapped_source = swapped_output = False
    for index, value in enumerate(argv):
        if value.endswith('iokit/KernelConfigTables.cpp'):
            argv[index] = str(source)
            swapped_source = True
        elif value.endswith('KernelConfigTables.cpo'):
            argv[index] = str(output)
            swapped_output = True
    if not swapped_source or not swapped_output:
        raise SystemExit('FAIL the record does not name iokit/KernelConfigTables.cpp and its object')
    return argv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', type=pathlib.Path,
                        default=pathlib.Path(__file__).resolve().parents[1])
    parser.add_argument('--tree', type=pathlib.Path, required=True,
                        help='build tree holding build/xnu/ios-obj/*/iokit records')
    parser.add_argument('--record', type=pathlib.Path,
                        help='explicit KernelConfigTables.cpo.json; defaults to the first under --tree')
    parser.add_argument('--out', type=pathlib.Path, default=pathlib.Path('out/native-ufs-linux'))
    parser.add_argument('--archiver', default=None)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    device = args.device.resolve()
    tree = args.tree.resolve()
    out = args.out
    record = args.record or find_record(tree)
    arguments, directory = record_arguments(pathlib.Path(record))

    extra = ['-D', DEFINES[0], '-D', DEFINES[1],
             '-I', str(device / 'drivers'),
             '-I', str(device / 'drivers/NativeUfs')]
    storage = tree / 'build/storage-abi/include'
    if storage.is_dir():
        extra += ['-I', str(storage)]
    else:
        print('note: %s absent, the transport header may not resolve' % storage)

    out.mkdir(parents=True, exist_ok=True)
    objects = []
    for name, obj in SOURCES:
        source = device / 'drivers/NativeUfs' / name
        if not source.is_file():
            raise SystemExit('FAIL %s not found' % source)
        argv = rewrite(arguments, source, out / obj)
        argv[1:1] = extra
        if args.dry_run:
            print(' '.join(argv))
        else:
            done = subprocess.run(argv, cwd=directory, capture_output=True, text=True)
            errors = [line for line in done.stderr.splitlines() if ': error:' in line]
            if done.returncode != 0 or errors:
                print(done.stderr[-2000:])
                raise SystemExit('FAIL %s: %d error(s)' % (name, len(errors)))
            print('  compiled %-22s %8d bytes' % (obj, (out / obj).stat().st_size))
        objects.append(str(out / obj))

    archiver = args.archiver or shutil.which('llvm-ar') or shutil.which('ar')
    if not archiver:
        raise SystemExit('FAIL no llvm-ar or ar; pass --archiver')
    archive = out / 'libNativeUfs.a'
    command = [archiver, 'rcs', str(archive)] + objects
    if args.dry_run:
        print(' '.join(command))
    else:
        if archive.exists():
            archive.unlink()
        subprocess.run(command, check=True)
        print('  archived %-22s %8d bytes' % ('libNativeUfs.a', archive.stat().st_size))
    print('native-ufs-linux: %s' % ('dry run' if args.dry_run else 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
