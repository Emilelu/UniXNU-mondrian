#!/usr/bin/env python3
"""Tests for P-250: a repeated patch number must be disambiguated.

The gate exists because a merge appended a series tail verbatim and produced two
0624 entries, and every build kept passing.  These cases pin the shapes: the three
deliberate historical collisions stay legal, and a fresh collision is refused.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
GATE = os.path.join(REPO, 'scripts', 'check-series-numbering.py')

CASES = []


def case(name):
    def register(func):
        CASES.append((name, func))
        return func
    return register


def run(series_text):
    """Write a series file and run the gate against it."""
    handle = tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='utf-8')
    handle.write(series_text)
    handle.close()
    try:
        result = subprocess.run(
            [sys.executable, GATE, '--series', handle.name, '--root', REPO],
            capture_output=True, text=True,
        )
        return result.returncode, result.stdout + result.stderr
    finally:
        os.unlink(handle.name)


@case('the two remaining historical collisions are accepted')
def test_historical_collisions():
    code, out = run(
        '0334-k60-panic-reset-fastboot.patch\n'
        '0334b-k60-autoreset.patch\n'
        '0502-k60-bt-qbt-bsd-init.patch\n'
        '0502b-k60-bt-qbt-kernel-stubs.patch\n'
    )
    assert code == 0, out
    assert '4 entries' in out, out


@case('two bare entries for unrelated changes are refused')
def test_two_bare_entries_are_refused():
    # This is the shape the gate found in the live series: a dyld probe and a set
    # of weak stubs both numbered 0392 with no suffix to tell them apart.
    code, out = run(
        '0392-k60-dyld-cache-probe.patch\n'
        '0392-k60-weak-scanout-stubs.patch\n'
    )
    assert code == 1, out
    assert '2 entries, 0 suffixed' in out, out


@case('two bare entries with one number are refused')
def test_two_bare_entries():
    code, out = run(
        '0624-k60-platform-sleep-boot-complete.patch\n'
        '0624-k60-quiet-managed-page-report.patch\n'
    )
    assert code == 1, out
    assert '0624' in out, out
    assert '2 entries, 0 suffixed' in out, out


@case('two suffixed entries with one number are refused')
def test_two_suffixed_entries():
    # "a" and "b" both present says nothing about which one comes first, so the
    # pair is just as ambiguous as two bare entries.
    code, out = run(
        '0624a-first.patch\n'
        '0624b-second.patch\n'
    )
    assert code == 1, out
    assert '2 suffixed' in out, out


@case('three entries on one number are refused even with one suffix')
def test_three_entries():
    code, out = run(
        '0700-a.patch\n'
        '0700b-b.patch\n'
        '0700-c.patch\n'
    )
    assert code == 1, out
    assert '3 entries' in out, out


@case('comments and blank lines do not count as entries')
def test_comments_ignored():
    code, out = run(
        '# this line explains why 0624 is not in the series\n'
        '\n'
        '0626-k60-touch-activity.patch\n'
        '0627-k60-platform-sleep.patch\n'
    )
    assert code == 0, out
    assert '2 entries' in out, out


@case('the live series is clean')
def test_live_series():
    series = os.path.join(REPO, 'patches', 'xnu', 'series')
    result = subprocess.run([sys.executable, GATE], capture_output=True, text=True, cwd=REPO)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'patches/xnu/series' in result.stdout, result.stdout
    # The renumbered power patches must be the entries that made it clean.
    body = open(series, encoding='utf-8').read()
    assert '0628-k60-platform-sleep-boot-complete.patch' in body
    assert '0624-k60-platform-sleep-boot-complete.patch' not in body


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
