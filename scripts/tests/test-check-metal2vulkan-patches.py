#!/usr/bin/env python3
"""Tests for scripts/check-metal2vulkan-patches.py."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE.parent / 'check-metal2vulkan-patches.py'
spec = importlib.util.spec_from_file_location('gate', GATE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def make_repo(base: Path, patches: dict[str, str], script_text: str | None, notes: str | None) -> Path:
    folder = base / 'patches' / 'metal2vulkan'
    folder.mkdir(parents=True)
    for name in patches:
        (folder / name).write_text('# patch\n', encoding='utf-8')
    if notes is not None:
        (folder / 'DATA-A-LIVE.md').write_text(notes, encoding='utf-8')
    if script_text is not None:
        (base / 'scripts').mkdir()
        (base / 'scripts' / 'build.py').write_text(script_text, encoding='utf-8')
    return base


class PatchAccounting(unittest.TestCase):
    def test_a_patch_named_by_a_build_script_is_accounted_for(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), {'0001-a.patch': ''}, "apply('0001-a.patch')\n", '')
            problems, total = gate.check(repo)
            self.assertEqual((problems, total), ([], 1))

    def test_a_patch_nobody_applies_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), {'0002-b.patch': ''}, "apply('0001-a.patch')\n", '')
            problems, total = gate.check(repo)
            self.assertEqual(total, 1)
            self.assertEqual(len(problems), 1)
            self.assertIn('0002-b.patch', problems[0])

    def test_a_patch_declared_unused_passes(self):
        notes = '# notes\n\n## 未启用\n\n- `0002-b.patch` — 不适用\n'
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), {'0002-b.patch': ''}, 'print(1)\n', notes)
            problems, _ = gate.check(repo)
            self.assertEqual(problems, [])

    def test_a_declaration_outside_the_unused_section_does_not_count(self):
        notes = '# notes\n\n- `0002-b.patch` 只是提到，不在未启用小节\n'
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), {'0002-b.patch': ''}, 'print(1)\n', notes)
            problems, _ = gate.check(repo)
            self.assertEqual(len(problems), 1)

    def test_an_empty_patch_directory_is_an_error_not_a_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / 'patches' / 'metal2vulkan').mkdir(parents=True)
            problems, total = gate.check(repo)
            self.assertEqual(total, 0)
            self.assertEqual(len(problems), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
