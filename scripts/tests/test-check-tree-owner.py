#!/usr/bin/env python3
"""check-tree-owner must recognise one checkout under every host spelling (P-184).

TREE-OWNERS.toml records WSL paths; the gate also runs on the Windows host,
where the same checkout is spelled with a drive letter. Comparing raw strings
made a registered tree look unregistered, so iron-11 failed on a tree that was
in fact owned - noise in the one check that protects uncommitted work.

Paths here are derived from this file's location, never written out: hard-39
forbids a literal checkout path under scripts/.
"""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / 'scripts' / 'check-tree-owner.py'
HOST_FORM = ROOT.as_posix()


def wsl_form(posix: str) -> str:
    """The same path as the build side spells it: E:/x -> /mnt/e/x."""
    if len(posix) > 2 and posix[1] == ':':
        return '/mnt/' + posix[0].lower() + '/' + posix[3:]
    return posix


def load():
    spec = importlib.util.spec_from_file_location('check_tree_owner', GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PathForms(unittest.TestCase):
    def test_a_wsl_path_gains_its_host_form(self):
        forms = load().path_forms(wsl_form(HOST_FORM))
        self.assertIn(wsl_form(HOST_FORM), forms)
        self.assertIn(HOST_FORM, forms)

    def test_a_host_path_gains_its_wsl_form(self):
        self.assertIn(wsl_form(HOST_FORM), load().path_forms(HOST_FORM))

    def test_a_plain_relative_path_is_left_alone(self):
        self.assertEqual(load().path_forms('relative/tree'), {'relative/tree'})

    def test_a_sibling_checkout_stays_a_different_tree(self):
        sibling = wsl_form(HOST_FORM).replace(ROOT.name, ROOT.name + '-sibling')
        self.assertNotIn(sibling, load().path_forms(wsl_form(HOST_FORM)))


class Registration(unittest.TestCase):
    def test_this_checkout_is_registered_under_its_host_spelling(self):
        self.assertEqual(load().main(), 0, 'this checkout must be recognised as owned')


if __name__ == '__main__':
    sys.exit(0 if unittest.main(exit=False, verbosity=1).result.wasSuccessful() else 1)
