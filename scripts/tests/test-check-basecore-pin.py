#!/usr/bin/env python3
"""Cases for check-basecore-pin.py (P-217).

The gate reads a real nested git repository, so each fixture builds two tiny
repositories: a parent that records a submodule pointer, and a nested checkout
that may or may not sit on that pointer.
"""

import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE.parent / 'check-basecore-pin.py'


def load_gate():
    spec = importlib.util.spec_from_file_location('k60_basecore_pin', GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(cwd, *args):
    env = dict(os.environ)
    env.setdefault('GIT_AUTHOR_NAME', 'test')
    env.setdefault('GIT_AUTHOR_EMAIL', 'test@example.com')
    env.setdefault('GIT_COMMITTER_NAME', 'test')
    env.setdefault('GIT_COMMITTER_EMAIL', 'test@example.com')
    subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, env=env)


class Fixture(unittest.TestCase):
    """A device repo plus a sibling uefi repo with a nested basecore."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='basecore-'))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.repo = self.root / 'device'
        self.uefi = self.root / 'uefi-mondrian'
        self.base = self.uefi / 'Mu_Basecore'
        self.repo.mkdir()
        self.base.mkdir(parents=True)

        # nested basecore: two commits so HEAD can differ from the pin
        git(self.base, 'init', '-q')
        (self.base / 'file.txt').write_text('one\n')
        git(self.base, 'add', '.')
        git(self.base, 'commit', '-q', '-m', 'first')
        self.pin = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=self.base,
                                  capture_output=True, text=True).stdout.strip()
        (self.base / 'file.txt').write_text('two\n')
        git(self.base, 'commit', '-q', '-am', 'second')
        self.head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=self.base,
                                   capture_output=True, text=True).stdout.strip()

        # parent uefi repo records the pin as a gitlink
        git(self.uefi, 'init', '-q')
        subprocess.run(
            ['git', 'update-index', '--add', '--cacheinfo',
             f'160000,{self.pin},Mu_Basecore'],
            cwd=self.uefi, check=True, capture_output=True,
        )
        git(self.uefi, 'commit', '-q', '-m', 'record the pin')

        # device repo: board.toml plus the manual
        (self.repo / 'docs/engineering').mkdir(parents=True)
        self.write_board([])
        self.write_manual('Nothing to declare.\n')

    def write_board(self, entries):
        body = '\n'.join(f'  "{e}",' for e in entries)
        (self.repo / 'board.toml').write_text(
            f'[firmware]\nconfig = "mondrian"\npatches = [\n{body}\n]\npackages = [\n  "{{uefi}}",\n]\n',
            encoding='utf-8',
        )

    def write_manual(self, text):
        (self.repo / 'docs/engineering/FIRMWARE-REBUILD.md').write_text(text, encoding='utf-8')

    def run_gate(self):
        gate = load_gate()
        return gate.check(self.repo, self.uefi)


class PinMatch(Fixture):
    def test_the_pinned_worktree_passes(self):
        git(self.base, 'checkout', '-q', self.pin)
        problems, _ = self.run_gate()
        self.assertEqual(problems, [])

    def test_a_different_worktree_fails(self):
        problems, _ = self.run_gate()
        self.assertTrue(problems)
        self.assertTrue(any('clean clone would build different firmware' in p for p in problems))

    def test_quoting_the_old_wrong_claim_does_not_count(self):
        # The real manual quotes "3d2a9fa is an ancestor" to explain the mistake.
        self.write_manual('Mu_Basecore 6f805f2 already carries all six fixes (3d2a9fa is an ancestor).\n')
        problems, _ = self.run_gate()
        self.assertTrue(problems, 'quoting the old claim must not satisfy the gate')

    def test_a_recorded_deviation_passes(self):
        self.write_manual('The Mu_Basecore worktree sits at `3d2a9fa` on purpose, see below.\n')
        problems, notes = self.run_gate()
        self.assertEqual(problems, [])
        self.assertTrue(any('recorded deviation' in n for n in notes))


class BoardPatches(Fixture):
    def test_a_missing_patch_fails(self):
        git(self.base, 'checkout', '-q', self.pin)
        self.write_board(['Resources/MuPatches/Timer.patch'])
        problems, _ = self.run_gate()
        self.assertTrue(problems)
        self.assertTrue(any('listed in [firmware].patches but missing' in p for p in problems))

    def test_an_applying_patch_passes(self):
        git(self.base, 'checkout', '-q', self.pin)
        patches = self.uefi / 'Resources/MuPatches'
        patches.mkdir(parents=True)
        (self.base / 'file.txt').write_text('three\n')
        git(self.base, 'diff', '--output', str(patches / 'Timer.patch'))
        git(self.base, 'checkout', '-q', '--', 'file.txt')
        self.write_board(['Resources/MuPatches/Timer.patch'])
        problems, _ = self.run_gate()
        self.assertEqual(problems, [])

    def test_a_patch_that_does_not_apply_fails(self):
        git(self.base, 'checkout', '-q', self.pin)
        patches = self.uefi / 'Resources/MuPatches'
        patches.mkdir(parents=True)
        (patches / 'Timer.patch').write_text(
            'diff --git a/file.txt b/file.txt\n--- a/file.txt\n+++ b/file.txt\n'
            '@@ -1 +1 @@\n-nonexistent\n+other\n'
        )
        self.write_board(['Resources/MuPatches/Timer.patch'])
        problems, _ = self.run_gate()
        self.assertTrue(problems)
        self.assertTrue(any('does not apply to the pinned basecore' in p for p in problems))

    def test_a_comment_is_not_a_patch_entry(self):
        git(self.base, 'checkout', '-q', self.pin)
        (self.repo / 'board.toml').write_text(
            '[firmware]\npatches = [\n'
            '  # the old note said "3d2a9fa is an ancestor", which was wrong\n'
            ']\n',
            encoding='utf-8',
        )
        problems, notes = self.run_gate()
        self.assertEqual(problems, [])
        self.assertTrue(any('patches is empty' in n for n in notes))


class Scope(Fixture):
    def test_a_missing_nested_checkout_skips(self):
        shutil.rmtree(self.base)
        problems, notes = self.run_gate()
        self.assertEqual(problems, [])
        self.assertTrue(any('is not present' in n for n in notes))

    def test_the_real_repository_runs(self):
        gate = load_gate()
        problems, notes = gate.check(HERE.parents[1])
        # The live tree may legitimately deviate while the deviation is being
        # fixed; this case only asserts the gate runs and returns a list.
        self.assertIsInstance(problems, list)
        self.assertIsInstance(notes, list)


if __name__ == '__main__':
    unittest.main(verbosity=2)
