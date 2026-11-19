#!/usr/bin/env python3
"""Cases for check-component-pin.py.

The gate compares board.toml components with the framework catalog. Each case
replaces the catalog/board/deviation readers with in-memory data so the decision
logic (match / documented drift / stale entry) is tested without any checkout.
"""

import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE.parent / 'check-component-pin.py'


def load_gate():
    spec = importlib.util.spec_from_file_location('k60_component_pin', GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PinCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='component-pin-')
        self.gate = load_gate()
        self.gate.REPO = Path(self.tmp)
        self.gate.FRAMEWORK = Path(self.tmp) / 'fw'
        os.makedirs(self.gate.FRAMEWORK, exist_ok=True)
        with io.open(self.gate.FRAMEWORK / 'components.toml', 'w', encoding='utf-8') as fh:
            fh.write('')
        self.gate.PINS = Path(self.tmp) / 'COMPONENT-PINS.toml'
        self.catalog = {'A': {'id': 'A', 'revision': '1111', 'path': 'drivers/A'}}

    def run_gate(self, board=('A',), deviations=(), local='1111'):
        self.gate.load_catalog = lambda: self.catalog
        self.gate.load_board = lambda: list(board)
        self.gate.load_deviations = lambda: list(deviations)
        self.gate.resolve_local = lambda entry: (Path('/x'), local, 'worktree')
        return self.gate.main()

    def test_matching_pin_is_clean(self):
        self.assertEqual(self.run_gate(), 0)

    def test_unexplained_drift_fails(self):
        self.assertEqual(self.run_gate(local='2222'), 1)

    def test_documented_drift_passes(self):
        dev = [{'component': 'A', 'our_revision': '2222',
                'catalog_revision': '1111', 'reason': 'old tree'}]
        self.assertEqual(self.run_gate(local='2222', deviations=dev), 0)

    def test_stale_deviation_fails(self):
        dev = [{'component': 'A', 'our_revision': '2222', 'catalog_revision': '1111',
                'reason': 'old tree'}]
        self.assertEqual(self.run_gate(local='1111', deviations=dev), 1)

    def test_board_component_missing_from_catalog_fails(self):
        self.assertEqual(self.run_gate(board=('A', 'B')), 1)


if __name__ == '__main__':
    unittest.main()
