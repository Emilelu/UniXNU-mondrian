#!/usr/bin/env python3
"""State, without running it, what compiling QcomDwc3.cpp against the 27 kernel needs.

`plan` reads the compile recipe the 27 XNU build itself wrote
(iokit/DEVELOPMENT/IOPlatformExpert.cpo.json) and turns it into one exact
command: same compiler, same 540 arguments, the component's own include roots
added, source and output swapped. It writes the request document, the command
JSON and nothing else. `run` executes that command (Lead's call, not this
script's) and then classifies every symbol the object leaves undefined.

Why the recipe rather than a hand-written flag list: -std=gnu++2b, -arch arm64e,
-mkernel, -fapple-kext, -DKERNEL_PRIVATE/-DXNU_KERNEL_PRIVATE/-DIOKIT_KERNEL_PRIVATE,
VM_KERNEL_LINK_ADDRESS and the 16 -I roots are what the kernel was built with.
Any flag we type by hand can drift from the kernel it must link against.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import shlex
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

# The recipes live under <build>/tree, next to .cache/xnu-work and the exported headers.
DEFAULT_TREE = pathlib.Path('/opt/k60/trees/ios27-out/mondrian/'
                            'ios-27.0.1-24A446/mondrian_ios27/tree')
DEFAULT_COMPONENT = pathlib.Path('/mnt/e/k60-work/scratch/usb27/refs-QcomDwc3')
DEFAULT_PACKAGE = pathlib.Path('/mnt/e/hackios/UniXNU-sheng/package')
PACKAGE_HEADERS = ('GeniI2c.h', 'QcomRpmh.h', 'AppsSmmuLock.h')
COMPONENT_HEADERS = ('QcomUcsi.h', 'QcomEusb2Phy.h', 'QcomQmpUsb3.h')
ABI_HEADERS = ('OriginalUsbXdciABI.h', 'OriginalUsbXhciABI.h')

# Symbols the object may leave undefined without blocking the export-surface
# answer, each for a stated reason. Anything outside these patterns is a bucket
# of its own and has to be named one by one.
FAMILY = re.compile(r'12AppleUSBX(DCI|HCI)')
FAMILY_EXTRA = ('__ZTV12AppleUSBXDCI', '__ZTI12AppleUSBXDCI', '__ZTS12AppleUSBXDCI',
                '__ZTV12AppleUSBXHCI', '__ZTI12AppleUSBXHCI', '__ZTS12AppleUSBXHCI')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_recipe(path):
    record = json.loads(path.read_text().strip().rstrip(','))
    arguments = record['arguments']
    if record['file'] not in arguments:
        raise SystemExit(f'{path}: arguments do not contain the source {record["file"]}')
    return record


def command_from(record, source, output, include_dirs):
    """Rewrite the recipe into a compile of `source` with the component's roots."""
    arguments = record['arguments']
    command = [arguments[0]]
    index = 1
    while index < len(arguments):
        value = arguments[index]
        if value == record['file']:
            command.append(str(source))
        elif value == '-o':
            command.extend(['-o', str(output)])
            index += 1
        elif value in ('-MF', '-MT', '-MQ', '-MJ'):
            index += 1
        elif value in ('-MD', '-MMD', '-MP'):
            pass
        else:
            command.append(value)
        index += 1
    for directory in include_dirs:
        command.extend(['-I', str(directory)])
    return command


def plan(args):
    tree, component = args.tree, args.component
    recipe_path = (tree / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/'
                   'IOPlatformExpert.cpo.json')
    if not recipe_path.is_file():
        raise SystemExit(f'{recipe_path}: the 27 build wrote no compile recipe here; '
                         'point --tree at a completed 27 build')
    record = load_recipe(recipe_path)
    source = component / 'QcomDwc3.cpp'
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    object_path = out / 'QcomDwc3.o'

    missing = []
    for name in COMPONENT_HEADERS:
        if not (component / name).is_file():
            missing.append(f'{component / name} (component checkout)')
    for name in PACKAGE_HEADERS:
        if not (args.package / name).is_file():
            missing.append(f'{args.package / name} (package headers)')
    for name in ABI_HEADERS:
        if not (args.abi / name).is_file():
            missing.append(f'{args.abi / name} (generated ABI headers)')

    command = command_from(record, source, object_path,
                           (args.abi, component, args.package))
    (out / 'QcomDwc3.command.json').write_text(json.dumps(command, indent=2) + '\n')

    quoted = ' \\\n  '.join(shlex.quote(part) for part in command)
    lines = []
    lines.append('# Build request: QcomDwc3.cpp against the 27 kernel\n')
    lines.append('Offline request only. Nothing here has been compiled by the usb27 line.\n')
    lines.append('## Recipe it is derived from\n')
    lines.append(f'- `{recipe_path}` (sha256 `{sha(recipe_path)}`)')
    lines.append(f'- compiler `{record["arguments"][0]}`')
    lines.append(f'- working directory `{record["directory"]}`')
    lines.append(f'- {len(record["arguments"])} arguments; the kernel flags stay as they are\n')
    lines.append('## Preconditions\n')
    lines.append(f'- component checkout at the catalog revision, `{source}`')
    lines.append(f'- package headers in `{args.package}`: {", ".join(PACKAGE_HEADERS)}')
    lines.append(f'- generated ABI headers in `{args.abi}`: {", ".join(ABI_HEADERS)}')
    lines.append('  (produced by `UniXNU-sheng/scripts/build-gop-legacy-display-27.py:551-589`'
                 ' from `scripts/usb-xdci-24A446.json`; this line does not regenerate them)')
    if missing:
        lines.append('')
        for item in missing:
            lines.append(f'- MISSING: {item}')
    lines.append('\n## Command\n')
    lines.append('```sh')
    lines.append(quoted)
    lines.append('```\n')
    lines.append(f'## Object to inspect\n\n`{object_path}`\n')
    lines.append('## Criteria\n')
    lines.append('1. the object exists and `llvm-nm-18 --format=posix` lists it;')
    lines.append('2. every undefined symbol is printed by name — no "and others", no counts;')
    lines.append('3. each name falls in exactly one bucket:')
    lines.append('   - family ABI (`AppleUSBXDCI`/`AppleUSBXHCI`), expected because the 27')
    lines.append('     collection ships neither kext;')
    lines.append('   - a 16.6.1 K60 diagnostic symbol with its patch, from')
    lines.append('     `docs/research/eight-step/usb-27-providers.tsv`;')
    lines.append('   - anything else: that bucket must be empty, and each name in it is a')
    lines.append('     finding for ② in `usb-27-export-surface.md`.')
    lines.append('4. `python3 scripts/usb27/kc-surface.py object <27 kernel> <object> '
                 '--providers docs/research/eight-step/usb-27-providers.tsv` prints the')
    lines.append('   resolvable count and one `FAIL <symbol> <- <provider>` line per missing')
    lines.append('   symbol.\n')
    (out / 'REQUEST.md').write_text('\n'.join(lines) + '\n')

    print(f'recipe  {recipe_path}')
    print(f'  sha256 {sha(recipe_path)}')
    print(f'command {out / "QcomDwc3.command.json"}')
    print(f'request {out / "REQUEST.md"}')
    print(f'object  {object_path}')
    for item in missing:
        print(f'MISSING {item}')
    if missing:
        print('RESULT FAIL (preconditions)')
        return 1
    print('RESULT PASS (plan only, nothing compiled)')
    return 0


def classify(names, providers):
    family, known, unknown = [], [], []
    for name in sorted(names):
        bare = name[1:] if name.startswith('_') else name
        if name in FAMILY_EXTRA or FAMILY.search(name):
            family.append(name)
        elif name in providers or bare in providers:
            known.append((name, providers.get(name) or providers[bare]))
        else:
            unknown.append(name)
    return family, known, unknown


def read_providers(path):
    providers = {}
    if path is None:
        return providers
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split('\t')
        if len(parts) >= 2:
            providers[parts[0]] = parts[1]
    return providers


def run(args):
    command_path = args.out / 'QcomDwc3.command.json'
    if not command_path.is_file():
        raise SystemExit(f'{command_path}: run the plan step first')
    command = json.loads(command_path.read_text())
    log = args.out / 'QcomDwc3.log'
    result = subprocess.run(command, cwd=args.out, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log.write_text(result.stdout)
    print(f'compile exit {result.returncode} (log {log})')
    if result.returncode:
        print(result.stdout[-4000:])
        print('RESULT FAIL (compile)')
        return 1
    return check(args)


def load_kc_surface():
    """Import kc-surface.py beside this script so both read symbols the same way."""
    import importlib.util
    path = pathlib.Path(__file__).resolve().with_name('kc-surface.py')
    spec = importlib.util.spec_from_file_location('kc_surface', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(args):
    object_path = args.object or (args.out / 'QcomDwc3.o')
    if not object_path.is_file():
        raise SystemExit(f'{object_path}: no object to inspect')
    surface = load_kc_surface()
    defined, _ = surface.nm_symbols(args.kernel, args.nm)
    _, needed = surface.nm_symbols(object_path, args.nm)
    missing = needed - defined
    providers = read_providers(args.providers)
    family, known, unknown = classify(missing, providers)
    print(f'kernel  {args.kernel} ({len(defined)} defined symbols)')
    print(f'object  {object_path} ({len(needed)} undefined symbols, sha256 {sha(object_path)})')
    print(f'  missing from the kernel {len(missing)}')
    print(f'  family ABI {len(family)}')
    for name in family:
        print(f'    family  {name}')
    print(f'  known 16.6.1 diagnostics {len(known)}')
    for name, provider in known:
        print(f'    known   {name} <- {provider}')
    print(f'  other {len(unknown)}')
    for name in unknown:
        print(f'    other   {name}')
    if unknown:
        print(f'RESULT FAIL ({len(unknown)} unexplained symbols)')
        return 1
    print('RESULT PASS')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('mode', nargs='?', default='plan', choices=('plan', 'run', 'check'))
    parser.add_argument('--tree', type=pathlib.Path, default=DEFAULT_TREE)
    parser.add_argument('--component', type=pathlib.Path, default=DEFAULT_COMPONENT)
    parser.add_argument('--package', type=pathlib.Path, default=DEFAULT_PACKAGE)
    parser.add_argument('--abi', type=pathlib.Path,
                        default=ROOT / 'build/usb27/abi',
                        help='directory holding the generated OriginalUsb*ABI.h')
    parser.add_argument('--out', type=pathlib.Path, default=ROOT / 'build/usb27/qcom-dwc3')
    parser.add_argument('--kernel', type=pathlib.Path,
                        default=pathlib.Path('/mnt/e/k60-work/scratch/usb27/'
                                             'kernel-27-652237c6.macho'))
    parser.add_argument('--nm', default='llvm-nm-18')
    parser.add_argument('--object', type=pathlib.Path,
                        help='inspect this object instead of the built one')
    parser.add_argument('--providers', type=pathlib.Path,
                        default=ROOT / 'docs/research/eight-step/usb-27-providers.tsv')
    args = parser.parse_args()
    handler = {'plan': plan, 'run': run, 'check': check}[args.mode]
    return handler(args)


if __name__ == '__main__':
    sys.exit(main())
