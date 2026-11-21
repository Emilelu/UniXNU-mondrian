"""Tests for scripts/check-prelink-roots.py.

The gate exists because the root list is duplicated into board.toml (profiles.merge
replaces lists) and `dependency_closure()` raises on a root the kernelcache lacks.
Each case below is a way that hand-edited list goes wrong silently.
"""

import importlib.util
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), 'check-prelink-roots.py')

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def load():
    spec = importlib.util.spec_from_file_location('roots', TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules['roots'] = module
    spec.loader.exec_module(module)
    return module


CACHE = {'com.apple.a', 'com.apple.b', 'com.apple.c'}


@case
def a_clean_list_passes(base):
    mod = load()
    problems, inc, exc = mod.judge(['com.apple.a', 'com.apple.b'], ['com.apple.a'], CACHE)
    assert problems == [] and inc == 2 and exc == 0, problems


@case
def a_duplicate_is_reported(base):
    mod = load()
    problems, _, _ = mod.judge(['com.apple.a', 'com.apple.a'], None, CACHE)
    assert any('duplicate' in p for p in problems), problems


@case
def a_root_missing_from_the_kernelcache_is_reported(base):
    mod = load()
    problems, _, _ = mod.judge(['com.apple.zzz'], None, CACHE)
    assert any('not in the kernelcache' in p for p in problems), problems


@case
def the_same_bundle_as_root_and_exclusion_is_reported(base):
    mod = load()
    problems, _, _ = mod.judge(['com.apple.a', '!com.apple.a'], None, CACHE)
    assert any('both a root and an exclusion' in p for p in problems), problems


@case
def dropping_a_profile_root_is_reported(base):
    mod = load()
    problems, _, _ = mod.judge(['com.apple.a'], ['com.apple.a', 'com.apple.b'], CACHE)
    assert any('the OS profile declares it' in p for p in problems), problems


@case
def an_exclusion_satisfies_the_profile_list(base):
    mod = load()
    problems, _, _ = mod.judge(['com.apple.a', '!com.apple.b'], ['com.apple.a', 'com.apple.b'], CACHE)
    assert problems == [], problems


@case
def an_unreadable_cache_is_not_a_verdict(base):
    mod = load()
    with tempfile.NamedTemporaryFile('wb', suffix='.kc', delete=False) as fh:
        fh.write(b'not a mach-o at all')
        path = fh.name
    try:
        assert mod.kernelcache_bundles(path) is None
        problems, _, _ = mod.judge(['com.apple.zzz'], None, None)
        assert problems == [], problems  # membership unjudged, not failed
    finally:
        os.unlink(path)


@case
def an_empty_list_is_a_failure_not_a_default(base):
    mod = load()
    with tempfile.TemporaryDirectory() as d:
        board = os.path.join(d, 'board.toml')
        open(board, 'w', encoding='utf-8').write('[kernel]\narchives = []\n')
        assert mod.main(['--board', board, '--framework', d]) == 1


def main():
    failed = 0
    for fn in CASES:
        with tempfile.TemporaryDirectory() as base:
            try:
                fn(base)
                print('ok   %s' % fn.__name__)
            except AssertionError as exc:
                failed += 1
                print('FAIL %s: %s' % (fn.__name__, exc))
    if failed:
        print('FAILED %d of %d' % (failed, len(CASES)))
        return 1
    print('OK %d cases: the root list is judged for duplicates, membership, overlap and '
          'profile coverage, and an unreadable kernelcache is "cannot judge"' % len(CASES))
    return 0


if __name__ == '__main__':
    sys.exit(main())
