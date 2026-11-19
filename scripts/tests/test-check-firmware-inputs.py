#!/usr/bin/env python3
"""Cases for check-firmware-inputs.py (P-227).

The gate reads a real `build_uefi.py`, so each fixture writes a tiny one.  What
matters is the shape of the statement, not the firmware: a path handed to a tool
either exists in the checkout or sits behind an existence check.
"""

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE.parent / 'check-firmware-inputs.py'

SCRIPT = """from pathlib import Path

RESOURCE_DTBS_PATH = Path ("Resources/DTBs")


def create (device):
    device_dtb = RESOURCE_DTBS_PATH / f"{device}.dtb"
    if not device_dtb.is_file ():
        print ("missing")
        return False
    ramdisk_path = Path ("Resources/ramdisk")
    cmd = ["mkbootimg"]
    if ramdisk_path.is_file ():
        cmd += ["--ramdisk", str (ramdisk_path)]
    return cmd
"""


def load_gate():
    spec = importlib.util.spec_from_file_location('k60_firmware_inputs', GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Fixture(unittest.TestCase):
    """A device repo plus a sibling uefi repo holding a build_uefi.py."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='fwinputs-'))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.repo = self.root / 'device'
        self.uefi = self.root / 'uefi-mondrian'
        self.repo.mkdir()
        self.uefi.mkdir(parents=True)
        self.write_script(SCRIPT)

    def write_script(self, text):
        (self.uefi / 'build_uefi.py').write_text(text, encoding='utf-8')

    def touch(self, relative, body='x'):
        path = self.uefi / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding='utf-8')

    def run_gate(self):
        return load_gate().check(self.repo, self.uefi)


class Inputs(Fixture):
    def test_a_present_input_passes(self):
        self.touch('Resources/DTBs/mondrian.dtb')
        problems, notes = self.run_gate()
        self.assertEqual(problems, [])
        self.assertTrue(any('guarded' in n for n in notes))

    def test_a_guarded_absent_input_only_notes(self):
        self.touch('Resources/DTBs/mondrian.dtb')
        problems, notes = self.run_gate()
        self.assertEqual(problems, [], 'an is_file() guard turns absence into a decision')
        self.assertTrue(any('Resources/ramdisk' in n for n in notes))

    def test_an_unguarded_absent_input_fails(self):
        # The historical shape: the path is handed to mkbootimg unconditionally.
        self.write_script(
            'from pathlib import Path\n\n'
            'def create ():\n'
            '    return ["mkbootimg", "--ramdisk", "Resources/ramdisk"]\n'
        )
        problems, _ = self.run_gate()
        self.assertTrue(problems)
        self.assertTrue(any('Resources/ramdisk' in p for p in problems))
        self.assertTrue(any('P-227' in p for p in problems))

    def test_a_guard_on_another_variable_does_not_count(self):
        self.touch('Resources/DTBs/mondrian.dtb')
        self.write_script(
            'from pathlib import Path\n\n'
            'def create ():\n'
            '    ramdisk = Path ("Resources/ramdisk")\n'
            '    other = Path ("Resources/other")\n'
            '    if not other.is_file ():\n'
            '        return False\n'
            '    return ["mkbootimg", "--ramdisk", str (ramdisk)]\n'
        )
        problems, _ = self.run_gate()
        self.assertTrue(any('Resources/ramdisk' in p for p in problems))
        self.assertFalse(any('Resources/other' in p for p in problems))

    def test_a_path_inside_a_sentence_is_not_an_input(self):
        self.touch('Resources/DTBs/mondrian.dtb')
        self.write_script(
            'from pathlib import Path\n\n'
            'def create ():\n'
            '    print ("see Resources/DTBs/MANIFEST.md for where it came from")\n'
            '    return Path ("Resources/DTBs")\n'
        )
        problems, _ = self.run_gate()
        self.assertEqual(problems, [])


class Scope(Fixture):
    def test_a_missing_uefi_checkout_skips(self):
        shutil.rmtree(self.uefi)
        problems, notes = self.run_gate()
        self.assertEqual(problems, [])
        self.assertTrue(any('is not present' in n for n in notes))

    def test_an_unparsable_script_fails(self):
        self.write_script('def broken(:\n')
        problems, _ = self.run_gate()
        self.assertTrue(any('cannot parse' in p for p in problems))

    def test_the_real_repository_runs(self):
        problems, notes = load_gate().check(HERE.parents[1])
        # The live tree may legitimately carry an absent guarded input; this case
        # only asserts the gate runs against the real script and returns lists.
        self.assertIsInstance(problems, list)
        self.assertIsInstance(notes, list)


if __name__ == '__main__':
    unittest.main(verbosity=2)
