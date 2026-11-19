#!/usr/bin/env python3
"""Run both P-258 regressions: linked-worktree refusal and WSL-visible gitdir."""
import os
import pathlib
import subprocess
import sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}
for name in ("test-git-guard-worktree-prune.py", "test-repair-worktrees-relative-gitdir.py"):
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "tests" / name)],
                            cwd=ROOT, env=ENV)
    if result.returncode:
        raise SystemExit(result.returncode)
print("P-258: both linked-worktree regressions passed")
