#!/usr/bin/env python3
"""Tests for scripts/repair-worktrees.py — the P-203 worktree restore path.

Each case builds a throwaway main checkout with linked worktrees beside it, so
nothing here touches the real trees. A prune accident is simulated by deleting
the admin directory directly: the script under test never runs a pruning verb,
and neither does this test.

Run: python3 scripts/tests/test-repair-worktrees.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPAIR = ROOT / "scripts/repair-worktrees.py"

CASES = 0
FAILURES = 0


def check(condition: bool, label: str, detail: str = "") -> None:
    global CASES, FAILURES
    CASES += 1
    if condition:
        print("ok   " + label)
    else:
        FAILURES += 1
        print("FAIL " + label + (": " + detail if detail else ""))


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=False)


def run(worktree: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(REPAIR), *args],
                          capture_output=True, text=True, check=False,
                          env={**os.environ, "K60_REPO": str(worktree)})


def make_main(root: Path) -> Path:
    """A main checkout with two tracked files, committed on main."""
    main = root / "hackios" / "UniXNU-mondrian"
    main.mkdir(parents=True)
    git(main, "init", "-q", "-b", "main")
    git(main, "config", "user.email", "test@example.com")
    git(main, "config", "user.name", "test")
    (main / "base.txt").write_text("base\n", encoding="utf-8")
    (main / "topic.txt").write_text("main\n", encoding="utf-8")
    git(main, "add", "base.txt", "topic.txt")
    git(main, "commit", "-q", "-m", "initial")
    return main


def add_worktree(main: Path, name: str, branch: str, topic: str) -> Path:
    worktree = main.parent / name
    git(main, "worktree", "add", "-q", "-b", branch, str(worktree))
    (worktree / "topic.txt").write_text(topic + "\n", encoding="utf-8")
    git(worktree, "add", "topic.txt")
    git(worktree, "commit", "-q", "-m", topic)
    return worktree


def break_admin(main: Path, name: str) -> None:
    shutil.rmtree(main / ".git/worktrees" / name, ignore_errors=True)


def write_pointer(worktree: Path, text: str) -> None:
    """Windows marks a worktree .git file hidden, and writing one in place is refused."""
    pointer = worktree / ".git"
    if pointer.exists():
        os.remove(pointer)
    pointer.write_text(text, encoding="utf-8")


def test_recovers_a_deleted_admin_directory(root: Path) -> None:
    main = make_main(root / "deleted")
    worktree = add_worktree(main, "k60-demo", "feat/demo", "demo")
    (worktree / "base.txt").write_text("edited in the tree\n", encoding="utf-8")
    (worktree / "scratch.txt").write_text("untracked\n", encoding="utf-8")
    before = (worktree / "base.txt").read_text(encoding="utf-8")

    break_admin(main, "k60-demo")
    check(not (main / ".git/worktrees/k60-demo").exists(), "the admin directory really is gone")
    check(git(worktree, "rev-parse", "--git-dir").returncode != 0,
          "a tree without its admin directory cannot resolve a repository")

    repaired = run(main)
    check(repaired.returncode == 0, "repair exits 0", repaired.stdout + repaired.stderr)
    check("fixed   k60-demo: restored feat/demo" in repaired.stdout,
          "the report names the restored branch", repaired.stdout)

    branch = git(worktree, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    check(branch == "feat/demo", "the branch is recovered from the file contents", branch)
    check((worktree / "base.txt").read_text(encoding="utf-8") == before,
          "the uncommitted edit survived byte for byte")
    check((worktree / "scratch.txt").is_file(), "the untracked file survived")
    status = git(worktree, "status", "--porcelain").stdout
    check("base.txt" in status and "scratch.txt" in status,
          "the restored index shows exactly the uncommitted work", status)
    listed = git(main, "worktree", "list", "--porcelain").stdout
    check(str(worktree) in listed and "prunable" not in listed,
          "git worktree list has the tree back and calls nothing prunable", listed)


def test_picks_the_right_branch_among_several(root: Path) -> None:
    main = make_main(root / "several")
    first = add_worktree(main, "k60-a", "feat/a", "alpha")
    second = add_worktree(main, "k60-b", "feat/b", "beta")
    break_admin(main, "k60-a")
    break_admin(main, "k60-b")

    repaired = run(main)
    check(repaired.returncode == 0, "repair exits 0 for both trees", repaired.stdout + repaired.stderr)
    check(git(first, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feat/a",
          "the first tree is matched to feat/a")
    check(git(second, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feat/b",
          "the second tree is matched to feat/b")
    check(git(first, "status", "--porcelain").stdout.strip() == "",
          "the first tree comes back clean", git(first, "status", "--porcelain").stdout)


def test_admin_directory_that_does_not_resolve(root: Path) -> None:
    main = make_main(root / "stale")
    worktree = add_worktree(main, "k60-stale", "feat/stale", "stale")
    admin = main / ".git/worktrees/k60-stale"
    (admin / "HEAD").write_text("ref: refs/heads/feat/deleted-long-ago\n", encoding="utf-8")
    (admin / "gitdir").write_text("nowhere/.git\n", encoding="utf-8")
    check(git(worktree, "rev-parse", "--verify", "HEAD").returncode != 0,
          "the stale admin HEAD names no commit, so the tree does not resolve a branch")

    repaired = run(main)
    check(repaired.returncode == 0, "repair exits 0", repaired.stdout + repaired.stderr)
    check(git(worktree, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feat/stale",
          "a dead admin HEAD is replaced by the matched branch")
    check(git(worktree, "status", "--porcelain").stdout.strip() == "",
          "the tree comes back clean")


def test_check_mode_is_read_only(root: Path) -> None:
    main = make_main(root / "check")
    worktree = add_worktree(main, "k60-readonly", "feat/ro", "ro")
    break_admin(main, "k60-readonly")

    checked = run(main, "--check")
    check(checked.returncode == 1, "check exits 1 while a tree is broken", checked.stdout)
    check("BROKEN  k60-readonly" in checked.stdout, "check names the broken tree", checked.stdout)
    check(not (main / ".git/worktrees/k60-readonly").exists(), "check wrote nothing")
    check(git(worktree, "rev-parse", "--git-dir").returncode != 0,
          "the tree is still broken after check")


def test_dry_run_writes_nothing(root: Path) -> None:
    main = make_main(root / "dry")
    add_worktree(main, "k60-dry", "feat/dry", "dry")
    break_admin(main, "k60-dry")

    dried = run(main, "--dry-run")
    check(dried.returncode == 0, "dry-run exits 0", dried.stdout + dried.stderr)
    check("dry     k60-dry: would restore feat/dry" in dried.stdout,
          "dry-run says what it would restore", dried.stdout)
    check(not (main / ".git/worktrees/k60-dry").exists(), "dry-run wrote nothing")


def test_healthy_tree_is_left_alone(root: Path) -> None:
    main = make_main(root / "healthy")
    worktree = add_worktree(main, "k60-ok", "feat/ok", "ok")
    head_before = git(worktree, "rev-parse", "HEAD").stdout.strip()
    admin_before = (main / ".git/worktrees/k60-ok/HEAD").read_text(encoding="utf-8")

    first = run(main)
    second = run(main)
    check(first.returncode == 0 and second.returncode == 0, "both runs exit 0",
          first.stdout + second.stdout)
    check("ok      k60-ok: feat/ok" in second.stdout, "a healthy tree is reported ok", second.stdout)
    check("0 broken, 0 repaired" in second.stdout, "a healthy tree is not repaired", second.stdout)
    check((main / ".git/worktrees/k60-ok/HEAD").read_text(encoding="utf-8") == admin_before,
          "the admin HEAD is untouched")
    check(git(worktree, "rev-parse", "HEAD").stdout.strip() == head_before,
          "HEAD is untouched")


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="k60-repair-worktrees-"))
    try:
        test_recovers_a_deleted_admin_directory(root)
        test_picks_the_right_branch_among_several(root)
        test_admin_directory_that_does_not_resolve(root)
        test_check_mode_is_read_only(root)
        test_dry_run_writes_nothing(root)
        test_healthy_tree_is_left_alone(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print("\nTESTS {} {} case(s) ({} failure(s))".format(
        "OK" if not FAILURES else "FAILED", CASES, FAILURES))
    return 0 if FAILURES == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
