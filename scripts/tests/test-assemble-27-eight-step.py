#!/usr/bin/env python3
"""The 27 eight-step assembler refuses every shape the gate would misread."""

import importlib.util
import pathlib
import sys
import tempfile
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE = ROOT / 'scripts/assemble-27-eight-step.py'

spec = importlib.util.spec_from_file_location('assemble27', MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

ALLOWED, HARDWARE = module.schema()
CHECKS = 0
FAILED = 0


def ok(name, condition, detail=''):
    global CHECKS, FAILED
    CHECKS += 1
    if condition:
        return
    FAILED += 1
    print(f'FAIL {name}' + (f': {detail}' if detail else ''))


def block(item='cellular', steps=None, extra_step=None, hardware_extra=None):
    steps = module.STEPS if steps is None else steps
    body = {'name': item, 'status': 'planned'}
    body.update(hardware_extra or {})
    body['step'] = {}
    for name in steps:
        fields = {'done': False, 'evidence': ['file.c:1']}
        if name == 'wide':
            fields.update({'catalog_checked': False, 'catalog_result': 'no'})
        if name == 'verify':
            fields.update({'static_check': False, 'unit_test': False,
                           'artifact_check': False, 'local_verified': False})
        if extra_step and name in extra_step:
            fields.update(extra_step[name])
        body['step'][name] = fields
    return {'hardware': {item: body}}


def write(payload):
    lines = []
    for item, body in payload['hardware'].items():
        lines.append(f'[hardware.{item}]')
        for key, value in body.items():
            if key == 'step':
                continue
            lines.append(f'{key} = "{value}"')
        lines.append('')
        for step, fields in body['step'].items():
            lines.append(f'[hardware.{item}.step.{step}]')
            for key, value in fields.items():
                if isinstance(value, bool):
                    lines.append(f'{key} = {"true" if value else "false"}')
                elif isinstance(value, list):
                    inner = ', '.join('"' + one + '"' for one in value)
                    lines.append(f'{key} = [{inner}]')
                else:
                    lines.append(f'{key} = "{value}"')
            lines.append('')
    directory = pathlib.Path(tempfile.mkdtemp())
    path = directory / 'fragment.toml'
    path.write_text('\n'.join(lines), encoding='utf-8')
    return path


def expect(name, payload, needle):
    try:
        module.read(write(payload), ALLOWED, HARDWARE)
    except module.Failure as error:
        ok(name, needle in str(error), f'raised {error}')
    else:
        ok(name, False, 'was accepted')


def main():
    ok('schema.has_verify', 'verify' in ALLOWED)
    ok('schema.has_status', 'status' in HARDWARE)

    clean = block()
    rendered = module.render(dict(clean['hardware']))
    ok('render.round_trip', 'hardware' in tomllib.loads(rendered))

    expect('refuse.extra_step_key', block(extra_step={'plan': {'files': 'a.c'}}),
           'does not read')
    expect('refuse.missing_step', block(steps=['same_model', 'official']),
           'missing steps')

    device = block()
    device['hardware']['cellular']['step']['device'] = {'done': False}
    expect("refuse.device_block", device, "the Lead owns")

    expect("refuse.extra_hardware_key", block(hardware_extra={"colour": "red"}),
           "has keys the ledger does not")

    try:
        module.merge([{'cellular': {}}, {'cellular': {}}])
    except module.Failure as error:
        ok('refuse.duplicate_item', 'more than one fragment' in str(error), str(error))
    else:
        ok('refuse.duplicate_item', False, 'two fragments claimed one item')

    print(f'{CHECKS - FAILED}/{CHECKS} checks passed')
    if FAILED:
        return 1
    print('OK the 27 assembler enforces the step schema the gate reads')
    return 0


if __name__ == '__main__':
    sys.exit(main())
