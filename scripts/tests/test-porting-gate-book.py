#!/usr/bin/env python3
"""P-222: the porting gate must trust a booted baseline in the book, and only
that — an unproven series must still be refused.

The failure this guards against: /mnt/e/k60-work/ledger.jsonl is global across
every worktree, so a flight from another branch rewrites "the last successful
boot". On 2026-11-16 the bluetooth line flew at 08:59 with a 234-patch series
and the porting gate then told main that its own 227-patch series — the one
baseline-20261116a had booted at 07:36 — had changed.
"""
import io
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE.parent / 'porting-gate.py'
BOOK = HERE.parent.parent / 'docs' / 'engineering' / 'MAIN-BASELINE.toml'


def load_gate():
    """Import porting-gate.py without running its module-level checks.

    The gate executes its whole registry on import, so the two definitions this
    test needs are cut out by line and exec'd in a fresh namespace.
    """
    lines = GATE.read_text(encoding='utf-8').splitlines()
    chunks, current = [], None
    for line in lines:
        if line.startswith('def booted_series(') or line.startswith('def series_fingerprint('):
            current = [line]
            chunks.append(current)
        elif current is not None:
            if line and not line[0].isspace() and not line.startswith(')'):
                current = None
            else:
                current.append(line)
    repo = HERE.parent.parent
    namespace = {'io': io, 're': re, 'os': os, 'REPO': str(repo),
                 'WORK': '/mnt/e/k60-work',
                 'SERIES': str(repo / 'patches/xnu/series'),
                 'BOOK': str(BOOK)}
    for chunk in chunks:
        exec('\n'.join(chunk), namespace)
    return namespace


class BookLookup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gate = load_gate()

    def test_the_real_book_yields_booted_series_only(self):
        table = self.gate['booted_series']()
        self.assertTrue(table, 'the real book must have at least one booted entry')
        for fp, value in table.items():
            self.assertRegex(fp, r'^[0-9a-f]{16}$')
            self.assertRegex(value[0], r'^[0-9a-f]{7,40}$')

    def test_a_build_only_entry_never_vouches(self):
        table = self.gate['booted_series']()
        text = BOOK.read_text(encoding='utf-8')
        build_only = set()
        for m in re.finditer(r'\[\[entry\]\](.*?)(?=\n\[\[|\Z)', text, re.S):
            block = m.group(1)
            fields = dict(re.findall(r'^(\w+)\s*=\s*"([^"]*)"', block, re.M))
            if fields.get('state') == 'build-only' and fields.get('series_sha256'):
                build_only.add(fields['series_sha256'])
        self.assertEqual(build_only & set(table), set(),
                         'a build-only baseline has never been on a device')

    def test_the_current_series_is_proven_by_the_book(self):
        """The exact 2026-11-16 situation: main's series is in the book."""
        fp, count = self.gate['series_fingerprint']()
        self.assertIsNotNone(fp)
        table = self.gate['booted_series']()
        self.assertIn(fp, table,
                      'main series %s (%d patches) should match a booted baseline'
                      % (fp, count))

    def test_an_unknown_series_is_not_proven(self):
        table = self.gate['booted_series']()
        self.assertNotIn('deadbeefdeadbeef', table)

    def test_a_book_without_the_series_yields_nothing(self):
        saved = self.gate['BOOK']
        handle = tempfile.NamedTemporaryFile('w', suffix='.toml', delete=False,
                                             encoding='utf-8')
        handle.write('[[entry]]\nsha = "abc1234"\nstate = "booted"\n'
                     'series_sha256 = "0000000000000000"\n')
        handle.close()
        try:
            self.gate['BOOK'] = handle.name
            table = self.gate['booted_series']()
            self.assertEqual(set(table), {'0000000000000000'})
        finally:
            self.gate['BOOK'] = saved
            os.unlink(handle.name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
