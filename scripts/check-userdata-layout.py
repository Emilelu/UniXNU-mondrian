#!/usr/bin/env python3
"""check-userdata-layout.py -- the SHNGROOT layout in concepts/userdata.md.

The official page fixes more than the Data-volume UUID: a 4096-byte
SHNGROOT header, version 1, the first window at 1 MiB, every following
window 1 MiB aligned, 512-byte blocks, read-only flags, a SHA-256 per window and
a capacity ceiling.  The registry used to map the page to
check-defconfig-uuid.py alone; that gate is necessary (a seed UUID
self-panics before the console exists) but it does not cover the layout, so a
builder could change the header and the page would still count as mapped.

This gate pins the builder's constants, the exact struct layouts, the alignment
and capacity checks, and then runs the existing UUID gate.  It accepts
--repo so it can check the shared k60-gates checkout without writing it.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MIB = 1 << 20
FIRST_LBA = 0x413248
LAST_LBA = 0x75A40EA
BLOCK_BYTES = 4096

MARKERS = (
    ('header magic', "header[:8] = b'SHNGROOT'"),
    ('header size', 'header = bytearray(4096)'),
    ('header version/count/image_bytes',
     "struct.pack_into('<IIQ', header, 8, 1, len(entries), cursor)"),
    ('entry offset', "struct.pack_into('<32sQQII32s40s', header, 24 + index * 128"),
    ('entry fields', 'name.encode(), offset, size, 512, 1, digest, bytes(40))'),
    ('header digest', 'header[4064:] = hashlib.sha256(header[:4064]).digest()'),
    ('first window', 'cursor = MIB'),
    ('window alignment', 'cursor += ((size + MIB - 1) // MIB) * MIB'),
    ('capacity refusal', 'if cursor > USERDATA_BYTES:'),
    ('report capacity', "'capacity_bytes': USERDATA_BYTES"),
    ('report image bytes', "'image_bytes': cursor"),
)


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(repo: Path, include_uuid: bool = True) -> list[str]:
    repo = Path(repo)
    builder = repo / 'scripts/build-userdata.py'
    if not builder.is_file():
        return [f'{builder}: no SHNGROOT builder']
    problems: list[str] = []
    try:
        module = load(builder, f'k60_build_userdata_{id(builder)}')
    except Exception as error:
        return [f'{builder}: {type(error).__name__}: {error}']

    if getattr(module, 'MIB', None) != MIB:
        problems.append(f'{builder}: MIB is {getattr(module, "MIB", None)!r}, not 1 MiB')
    if getattr(module, 'FIRST_LBA', None) != FIRST_LBA:
        problems.append(f'{builder}: FIRST_LBA is {getattr(module, "FIRST_LBA", None)!r}, '
                        f'not {FIRST_LBA:#x}')
    if getattr(module, 'LAST_LBA', None) != LAST_LBA:
        problems.append(f'{builder}: LAST_LBA is {getattr(module, "LAST_LBA", None)!r}, '
                        f'not {LAST_LBA:#x}')
    capacity = getattr(module, 'USERDATA_BYTES', None)
    expected = (LAST_LBA - FIRST_LBA + 1) * BLOCK_BYTES
    if capacity != expected:
        problems.append(f'{builder}: USERDATA_BYTES is {capacity!r}, '
                        f'not (LAST_LBA-FIRST_LBA+1)*{BLOCK_BYTES} = {expected}')

    text = builder.read_text(encoding='utf-8')
    for label, marker in MARKERS:
        if marker not in text:
            problems.append(f'{builder}: {label} marker is missing: {marker}')

    if include_uuid:
        uuid_gate = repo / 'scripts/check-defconfig-uuid.py'
        if not uuid_gate.is_file():
            problems.append(f'{uuid_gate}: the Data-volume gate is missing')
        else:
            try:
                uuid = load(uuid_gate, f'k60_defconfig_uuid_{id(uuid_gate)}')
                result = uuid.run(repo)
            except Exception as error:
                problems.append(f'{uuid_gate}: {type(error).__name__}: {error}')
            else:
                if not result.get('ok'):
                    problems.extend(f'Data-volume identity: {item}'
                                    for item in result.get('failures', []))
    return problems


def self_test() -> int:
    source = (REPO / 'scripts/build-userdata.py').read_text(encoding='utf-8')
    cases = (
        ('baseline', source, None),
        ('magic', source.replace("b'SHNGROOT'", "b'SHNGROO7'"), 'header magic'),
        ('first-window', source.replace('cursor = MIB', 'cursor = 0'), 'first window'),
        ('capacity-formula',
         source.replace('USERDATA_BYTES = (LAST_LBA - FIRST_LBA + 1) * 4096',
                        'USERDATA_BYTES = (LAST_LBA - FIRST_LBA + 1) * 512'),
         'USERDATA_BYTES'),
    )
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix='k60-userdata-selftest-') as temporary:
        repo = Path(temporary)
        scripts = repo / 'scripts'
        scripts.mkdir()
        for name, body, expected in cases:
            (scripts / 'build-userdata.py').write_text(body, encoding='utf-8')
            problems = check(repo, include_uuid=False)
            if expected is None:
                if problems:
                    failures.append(f'{name}: {problems[0]}')
            elif not any(expected in problem for problem in problems):
                failures.append(f'{name}: expected a {expected!r} problem, got {problems!r}')
    if failures:
        for failure in failures:
            print(f'FAIL self-test: {failure}')
        return 1
    print(f'userdata-layout self-test: OK ({len(cases)} cases)')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='check the SHNGROOT layout and Data-volume identity')
    parser.add_argument('--repo', type=Path, default=REPO, help='repository root')
    parser.add_argument('--json', action='store_true', help='machine-readable result')
    parser.add_argument('--self-test', action='store_true', help='exercise the gate on synthetic builders')
    options = parser.parse_args(argv)
    if options.self_test:
        return self_test()
    problems = check(options.repo)
    if options.json:
        print(json.dumps({'repo': str(options.repo), 'problems': problems,
                          'ok': not problems}, ensure_ascii=False, indent=2))
    else:
        for problem in problems:
            print(f'FAIL {problem}')
        if not problems:
            print('userdata-layout: OK (SHNGROOT v1, 4096-byte header, first window 1 MiB, '
                  '1 MiB alignment, 512-byte blocks, capacity ceiling and Data UUID all pinned)')
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
