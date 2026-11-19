#!/usr/bin/env python3
"""Cases for check-doc-citations.py.

The gate scans markdown citations against the real repository; each case builds a
throwaway tree so it can control which targets exist and how long they are.
"""

import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE.parent / 'check-doc-citations.py'


def load_gate():
    spec = importlib.util.spec_from_file_location('k60_doc_citations', GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScanCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='doc-citations-')
        self.gate = load_gate()
        self.gate.REPO = self.tmp
        os.makedirs(os.path.join(self.tmp, 'docs', 'research'), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, 'drivers'), exist_ok=True)
        with io.open(os.path.join(self.tmp, 'drivers', 'ok.cpp'), 'w',
                     encoding='utf-8') as fh:
            fh.write('line1\nline2\nline3\n')

    def write_doc(self, body):
        p = os.path.join(self.tmp, 'docs', 'research', 'a.md')
        with io.open(p, 'w', encoding='utf-8') as fh:
            fh.write(body)
        return p

    def test_existing_target_with_valid_line_is_clean(self):
        self.write_doc('see drivers/ok.cpp:3 for the path\n')
        total, missing, overflow = self.gate.scan()
        self.assertEqual(total, 1)
        self.assertEqual(missing, {})
        self.assertEqual(overflow, {})

    def test_missing_target_is_reported(self):
        self.write_doc('see drivers/nope.cpp:1\n')
        total, missing, overflow = self.gate.scan()
        self.assertEqual(total, 1)
        self.assertIn('drivers/nope.cpp', missing)

    def test_line_past_end_is_reported(self):
        self.write_doc('see drivers/ok.cpp:9 and drivers/ok.cpp:2-9\n')
        total, missing, overflow = self.gate.scan()
        self.assertEqual(total, 2)
        self.assertEqual(sorted(overflow), ['drivers/ok.cpp|9'])

    def test_bare_path_without_line_is_checked_but_not_overflow(self):
        self.write_doc('the string drivers/nope.cpp has no line number\n')
        total, missing, overflow = self.gate.scan()
        self.assertEqual(total, 1)
        self.assertEqual(missing, {'drivers/nope.cpp': ['docs/research/a.md:1']})
        self.assertEqual(overflow, {})

    def test_baseline_round_trip(self):
        self.write_doc('see drivers/nope.cpp:1\n')
        _total, missing, overflow = self.gate.scan()
        self.gate.BASELINE = os.path.join(self.tmp, 'baseline.toml')
        self.gate.write_baseline(missing, overflow)
        allowed_missing, allowed_overflow = self.gate.load_baseline()
        self.assertEqual(allowed_missing, ['drivers/nope.cpp'])
        self.assertEqual(allowed_overflow, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
