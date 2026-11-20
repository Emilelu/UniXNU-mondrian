#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Apply 0542 to an original XNU excerpt, then execute its allocation/copy block.

Run in Linux/WSL with a C compiler and patch. The old block must reproduce
EMSGSIZE for the 540-byte association result before the patched block passes.
Fake mbufs check allocation selection, copy bounds and ENOMEM; socket delivery
and the real kernel allocator still need a device test.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/xnu-12377/0542-k60-association-event-cluster.patch"
FIXTURES = Path(__file__).resolve().parent / "fixtures/wifi-event"


def run(*args: str, cwd: Path) -> str:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(f"{args[0]} exited {result.returncode}:\n{result.stdout}{result.stderr}")
    return result.stdout


class AssociationEvent(unittest.TestCase):
    def test_series_contains_one_event_patch_and_no_duplicate_spi_patch(self):
        entries = [line.strip() for line in (PATCH.parent / "series").read_text(encoding="utf-8").splitlines()
                   if line.strip() and not line.lstrip().startswith("#")]
        self.assertEqual(entries.count(PATCH.name), 1)
        self.assertNotIn("availability-spi.patch", entries)
        self.assertIn("0530-k60-spi-availability.patch", entries)

    def check_event(self, mlen: int):
        compiler = shutil.which(os.environ.get("CC", "cc"))
        self.assertIsNotNone(compiler, "a host C compiler is required")
        self.assertIsNotNone(shutil.which("patch"), "patch is required")
        scratch = ROOT / "build/selftests"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="wifi-event-", dir=scratch) as directory:
            work = Path(directory)
            shutil.copytree(FIXTURES, work, dirs_exist_ok=True)
            common = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", f"-DTEST_MLEN={mlen}", "event-harness.c"]
            run(*common, "-DBASELINE", "-o", "original", cwd=work)
            self.assertIn("baseline rejects 16 + 540 bytes", run(str(work / "original"), cwd=work))
            run("patch", "--batch", "--fuzz=0", "-p1", "-i", str(PATCH), cwd=work)
            run(*common, "-o", "patched", cwd=work)
            output = run(str(work / "patched"), cwd=work)
            self.assertIn("19 checks passed", output)
            print(output.strip())

    def test_original_rejects_and_patch_preserves_bounds_mlen224(self):
        self.check_event(224)

    def test_original_rejects_and_patch_preserves_bounds_mlen256(self):
        self.check_event(256)


if __name__ == "__main__":
    unittest.main()
