#!/usr/bin/env python3
"""Build QcomBaseband with a prepared XNU tree's C++ and C compile records.

K60 device-local copy of the component build script. The upstream script
expects a macOS XNU record set with xcrun; this copy normalises the arguments
the K60 tree records, adds the missing -c, and uses llvm-ar on Linux. The
device copy overrides the root wrapper in tree/scripts, so a clean K60 build
does not depend on a patched QcomBaseband submodule.
"""
import argparse, hashlib, json, os, shutil, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'drivers/QcomBaseband'


def normalise(arguments):
    """Rejoin macro arguments the XNU record split on spaces.

    A build record stores argv as plain strings; a command line that carried
    -DCONFIG_NMBCLUSTERS=((1024 * 256) / MCLBYTES) arrives as five tokens.
    Rejoin a -D token whose parentheses are still open until the expression
    closes. No other token is touched.
    """
    out, i = [], 0
    while i < len(arguments):
        value = arguments[i]
        if value.startswith('-D') and value.count('(') > value.count(')'):
            pieces = [value]
            i += 1
            expression = value
            while i < len(arguments) and expression.count('(') > expression.count(')'):
                pieces.append(arguments[i])
                expression = ' '.join(pieces)
                i += 1
            out.append(expression)
            continue
        out.append(value)
        i += 1
    return out


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tree', type=Path, required=True)
parser.add_argument('--coachz', action='store_true', help='include the SC7180 IPA v4.2 board adapter')
args = parser.parse_args()
tree = args.tree.resolve()
out = tree / 'build/qcom-baseband'
out.mkdir(parents=True, exist_ok=True)


def record_for(name):
    matches = sorted((tree / 'build/xnu/ios-obj').glob('**/' + name))
    if len(matches) != 1:
        raise SystemExit(f'Expected one {name} compile record, found {len(matches)}')
    return json.loads(matches[0].read_text().strip().rstrip(','))


cpp = record_for('IOPlatformExpert.cpo.json')
c = record_for('vfs_conf.o.json') if args.coachz else None
sources = [(SOURCE / 'baseband/coachz_baseband.cpp', cpp)]
if args.coachz:
    sources += [(SOURCE / name, c) for name in ('ipa/coachz_ipa_config.c', 'ipa/coachz_gsi.c', 'platform/coachz/coachz_modem.c')]
objects, report = [], []
for source, record in sources:
    obj = out / (source.stem + '.o')
    argv, i = [], 0
    raw = normalise(record['arguments'])
    while i < len(raw):
        value = raw[i]
        if value in ('-o', '-MF', '-MT', '-MJ'):
            i += 2
            continue
        if value == '-Xclang' and i + 1 < len(raw) and raw[i + 1].startswith('-W'):
            i += 2
            continue
        if value == record['file'] or (value.endswith(('.cpp', '.c')) and not value.startswith('-')):
            value = str(source)
        if value not in ('-MD', '-MP') and not value.startswith('-W'):
            argv.append(value)
        i += 1
    if '-c' not in argv:
        argv.append('-c')
    argv += ['-o', str(obj), '-I', str(SOURCE / 'baseband'), '-I', str(SOURCE / 'ipa'), '-mgeneral-regs-only', '-Wall', '-Wextra']
    if str(source) not in argv:
        raise SystemExit('Compile record did not name its source: ' + record['file'])
    result = subprocess.run(argv, cwd=record['directory'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (out / (source.stem + '.log')).write_text(result.stdout)
    (out / (source.stem + '.command.json')).write_text(json.dumps(argv, indent=2) + '\n')
    if result.returncode:
        raise SystemExit(result.stdout[-6000:])
    objects.append(obj)
    report.append(dict(source=str(source.relative_to(SOURCE)), sha256=hashlib.sha256(source.read_bytes()).hexdigest(), object_sha256=hashlib.sha256(obj.read_bytes()).hexdigest()))
archive = out / 'libQcomBaseband.a'
archive.unlink(missing_ok=True)
ar = os.environ.get('AR') or shutil.which('llvm-ar') or shutil.which('ar')
if not ar:
    raise SystemExit('No archiver found: set AR or put llvm-ar on PATH')
subprocess.run([ar, 'rcs', str(archive), *map(str, objects)], check=True)
(out / 'build-report.json').write_text(json.dumps(dict(coachz=args.coachz, sources=report, archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest()), indent=2) + '\n')
print(f'QcomBaseband: {len(objects)} objects -> {archive}')
