#!/usr/bin/env python3
"""Tests for scripts/official-audit-report.py.

The interesting failures are the quiet ones: a page written as an absolute
path in one batch and relative in another, a page audited twice, and a page
the registry has never heard of.  Each of those would make the coverage number
look better than it is, so each gets a case here.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/official-audit-report.py'

REGISTRY = '''
schema_version = 1

[[page]]
path = "porting/gpu.md"
state = "mapped"

[[page]]
path = "porting/power.md"
state = "unmapped"

[[page]]
path = "xnu/patch-reference.md"
state = "na"
why = "no porter obligation"
'''

PASS = 0


def check(name, condition, detail=''):
    global PASS
    if condition:
        PASS += 1
        print(f'ok   {name}')
    else:
        print(f'FAIL {name}{": " + detail if detail else ""}')
        raise SystemExit(1)


def page(path, statuses=('satisfied', 'unknown')):
    return {
        'path': path,
        'requirements': [
            {'heading': f'h{i}', 'quote': 'q', 'kind': 'config',
             'gate_idea': 'scripts/check-x.py', 'status': status}
            for i, status in enumerate(statuses)
        ],
    }


def write(directory, name, pages):
    path = Path(directory) / name
    path.write_text(json.dumps({'pages': pages}, ensure_ascii=False),
                    encoding='utf-8')
    return path


def run(registry, audits, expect_rc=None):
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        reg = directory / 'registry.toml'
        reg.write_text(registry, encoding='utf-8')
        for name, pages in audits.items():
            write(directory, name, pages)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), '--audit-dir', str(directory),
             '--registry', str(reg)],
            capture_output=True, text=True)
        if expect_rc is not None:
            check(f'rc == {expect_rc}',
                  result.returncode == expect_rc,
                  f'got {result.returncode}: {result.stdout}{result.stderr}')
        return result


def main():
    # One page, two spellings, one key: the whole point of page_name().
    result = run(REGISTRY, {
        'audit-a.json': [page('porting/gpu.md')],
        'audit-b.json': [page(
            '/mnt/e/iOS Port/Sources/Repos/UniXNU/UniXNU/docs/zh/porting/power.md')],
    }, expect_rc=0)
    check('absolute and relative spellings both resolve',
          'porting/power.md' in result.stdout and 'never audited             : 1'
          in result.stdout, result.stdout[-300:])

    # The same page twice across batches is a merge error, not a bigger number.
    result = run(REGISTRY, {
        'audit-a.json': [page('porting/gpu.md')],
        'audit-b.json': [page('porting/gpu.md')],
    }, expect_rc=2)
    check('a page audited twice is refused',
          'audited twice' in result.stdout, result.stdout)

    # A page the registry does not know means the two lists have drifted.
    result = run(REGISTRY, {
        'audit-a.json': [page('porting/gpu.md'), page('porting/nope.md')],
    }, expect_rc=1)
    check('an unknown page fails the report',
          'pages the registry does not have' in result.stdout, result.stdout)

    # A status outside the vocabulary would silently vanish from the counts.
    bad = page('porting/gpu.md')
    bad['requirements'][0]['status'] = 'violated'
    result = run(REGISTRY, {'audit-a.json': [bad]}, expect_rc=2)
    check('an unknown status is refused', 'has status' in result.stdout,
          result.stdout)

    # A row with no gate idea is a note, not a requirement.
    bad = page('porting/gpu.md')
    bad['requirements'][0]['gate_idea'] = ''
    result = run(REGISTRY, {'audit-a.json': [bad]}, expect_rc=2)
    check('a row without a gate is refused', 'without gate_idea' in result.stdout,
          result.stdout)

    # An empty registry cannot pass on silence.
    result = run('schema_version = 1\n',
                 {'audit-a.json': [page('porting/gpu.md')]}, expect_rc=2)
    check('an empty registry is refused', 'no [[page]]' in result.stdout,
          result.stdout)

    print(f'\nOK {PASS} checks: the audit report merges batches, normalises '
          f'page names and refuses drift')


if __name__ == '__main__':
    main()
