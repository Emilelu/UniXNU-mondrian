#!/usr/bin/env python3
"""Report whether the NativeUfs archive can join the 27 kernel link.

The 27 kernel is an MH_FILESET: IOBlockStorageDevice ships in the
com.apple.iokit.IOStorageFamily entry, not in the kernel proper. The block
driver derives from it, so linking the archive adds imports the kernel image
cannot satisfy. Running the recorded link twice (control, then force_load the
archive) makes that measurable without a device.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_ARCHIVE = 'build/native-ufs/libNativeUfs.a'
CLASSLIB = 'IOBlockStorageDevice'
SHIM = '/opt/unixnu-linux/CommandLineTools/usr/bin'
TARGET = 'arm64e-apple-ios27.0'


def parse_undefined(text):
    out = {}
    current = None
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith('"') and '", referenced from:' in stripped:
            current = stripped[1:stripped.index('", referenced from:')]
            out[current] = []
            continue
        if current is None:
            continue
        if not stripped or stripped.startswith('ld:') or stripped.startswith('"'):
            current = None
            continue
        out[current].append(stripped.split(' in ')[0])
    return out


def linker_arguments(tree, archive, output):
    ldf = tree / '.LDFLAGS'
    if not ldf.is_file():
        raise SystemExit(f'no recorded link line at {ldf}')
    tokens = ldf.read_bytes().replace(b'\x00', b' ').replace(b'\n', b' ').decode().split()
    if not tokens:
        raise SystemExit(f'empty link line in {ldf}')
    args = tokens[:1] + ['-target', TARGET] + tokens[1:]
    if archive is not None:
        args.append('-Wl,-force_load,' + str(archive))
    args += ['-Wl,-filelist,' + str(tree / 'link.filelist'), '-o', str(output)]
    env = dict(os.environ)
    env['PATH'] = SHIM + os.pathsep + env.get('PATH', '')
    return args, env


def link(tree, archive, output):
    args, env = linker_arguments(tree, archive, output)
    run = subprocess.run(args, cwd=str(tree), capture_output=True, text=True, env=env)
    return run.returncode, run.stderr, args


def classify(symbol):
    if CLASSLIB in symbol:
        return 'storage-class'
    if symbol.startswith('_ZTV') or symbol.startswith('_ZN'):
        return 'cxx'
    return 'other'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tree', type=Path, required=True,
                        help='the xnu object directory holding .LDFLAGS and link.filelist')
    parser.add_argument('--archive', type=Path, default=None,
                        help='the archive to force_load; default <tree>/' + DEFAULT_ARCHIVE)
    parser.add_argument('--out', type=Path, default=None, help='write report.json here')
    parser.add_argument('--control-stderr', type=Path, default=None,
                        help='parse a saved ld stderr instead of linking the control')
    parser.add_argument('--archive-stderr', type=Path, default=None,
                        help='parse a saved ld stderr instead of linking with the archive')
    parser.add_argument('--dry-run', action='store_true', help='print the two link commands')
    parser.add_argument('--require-linkable', action='store_true',
                        help='exit 1 when the archive adds unresolved symbols')
    parser.add_argument('--out-report', type=Path, default=None, help='alias of --out')
    args = parser.parse_args()
    out = args.out or args.out_report

    archive = args.archive
    if archive is None:
        archive = args.tree.resolve().parents[3] / DEFAULT_ARCHIVE
        if not archive.is_file():
            archive = args.tree / DEFAULT_ARCHIVE

    if args.dry_run:
        for label, item in (('control', None), ('archive', archive)):
            args_list, _ = linker_arguments(args.tree, item, Path('/tmp/kernel-' + label))
            print(' '.join(args_list))
        print('bluetooth-storage-link: dry run')
        return 0

    if not (args.tree / '.LDFLAGS').is_file():
        print(f'FAIL no recorded link line at {args.tree / ".LDFLAGS"}')
        print('bluetooth-storage-link: FAILED')
        return 1
    if not archive.is_file():
        print(f'FAIL archive {archive} not found')
        print('bluetooth-storage-link: FAILED')
        return 1

    if args.control_stderr and args.archive_stderr:
        control_rc = int(os.environ.get('CONTROL_RC', '1'))
        archive_rc = int(os.environ.get('ARCHIVE_RC', '1'))
        control_err = args.control_stderr.read_text(errors='replace')
        archive_err = args.archive_stderr.read_text(errors='replace')
    else:
        if not archive.is_file():
            print(f'FAIL archive {archive} not found')
            print('bluetooth-storage-link: FAILED')
            return 1
        control_rc, control_err, _ = link(args.tree, None, Path('/tmp/kernel-control'))
        archive_rc, archive_err, _ = link(args.tree, archive, Path('/tmp/kernel-archive'))

    control = parse_undefined(control_err)
    with_archive = parse_undefined(archive_err)
    new = [s for s in with_archive if s not in control]
    rows = [{'symbol': s, 'class': classify(s),
             'referenced_from': with_archive[s][:4]} for s in new]
    storage = [r for r in rows if r['class'] == 'storage-class']

    print(f'control: rc={control_rc} undefined={len(control)}')
    print(f'archive: rc={archive_rc} undefined={len(with_archive)} new={len(new)}')
    for row in rows:
        print(f'  {row["class"]:<14} {row["symbol"]}')
        for referrer in row['referenced_from']:
            print(f'                 from {referrer}')

    if archive_rc == 0:
        print(f'linked {archive.name} into the recorded kernel link')
        print('bluetooth-storage-link: OK')
        return 0
    if storage:
        print(f'the archive needs {len(storage)} {CLASSLIB} import(s) the kernel image does not define')
        print(f'they live in the com.apple.iokit.IOStorageFamily fileset entry, not in the kernel proper')
        verdict = 'the archive does not link yet'
    elif new:
        print('the archive adds unresolved symbols that are not from the storage class')
        verdict = 'the archive does not link yet'
    elif control_rc != 0:
        print('the archive adds no new symbols; the recorded link already fails on its own')
        verdict = 'the recorded link does not stand on its own'
    else:
        verdict = 'the recorded link fails after the archive'
    print(verdict)

    if out is not None:
        import json
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            'archive': str(archive),
            'control_rc': control_rc,
            'archive_rc': archive_rc,
            'control_undefined': sorted(control),
            'archive_undefined': sorted(with_archive),
            'new_symbols': rows,
            'storage_imports': [r['symbol'] for r in storage],
            'hardware_verified': False,
        }, indent=2) + '\n')

    failed = bool(storage or new) or (control_rc != 0 and archive_rc != 0)
    if failed and args.require_linkable:
        print('bluetooth-storage-link: FAILED')
        return 1
    print('bluetooth-storage-link: gap')
    return 0


if __name__ == '__main__':
    sys.exit(main())
