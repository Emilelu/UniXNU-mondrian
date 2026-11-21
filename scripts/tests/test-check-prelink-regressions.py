#!/usr/bin/env python3
"""Tests for the prelink regression gate: growth, stale bounds, and the expiry."""

import importlib.util
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('prelink_regressions',
                                             HERE.parent / 'check-prelink-regressions.py')
MODULE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MODULE)

SLIDE = '0x400000'


def record(missing=None, stubbed=None, branches=()):
    return {
        'candidate_sha256': 'a' * 64,
        'collection_slide': SLIDE,
        'missing': missing or {},
        'stubbed': stubbed or {},
        'native_original_branches': [{'symbol': name} for name in branches],
    }


def policy(missing=None, stubbed=None, required=(), review='2026-12-01'):
    document = {'missing': missing or {}, 'stubbed': stubbed or {},
                'required_original_branches': list(required)}
    if not required:
        document['required_original_branches_waiver'] = {
            'reason': 'fixture: the kit does not emit branches yet',
            'review_after': review,
        }
    return document


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


def main():
    tests = Results()
    import datetime
    today = datetime.date(2026, 11, 21)

    # The baseline itself must pass, including the slide correction: policy keys are
    # native addresses, records are collection-relative.
    baseline = record(stubbed={'bundle.a': {'0x401000': 2}})
    bound = policy(stubbed={'bundle.a': {'0x1000': 2}})
    tests.check('pass.at_baseline', MODULE.grown(baseline, bound) == [])
    tests.check('pass.branch_waiver_is_dated',
                MODULE.branch_problems(baseline, bound, today) == [])

    # One more site for the same address, and a first site for a new address, both grow.
    tests.check('fail.count_grew',
                bool(MODULE.grown(record(stubbed={'bundle.a': {'0x401000': 3}}), bound)))
    tests.check('fail.new_address',
                bool(MODULE.grown(record(stubbed={'bundle.a': {'0x401000': 2, '0x402000': 1}}), bound)))
    tests.check('fail.new_owner',
                bool(MODULE.grown(record(stubbed={'bundle.b': {'0x401000': 1}}), bound)))

    # Shrinking is allowed; a bound that no longer matches anything is stale debt.
    tests.check('pass.shrink_allowed',
                MODULE.grown(record(stubbed={'bundle.a': {'0x401000': 1}}), bound) == [])
    stale = MODULE.grown(record(stubbed={}), bound)
    tests.check('fail.stale_bound', any('no longer appears' in problem for problem in stale))

    # Required branches: satisfied, missing, and the empty clause that must not pass forever.
    required = policy(required=['__ZN3FooC1EPK11OSMetaClass'])
    tests.check('pass.required_branch_present',
                MODULE.branch_problems(record(branches=['__ZN3FooC1EPK11OSMetaClass']),
                                       required, today) == [])
    tests.check('fail.required_branch_absent',
                bool(MODULE.branch_problems(record(branches=[]), required, today)))
    expired = policy(review='2026-11-01')
    tests.check('fail.waiver_expired',
                any('expired' in problem for problem in MODULE.branch_problems(record(), expired, today)))
    no_waiver = {'missing': {}, 'stubbed': {}, 'required_original_branches': []}
    tests.check('fail.empty_clause_without_waiver',
                bool(MODULE.branch_problems(record(), no_waiver, today)))

    # Written policy round-trips: --write then read must not report growth.
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / 'policy.json'
        tests.check('pass.write_policy', MODULE.write_policy(baseline, target, force=False) is None)
        written = json.loads(target.read_text())
        tests.check('pass.write_uses_native_addresses', '0x1000' in written['stubbed']['bundle.a'])
        tests.check('pass.round_trip', MODULE.grown(baseline, written) == [])
        tests.check('fail.write_refuses_overwrite',
                    MODULE.write_policy(baseline, target, force=False) is not None)

    return tests.report('the prelink gate stops growth, refuses stale bounds and expires its waiver')


if __name__ == '__main__':
    raise SystemExit(main())
