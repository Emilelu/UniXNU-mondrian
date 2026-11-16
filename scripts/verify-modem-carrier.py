#!/usr/bin/env python3
"""Offline acceptance for the modem-carrier handoff, on real inputs.

Runs the framework half of docs/research/cellular/16-FRAMEWORK-REQUEST.md
section 5 and records the receipt described by
docs/research/cellular/17-OFFLINE-ACCEPTANCE-CHECKLIST.md section 5.1-5.3:

  5.1  modem=True publishes K60ModemImage in /chosen/memory-map as exactly 16
       zero bytes; modem=False has no such key; data=True and modem=True
       coexist.
  5.2  a carrier directory passes the shipped-table check, and a volume built
       from it carries the 27 streams under EFI/UniXNU/MODEM with the names the
       manifest lists; payload.json can record their identity.
  5.3  without the switch the ADT is unchanged (modulo the random seed that
       generate() draws from os.urandom, which this tool masks and declares).

Every input is a parameter; nothing about /mnt is assumed.  The tool reads the
framework checkout and the firmware inputs and writes only under --work.  It
does not run 'unixnu build payload', does not build the kernel, and never talks
to a device: it stops at the framework-level subset of the checklist.  The full
whole-pipeline acceptance needs the strict build receipts listed in doc 17.

Exit code 0 only when every check passes, 1 when a check fails, 2 when a
preflight input is missing or the framework checkout cannot be trusted.
"""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path

CELLULAR = Path(__file__).resolve().parent.parent
DEFAULT_SEED = '4B36305400000001'
# Files that make up the carrier implementation.  If any of them is modified in
# the worktree, the framework under test is not the delivered revision and the
# receipt would be about a different program.
CARRIER_IMPLEMENTATION = (
    'scripts/unixnu/payload.py',
    'scripts/unixnu/devicetree.py',
    'scripts/unixnu/cli.py',
)
EXPECTED_FILES = 27
EXPECTED_DECLARED = 109060761
# The firmware table has 30 rows: 27 file rows plus the pure-bss rows 14, 21 and
# 30.  The names are therefore NOT b01..b27 and NOT b01..b30 - a range() would
# reject b28/b29 and demand b14/b21/b30, which have no file.
EXPECTED_FIRST = {'modem.b01', 'modem.b02'}
EXPECTED_LAST = {'modem.b28', 'modem.b29'}
EXPECTED_BSS_ONLY = {'modem.b14', 'modem.b21', 'modem.b30'}


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def describe(path):
    return {'path': str(path.resolve()), 'size': path.stat().st_size, 'sha256': sha256_file(path)}


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Offline acceptance for the modem-carrier handoff (doc 17 section 5).',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument('--unixnu', type=Path, default=Path('/mnt/e/hackios/UniXNU'),
                        help='framework checkout that carries the delivered carrier implementation')
    parser.add_argument('--board', type=Path, default=None,
                        help='board.toml used by generate(); defaults to <unixnu>/../UniXNU-mondrian/board.toml')
    parser.add_argument('--dtb', type=Path, required=True,
                        help='hardware.dtb handed to generate()')
    parser.add_argument('--carrier', type=Path, required=True,
                        help='carrier directory holding <segment>.lzma streams')
    parser.add_argument('--manifest', type=Path, default=None,
                        help='table text (segment name and bytes per line); defaults to <carrier>/modem-table.txt')
    parser.add_argument('--seed', default=DEFAULT_SEED,
                        help='unique chip id passed to generate()')
    parser.add_argument('--work', type=Path, required=True,
                        help='evidence directory; must be new or disposable, receives all output')
    parser.add_argument('--receipt', default='acceptance.json',
                        help='receipt filename written under --work')
    parser.add_argument('--modem-size-mib', type=int, default=96,
                        help='volume size passed to payload.write_volume()')
    parser.add_argument('--expect-framework-sha', default=None,
                        help='refuse to run unless the framework HEAD equals this 40-character SHA')
    return parser.parse_args(argv)


def preflight(args):
    """Return (unixnu, board, dtb, carrier, manifest, work, problems)."""
    problems = []
    unixnu = args.unixnu.resolve()
    board = (args.board or (unixnu.parent / 'UniXNU-mondrian' / 'board.toml')).resolve()
    dtb = args.dtb.resolve()
    carrier = args.carrier.resolve()
    manifest = (args.manifest.resolve() if args.manifest
                else carrier / 'modem-table.txt')
    work = args.work.resolve()

    for label, path in (('framework checkout', unixnu), ('board.toml', board),
                        ('hardware.dtb', dtb), ('carrier', carrier),
                        ('manifest', manifest)):
        if not path.exists():
            problems.append(f'{label} does not exist: {path}')
    if problems:
        return unixnu, board, dtb, carrier, manifest, work, problems

    if not carrier.is_dir():
        problems.append(f'carrier is not a directory: {carrier}')
        return unixnu, board, dtb, carrier, manifest, work, problems

    head = git(unixnu, 'rev-parse', 'HEAD')
    if head.returncode != 0:
        problems.append(f'{unixnu} is not a readable git checkout: {head.stderr.strip()}')
    elif args.expect_framework_sha and head.stdout.strip() != args.expect_framework_sha:
        problems.append(f'framework HEAD is {head.stdout.strip()}, expected {args.expect_framework_sha}')

    status = git(unixnu, 'status', '--porcelain')
    if status.returncode == 0:
        for line in status.stdout.splitlines():
            path = line[3:].strip()
            if path in CARRIER_IMPLEMENTATION:
                problems.append(f'the carrier implementation is modified in the worktree: {path}')
    else:
        problems.append(f'git status failed in {unixnu}: {status.stderr.strip()}')

    if not any(carrier.glob('*.lzma')):
        problems.append(f'carrier holds no .lzma stream: {carrier}')
    return unixnu, board, dtb, carrier, manifest, work, problems


def mtools_version():
    try:
        result = subprocess.run(['mdir', '--version'], capture_output=True, text=True)
        text = (result.stdout or result.stderr).strip().splitlines()
        return text[0] if text else 'unknown'
    except OSError:
        return 'missing'


def main(argv=None):
    args = parse_args(argv)
    unixnu, board, dtb, carrier_path, manifest_path, work, problems = preflight(args)
    if problems:
        for problem in problems:
            print(f'PREFLIGHT FAIL: {problem}')
        return 2
    work.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(unixnu / 'scripts'))
    sys.path.insert(0, str(CELLULAR / 'scripts'))
    from unixnu import payload as payload_step            # noqa: E402
    from unixnu.devicetree import generate                # noqa: E402
    from pong_adt_contract import parse_adt               # noqa: E402

    results = []

    def check(name, condition, detail=''):
        results.append({'id': name, 'ok': bool(condition), 'detail': str(detail)})
        suffix = f': {detail}' if detail and not condition else ''
        print(('ok   ' if condition else 'FAIL ') + name + suffix)

    board_config = tomllib.loads(board.read_text(encoding='utf-8'))

    # ---- 5.1 the placeholder is published only with the switch ----------------
    on = generate(dtb, board_config, unique_chip_id=args.seed, data=True, modem=True)
    off = generate(dtb, board_config, unique_chip_id=args.seed, data=True, modem=False)
    plain = generate(dtb, board_config, unique_chip_id=args.seed, data=True)
    (work / 'adt-modem-on.bin').write_bytes(on)
    (work / 'adt-modem-off.bin').write_bytes(off)

    on_map = parse_adt(on)['/chosen/memory-map']
    off_map = parse_adt(off)['/chosen/memory-map']
    plain_map = parse_adt(plain)['/chosen/memory-map']
    check('5.1 modem=True publishes K60ModemImage as exactly 16 zero bytes',
          on_map.get('K60ModemImage') == bytes(16), repr(on_map.get('K60ModemImage')))
    check('5.1 modem=False has no K60ModemImage key at all',
          'K60ModemImage' not in off_map, repr(sorted(off_map)))
    check('5.1 the default call is the same as modem=False',
          plain_map == off_map, f'{sorted(plain_map)} vs {sorted(off_map)}')
    check('5.1 data=True and modem=True coexist',
          'RAMDisk' in on_map and 'K60ModemImage' in on_map, repr(sorted(on_map)))
    def without_carrier(tree):
        stripped = {path: dict(props) for path, props in tree.items()}
        stripped.get('/chosen', {}).pop('random-seed', None)
        stripped.get('/chosen/memory-map', {}).pop('K60ModemImage', None)
        return stripped

    on_full, off_full = parse_adt(on), parse_adt(off)
    check('5.3 the ADT differs only by the carrier entry',
          without_carrier(on_full) == without_carrier(off_full) and
          'K60ModemImage' in on_full['/chosen/memory-map'],
          f'paths only in one side: {sorted(set(on_full) ^ set(off_full))}')

    # generate() draws the random-seed from os.urandom(256); the off path can
    # only be shown equivalent modulo that documented input.
    again = parse_adt(generate(dtb, board_config, unique_chip_id=args.seed, data=True, modem=False))
    off_all = parse_adt(off)
    mask = lambda props: {k: v for k, v in props.items() if k != 'random-seed'}  # noqa: E731
    check('5.3 modem=False matches a second default run except for the random seed',
          mask(again['/chosen']) == mask(off_all['/chosen']) and
          again['/chosen/memory-map'] == off_all['/chosen/memory-map'],
          str(sorted(set(mask(again['/chosen'])) ^ set(mask(off_all['/chosen'])))))

    # ---- 5.2 the carrier, its table and the volume ---------------------------
    carrier_dir = work / 'carrier'
    shutil.rmtree(carrier_dir, ignore_errors=True)
    carrier_dir.mkdir()
    for path in sorted(carrier_path.iterdir()):
        if path.suffix == '.lzma':
            (carrier_dir / path.name).symlink_to(path.resolve())
    (carrier_dir / payload_step.MODEM_MANIFEST).write_text(
        manifest_path.read_text(encoding='utf-8'), encoding='utf-8')

    carrier = payload_step.read_modem_carrier(carrier_dir)
    names = carrier['names']
    shape_ok = (len(names) == EXPECTED_FILES and
                EXPECTED_FIRST <= set(names) and EXPECTED_LAST <= set(names) and
                not (EXPECTED_BSS_ONLY & set(names)))
    check('5.2 the carrier passes the table check',
          len(names) == EXPECTED_FILES and shape_ok,
          f'{len(names)} name(s), first={names[:2]}, last={names[-2:]}')
    check('5.2 the declared total matches the firmware table',
          carrier['declared'] == EXPECTED_DECLARED, str(carrier['declared']))

    stage = work / 'stage'
    shutil.rmtree(stage, ignore_errors=True)
    (stage / 'EFI/UniXNU/Payloads').mkdir(parents=True)
    (stage / 'EFI/UniXNU/Payloads/kernel.macho').write_bytes(b'\0' * 4096)
    (stage / 'EFI/UniXNU/unixnu.toml').write_text('version = 1\n')
    modem = stage / payload_step.MODEM_DIRECTORY
    modem.mkdir(parents=True)
    for name in names:
        shutil.copyfile(carrier['directory'] / f'{name}.lzma', modem / f'{name}.lzma')

    image = work / 'payload.img'
    payload_step.write_volume(stage, image, 'UNIXNU', args.modem_size_mib)
    listing = subprocess.run(
        ['mdir', '-i', str(image), '-b', f'::{payload_step.MODEM_DIRECTORY}'],
        env={**os.environ, 'MTOOLS_SKIP_CHECK': '1', 'TZ': 'UTC'},
        capture_output=True, text=True)
    listed = [line.strip() for line in listing.stdout.splitlines() if line.strip()]
    check('5.2 the volume carries 27 streams',
          listing.returncode == 0 and len(listed) == EXPECTED_FILES,
          f'rc={listing.returncode} lines={len(listed)} {listing.stderr.strip()[:120]}')
    check('5.2 the volume carries the same names the table lists',
          sorted(Path(name).name for name in listed) == [f'{name}.lzma' for name in names],
          f'{sorted(listed)[:3]}')

    report = {'modem_carrier_files': len(names), 'modem_carrier_bytes': carrier['declared'],
              'modem_carrier_compressed_bytes': carrier['compressed'],
              'modem_carrier_sha256': carrier['sha256'], 'modem_carrier_placeholder': True,
              'payload_sha256': sha256_file(image)}
    (work / 'payload.json').write_text(json.dumps(report, indent=2) + '\n')
    check('5.2 payload.json records the carrier identity',
          report['modem_carrier_files'] == EXPECTED_FILES and len(report['modem_carrier_sha256']) == 64,
          json.dumps(report)[:120])

    failures = [item for item in results if not item['ok']]
    acceptance = 'PASS' if not failures else 'FAIL'
    receipt = {
        'tool': str(Path(__file__).resolve()),
        'scope': 'framework-level subset of doc 17 section 5 (5.1, 5.2 volume, 5.3); '
                 'not the whole unixnu payload step',
        'started_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'argv': sys.argv,
        'inputs': {
            'framework': {'path': str(unixnu),
                          'head': git(unixnu, 'rev-parse', 'HEAD').stdout.strip(),
                          'dirty': [line for line in git(unixnu, 'status', '--porcelain').stdout.splitlines()]},
            'board': describe(board), 'dtb': describe(dtb), 'manifest': describe(manifest_path),
            'carrier': {'path': str(carrier_path), 'names': len(names),
                        'declared': carrier['declared'], 'compressed': carrier['compressed'],
                        'aggregate_sha256': carrier['sha256'],
                        'streams': {name: {'size': (carrier['directory'] / f'{name}.lzma').stat().st_size,
                                           'sha256': sha256_file(carrier['directory'] / f'{name}.lzma')}
                                    for name in names}},
        },
        'tools': {'python': platform.python_version(), 'mtools': mtools_version()},
        'checks': results,
        'expected': {'files': EXPECTED_FILES, 'declared': EXPECTED_DECLARED,
                     'bss_only_rows': sorted(EXPECTED_BSS_ONLY)},
        'acceptance': acceptance,
        'passed': len(results) - len(failures),
        'total': len(results),
        'exit_code': 0 if not failures else 1,
    }
    receipt_path = work / args.receipt
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')

    print(f'\nACCEPTANCE {acceptance} {len(results) - len(failures)}/{len(results)}')
    print(f'receipt: {receipt_path}')
    if failures:
        for item in failures:
            print(f'  failed: {item["id"]}')
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main())
