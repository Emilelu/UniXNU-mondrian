#!/usr/bin/env python3
"""Tests for the three tools that exist because of the 2026-11-14 incident.

  * scripts/snapshot-worktree.py  — must capture tracked + untracked + staged
  * scripts/git-safe.sh           — must refuse destructive git, snapshot first
  * scripts/check-tree-owner.py   — must fail in a tree that holds another
                                    actor's uncommitted work

Each test builds a throwaway git repository, so nothing here touches the real
tree or the real snapshot directory.

Run: python3 scripts/tests/test-worktree-safety.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "scripts/snapshot-worktree.py"
GIT_SAFE = ROOT / "scripts/git-safe.sh"
TREE_OWNER = ROOT / "scripts/check-tree-owner.py"

CASES = 0
FAILURES = 0


def check(condition: bool, label: str, detail: str = "") -> None:
    global CASES, FAILURES
    CASES += 1
    if condition:
        print(f"ok   {label}")
    else:
        FAILURES += 1
        print(f"FAIL {label}" + (f": {detail}" if detail else ""))


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )


def run(script: Path, repo: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    environment = {**os.environ, **(env or {})}
    if script.suffix == ".py":
        command = [sys.executable, str(script), *args]
    else:
        command = ["bash", str(script), *args]
    return subprocess.run(
        command, cwd=str(repo), capture_output=True, text=True, check=False,
        env=environment,
    )


def make_repo(root: Path) -> Path:
    repo = root / "work"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "test")
    (repo / "tracked.txt").write_text("original\n", encoding="utf-8")
    git(repo, "add", "tracked.txt")
    git(repo, "commit", "-q", "-m", "initial")
    return repo


def test_snapshot_git_safe(root: Path) -> None:
    repo = make_repo(root / "snapshot")
    snaps = root / "snaps"
    snaps.mkdir()

    # A tracked edit, a staged edit and an untracked file, all at once.
    (repo / "tracked.txt").write_text("edited\n", encoding="utf-8")
    (repo / "staged.txt").write_text("staged\n", encoding="utf-8")
    git(repo, "add", "staged.txt")
    (repo / "untracked/deep/file.txt").parent.mkdir(parents=True)
    (repo / "untracked/deep/file.txt").write_text("untracked body\n", encoding="utf-8")

    env = {"K60_SNAPSHOT_DIR": str(snaps)}
    result = run(SNAPSHOT, repo, "--repo", str(repo), env=env)
    check(result.returncode == 0, "snapshot exits 0", result.stderr.strip())
    dirs = sorted(p for p in snaps.iterdir() if p.is_dir())
    check(len(dirs) == 1, "snapshot writes exactly one directory", str(dirs))
    if not dirs:
        return
    snap = dirs[0]
    check((snap / "tracked.patch").read_text(encoding="utf-8").find("+edited") >= 0,
          "tracked.patch carries the tracked edit")
    check((snap / "staged.patch").read_text(encoding="utf-8").find("+staged") >= 0,
          "staged.patch carries the staged file")
    # The snapshot's `untracked/` root mirrors the repository, so a repo path of
    # `untracked/deep/file.txt` lands at `<snap>/untracked/untracked/deep/file.txt`.
    check((snap / "untracked/untracked/deep/file.txt").is_file(),
          "untracked/ preserves the nested path")
    check((snap / "restore.sh").is_file(), "restore.sh is written")
    check((snap / "HEAD.txt").is_file() and len((snap / "HEAD.txt").read_text().strip()) == 40,
          "HEAD.txt records the 40-char commit")
    check("tracked.txt" in (snap / "status.txt").read_text(encoding="utf-8"),
          "status.txt lists the changed path")

    # Restoring into a clean clone must reproduce the bytes exactly.
    clone = root / "snapshot" / "clone"
    subprocess.run(["git", "clone", "-q", str(repo), str(clone)], check=False,
                   capture_output=True)
    git(clone, "checkout", "-q", (snap / "HEAD.txt").read_text().strip())
    restore = subprocess.run(["bash", str(snap / "restore.sh")], cwd=str(clone),
                             capture_output=True, text=True, check=False)
    check(restore.returncode == 0, "restore.sh runs", restore.stderr.strip())
    check((clone / "tracked.txt").read_text(encoding="utf-8") == "edited\n",
          "restore reproduces the tracked edit")
    check((clone / "untracked/deep/file.txt").is_file(),
          "restore reproduces the untracked file")


def test_git_safe(root: Path) -> None:
    repo = make_repo(root / "safe")
    env = {"K60_SNAPSHOT_DIR": str(root / "snaps-safe")}
    (root / "snaps-safe").mkdir()

    for command in (["checkout", "--", "tracked.txt"], ["restore", "."],
                    ["reset", "--hard", "HEAD"], ["clean", "-fd"], ["stash"],
                    ["checkout", "-f", "main"]):
        refused = run(GIT_SAFE, repo, *command, env=env)
        check(refused.returncode == 2, f"git-safe refuses {' '.join(command)}",
              f"rc={refused.returncode}")

    allowed = run(GIT_SAFE, repo, "status", "--porcelain", env=env)
    check(allowed.returncode == 0, "git-safe allows read-only git")

    # Ownership override must still snapshot first.
    (repo / "tracked.txt").write_text("doomed\n", encoding="utf-8")
    owned = run(GIT_SAFE, repo, "checkout", "--", "tracked.txt",
                env={**env, "K60_I_OWN_THIS_TREE": "1"})
    check(owned.returncode == 0, "git-safe allows a destructive command when the tree is owned",
          owned.stderr.strip())
    check((repo / "tracked.txt").read_text(encoding="utf-8") == "original\n",
          "the owned destructive command really discarded the edit")
    snaps = [p for p in (root / "snaps-safe").iterdir() if p.is_dir()]
    check(len(snaps) == 1, "a snapshot was taken before the discard", str(snaps))
    if snaps:
        check("+doomed" in (snaps[0] / "tracked.patch").read_text(encoding="utf-8"),
              "the discarded edit is recoverable from the snapshot")


def test_tree_owner(root: Path) -> None:
    repo = make_repo(root / "owner")
    owners = repo / "docs/engineering"
    owners.mkdir(parents=True)
    (owners / "TREE-OWNERS.toml").write_text(
        f'[[tree]]\npath = "{repo.as_posix()}"\nowner = "somebody-else"\n', encoding="utf-8"
    )
    # The gate resolves its own repo from __file__, so run a copy placed inside.
    (repo / "scripts").mkdir()
    shutil.copy2(TREE_OWNER, repo / "scripts/check-tree-owner.py")
    # Commit the scaffolding, otherwise the tree is already dirty before the test
    # means it to be.
    git(repo, "add", "docs", "scripts")
    git(repo, "commit", "-q", "-m", "scaffolding")

    clean = run(repo / "scripts/check-tree-owner.py", repo, env={"K60_AGENT_ID": "lead"})
    check(clean.returncode == 0, "a clean foreign tree is allowed",
          clean.stdout.strip() + clean.stderr.strip())
    (repo / "dirty.txt").write_text("mine\n", encoding="utf-8")
    dirty = run(repo / "scripts/check-tree-owner.py", repo, env={"K60_AGENT_ID": "lead"})
    check(dirty.returncode == 1, "a dirty foreign tree is refused",
          f"rc={dirty.returncode}")
    check("somebody-else" in (dirty.stdout + dirty.stderr),
          "the refusal names the owner")

    own = run(repo / "scripts/check-tree-owner.py", repo, env={"K60_AGENT_ID": "somebody-else"})
    check(own.returncode == 0, "the owner may be dirty in its own tree", own.stdout.strip())


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="k60-worktree-safety-"))
    try:
        test_snapshot_git_safe(root)
        test_git_safe(root)
        test_tree_owner(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print(f"\nTESTS {'OK' if not FAILURES else 'FAILED'} {CASES} case(s) ({FAILURES} failure(s))")
    return 0 if FAILURES == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
