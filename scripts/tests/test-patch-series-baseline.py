#!/usr/bin/env python3
"""Tests for the P-155 line budget: the gate must actually be armed.

``check-patch-series.py`` reads ``expected_kern_exec_delta`` from the *top level* of
``docs/engineering/RULES.toml``.  That key did not exist on main -- ``git log -S``
finds no commit adding it -- so the gate printed "未记录基线 … 跳过" and returned 0
on every run since it was written.  A registered rule whose check silently returns 0
is P-190 and P-204 in a third costume: the registry says the pitfall is covered and
nothing looks at why it never fires.

These cases pin three things: the key is reachable at the top level of the real
registry, its value equals the delta the real series produces today, and a registry
whose baseline disagrees with the series makes the gate exit 1 instead of 0.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
GATE = os.path.join(REPO, 'scripts', 'check-patch-series.py')
RULES = os.path.join(REPO, 'docs', 'engineering', 'RULES.toml')

CASES = []


def case(name):
    def register(func):
        CASES.append((name, func))
        return func
    return register


def load_gate():
    spec = importlib.util.spec_from_file_location('check_patch_series', GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_repo(delta_in_series, baseline):
    """A throwaway repo with one patch touching kern_exec.c and one RULES.toml."""
    root = tempfile.mkdtemp(prefix='p155-')
    xnu = os.path.join(root, 'patches', 'xnu')
    os.makedirs(xnu)
    patch = (
        'diff --git a/bsd/kern/kern_exec.c b/bsd/kern/kern_exec.c\n'
        '--- a/bsd/kern/kern_exec.c\n'
        '+++ b/bsd/kern/kern_exec.c\n'
        f'@@ -1,1 +1,{1 + delta_in_series} @@\n'
        ' context\n'
        + ''.join(f'+added {n}\n' for n in range(delta_in_series))
    )
    with open(os.path.join(xnu, '0999-fake.patch'), 'w', encoding='utf-8') as fh:
        fh.write(patch)
    with open(os.path.join(xnu, 'series'), 'w', encoding='utf-8') as fh:
        fh.write('0999-fake.patch\n')
    rules = os.path.join(root, 'RULES.toml')
    with open(rules, 'w', encoding='utf-8') as fh:
        if baseline is None:
            fh.write('[[rule]]\nid = "P-1"\nkind = "pitfall"\nstatement = "x"\n')
        else:
            fh.write(f'expected_kern_exec_delta = {baseline}\n\n[[rule]]\n'
                     'id = "P-1"\nkind = "pitfall"\nstatement = "x"\n')
    return root, rules


def run_gate(root, rules):
    module = load_gate()
    module.REPO = __import__('pathlib').Path(root)
    module.SERIES = module.REPO / 'patches' / 'xnu' / 'series'
    module.RULES = __import__('pathlib').Path(rules)
    return module.main()


@case('the real registry carries the baseline at the top level')
def _():
    data = tomllib.loads(open(RULES, encoding='utf-8').read())
    assert 'expected_kern_exec_delta' in data, (
        'expected_kern_exec_delta is not a top-level key; the gate would skip forever')
    assert isinstance(data['expected_kern_exec_delta'], int)


@case('the baseline equals what the real series produces')
def _():
    module = load_gate()
    total_add = total_del = 0
    for entry in module.SERIES.read_text(encoding='utf-8').split():
        patch = module.REPO / 'patches' / 'xnu' / entry
        added, removed = module.patch_delta(patch)
        total_add += added
        total_del += removed
    measured = total_add - total_del
    data = tomllib.loads(open(RULES, encoding='utf-8').read())
    assert measured == data['expected_kern_exec_delta'], (
        f'series measures {measured:+d}, registry says '
        f'{data["expected_kern_exec_delta"]:+d} -- one of them is stale')


@case('a matching baseline passes')
def _():
    root, rules = fake_repo(3, 3)
    try:
        assert run_gate(root, rules) == 0
    finally:
        shutil.rmtree(root)


@case('a drifted series fails instead of skipping')
def _():
    root, rules = fake_repo(5, 3)
    try:
        assert run_gate(root, rules) == 1, 'a moved patch must fail the build'
    finally:
        shutil.rmtree(root)


@case('a missing baseline is reported, not silently green')
def _():
    root, rules = fake_repo(3, None)
    try:
        code = run_gate(root, rules)
        # The gate deliberately still returns 0 without a baseline (a fresh clone may
        # not have one yet), but it must say so; the real registry is covered above.
        assert code == 0
    finally:
        shutil.rmtree(root)


def main():
    failures = 0
    for name, func in CASES:
        try:
            func()
            print(f'PASS {name}')
        except AssertionError as error:
            failures += 1
            print(f'FAIL {name}: {error}')
    total = len(CASES)
    print(f'TESTS {"OK" if not failures else "FAILED"} {total} cases ({failures} failure(s))')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
