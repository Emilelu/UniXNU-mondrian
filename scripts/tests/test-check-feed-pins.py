#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Cases for check-feed-pins.py.

The gate compares feeds.toml with a real checkout, so each case builds a tiny
git repository at the exact path the framework would use.  The cases pin the
three outcomes that matter: a matching pin passes, drift is red, and an absent
pin or checkout is "cannot judge" (exit 2), never a permanent red.
"""

import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE.parent / "check-feed-pins.py"
PIN = "20a30fd623dbcfacdd71350a24fae67a2158884f"
URL = "https://github.com/xNekom/UniXNU-sm8475-common"


def load_gate():
    spec = importlib.util.spec_from_file_location("k60_feed_pins", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(cwd, *args):
    env = dict(os.environ)
    env.setdefault("GIT_AUTHOR_NAME", "test")
    env.setdefault("GIT_AUTHOR_EMAIL", "test@example.com")
    env.setdefault("GIT_COMMITTER_NAME", "test")
    env.setdefault("GIT_COMMITTER_EMAIL", "test@example.com")
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=env)


def head(path):
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="feed-pins-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.gate = load_gate()
        self.feeds = self.tmp / "feeds.toml"
        self.feeds_dir = self.tmp / "out" / "feeds"
        self.feeds_dir.mkdir(parents=True)

    def write_feeds(self, commit=PIN):
        line = 'commit = "%s"\n' % commit if commit is not None else ""
        self.feeds.write_text(
            '[[source]]\nname = "sm8475"\nkind = "soc"\ngit = "%s"\n%s'
            % (URL, line),
            encoding="utf-8",
        )

    def make_repo(self, remote=URL, with_origin=True):
        src = self.tmp / "repo"
        src.mkdir()
        git(src, "init", "-q")
        (src / "file.txt").write_text("one\n")
        git(src, "add", ".")
        git(src, "commit", "-q", "-m", "first")
        if with_origin:
            git(src, "remote", "add", "origin", remote)
        return head(src), src

    def place(self, pin, src):
        dest = self.gate.clone_dir(self.feeds_dir, URL, pin)
        shutil.move(str(src), str(dest))
        return dest

    def run_gate(self):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.gate.main(["--feeds", str(self.feeds),
                                   "--feeds-dir", str(self.feeds_dir)])
        return code, out.getvalue(), err.getvalue()


class Outcomes(Fixture):
    def test_clone_dir_matches_the_framework_formula(self):
        path = self.gate.clone_dir(Path("/feeds"), URL, PIN)
        self.assertEqual(path.name, "UniXNU-sm8475-common-6ebb3d7f")

    def test_a_matching_pin_passes(self):
        pin, src = self.make_repo()
        self.write_feeds(pin)
        self.place(pin, src)
        code, out, err = self.run_gate()
        self.assertEqual(code, 0)
        self.assertIn("PASS sm8475", out)
        self.assertIn("✅ feed pins", out)
        self.assertEqual(err, "")

    def test_drift_is_red_and_names_both_commits(self):
        pin, src = self.make_repo()
        self.write_feeds(pin)
        dest = self.place(pin, src)
        (dest / "file.txt").write_text("two\n")
        git(dest, "commit", "-q", "-am", "second")
        actual = head(dest)
        self.assertNotEqual(actual, pin)
        code, out, err = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn("FAIL sm8475", err)
        self.assertIn(pin, err)
        self.assertIn(actual, err)
        self.assertNotIn("✅ feed pins", out)

    def test_a_missing_pin_is_cannot_judge(self):
        self.write_feeds(commit=None)
        code, out, err = self.run_gate()
        self.assertEqual(code, 2)
        self.assertIn("UNJUDGED sm8475", err)
        self.assertIn("no commit pin", err)
        self.assertNotIn("PASS", out)
        self.assertNotIn("✅ feed pins", out)

    def test_a_missing_checkout_is_cannot_judge(self):
        self.write_feeds()
        code, out, err = self.run_gate()
        self.assertEqual(code, 2)
        self.assertIn("UNJUDGED sm8475", err)
        self.assertIn("run unixnu fetch", err)
        self.assertNotIn("✅ feed pins", out)

    def test_a_short_pin_is_cannot_judge(self):
        self.write_feeds(commit="20a30fd6")
        code, _, err = self.run_gate()
        self.assertEqual(code, 2)
        self.assertIn("not a 40-character sha", err)

    def test_a_repo_without_origin_is_cannot_judge(self):
        pin, src = self.make_repo(with_origin=False)
        self.write_feeds(pin)
        self.place(pin, src)
        code, out, err = self.run_gate()
        self.assertEqual(code, 2)
        self.assertIn("UNJUDGED sm8475", err)
        self.assertIn("has no origin", err)
        self.assertNotIn("PASS", out)

    def test_another_origin_is_red(self):
        pin, src = self.make_repo(remote="https://github.com/Emilelu/UniXNU-sm8475-common")
        self.write_feeds(pin)
        self.place(pin, src)
        code, _, err = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn("has origin", err)
        self.assertIn("feeds.toml names", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
