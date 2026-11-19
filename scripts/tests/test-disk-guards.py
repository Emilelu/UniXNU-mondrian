#!/usr/bin/env python3
"""The janitor must delete the right things and refuse the dangerous ones.

Both scripts are guards against a failure that already happened once (181.8 GB of
virtual disk on 2026-11-19), so the tests here are about their refusals, not their
happy path: a guard that cannot say no is the shape P-242 names.

Cases:
  1. the janitor keeps the newest N outputs of a prefix even when every one of
     them is old -- a line that has been idle for a week may still need the output
     it last produced to answer a question;
  2. it never deletes a /tmp symlink, because /tmp/k60build and /tmp/fakeroot point
     into build trees and removing the link breaks a shim silently;
  3. it leaves the mirrors alone (k60build, gates-device) even when they look like
     the oldest and largest thing in the directory;
  4. `--apply` removes what the dry run listed, and the dry run removes nothing;
  5. a tree that a /tmp symlink points at survives, because deleting it breaks the
     shim just as silently as deleting the link would.
"""
import io
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest

REPO = pathlib.Path(os.environ.get("K60_REPO") or pathlib.Path(__file__).resolve().parents[2])
JANITOR = REPO / "scripts" / "k60-janitor.py"
PYTHON = sys.executable


def run(script, *args, env=None):
    merged = dict(os.environ)
    merged.update(env or {})
    return subprocess.run([PYTHON, str(script)] + list(args), capture_output=True, text=True, env=merged)


def age(path, days):
    stamp = time.time() - days * 86400.0
    os.utime(path, (stamp, stamp))


class Janitor(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="k60-janitor-")
        self.trees = os.path.join(self.root, "trees")
        self.tmp = os.path.join(self.root, "tmp")
        os.makedirs(self.trees)
        os.makedirs(self.tmp)

    def tree(self, name, megabytes=1, days_old=10):
        path = os.path.join(self.trees, name)
        os.makedirs(path)
        with open(os.path.join(path, "blob.bin"), "wb") as handle:
            handle.write(b"x" * (megabytes * 1024))
        age(path, days_old)
        return path

    def test_newest_outputs_survive_even_when_old(self):
        for suffix, days in (("1", 9), ("2", 8), ("3", 7)):
            self.tree("power-battery-2026010%s" % suffix, days_old=days)
        result = run(JANITOR, "--trees", self.trees, "--tmp", self.tmp, "--keep", "2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("power-battery-20260101", result.stdout, "the oldest beyond the keep count must be listed")
        self.assertNotIn("power-battery-20260102", result.stdout, "the newest two must survive")
        self.assertEqual(len(os.listdir(self.trees)), 3, "a dry run deletes nothing")

    def test_apply_removes_exactly_what_it_listed(self):
        for suffix, days in (("1", 9), ("2", 8), ("3", 7)):
            self.tree("display-2026010%s" % suffix, days_old=days)
        dry = run(JANITOR, "--trees", self.trees, "--tmp", self.tmp, "--keep", "1")
        listed = [line.split()[-1] for line in dry.stdout.splitlines() if "display-2026010" in line]
        applied = run(JANITOR, "--trees", self.trees, "--tmp", self.tmp, "--keep", "1", "--apply")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        remaining = sorted(os.listdir(self.trees))
        self.assertEqual(len(remaining), 1, remaining)
        for path in listed:
            self.assertFalse(os.path.exists(path), "%s was listed and must be gone" % path)

    def test_symlink_in_tmp_is_never_removed(self):
        target = self.tree("mirror-20260101a", days_old=30)
        link = os.path.join(self.tmp, "k60build")
        os.symlink(target, link)
        age(link, 30)
        result = run(JANITOR, "--trees", self.trees, "--tmp", self.tmp, "--apply", "--keep", "0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.path.islink(link), "the symlink must survive")
        self.assertTrue(os.path.isdir(target), "and so must its target")

    def test_mirrors_are_not_outputs(self):
        for name in ("k60build", "gates-device"):
            path = os.path.join(self.trees, name)
            os.makedirs(path)
            open(os.path.join(path, "keep"), "w").close()
            age(path, 40)
        result = run(JANITOR, "--trees", self.trees, "--tmp", self.tmp, "--apply", "--keep", "0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(os.listdir(self.trees)), ["gates-device", "k60build"])

    def test_young_outputs_stay(self):
        self.tree("gpu-20261119a", days_old=0.1)
        self.tree("gpu-20261118b", days_old=0.2)
        result = run(JANITOR, "--trees", self.trees, "--tmp", self.tmp, "--apply", "--keep", "0", "--days", "3")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(os.listdir(self.trees)), 2, "nothing younger than --days is touched")


if __name__ == "__main__":
    unittest.main(verbosity=2)
