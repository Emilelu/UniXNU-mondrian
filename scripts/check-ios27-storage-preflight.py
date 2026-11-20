#!/usr/bin/env python3
"""Run the storage contract checks as one preflight.

Storage is the F3 line.  Stage 0 does not build NativeUfs, so at stage 0 this
preflight must stay green and say what it could check; it must not turn a
deliberately closed switch into a red build.  When the switch is on, one run
must satisfy all three closing conditions:

  1. CONFIG_XNU_NATIVE_UFS resolves to 1 and board.toml includes NativeUfs;
  2. the 190-slot vtable assertion passes (--require-entry);
  3. the prelink reports zero untranslated targets (--require-translated).

They have to hold in the same run: a config that says yes while the collection
was built before the flip does not open the gate.  The switch state is printed
last, after both contract results, so a reader sees the evidence before the
verdict.

When the switch is off the exit status is 0 even if no build inputs exist.  The
checks then run against whatever inputs were supplied, and the run reports
itself as pending rather than failed.

Nothing here builds, boots or writes into the output tree.
"""

import argparse
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


def run(command):
    done = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
    return done.returncode, (done.stdout or '') + (done.stderr or '')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--framework', default='')
    parser.add_argument('--profile', default=DEFAULT_PROFILE)
    parser.add_argument('--kernelcache')
    parser.add_argument('--report')
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
    switch_on = switch_value == 1 and include_ufs
    switch_source = origin.get('CONFIG_XNU_NATIVE_UFS', 'missing')

    cache = Path(args.kernelcache) if args.kernelcache else None
    report = Path(args.report) if args.report else None

    entry_rc = None
    translated_rc = None
    entry_output = ''
    translated_output = ''

    if cache and cache.is_file():
        command = [sys.executable, str(scripts / 'check-ios27-storage-vtable.py'),
                   '--kernelcache', str(cache), '--vtable', args.vtable,
                   '--require-entry']
        if args.table:
            command += ['--table', args.table]
        entry_rc, entry_output = run(command)
        print('[entry] --require-entry: ' + ('pass' if entry_rc == 0 else 'FAIL'))
        for line in entry_output.strip().splitlines():
            print('  ' + line)
    else:
        print('[entry] skipped: no kernelcache supplied')

    if cache and cache.is_file() and report and report.is_file():
        command = [sys.executable, str(scripts / 'check-ios27-prelink-closure.py'),
                   '--report', str(report), '--kernelcache', str(cache),
                   '--require-translated']
        translated_rc, translated_output = run(command)
        print('[translated] --require-translated: '
              + ('pass' if translated_rc == 0 else 'FAIL'))
        for line in translated_output.strip().splitlines():
            print('  ' + line)
    else:
        print('[translated] skipped: no kernelcache and report supplied')

    print(f'switch: CONFIG_XNU_NATIVE_UFS={switch_value} ({switch_source}), '
          f'board.toml include has NativeUfs={include_ufs}')

    supplied = [str(path) for path in (cache, report) if path]
    source_text = ', '.join(supplied) if supplied else 'no build inputs'

    verdict = 'pending'
    code = 0
    if not switch_on:
        print(f'NOTE storage: stage 0 does not build NativeUfs (switch off); '
              f'contract checks ran against {source_text} only')
    elif entry_rc == 0 and translated_rc == 0:
        verdict = 'passed'
    else:
        verdict = 'failed'
        code = 1
        if entry_rc is None:
            print('FAIL storage: switch is on but no kernelcache was supplied for --require-entry')
        if translated_rc is None:
            print('FAIL storage: switch is on but no kernelcache and report were supplied '
                  'for --require-translated')

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
            },
            'entry': {'ran': entry_rc is not None, 'rc': entry_rc},
            'translated': {'ran': translated_rc is not None, 'rc': translated_rc},
            'verdict': verdict,
            'hardware_verified': False,
        }, indent=1) + '\n')
    return code


if __name__ == '__main__':
    sys.exit(main())
