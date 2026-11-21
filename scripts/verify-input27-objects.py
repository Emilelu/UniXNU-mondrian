#!/usr/bin/env python3
"""Check the iOS 27 input objects against the contract in the eight-step ledger.

The input line ships two kernel sources to the 27 tree (bsd/dev/pong_goodix.c and
bsd/dev/pong_buttons.c). Building them belongs to the Lead; this script only
answers one question once the `.o` files exist: are they the objects that the 27
sources would produce, or are they something else?

Every path is a parameter. A hardcoded /opt path once produced a false verdict on
a different tree, so nothing here knows where the build lives.

Verdicts
  PASS     every check passed; the ledger's artifact_check can be filled in.
  FAIL     the object exists and came from the 27 tree but contradicts the
           sources: a format string or a defined symbol is missing, the line
           table is short, the struct size is wrong, or an unmapped-fileset stub
           is left in the undefined symbols.
  INVALID  the evidence itself is unusable, so no judgement is possible: an
           object is missing or empty, DWARF is absent, the source path is not
           the 27 tree, or the build's input manifests are missing.

Usage
  verify-input27-objects.py --xnu-work /path/to/tree/.cache/xnu-work \
      --obj-dir /path/to/build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG
  verify-input27-objects.py --xnu-work DIR --work DIR --obj-dir DIR --json
  verify-input27-objects.py --self-test        # builds fixtures with host clang
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

GOODIX = 'bsd/dev/pong_goodix.c'
BUTTONS = 'bsd/dev/pong_buttons.c'
INPUT = 'bsd/dev/pong_input.c'

# Expected shapes. Line counts are the lengths of the 27 sources after the touch
# and keys patches apply; a shorter table means the object was built from an
# older, truncated source.
EXPECT = {
    'goodix': {
        'object': 'pong_goodix.o',
        'source': GOODIX,
        'min_lines': 1375,
        'strings': ['COORD-ON', 'goodix: %s ack=%02x'],
        'symbols': ['pong_goodix_init'],
    },
    'buttons': {
        'object': 'pong_buttons.o',
        'source': BUTTONS,
        'min_lines': 171,
        'strings': ['Pong keys: arbiter v%u'],
        'symbols': ['pong_buttons_init'],
    },
    'input': {
        'object': 'pong_input.o',
        'source': INPUT,
        'min_lines': 107,
        'strings': ['Pong touch'],
        'symbols': ['pong_touch_post', 'pong_touch_device_ready'],
        'optional': True,
    },
}
TOUCH_PATCH = 'pong-touch-console'
KEYS_PATCH = 'pong-physical-keys'
STRUCT = 'pong_touch'
STRUCT_BYTES = 24
STUB_SUFFIX = '_unixnu_fileset_unmapped'
NEAR_MISS = 0.05  # a line table this close below the expectation is INVALID, not FAIL


def find_tool(name, override=None, versions=(18, 17, 19, 20)):
    if override:
        return override
    found = shutil.which(name)
    if found:
        return found
    for version in versions:
        found = shutil.which(f'{name}-{version}')
        if found:
            return found
    return None


def run(argv):
    return subprocess.run(argv, capture_output=True, text=True, errors='replace')


class Report:
    def __init__(self):
        self.rows = []

    def add(self, code, ok, detail):
        self.rows.append({'code': code, 'ok': bool(ok), 'detail': detail})

    @property
    def invalid(self):
        return [row for row in self.rows if row['code'].startswith('I') and not row['ok']]

    @property
    def failed(self):
        return [row for row in self.rows if row['code'].startswith('F') and not row['ok']]

    def verdict(self):
        if self.invalid:
            return 'INVALID'
        if self.failed:
            return 'FAIL'
        return 'PASS'

    def explain(self):
        lines = []
        for row in self.rows:
            mark = 'ok  ' if row['ok'] else 'FAIL'
            lines.append(f'  [{mark}] {row["code"]}: {row["detail"]}')
        return '\n'.join(lines)


def resolve_work(xnu_work, work):
    """Find the directory holding xnu-inputs.json and xnu-patches.list.

    patches.py writes both into the build work directory (`ctx.work`), which sits
    beside `tree/`, not inside `.cache/xnu-work`; older notes put them under the
    checkout. Search upward instead of assuming either layout.
    """
    if work:
        return work
    current = os.path.abspath(xnu_work)
    for _ in range(6):
        if os.path.isfile(os.path.join(current, 'xnu-inputs.json')):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None


def check_manifests(report, work, xnu_work):
    if not work:
        report.add('I4', False, 'no xnu-inputs.json found upward from --xnu-work; pass --work')
        return None
    stamp = os.path.join(work, 'xnu-inputs.json')
    listing = os.path.join(work, 'xnu-patches.list')
    if not os.path.isfile(stamp) or not os.path.isfile(listing):
        report.add('I4', False, f'manifests missing in {work} (xnu-inputs.json / xnu-patches.list)')
        return None
    try:
        data = json.loads(open(stamp, encoding='utf-8').read())
    except ValueError as error:
        report.add('I4', False, f'xnu-inputs.json does not parse: {error}')
        return None
    patches = data.get('patches') or []
    names = [os.path.basename(entry.get('path', '')) for entry in patches]
    absent = [name for name in (TOUCH_PATCH, KEYS_PATCH)
              if not any(name in entry for entry in names)]
    listed = [line.strip() for line in open(listing, encoding='utf-8') if line.strip()]
    problems = []
    if absent:
        problems.append('input patches absent from the manifest: ' + ', '.join(absent))
    if len(listed) != len(patches):
        problems.append(f'xnu-patches.list has {len(listed)} lines but the stamp records {len(patches)}')
    checked = 0
    for entry in patches:
        path = entry.get('path', '')
        digest = entry.get('sha256', '')
        if not path or not os.path.isfile(path):
            continue
        actual = hashlib.sha256(open(path, 'rb').read()).hexdigest()
        checked += 1
        if actual != digest:
            problems.append(f'sha256 mismatch: {os.path.basename(path)}')
            break
    if problems:
        report.add('I4', False, '; '.join(problems))
        return None
    report.add('I4', True, f'{len(patches)} patched inputs, {checked} re-hashed, '
                           f'source {data.get("source")} at {str(data.get("commit"))[:12]}, '
                           f'touch and keys present')
    return data


def dwarf_dump(dwarfdump, obj, *flags):
    result = run([dwarfdump, *flags, obj])
    return result.stdout if result.returncode == 0 else ''


def check_object(report, label, spec, obj_dir, xnu_work, dwarfdump, nm):
    path = os.path.join(obj_dir, spec['object'])
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        report.add('I1', False, f'{label}: {spec["object"]} missing or empty in {obj_dir}')
        return
    report.add('I1', True, f'{label}: {spec["object"]} {os.path.getsize(path):,} B')

    info = dwarf_dump(dwarfdump, path, '--debug-info')
    if not info.strip():
        report.add('I3', False, f'{label}: no DWARF debug info (llvm-dwarfdump returned nothing)')
        return
    report.add('I3', True, f'{label}: DWARF present ({len(info.splitlines())} lines)')

    unit = re.search(r'DW_TAG_compile_unit.*?DW_AT_name\s*\("([^"]+)"\)', info, re.S)
    if not unit:
        report.add('I2', False, f'{label}: compile unit has no DW_AT_name')
        return
    name = unit.group(1)
    source = os.path.join(xnu_work, spec['source'])
    inside = os.path.abspath(source) in os.path.abspath(name) or name.endswith(spec['source'])
    if not inside:
        report.add('I2', False, f'{label}: built from {name}, not the 27 tree copy of {spec["source"]}')
        return
    if not os.path.isfile(source):
        report.add('I2', False, f'{label}: DW_AT_name points at {name} but {source} does not exist')
        return
    report.add('I2', True, f'{label}: DW_AT_name {name}')

    producer = re.search(r'DW_AT_producer\s*\("([^"]+)"\)', info)
    if producer:
        report.add('I2', True, f'{label}: producer {producer.group(1)[:90]}')
    else:
        report.add('I2', True, f'{label}: producer not recorded')

    lines = [int(match) for match in re.findall(r'^\s*0x[0-9a-f]+\s+(\d+)\s', dwarf_dump(dwarfdump, path, '--debug-line'), re.M)]
    longest = max(lines) if lines else 0
    expected = spec['min_lines']
    if longest >= expected:
        report.add('F5', True, f'{label}: line table reaches {longest} (>= {expected})')
    elif longest >= expected * (1 - NEAR_MISS):
        report.add('I5', False, f'{label}: line table reaches {longest}, within 5% of {expected} — '
                                 '台账里的行数可能是我数错，先复核源文件再判')
    else:
        report.add('F5', False, f'{label}: line table stops at {longest}, expected >= {expected}')

    strings = run([nm, '--format=just-symbols', path]).stdout
    blob = dwarf_dump(dwarfdump, path, '--debug-str') + info
    binary = open(path, 'rb').read()
    for wanted in spec['strings']:
        if wanted.encode() in binary:
            report.add('F1' if 'goodix' in wanted or 'COORD' in wanted else 'F3', True,
                       f'{label}: string {wanted!r} present')
        else:
            report.add('F1' if 'goodix' in wanted or 'COORD' in wanted else 'F3', False,
                       f'{label}: string {wanted!r} absent from {spec["object"]} — 对象不是从这份源产出的')

    defined = set(run([nm, '--defined-only', '--format=just-symbols', path]).stdout.split())
    for symbol in spec['symbols']:
        if symbol in defined:
            report.add('F4', True, f'{label}: defined {symbol}')
        else:
            report.add('F4', False, f'{label}: {symbol} is not defined in {spec["object"]}')

    if label == 'goodix':
        struct = dwarf_dump(dwarfdump, path, f'--name={STRUCT}', '--debug-info')
        size = re.search(r'DW_AT_byte_size\s*\(\s*(0x[0-9a-f]+|\d+)', struct)
        if not size:
            report.add('I5', False, f'{label}: {STRUCT} not found in DWARF; cannot check the 24-byte contract')
        else:
            value = int(size.group(1), 0)
            report.add('F6', value == STRUCT_BYTES,
                       f'{label}: struct {STRUCT} is {value} B (contract {STRUCT_BYTES} B)')

    undefined = set(run([nm, '--undefined-only', '--format=just-symbols', path]).stdout.split())
    stubs = sorted(symbol for symbol in undefined if STUB_SUFFIX in symbol)
    if stubs:
        report.add('F7', False, f'{label}: {len(stubs)} unmapped-fileset stubs still undefined, e.g. {stubs[0]}')
    else:
        report.add('F7', True, f'{label}: no {STUB_SUFFIX} stub in {len(undefined)} undefined symbols')


GOODIX_FIXTURE = f'''
#include <stdint.h>
struct {STRUCT} {{ uint64_t time; uint32_t type, finger, x, y; }};
struct {STRUCT} queue[4];
const char ack[] = "goodix: %s ack=%02x";
const char coord[] = "COORD-ON";
const char ready[] = "Pong touch: Berlin-D ready";
const char keys[] = "Pong keys: arbiter v%u";
void pong_goodix_init(void) {{ pong_goodix_init; }}
void pong_touch_post(void) {{ queue[0].type = 1; }}
void pong_touch_device_ready(void) {{ queue[0].time = 0; }}
'''

BUTTONS_FIXTURE = f'''
#include <stdint.h>
const char keys[] = "Pong keys: arbiter v%u";
void pong_buttons_init(void) {{ pong_buttons_init; }}
'''


def self_test(dwarfdump, nm, clang):
    """Compile fixtures and prove the checks fire in both directions.

    Three expectations, all asserted:
      A. well-formed objects at the right source paths pass when the line-table
         bar is relaxed to 1 (a fixture cannot have 1375 lines);
      B. an object built without the COORD-ON string fails F1;
      C. the same well-formed object judged against the real line-table bar fails
         on the table length, which is what a stale source would look like.
    """
    if not clang:
        print('self-test: clang not found; nothing to compile')
        return 2
    dwarfdump = dwarfdump or 'llvm-dwarfdump'
    nm = nm or 'llvm-nm'
    with tempfile.TemporaryDirectory() as area:
        xnu = os.path.join(area, 'xnu')
        sources = {'goodix': os.path.join(xnu, GOODIX), 'buttons': os.path.join(xnu, BUTTONS)}
        for path, text in ((sources['goodix'], GOODIX_FIXTURE), (sources['buttons'], BUTTONS_FIXTURE)):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, 'w', encoding='utf-8').write(text)

        def compile_object(label, source, name):
            out = os.path.join(area, name)
            build = run([clang, '-c', '-g', '-O1', '-o', out, source])
            if build.returncode != 0:
                raise SystemExit(f'self-test: cannot compile the {label} fixture:\n{build.stderr}')
            return out

        compile_object('goodix', sources['goodix'], 'pong_goodix.o')
        compile_object('buttons', sources['buttons'], 'pong_buttons.o')

        stamp = {'source': 'self-test', 'commit': '0' * 40,
                 'patches': [{'path': f'/nowhere/{TOUCH_PATCH}.patch', 'sha256': '0' * 64},
                             {'path': f'/nowhere/{KEYS_PATCH}.patch', 'sha256': '0' * 64}]}
        open(os.path.join(xnu, 'xnu-inputs.json'), 'w').write(json.dumps(stamp))
        open(os.path.join(xnu, 'xnu-patches.list'), 'w').write('a\nb\n')

        relaxed = {label: dict(spec, min_lines=1) for label, spec in EXPECT.items()}

        def judge(specs, directory=area):
            report = Report()
            check_manifests(report, xnu, xnu)
            for label in ('goodix', 'buttons'):
                check_object(report, label, specs[label], directory, xnu, dwarfdump, nm)
            return report

        cases = []
        report_a = judge(relaxed)
        cases.append(('A well-formed objects pass', 'PASS', report_a))

        broken = os.path.join(area, 'broken-src')
        os.makedirs(os.path.dirname(os.path.join(broken, GOODIX)), exist_ok=True)
        open(os.path.join(broken, GOODIX), 'w').write(GOODIX_FIXTURE.replace('"COORD-ON"', '"COORD-OFF"'))
        broken_dir = os.path.join(area, 'broken')
        os.makedirs(broken_dir)
        compile_object('goodix', os.path.join(broken, GOODIX), 'broken/pong_goodix.o')
        shutil.copy(os.path.join(area, 'pong_buttons.o'), os.path.join(broken_dir, 'pong_buttons.o'))
        report_b = judge(relaxed, broken_dir)
        cases.append(('B a source without COORD-ON fails', 'FAIL', report_b))

        report_c = judge(EXPECT)
        cases.append(('C real line-table bar rejects a short table', ('FAIL', 'INVALID'), report_c))

        ok = True
        for title, expected, report in cases:
            got = report.verdict()
            good = got in (expected if isinstance(expected, tuple) else (expected,))
            ok = ok and good
            print(f'  [{"ok  " if good else "FAIL"}] {title}: {got} (expected {expected})')
            if not good:
                print(report.explain())
        print('self-test:', 'OK' if ok else 'BROKEN')
        return 0 if ok else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description='Check the iOS 27 input objects against the ledger contract.')
    parser.add_argument('--xnu-work', required=False, help='the patched XNU checkout (tree/.cache/xnu-work)')
    parser.add_argument('--work', help='directory holding xnu-inputs.json and xnu-patches.list; searched upward when omitted')
    parser.add_argument('--obj-dir', help='directory holding pong_goodix.o / pong_buttons.o / pong_input.o')
    parser.add_argument('--dwarfdump', help='llvm-dwarfdump to use')
    parser.add_argument('--nm', help='llvm-nm to use')
    parser.add_argument('--json', action='store_true', help='print the report as JSON')
    parser.add_argument('--self-test', action='store_true', help='compile fixtures and exercise the checks')
    args = parser.parse_args(argv)

    dwarfdump = find_tool('llvm-dwarfdump', args.dwarfdump)
    nm = find_tool('llvm-nm', args.nm)
    clang = find_tool('clang')

    if args.self_test:
        return self_test(dwarfdump, nm, clang)
    if not args.xnu_work or not args.obj_dir:
        parser.error('--xnu-work and --obj-dir are required (or use --self-test)')
    if not dwarfdump or not nm:
        print('error: llvm-dwarfdump and llvm-nm are required (pass --dwarfdump/--nm)', file=sys.stderr)
        return 2

    report = Report()
    work = resolve_work(args.xnu_work, args.work)
    check_manifests(report, work, args.xnu_work)
    for label in ('goodix', 'buttons', 'input'):
        spec = EXPECT[label]
        if spec.get('optional') and not os.path.isfile(os.path.join(args.obj_dir, spec['object'])):
            report.add('I1', True, f'{label}: {spec["object"]} not supplied (optional)')
            continue
        check_object(report, label, spec, args.obj_dir, args.xnu_work, dwarfdump, nm)

    verdict = report.verdict()
    if args.json:
        print(json.dumps({'verdict': verdict, 'xnu_work': args.xnu_work, 'work': work,
                          'obj_dir': args.obj_dir, 'rows': report.rows}, indent=2))
    else:
        print(f'verdict: {verdict}')
        print(report.explain())
        if verdict == 'PASS':
            print('\nPASS only fills the ledger artifact_check; local_verified stays false '
                  'until the object runs on the device.')
        elif verdict == 'INVALID':
            print('\nINVALID is not an input-line failure: the evidence is unusable, so ask for '
                  'a rebuild or the missing manifests before judging.')
    return 0 if verdict == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
