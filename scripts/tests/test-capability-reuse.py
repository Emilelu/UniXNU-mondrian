#!/usr/bin/env python3
"""Tests for scripts/check-capability-reuse.py (P-324 / iron-20).

A fixture repository has one IOBlockStorageDevice subclass on main; a feature
branch adds another one. The check must fail the branch, and must pass once the
capability ledger records a reuse decision.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check-capability-reuse.py"


def run(repo: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, K60_REPO=str(repo))
    return subprocess.run(["python3", str(SCRIPT), "--base", "main"],
                          cwd=repo, env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> int:
    with tempfile.TemporaryDirectory() as folder:
        repo = Path(folder)
        git(repo, "init", "-q", "-b", "main")
        git(repo, "config", "user.email", "test@example.invalid")
        git(repo, "config", "user.name", "test")
        (repo / "drivers/Old").mkdir(parents=True)
        (repo / "drivers/Old/Old.cpp").write_text(
            "class OldBlock : public IOBlockStorageDevice { };\n", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "main adds the first block driver")
        git(repo, "checkout", "-q", "-b", "feat/repeat")

        (repo / "drivers/New").mkdir()
        (repo / "drivers/New/New.cpp").write_text(
            "class NewBlock : public IOBlockStorageDevice { };\n", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "branch repeats the block driver")

        failed = run(repo)
        assert failed.returncode == 1, failed.stdout
        assert "FAIL capability-reuse" in failed.stdout, failed.stdout
        assert "drivers/Old/Old.cpp" in failed.stdout, failed.stdout

        (repo / "docs/engineering").mkdir(parents=True)
        (repo / "docs/engineering/CAPABILITY-REUSE.toml").write_text(
            '[[decision]]\nbase = "IOBlockStorageDevice"\nverdict = "reuse"\n'
            'implementations = ["drivers/Old/Old.cpp"]\nevidence = "test fixture"\n',
            encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "record the reuse decision")

        passed = run(repo)
        assert passed.returncode == 0, passed.stdout
        assert "OK capability-reuse" in passed.stdout, passed.stdout
    print("TESTS OK capability-reuse fixture accepted and rejected as designed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
