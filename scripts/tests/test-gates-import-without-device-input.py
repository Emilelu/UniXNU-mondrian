#!/usr/bin/env python3
"""P-214/P-220: the gate modules must be importable without K60_DEVICE_INPUT.

The gates refuse to judge a tree against an unnamed mirror, which is right for
the command line. The first version enforced it at module level, so any unit
test that imported the file got SystemExit halfway through the module and then
reported `module has no attribute series_fingerprint` -- two reds in
check-rules that had nothing to do with the tree. The refusal belongs to the
CLI entry point, not to the import.
"""
import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def load_without_env(name, filename):
    env = dict(os.environ)
    env.pop("K60_DEVICE_INPUT", None)
    code = (
        "import importlib.util, sys\n"
        "spec = importlib.util.spec_from_file_location(%r, %r)\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "try:\n"
        "    spec.loader.exec_module(mod)\n"
        "except SystemExit:\n"
        "    pass\n"
        "assert hasattr(mod, 'series_fingerprint') or hasattr(mod, 'main'), dir(mod)\n"
    ) % (name, str(ROOT / "scripts" / filename))
    return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)


class ImportsWithoutMirror(unittest.TestCase):
    def test_porting_gate_imports(self):
        r = load_without_env("porting_gate", "porting-gate.py")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_check_build_applied_imports(self):
        r = load_without_env("k60_build_applied", "check-build-applied.py")
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
