#!/usr/bin/env python3
"""Run the storage contract checks as one preflight.

Storage is the F3 line.  Stage 0 does not build NativeUfs, so at stage 0 this
preflight must stay green and say what it could check; it must not turn a
deliberately closed switch into a red build.  When the switch is on, one run
must satisfy all three closing conditions:

  1. CONFIG_XNU_NATIVE_UFS resolves to 1 and board.toml includes NativeUfs;
  2. the 190-slot vtable assertion passes on the built collection
     (--require-entry; this entry fixes the slot count at 190);
  3. the prelink report describes this run and no rebased target lies inside
     the input kernel's __TEXT (--require-translated with --collection, which
     supplies the output spans the report's layout omits): the report's input
     kernelcache and the collection it wrote must both be the files supplied
     here.

They have to hold in the same run: a config that says yes while the collection
was built before the flip does not open the gate, and a report from an older
build does not describe today's collection.  The switch state is printed last,
after both contract results, so a reader sees the evidence before the verdict.

The two selectors must agree as well: a config that says yes while the board
does not select NativeUfs (or the other way round) is a half-set switch, and a
half-set switch fails rather than pends.

Two inputs are separate on purpose:

  --collection   the built kernel collection; the vtable lives here
  --kernelcache  the input kernelcache the prelink read; the report's target
                 addresses are expressed in its address space

When the switch is off the exit status is 0 even if no build inputs exist.  The
checks then run against whatever inputs were supplied, and the run reports
itself as pending rather than failed.

Nothing here builds, boots or writes into the output tree.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - the Linux host has 3.11+
    tomllib = None

DEFAULT_PROFILE = 'ios-27.0.1-24A446'
DEFAULT_VTABLE = '0xfffffff008314d88'
SLOTS = 190  # fixed by the contract; not a command line choice


def parse_config(path):
    values, origin = {}, {}
    if not path.is_file():
        return values, origin
    for number, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('CONFIG_') and '=' in line:
            name, value = line.split('=', 1)
        elif line.startswith('CONFIG_'):
            name, value = line, 'y'
        else:
            continue
        value = value.strip().strip('"')
        if value == 'y':
            value = 1
        elif value == 'n':
            value = 0
        elif value.isdigit():
            value = int(value)
        values[name] = value
        origin[name] = f'{path.name}:{number}'
    return values, origin


def profile_section(board, profile):
    overrides = board.get('os_overrides', {}).get(profile, {})
    if not overrides:
        raise SystemExit(f'FAIL board.toml has no os_overrides entry for {profile}')
    return overrides


def config_layers(root, framework, profile, section):
    kernel = section.get('kernel', {})
    layers = []
    for entry in kernel.get('config_fragments', []):
        if ':' in entry:
            component, rest = entry.split(':', 1)
            bases = {
                'arch': framework / 'profiles' / 'arch' / 'arm64e',
                'os': framework / 'profiles' / 'os' / profile,
                'soc': root.parent / 'UniXNU-sm8475-common',
            }
            path = bases.get(component, root) / rest
        else:
            path = root / entry
        layers.append(path)
    name = kernel.get('defconfig')
    if name:
        layers.append(root / 'configs' / name)
    return layers


def read_board(root):
    path = root / 'board.toml'
    if not path.is_file():
        raise SystemExit(f'FAIL {path} not found')
    if tomllib is None:
        raise SystemExit('FAIL python3 has no tomllib to read board.toml')
    return tomllib.loads(path.read_text())


def sha256_of(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def run(command):
    done = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
    return done.returncode, (done.stdout or '') + (done.stderr or '')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--framework', default='')
    parser.add_argument('--profile', default=DEFAULT_PROFILE)
    parser.add_argument('--collection', help='built kernel collection (vtable evidence)')
    parser.add_argument('--kernelcache', help='input kernelcache the prelink read')
    parser.add_argument('--report', help='kernel.json from the prelink emitter')
    parser.add_argument('--vtable', default=DEFAULT_VTABLE)
    parser.add_argument('--table')
    parser.add_argument('--out')
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    framework = Path(args.framework).resolve() if args.framework else root.parent / 'UniXNU'
    scripts = Path(__file__).resolve().parent

    board = read_board(root)
    section = profile_section(board, args.profile)
    layers = config_layers(root, framework, args.profile, section)

    values, origin, used = {}, {}, []
    for path in layers:
        layer_values, layer_origin = parse_config(path)
        values.update(layer_values)
        origin.update(layer_origin)
        if layer_values:
            used.append(path)

    include = section.get('components', {}).get('include', [])
    include_ufs = 'NativeUfs' in include
    switch_value = values.get('CONFIG_XNU_NATIVE_UFS')
    config_on = switch_value == 1
    switch_on = config_on and include_ufs
    half_set = config_on != include_ufs
    switch_source = origin.get('CONFIG_XNU_NATIVE_UFS', 'missing')

    collection = Path(args.collection) if args.collection else None
    cache = Path(args.kernelcache) if args.kernelcache else None
    report = Path(args.report) if args.report else None

    problems = []
    binding = []
    entry_rc = None
    translated_rc = None

    if collection is not None and collection.is_file():
        command = [sys.executable, str(scripts / 'check-ios27-storage-vtable.py'),
                   '--kernelcache', str(collection), '--vtable', args.vtable,
                   '--slots', str(SLOTS), '--require-entry']
        if args.table:
            command += ['--table', args.table]
        entry_rc, output = run(command)
        print('[entry] --require-entry on the collection: '
              + ('pass' if entry_rc == 0 else 'FAIL'))
        for line in output.strip().splitlines():
            print('  ' + line)
    elif collection is not None:
        problems.append(f'collection {collection} not found')
    elif switch_on:
        problems.append('no --collection supplied, so the slot assertion has no subject')
    else:
        print('[entry] skipped: no collection supplied')

    record = None
    if report is not None and report.is_file():
        try:
            record = json.loads(report.read_text())
        except ValueError as error:
            record = None
            problems.append(f'report {report} is not JSON: {error}')
    elif report is not None:
        problems.append(f'report {report} not found')
    elif switch_on:
        problems.append('no --report supplied, so the prelink result cannot be bound')

    if record is not None:
        inputs = record.get('inputs') or {}
        if collection is not None and collection.is_file():
            expected = record.get('candidate_sha256')
            actual = sha256_of(collection)
            ok = bool(expected) and expected == actual
            binding.append({'what': 'collection', 'expected': expected,
                            'actual': actual, 'ok': ok})
            if not expected:
                problems.append('the report does not name the collection it described')
            elif not ok:
                problems.append(f'the report describes collection {expected} '
                                f'but this run supplies {actual}')
            print('binding: collection ' + actual
                  + (' matches the report' if ok else ' does not match the report'))
        if cache is not None and cache.is_file():
            expected = inputs.get('kernelcache_sha256')
            actual = sha256_of(cache)
            ok = bool(expected) and expected == actual
            binding.append({'what': 'kernelcache', 'expected': expected,
                            'actual': actual, 'ok': ok})
            if not expected:
                problems.append('the report does not name the input kernelcache it was made from')
            elif not ok:
                problems.append(f'the report was made from kernelcache {expected} '
                                f'but this run supplies {actual}')
            print('binding: kernelcache ' + actual
                  + (' matches the report' if ok else ' does not match the report'))

    if cache is not None and cache.is_file() and record is not None:
        command = [sys.executable, str(scripts / 'check-ios27-prelink-closure.py'),
                   '--report', str(report), '--kernelcache', str(cache),
                   '--require-translated']
        if collection is not None and collection.is_file():
            command += ['--collection', str(collection)]
        else:
            command += []
        translated_rc, output = run(command)
        print('[translated] --require-translated: '
              + ('pass' if translated_rc == 0 else 'FAIL'))
        for line in output.strip().splitlines():
            print('  ' + line)
    elif switch_on:
        problems.append('no --kernelcache and --report supplied, '
                        'so the translation assertion has no subject')
    else:
        print('[translated] skipped: no kernelcache and report supplied')

    print(f'switch: CONFIG_XNU_NATIVE_UFS={switch_value} ({switch_source}), '
          f'board.toml include has NativeUfs={include_ufs}')

    supplied = [str(path) for path in (collection, cache, report) if path]
    source_text = ', '.join(supplied) if supplied else 'no build inputs'
    if half_set:
        problems.append(f'the selectors disagree: CONFIG_XNU_NATIVE_UFS={switch_value} '
                        f'({switch_source}), board.toml include has NativeUfs={include_ufs}')
    label = 'FAIL storage: ' if (switch_on or half_set) else 'note storage: '
    for problem in problems:
        print(label + problem)

    verdict = 'pending'
    code = 0
    if half_set:
        verdict = 'failed'
        code = 1
    elif not switch_on:
        print(f'NOTE storage: stage 0 does not build NativeUfs (switch off); '
              f'contract checks ran against {source_text} only')
    elif entry_rc == 0 and translated_rc == 0 and not problems:
        verdict = 'passed'
    else:
        verdict = 'failed'
        code = 1

    print(f'storage preflight: {verdict}')
    if args.out:
        Path(args.out).write_text(json.dumps({
            'root': str(root),
            'profile': args.profile,
            'layers': [str(path) for path in used],
            'switch': {
                'config': switch_value,
                'config_origin': switch_source,
                'include': include,
                'include_ufs': include_ufs,
                'on': switch_on,
                'half_set': half_set,
            },
            'collection': str(collection) if collection else None,
            'kernelcache': str(cache) if cache else None,
            'report': str(report) if report else None,
            'slots': SLOTS,
            'binding': binding,
            'entry': {'ran': entry_rc is not None, 'rc': entry_rc},
            'translated': {'ran': translated_rc is not None, 'rc': translated_rc},
            'problems': problems,
            'verdict': verdict,
            'hardware_verified': False,
        }, indent=1) + '\n')
    return code


if __name__ == '__main__':
    sys.exit(main())
