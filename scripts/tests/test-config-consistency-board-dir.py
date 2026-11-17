#!/usr/bin/env python3
"""The config gate must grade the tree this build used, not the first alphabetically.

P-225: `resolve_generated()` returned `found[0]` from a sorted glob.  When an OUT
holds two board directories (one from the full defconfig, one left behind by a
build of `mondrian_wifi_defconfig`), the gate silently graded whichever sorted
first -- the same defect that made `build-strict.sh` pick a board directory by
mtime and skip the Metal plugin and the battery archive.

The ranking is deliberately the same in both places: a config that names the
two feature keys outranks one that does not, and mtime only breaks a tie.
"""

import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE.parent / "check-config-consistency.py"
SDK = "ipados-16.6.1-20G81"

FULL = "CONFIG_XNU_GPU_ADDON=y\nCONFIG_XNU_K60_PHYSICAL_BATTERY=y\n"
PARTIAL = "# CONFIG_XNU_GPU_ADDON is not set\n# CONFIG_XNU_K60_PHYSICAL_BATTERY is not set\n"


def load_gate():
    spec = importlib.util.spec_from_file_location("config_gate", str(GATE))
    module = importlib.util.module_from_spec(spec)
    # @dataclass resolves annotations through sys.modules[cls.__module__], so the
    # module has to be registered before exec_module or the gate fails to import.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_board(out: Path, name: str, body: str, age_seconds: float = 0.0) -> Path:
    """Create out/mondrian/<sdk>/<name>/.config and backdate it if asked."""
    board = out / "mondrian" / SDK / name
    board.mkdir(parents=True, exist_ok=True)
    config = board / ".config"
    config.write_text(body, encoding="utf-8")
    if age_seconds:
        stamp = time.time() - age_seconds
        os.utime(config, (stamp, stamp))
    return config


class ResolveGenerated(unittest.TestCase):
    def setUp(self):
        self.gate = load_gate()
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_full_config_beats_an_older_partial_one(self):
        """The real case: mondrian_wifi sorts first but lacks both feature keys."""
        make_board(self.out, "mondrian", FULL, age_seconds=3600)
        make_board(self.out, "mondrian_wifi", PARTIAL, age_seconds=0)
        chosen = self.gate.resolve_generated(self.out)
        self.assertEqual(chosen.parent.name, "mondrian")

    def test_a_full_config_beats_a_newer_partial_one(self):
        """Age must not outrank the keys, which is what P-225 was about."""
        make_board(self.out, "mondrian", FULL, age_seconds=7200)
        make_board(self.out, "mondrian_wifi", PARTIAL, age_seconds=0)
        chosen = self.gate.resolve_generated(self.out)
        self.assertEqual(chosen.parent.name, "mondrian")

    def test_two_full_configs_fall_back_to_the_newest(self):
        make_board(self.out, "alpha", FULL, age_seconds=7200)
        make_board(self.out, "mondrian", FULL, age_seconds=0)
        chosen = self.gate.resolve_generated(self.out)
        self.assertEqual(chosen.parent.name, "mondrian")

    def test_two_partial_configs_still_resolve_to_one(self):
        """A tree with no full config must still be graded, not crash."""
        make_board(self.out, "alpha", PARTIAL, age_seconds=7200)
        make_board(self.out, "mondrian_wifi", PARTIAL, age_seconds=0)
        chosen = self.gate.resolve_generated(self.out)
        self.assertEqual(chosen.parent.name, "mondrian_wifi")

    def test_a_single_board_is_returned_unchanged(self):
        make_board(self.out, "mondrian", PARTIAL)
        chosen = self.gate.resolve_generated(self.out)
        self.assertEqual(chosen.parent.name, "mondrian")

    def test_an_empty_out_falls_back_to_the_default_name(self):
        """No board directory at all: name the conventional path so the error is readable."""
        chosen = self.gate.resolve_generated(self.out)
        self.assertEqual(chosen, self.out / "mondrian" / SDK / "mondrian" / ".config")

    def test_an_unreadable_config_does_not_win(self):
        """A config we cannot read has no proven features; it must not outrank a readable one."""
        broken = self.out / "mondrian" / SDK / "zzz"
        broken.mkdir(parents=True)
        (broken / ".config").write_bytes(b"")
        os.chmod(broken / ".config", 0o000)
        make_board(self.out, "mondrian", FULL, age_seconds=3600)
        try:
            chosen = self.gate.resolve_generated(self.out)
        finally:
            os.chmod(broken / ".config", 0o644)
        self.assertEqual(chosen.parent.name, "mondrian")

    def test_the_dangling_number_is_gone(self):
        """P-187 was cited twice but never existed in PITFALLS.md."""
        source = GATE.read_text(encoding="utf-8")
        self.assertNotIn("P-187", source)
        self.assertIn("P-225", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
