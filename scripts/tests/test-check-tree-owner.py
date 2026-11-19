#!/usr/bin/env python3
"""check-tree-owner must recognise one checkout under every host spelling (P-184).

TREE-OWNERS.toml records WSL paths; the gate also runs on the Windows host,
where the same checkout is E:/hackios/<line>. Comparing raw strings made a
registered tree look unregistered, so iron-11 failed on a tree that was in
fact owned - noise in the one check that protects uncommitted work.
"""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / 'scripts' / 'check-tree-owner.py'


def load():
    spec = importlib.util.spec_from_file_location('check_tree_owner', GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PathForms(unittest.TestCase):
    def test_wsl_path_gains_its_windows_form(self):
        forms = load().path_forms('/mnt/e/hackios/k60-charger')
        self.assertIn('/mnt/e/hackios/k60-charger', forms)
        self.assertIn('E:/hackios/k60-charger', forms)

    def test_windows_path_gains_its_wsl_form(self):
        forms = load().path_forms('E:/hackios/k60-charger')
        self.assertIn('/mnt/e/hackios/k60-charger', forms)

    def test_a_plain_relative_path_is_left_alone(self):
        self.assertEqual(load().path_forms('relative/tree'), {'relative/tree'})

    def test_another_line_stays_a_different_tree(self):
        forms = load().path_forms('/mnt/e/hackios/k60-charger')
        self.assertNotIn('E:/hackios/k60-audio', forms)
        self.assertNotIn('/mnt/e/hackios/k60-audio', forms)


class Registration(unittest.TestCase):
    def test_this_checkout_is_registered_under_its_host_spelling(self):
        out = load().main()
        self.assertEqual(out, 0, 'the charger checkout must be recognised as owned')


if __name__ == '__main__':
    sys.exit(0 if unittest.main(exit=False, verbosity=1).result.wasSuccessful() else 1)
