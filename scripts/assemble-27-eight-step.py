#!/usr/bin/env python3
"""Assemble the iOS 27 eight-step ledger from the lane fragments.

Why a separate file: `docs/research/EIGHT-STEPS.toml` records what the iOS 16.6.1
line proved, one block per hardware item. The 27 fragments are different claims
about the same items for a different OS profile, so writing them into the 16
ledger would destroy the 16 evidence. This tool merges the fragments into
`EIGHT-STEPS-27.toml` and refuses anything that does not match the step schema
the gate already enforces.

Usage:
    python3 scripts/assemble-27-eight-step.py            # check and write
    python3 scripts/assemble-27-eight-step.py --check     # only check
"""

import argparse
import pathlib
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
FRAGMENTS = ROOT / 'docs/research/eight-step'
OUTPUT = ROOT / 'docs/research/EIGHT-STEPS-27.toml'
REFERENCE = ROOT / 'docs/research/EIGHT-STEPS.toml'

STEPS = ('same_model', 'official', 'decompile', 'wide', 'plan', 'deep', 'verify')
HARDWARE_KEYS = {'name', 'label', 'status', 'why', 'revisit', 'paths', 'files'}
REQUIRED_STEP_KEYS = {'done', 'evidence'}
STEP_KEYS = {
    'same_model': REQUIRED_STEP_KEYS | {'recorded_at'},
    'official': REQUIRED_STEP_KEYS | {'recorded_at'},
    'decompile': REQUIRED_STEP_KEYS | {'recorded_at'},
    'wide': REQUIRED_STEP_KEYS | {'recorded_at', 'catalog_checked', 'catalog_result'},
    'plan': REQUIRED_STEP_KEYS | {'recorded_at'},
    'deep': REQUIRED_STEP_KEYS | {'recorded_at'},
    'verify': REQUIRED_STEP_KEYS | {'recorded_at', 'static_check', 'unit_test',
                                    'artifact_check', 'local_verified'},
}


class Failure(Exception):
    pass


def schema():
    with open(REFERENCE, 'rb') as handle:
        data = tomllib.load(handle)
    allowed = {name: set() for name in STEPS}
    for block in data['hardware'].values():
        for name, fields in (block.get('step') or {}).items():
            if name in allowed:
                allowed[name].update(
                    key for key in fields if not key.startswith('previous_'))
    hardware = set()
    for block in data['hardware'].values():
        hardware.update(block.keys())
    return allowed, hardware - {'step'}


def fragments():
    if not FRAGMENTS.is_dir():
        raise Failure(f'no fragment directory at {FRAGMENTS}')
    found = sorted(FRAGMENTS.glob('*.toml'))
    if not found:
        raise Failure(f'{FRAGMENTS} holds no .toml fragment')
    return found


def read(path, allowed, hardware):
    with open(path, 'rb') as handle:
        data = tomllib.load(handle)
    if 'hardware' not in data:
        raise Failure(f'{path.name}: no [hardware.*] table')
    for key in data:
        if key != 'hardware':
            raise Failure(f'{path.name}: unexpected top-level table {key!r}')
    for name, block in data['hardware'].items():
        extra = set(block) - {'step'} - hardware
        if extra:
            raise Failure(f'{path.name}: [{name}] has keys the ledger does not: {sorted(extra)}')
        steps = block.get('step') or {}
        if 'device' in steps:
            raise Failure(f'{path.name}: [{name}] carries step.device, which the Lead owns')
        missing = [s for s in STEPS if s not in steps]
        if missing:
            raise Failure(f'{path.name}: [{name}] is missing steps {missing}')
        for step in STEPS:
            keys = set(steps[step])
            extra = keys - allowed.get(step, set())
            if extra:
                raise Failure(f'{path.name}: [{name}].step.{step} has keys the gate '
                              f'does not read: {sorted(extra)}')
            lack = REQUIRED_STEP_KEYS - keys
            if lack:
                raise Failure(f'{path.name}: [{name}].step.{step} is missing {sorted(lack)}')
    return data['hardware']


def merge(parts):
    """Combine fragments, refusing two lanes that claim one hardware item."""
    blocks = {}
    for part in parts:
        for name, block in part.items():
            if name in blocks:
                raise Failure(f'{name} appears in more than one fragment; '
                              'two lanes cannot own one hardware item')
            blocks[name] = block
    return blocks


def render(blocks):
    lines = [
        '# iOS 27.0.1 (24A446) eight-step ledger — assembled, do not hand-edit.',
        '#',
        '# One [hardware.<item>] block per line, steps 1-7 only: step 8 (device) is',
        '# written by the Lead after a flight, because it needs a boot that happened.',
        '# Regenerate with: python3 scripts/assemble-27-eight-step.py',
        '',
        'schema_version = 1',
        '',
    ]
    for name in sorted(blocks):
        block = blocks[name]
        lines.append(f'[hardware.{name}]')
        for key in ('name', 'label', 'status', 'why', 'revisit'):
            if key in block:
                lines.append(f'{key} = {value(block[key])}')
        lines.append('')
        for step in STEPS:
            lines.append(f'[hardware.{name}.step.{step}]')
            for key, item in block['step'][step].items():
                lines.append(f'{key} = {value(item)}')
            lines.append('')
    return '\n'.join(lines).rstrip('\n') + '\n'


def value(item):
    """TOML literal for the value shapes the fragments actually use."""
    if isinstance(item, bool):
        return 'true' if item else 'false'
    if isinstance(item, (int, float)):
        return repr(item)
    if isinstance(item, list):
        return '[' + ', '.join(value(one) for one in item) + ']'
    if isinstance(item, str):
        return '"' + item.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'
    raise Failure(f'cannot write a {type(item).__name__} to TOML')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true',
                        help='validate the fragments without writing the ledger')
    options = parser.parse_args(argv)

    allowed, hardware = schema()
    blocks = merge(read(path, allowed, hardware) for path in fragments())

    rendered = render(blocks)
    tomllib.loads(rendered)          # never write something we cannot read back
    if options.check:
        print(f'ok eight-step-27: {len(blocks)} item(s) from '
              f'{len(fragments())} fragment(s), all seven steps present')
        return 0
    OUTPUT.write_text(rendered, encoding='utf-8')
    print(f'wrote {OUTPUT.relative_to(ROOT)}: {len(blocks)} item(s)')
    for name in sorted(blocks):
        count = sum(len(v) for v in blocks[name]['step'].values())
        print(f'  {name}: {count} field(s)')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Failure as error:
        print(f'FAIL: {error}', file=sys.stderr)
        sys.exit(1)
