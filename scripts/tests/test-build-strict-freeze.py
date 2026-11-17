#!/usr/bin/env python3
"""P-224: the frozen-input list must not contain python bytecode caches.

The build hashes a file list before and after itself and declares the run void
when the two differ.  Bytecode is written by the build (python rewrites
scripts/__pycache__/*.pyc whenever it imports one of our scripts), so a build
that changed nothing used to fail its own comparison.  wifi-20261116c7 was
thrown away for exactly that on 2026-11-16.

This test reads the freeze() body out of scripts/build-strict.sh and runs it, so
it checks the shipped list rather than a copy of the intent.
"""

import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
BUILD_STRICT = os.path.join(REPO, 'scripts', 'build-strict.sh')


def freeze_body(with_comment=False):
    """Return the shell text of freeze() { ... } from build-strict.sh.

    With with_comment the contiguous '#' block directly above the function is
    included, because that is where the pitfall is cited.
    """
    with open(BUILD_STRICT, encoding='utf-8') as handle:
        lines = handle.read().split('\n')
    start = None
    for index, line in enumerate(lines):
        if line.startswith('freeze() {'):
            start = index
            break
    if start is None:
        raise AssertionError('build-strict.sh has no freeze() function')
    first = start
    if with_comment:
        while first > 0 and lines[first - 1].startswith('#'):
            first -= 1
    depth = 0
    for index in range(start, len(lines)):
        depth += lines[index].count('{') - lines[index].count('}')
        if depth == 0:
            return '\n'.join(lines[first:index + 1])
    raise AssertionError('freeze() is not closed')


def run_freeze():
    """Execute the real freeze() and return its output lines."""
    body = freeze_body()
    script = 'REPO=%s\n%s\nfreeze' % (shquote(REPO), body)
    result = subprocess.run(['bash', '-c', script], capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError('freeze() failed: %s' % result.stderr)
    return [line for line in result.stdout.split('\n') if line.strip()]


def shquote(text):
    return "'" + text.replace("'", "'\\''") + "'"


class FrozenInputsTest(unittest.TestCase):
    def test_the_list_excludes_bytecode_caches(self):
        """No entry may be a .pyc or live under __pycache__ (P-224)."""
        lines = run_freeze()
        offenders = [line for line in lines
                     if '__pycache__' in line or line.rstrip().endswith('.pyc')]
        self.assertEqual(offenders, [],
                         'frozen inputs must exclude bytecode: %r' % offenders[:3])

    def test_the_list_still_covers_the_real_inputs(self):
        """Excluding caches must not have emptied the list."""
        lines = run_freeze()
        self.assertGreater(len(lines), 400,
                           'frozen list shrank to %d entries' % len(lines))
        paths = ' '.join(lines)
        for needed in ('board.toml', 'patches/xnu/series', 'scripts/build-strict.sh'):
            self.assertIn(needed, paths, 'frozen list lost %s' % needed)

    def test_a_bytecode_rewrite_does_not_move_the_list(self):
        """The regression itself: import a script, re-run freeze, expect no change."""
        before = run_freeze()
        cache = os.path.join(REPO, 'scripts', '__pycache__')
        # Force python to (re)write a cache file, the exact event that voided
        # wifi-20261116c7.  Anything already there gets refreshed.
        subprocess.run([sys.executable, '-c',
                        'import sys; sys.path.insert(0, %r); import pong_paths'
                        % os.path.join(REPO, 'scripts')],
                       capture_output=True, text=True)
        self.assertTrue(os.path.isdir(cache), 'no __pycache__ to exercise')
        after = run_freeze()
        self.assertEqual(before, after,
                         'a bytecode rewrite changed the frozen list (P-224)')

    def test_the_exclusion_is_written_down(self):
        """A future edit must not silently drop the exclusion."""
        body = freeze_body()
        self.assertIn('__pycache__', body,
                      'freeze() no longer mentions __pycache__')
        # The pitfall is cited in the comment block above the function.
        annotated = freeze_body(with_comment=True)
        self.assertIn('P-224', annotated,
                      'freeze() no longer cites the pitfall it implements')


if __name__ == '__main__':
    unittest.main(verbosity=2)
