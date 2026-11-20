#!/usr/bin/env python3
"""Tests for iron-16's gate: a reading must resolve, and a blocker must have two."""

import importlib.util
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE.parent / 'check-reference-first.py'
spec = importlib.util.spec_from_file_location('reference_first', MODULE_PATH)
MODULE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MODULE)

BLOCKERS = '''schema_version = 1

[[blocker]]
id = "blocker-a"
state = "open"

[[blocker]]
id = "blocker-b"
state = "closed"
'''

SOURCES = '''[[repo]]
name = "alpha"
path = "{root}/alpha"

[[repo]]
name = "beta"
path = "{root}/beta"
'''

READING = '''schema_version = 1

[[entry]]
id = "blocker-a"
source = "alpha"
path = "notes.md"
line = 2
what = "the reference computes the slide by hand and checks the count per owner before packaging"
verdict = "copied"

[[entry]]
id = "blocker-a"
source = "beta"
path = "notes.md"
line = 1
what = "the second reference keeps a recorded baseline and refuses anything that adds a new gap"
verdict = "adapted"
'''

NOTES = '# title\nthe answer is on this line\n'


class Results:
    def __init__(self):
        self.passed = 0
        self.failed = []

    def check(self, name, condition, detail=''):
        if condition:
            self.passed += 1
        else:
            self.failed.append(f'{name}{": " + detail if detail else ""}')

    def report(self, label):
        for failure in self.failed:
            print(f'FAIL {failure}')
        print(f'{self.passed}/{self.passed + len(self.failed)} checks passed')
        if self.failed:
            return 1
        print(f'OK {label}')
        return 0


def tree(tests, label, entries, sources=None, blockers=BLOCKERS):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for name in ('alpha', 'beta'):
            (root / name).mkdir()
            (root / name / 'notes.md').write_text(NOTES)
        (root / 'sources.toml').write_text((sources or SOURCES).format(root=directory))
        (root / 'blockers.toml').write_text(blockers)
        (root / 'entries.toml').write_text(entries)
        code, problems = MODULE.check(root / 'blockers.toml', root / 'entries.toml',
                                     root / 'sources.toml')
        tests.check(label, code == 0 if label.startswith('pass') else code == 1,
                    f'rc={code} {problems}')
        return problems


def main():
    tests = Results()

    problems = tree(tests, 'pass.two_sources', READING)
    tests.check('pass.no_problems', problems == [])

    # One source, however well read, is one reference agreeing with itself.
    tree(tests, 'fail.one_source', READING.split('[[entry]]\nid = "blocker-a"\nsource = "beta"')[0])

    # A reading that no longer resolves is the reminder, not noise.
    tree(tests, 'fail.missing_path', READING.replace('path = "notes.md"', 'path = "gone.md"', 1))
    tree(tests, 'fail.line_past_end', READING.replace('line = 2', 'line = 99', 1))
    tree(tests, 'fail.unknown_verdict', READING.replace('verdict = "copied"', 'verdict = "ignored"', 1))
    tree(tests, 'fail.thin_what', READING.replace(
        'what = "the reference computes the slide by hand and checks the count per owner before packaging"',
        'what = "see docs"', 1))
    tree(tests, 'fail.unregistered_source', READING.replace('source = "alpha"', 'source = "gamma"', 1))

    # Readings for a blocker that is no longer open must be cleaned up or the blocker reopened.
    tree(tests, 'fail.closed_blocker_has_readings',
         READING + '\n[[entry]]\nid = "blocker-b"\nsource = "alpha"\npath = "notes.md"\n'
                   'line = 1\nwhat = "a reading that outlived its blocker and now means nothing at all"\n'
                   'verdict = "copied"\n')

    # An absent file is "cannot judge", which is not the same as passing (P-279).
    code, _ = MODULE.check(Path('/nonexistent/blockers.toml'), Path('/nonexistent/entries.toml'),
                           Path('/nonexistent/sources.toml'))
    tests.check('unknown.absent_inputs_exit_2', code == 2, f'rc={code}')

    return tests.report('the reference-first gate accepts resolvable readings and refuses '
                        'a one-source or stale claim')


if __name__ == '__main__':
    raise SystemExit(main())
