#!/usr/bin/env python3
"""Tests for the P-165 stamp selection in scripts/check-build-applied.py.

The gate has to tell three situations apart, and the first version could only
tell two:

  * a stamp whose bytes match this checkout's series  -> grade it, it passes;
  * a stamp with the same patch names but different bytes -> this checkout's
    series changed after that build, so the build no longer proves anything;
    that is a real red (P-165's whole point);
  * a stamp that lists *different* patch names -> it belongs to another branch
    or another board's series, and nothing about this checkout follows from it.
    The old fallback graded it anyway and reported "构建应用了 232 个补丁，但
    series 列了 227 个" for a tree nobody had built on this branch yet
    (P-189 fallback + P-207: never judge a stale artifact).
"""

import hashlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(os.path.dirname(HERE), "check-build-applied.py")

NAMES = ["0001-alpha.patch", "0002-beta.patch"]


def load_gate():
    spec = importlib.util.spec_from_file_location("k60_build_applied", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(text)


class Repo(object):
    """A miniature checkout: a series file plus the patch files it names."""

    def __init__(self, names=None):
        self.root = tempfile.mkdtemp(prefix="k60-applied-")
        self.names = list(names if names is not None else NAMES)
        self.write_series(self.names)

    def write_series(self, names):
        self.names = list(names)
        write(os.path.join(self.root, "patches/xnu/series"), "\n".join(names) + "\n")

    def patch(self, name, body):
        write(os.path.join(self.root, "patches/xnu", name), body)

    def stamp(self, names, bodies=None, name="xnu-inputs.json"):
        """Write a build stamp recording `names` with their current bytes."""
        bodies = bodies or {}
        entries = []
        for entry in names:
            path = os.path.join(self.root, "patches/xnu", entry)
            text = bodies.get(entry)
            if text is not None:
                write(path, text)
            elif not os.path.exists(path):
                # A stamp from another branch names patches this checkout has
                # never carried; the file only has to exist to be hashed.
                write(path, "body of %s\n" % entry)
            with open(path, "rb") as handle:
                digest = hashlib.sha256(handle.read()).hexdigest()
            entries.append({"name": entry, "path": path, "sha256": digest})
        out = os.path.join(self.root, "out", name, "xnu-inputs.json")
        write(out, json.dumps({"patches": entries}))
        return out

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


class StampSelectionTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.gate = load_gate()
        self.saved = (self.gate.REPO, self.gate.SERIES, self.gate.OUT_ROOTS,
                      self.gate.INPUT, os.environ.get("K60_OUT"),
                      self.gate.IN_PROGRESS)
        self.gate.REPO = type(self.gate.REPO)(self.repo.root)
        # SERIES and INPUT are module constants resolved at import, so they have
        # to be redirected too; otherwise every fixture is graded against the
        # real repository's 227-entry series and P-166 compares the fixture
        # series with the machine's shared build input.
        self.gate.SERIES = type(self.gate.REPO)(
            os.path.join(self.repo.root, "patches/xnu/series"))
        self.gate.INPUT = self.gate.SERIES
        self.gate.OUT_ROOTS = [type(self.gate.REPO)(os.path.join(self.repo.root, "out"))]
        # build-strict.sh exports K60_BUILD_IN_PROGRESS=1 so that the gate it
        # runs *during* a build cannot block that same build (P-165's deadlock).
        # The registry inherits it, so a test run from inside build-strict would
        # otherwise grade every "series changed" case as a warning and the
        # red-path assertions here would silently pass. Pin it off.
        self.gate.IN_PROGRESS = False
        os.environ.pop("K60_BUILD_IN_PROGRESS", None)
        os.environ.pop("K60_OUT", None)
        for name in NAMES:
            self.repo.patch(name, "body of %s\n" % name)

    def tearDown(self):
        (self.gate.REPO, self.gate.SERIES, self.gate.OUT_ROOTS,
         self.gate.INPUT, saved_out, self.gate.IN_PROGRESS) = self.saved
        if saved_out is None:
            os.environ.pop("K60_OUT", None)
        else:
            os.environ["K60_OUT"] = saved_out
        self.repo.cleanup()

    def test_a_matching_stamp_is_graded(self):
        stamp = self.repo.stamp(NAMES)
        self.assertEqual(self.gate.stamp_path(), type(self.gate.REPO)(stamp))

    def test_a_changed_patch_is_still_graded(self):
        """Same names, different bytes: the series moved after that build."""
        stamp = self.repo.stamp(NAMES)
        self.repo.patch(NAMES[1], "body changed after the build\n")
        self.assertEqual(self.gate.stamp_path(), type(self.gate.REPO)(stamp))
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = self.gate.check_stamp(type(self.gate.REPO)(stamp), quiet=True)
        self.assertEqual(code, 1)
        self.assertIn("与仓库不一致", buffer.getvalue())

    def test_another_branchs_stamp_is_not_graded(self):
        """Different names: nothing about this checkout follows from it."""
        stamp = self.repo.stamp(["0100-other.patch", "0101-other.patch"])
        self.assertIsNone(self.gate.stamp_path())
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = self.gate.main()
        self.assertEqual(code, 0)
        self.assertIn("跳过 P-165", buffer.getvalue())
        self.assertNotIn("232", buffer.getvalue())

    def test_the_newest_matching_stamp_wins_over_a_newer_foreign_one(self):
        mine = self.repo.stamp(NAMES, name="mine.json")
        foreign = self.repo.stamp(["0100-other.patch"], name="foreign.json")
        os.utime(foreign, (2_000_000_000, 2_000_000_000))
        self.assertEqual(self.gate.stamp_path(), type(self.gate.REPO)(mine))

    def test_a_stamp_without_names_falls_back_to_its_path(self):
        """Older stamps recorded only paths; the basename is the patch name."""
        entries = []
        for entry in NAMES:
            path = os.path.join(self.repo.root, "patches/xnu", entry)
            with open(path, "rb") as handle:
                digest = hashlib.sha256(handle.read()).hexdigest()
            entries.append({"path": path, "sha256": digest})
        out = os.path.join(self.repo.root, "out", "paths-only", "xnu-inputs.json")
        write(out, json.dumps({"patches": entries}))
        self.assertEqual(self.gate.stamp_path(), type(self.gate.REPO)(out))

    def test_an_unreadable_stamp_is_not_graded(self):
        out = os.path.join(self.repo.root, "out", "broken.json")
        write(out, "{not json")
        self.assertIsNone(self.gate.stamp_path())

    def test_the_real_repository_runs(self):
        gate = load_gate()
        self.assertGreater(len(gate.series_entries()), 100)


if __name__ == "__main__":
    unittest.main(verbosity=2)
