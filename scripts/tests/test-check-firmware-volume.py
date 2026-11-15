#!/usr/bin/env python3
"""Cases for check-firmware-volume.py (P-216).

Each case writes a throwaway repository with one manual and asserts whether the
gate accepts it.  The gate reads documentation only, so every fixture is a
short markdown file.
"""

import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE.parent / 'check-firmware-volume.py'


def load_gate():
    spec = importlib.util.spec_from_file_location('k60_firmware_volume', GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MANUAL = 'docs/engineering/FIRMWARE-REBUILD.md'


class Fixture(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='fwvol-'))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        (self.root / 'docs/engineering').mkdir(parents=True)

    def write(self, text, rel=MANUAL):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def run_gate(self):
        gate = load_gate()
        return gate.check(self.root)


class ReproducibilityClaims(Fixture):
    def test_a_deterministic_claim_fails(self):
        self.write('# manual\n\n## 2. 它是确定性的（同源 ⇒ 同字节）\n\n所以同样的源码 + 同样的 pin ⇒ 同一个 FD。\n')
        problems, _ = self.run_gate()
        self.assertTrue(problems, 'a deterministic claim must fail')
        self.assertTrue(any('reproducible' in p for p in problems))

    def test_an_explicit_refutation_passes(self):
        self.write(
            '# manual\n\n## 2. 它**不是**确定性的（同源也不得同字节）\n\n'
            '这句话「同源 ⇒ 同字节」是错的，三次重建给了三个哈希。\n'
        )
        problems, _ = self.run_gate()
        self.assertEqual(problems, [])

    def test_the_english_claim_fails(self):
        self.write('# manual\n\nThe same source yields the same bytes every time.\n')
        problems, _ = self.run_gate()
        self.assertTrue(problems)


class HashIdentity(Fixture):
    def test_a_hash_as_identity_fails(self):
        self.write('# manual\n\nFD 的 sha256 `4bbe76017eb4` 是这份固件的身份，可以据此判断同源。\n')
        problems, _ = self.run_gate()
        self.assertTrue(problems, 'a hash presented as an identity must fail')

    def test_a_hash_with_a_build_marker_passes(self):
        self.write('# manual\n\nFD 的 sha256 `4bbe76017eb4` 只是一次构建的标识，不是身份。\n')
        problems, _ = self.run_gate()
        self.assertEqual(problems, [])

    def test_a_hash_table_passes(self):
        self.write(
            '# manual\n\n| sha256（前 12） | 大小 |\n| --- | --- |\n'
            '| `4bbe76017eb4` | 3,145,728 B |\n| `9f20de15388a` | 3,145,728 B |\n'
        )
        problems, _ = self.run_gate()
        self.assertEqual(problems, [], 'listing hashes in a table is the correct shape')


class Scope(unittest.TestCase):
    def test_pitfalls_is_not_audited(self):
        root = Path(tempfile.mkdtemp(prefix='fwvol-'))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / 'docs/engineering').mkdir(parents=True)
        (root / 'docs/engineering/PITFALLS.md').write_text(
            '## P-216\n\n手册写着「同源 ⇒ 同字节」，这句话是错的。\n', encoding='utf-8'
        )
        gate = load_gate()
        problems, notes = gate.check(root)
        self.assertEqual(problems, [], 'PITFALLS quotes the mistake on purpose')
        self.assertTrue(any('not in this tree' in n for n in notes))

    def test_a_repo_without_the_manual_skips(self):
        root = Path(tempfile.mkdtemp(prefix='fwvol-'))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        gate = load_gate()
        problems, notes = gate.check(root)
        self.assertEqual(problems, [])
        self.assertTrue(any('no firmware-volume manual' in n or 'not in this tree' in n for n in notes))

    def test_the_real_repository_is_clean(self):
        gate = load_gate()
        problems, _ = gate.check(HERE.parents[1])
        self.assertEqual(problems, [], 'the landed manual must pass its own gate')


if __name__ == '__main__':
    unittest.main(verbosity=2)
