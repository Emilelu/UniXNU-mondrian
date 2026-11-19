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
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False,
        encoding="utf-8", errors="replace",
    )


_BASH_FORM: str | None = None


def _bash_forms(path: Path) -> dict[str, str]:
    posix = path.resolve().as_posix()
    drive = posix[0].lower()
    return {
        "native": posix,
        "msys": "/" + drive + posix[2:],
        "wsl": "/mnt/" + drive + posix[2:],
    }


def _bash_form() -> str:
    """Which spelling of a Windows path this host's bash can actually open.

    There is no single answer: MSYS bash wants "/e/x", the DSH winuxcmd shim
    forwards argv untouched to a Linux bash and therefore wants "/mnt/e/x", and
    a path that is already POSIX loses its backslashes on the way through.
    Probe once with the real script and remember the spelling that works.
    """
    global _BASH_FORM
    if _BASH_FORM:
        return _BASH_FORM
    if os.name != "nt":
        _BASH_FORM = "native"
        return _BASH_FORM
    # Statting is not a usable probe: some shims translate the path for
    # test(1) but hand the same string to bash unchanged. Run the real script
    # with a read-only verb instead - 127 means this spelling cannot be opened.
    for form, candidate in _bash_forms(GIT_SAFE).items():
        probe = subprocess.run(["bash", candidate, "rev-parse", "--git-dir"],
                               cwd=str(ROOT), capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
        if probe.returncode != 127 and "No such file" not in (probe.stderr or ""):
            _BASH_FORM = form
            return form
    _BASH_FORM = "native"
    return _BASH_FORM


def bash_path(script: Path) -> str:
    return _bash_forms(script)[_bash_form()]
    posix = script.resolve().as_posix()
    return "/" + posix[0].lower() + posix[2:]


def run(script: Path, repo: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8", **(env or {})}
    if script.suffix != ".py" and _bash_form() == "wsl":
        # A bash that forwards to WSL only passes through the variables listed
        # in WSLENV, so K60_I_OWN_THIS_TREE / K60_SNAPSHOT_DIR would vanish and
        # every ownership case would look refused.
        forward = "K60_SNAPSHOT_DIR/p:K60_I_OWN_THIS_TREE:K60_AGENT_ID:PYTHONIOENCODING"
        environment["WSLENV"] = (environment.get("WSLENV", "") + ":" + forward).lstrip(":")
    if script.suffix == ".py":
        command = [sys.executable, str(script), *args]
    else:
        command = ["bash", bash_path(script), *args]
    return subprocess.run(
        command, cwd=str(repo), capture_output=True, text=True, check=False,
        env=environment, encoding="utf-8", errors="replace",
    )


def make_repo(root: Path) -> Path:
    repo = root / "work"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "test")
    # Windows text mode turns \n into \r\n; a CRLF payload makes the snapshot's
    # patch unappliable in the clone, and git's own autocrlf rewrites the
    # checkout under the fixture's feet. Pin both (P-184: the fixture broke).
    git(repo, "config", "core.autocrlf", "false")
    (repo / "tracked.txt").write_text("original\n", encoding="utf-8", newline="\n")
    git(repo, "add", "tracked.txt")
    git(repo, "commit", "-q", "-m", "initial")
    return repo


def test_snapshot_git_safe(root: Path) -> None:
    repo = make_repo(root / "snapshot")
    snaps = root / "snaps"
    snaps.mkdir()

    # A tracked edit, a staged edit and an untracked file, all at once.
    (repo / "tracked.txt").write_text("edited\n", encoding="utf-8", newline="\n")
    (repo / "staged.txt").write_text("staged\n", encoding="utf-8", newline="\n")
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
    check("\r" not in (snap / "restore.sh").read_bytes().decode("utf-8"),
          "restore.sh stays LF-only so bash can read it on any host")
    check("\r" not in (snap / "HEAD.txt").read_bytes().decode("utf-8"),
          "HEAD.txt stays LF-only so git checkout sees a real revision")
    check((snap / "HEAD.txt").is_file() and len((snap / "HEAD.txt").read_text().strip()) == 40,
          "HEAD.txt records the 40-char commit")
    check("tracked.txt" in (snap / "status.txt").read_text(encoding="utf-8"),
          "status.txt lists the changed path")

    # Restoring into a clean clone must reproduce the bytes exactly.
    clone = root / "snapshot" / "clone"
    subprocess.run(["git", "clone", "-q", str(repo), str(clone)], check=False,
                   capture_output=True)
    git(clone, "checkout", "-q", (snap / "HEAD.txt").read_text().strip())
    restore = subprocess.run(["bash", bash_path(snap / "restore.sh")], cwd=str(clone),
                             capture_output=True, text=True, check=False,
                             encoding="utf-8", errors="replace")
    check(restore.returncode == 0, "restore.sh runs", restore.stderr.strip())
    # Compare after normalising line endings: on drvfs the clone is written by
    # one host's git and patched by the other's, so an all-LF payload can arrive
    # as CRLF. The snapshot's content is what this case is about.
    restored = (clone / "tracked.txt").read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
    check(restored == "edited\n", "restore reproduces the tracked edit", repr(restored[:40]))
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
    (repo / "tracked.txt").write_text("doomed\n", encoding="utf-8", newline="\n")
    owned = run(GIT_SAFE, repo, "checkout", "--", "tracked.txt",
                env={**env, "K60_I_OWN_THIS_TREE": "1"})
    check(owned.returncode == 0, "git-safe allows a destructive command when the tree is owned",
          owned.stderr.strip())
    check((repo / "tracked.txt").read_text(encoding="utf-8") == "original\n",
          "the owned destructive command really discarded the edit")
    # More than one directory is legitimate: the system-wide git guard
    # (/usr/local/bin/git) snapshots a dirty tree too, and in this throwaway repo
    # it cannot find scripts/snapshot-worktree.py, so it writes its own
    # "<stamp>-<repo>-fallback" copy. Two snapshots are the guard doing its job.
    # The invariant is that the edit is recoverable and one snapshot restores.
    snaps = sorted(p for p in (root / "snaps-safe").iterdir() if p.is_dir())
    check(len(snaps) >= 1, "a snapshot was taken before the discard", str(snaps))
    carrying = [p for p in snaps
                if (p / "tracked.patch").is_file()
                and "+doomed" in (p / "tracked.patch").read_text(encoding="utf-8")]
    check(bool(carrying), "the discarded edit is recoverable from the snapshot", str(snaps))
    check(any((p / "restore.sh").is_file() for p in snaps),
          "the snapshot the tool took carries restore.sh", str(snaps))


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
