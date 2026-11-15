#!/usr/bin/env python3
"""Exercise feed metadata sync in temporary trees; never use real mirrors."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "sync-device-input.py"
METADATA = {
    "feeds.toml": b'# pinned feed\r\n[[source]]\r\nname = "sm8475"\r\nkind = "soc"\r\ncommit = "0123456789abcdef"\r\n',
    "unixnu.lock": b'# resolved lock\r\n[source."sm8475"]\r\ncommit = "0123456789abcdef"\r\n',
}


class FeedMetadataSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="k60-feed-sync-")
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.repo, self.device = root / "repo", root / "device"
        self.repo.mkdir()
        self.device.mkdir()
        self.scratch = root / "scratch-series"
        self.scratch.write_bytes(b"unchanged scratch\n")
        for name, data in METADATA.items():
            (self.repo / name).write_bytes(data)
        spec = importlib.util.spec_from_file_location("k60_sync_under_test", SCRIPT)
        self.sync = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.sync)
        self.sync.REPO = str(self.repo)
        self.sync.DEV = str(self.device)
        self.sync.SCRATCH_SERIES = str(self.scratch)
        # Isolate the production script's separately configured shared CLI mirror.
        self.sync.FRAMEWORK_PAIRS = []

    def run_sync(self, check=False):
        output = io.StringIO()
        args = [str(SCRIPT)] + (["--check"] if check else [])
        with mock.patch.object(sys, "argv", args), mock.patch.dict(
            os.environ, {"K60_DEVICE_INPUT": str(self.device)}
        ), contextlib.redirect_stdout(output):
            rc = self.sync.main()
        return rc, output.getvalue()

    def test_check_reports_both_missing_files_without_writes(self):
        rc, output = self.run_sync(check=True)
        self.assertEqual(rc, 1, output)
        for name, data in METADATA.items():
            self.assertIn(name, output)
            self.assertFalse((self.device / name).exists())
            self.assertEqual((self.repo / name).read_bytes(), data)

    def test_sync_preserves_exact_pins_bytes_and_unrelated_files(self):
        sentinel = self.device / "local-cache.keep"
        sentinel.write_bytes(b"unrelated destination data\n")
        rc, output = self.run_sync()
        self.assertEqual(rc, 0, output)
        for name, data in METADATA.items():
            self.assertEqual((self.device / name).read_bytes(), data)
            self.assertEqual((self.repo / name).read_bytes(), data)
        self.assertEqual(sentinel.read_bytes(), b"unrelated destination data\n")
        self.assertEqual(self.scratch.read_bytes(), b"unchanged scratch\n")
        rc, output = self.run_sync(check=True)
        self.assertEqual(rc, 0, output)

    def test_check_detects_each_metadata_drift_without_repair(self):
        for name in METADATA:
            with self.subTest(name=name):
                for path, data in METADATA.items():
                    (self.device / path).write_bytes(data)
                stale = b"stale pin\n"
                (self.device / name).write_bytes(stale)
                rc, output = self.run_sync(check=True)
                self.assertEqual(rc, 1, output)
                self.assertIn(name, output)
                self.assertEqual((self.device / name).read_bytes(), stale)
                self.assertEqual((self.repo / name).read_bytes(), METADATA[name])

    def test_sync_replaces_stale_metadata_from_canonical_source(self):
        for name in METADATA:
            (self.device / name).write_bytes(b"stale pin\n")
        rc, output = self.run_sync()
        self.assertEqual(rc, 0, output)
        for name, data in METADATA.items():
            self.assertEqual((self.device / name).read_bytes(), data)

    def test_absent_optional_source_metadata_does_not_delete_destination(self):
        for name in METADATA:
            (self.repo / name).unlink()
            (self.device / name).write_bytes(b"existing optional metadata\n")
        rc, output = self.run_sync()
        self.assertEqual(rc, 0, output)
        for name in METADATA:
            self.assertEqual((self.device / name).read_bytes(), b"existing optional metadata\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
