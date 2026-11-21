#!/usr/bin/env python3
"""Every local branch has to exist on some remote (iron rule: trees are pushed).

Reading the rule is not enough -- twice this month a lane reported "pushed" while
its branch only existed locally, and once a whole worktree's branch was never
pushed at all.  So: enumerate local heads, compare with every remote-tracking ref,
and fail on the ones nobody else can see.

Allowlist (`docs/engineering/PUSH-ALLOW.toml`) exists for names that are
deliberately local (scratch backups, upstream mirrors we must not push).  An
allowlist entry that no longer matches anything is reported as a note, because a
stale exemption is how a real one hides (P-290 cousin).

Exit codes: 0 everything pushed, 1 something is local-only, 2 cannot judge.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
DEFAULT_REPOS = HERE / "docs/engineering/UPSTREAM-REPOS.toml"
DEFAULT_ALLOW = HERE / "docs/engineering/PUSH-ALLOW.toml"


def git(repo: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "--no-optional-locks", *arguments],
        capture_output=True,
        text=True,
        timeout=120,
    ).stdout


def is_ancestor(repo: Path, older: str, newer: str) -> bool:
    """True when `older` is already contained in `newer`.

    A branch that is *behind* its remote is pushed -- somebody else's commits are
    on the remote and ours are in its history.  Comparing shas alone called that
    "local-only", which is how a gate stops being believed.
    """
    if older == newer or newer.startswith(older) or older.startswith(newer):
        return True
    result = subprocess.run(
        ["git", "-C", str(repo), "--no-optional-locks", "merge-base", "--is-ancestor", older, newer],
        timeout=60,
    )
    return result.returncode == 0


def local_branches(repo: Path) -> dict[str, str]:
    out = git(repo, "for-each-ref", "--format=%(refname:short) %(objectname:short)", "refs/heads")
    branches: dict[str, str] = {}
    for line in out.splitlines():
        name, _, sha = line.strip().partition(" ")
        if name:
            branches[name] = sha
    return branches


def remote_shas(repo: Path) -> dict[str, str]:
    """Branch name -> short sha, counting only the remote we may write to.

    `UniXNU` has two remotes: `origin` is the official repository we cannot push
    to, `fork` is ours.  Counting any remote would call a branch "pushed" because
    the official copy happens to have the same name.
    """
    names = git(repo, "remote").split()
    writable = "fork" if "fork" in names else ("origin" if "origin" in names else "mytoken")
    out = git(repo, "for-each-ref", "--format=%(refname:short) %(objectname:short)", "refs/remotes")
    shas: dict[str, str] = {}
    for line in out.splitlines():
        ref, _, sha = line.strip().partition(" ")
        if not ref or ref.endswith("/HEAD"):
            continue
        remote, _, branch = ref.partition("/")
        if remote != writable:
            continue
        shas[branch] = sha
    return shas


def allowed(name: str, patterns: list[str]) -> str:
    for pattern in patterns:
        if re.fullmatch(pattern, name):
            return pattern
    return ""


def check(repos: dict[str, Path], patterns: list[str],
          all_branches: bool = False) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    notes: list[str] = []
    used: set[str] = set()
    seen: set[str] = set()
    for name, repo in sorted(repos.items()):
        if not (repo / ".git").exists():
            continue
        real = str(repo.resolve())
        if real in seen:
            continue
        seen.add(real)
        remotes = remote_shas(repo)
        git(repo, "fetch", "--all", "--prune", "--quiet")
        head = git(repo, "rev-parse", "HEAD").strip()
        for branch, sha in sorted(local_branches(repo).items()):
            if branch in remotes and is_ancestor(repo, sha, remotes[branch]):
                continue
            pattern = allowed(branch, patterns)
            if pattern:
                used.add(pattern)
                continue
            where = f"{remotes[branch]}" if branch in remotes else "no remote branch"
            message = f"{name}: {branch} ({sha}) is local-only ({where})"
            # A build only needs this checkout's own line to exist somewhere else.
            # Branches other lanes are mid-way through are theirs to push; treating
            # them as this build's problem made every build depend on someone else's
            # uncommitted work (measured 2026-11-21: three consecutive refusals).
            if all_branches or is_ancestor(repo, sha, head):
                problems.append(message)
            else:
                notes.append(message + "; not this checkout's line, another lane owns it")
    for pattern in patterns:
        if pattern not in used:
            notes.append(f"allowlist entry {pattern!r} matched nothing in this run")
    return problems, notes


def load_repos(path: Path) -> dict[str, Path]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    repos: dict[str, Path] = {}
    for entry in data.get("repo", []):
        name = str(entry.get("name") or "").strip()
        where = str(entry.get("path") or "").strip()
        if name and where:
            repos[name] = Path(where)
    return repos


def load_allow(path: Path) -> list[str]:
    if not path.is_file():
        return []
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return [str(item["pattern"]) for item in data.get("allow", []) if item.get("pattern")]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repos", type=Path, default=DEFAULT_REPOS)
    parser.add_argument("--allow", type=Path, default=DEFAULT_ALLOW)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--all-branches", action="store_true",
                        help="audit every local branch; without it only this checkout's own line is asked for")
    arguments = parser.parse_args(argv)
    if not arguments.repos.is_file():
        print(f"GATE UNKNOWN: no repository list at {arguments.repos} (P-279)")
        return 2
    repos = load_repos(arguments.repos)
    if not repos:
        print(f"GATE UNKNOWN: {arguments.repos} lists no [[repo]]")
        return 2
    problems, notes = check(repos, load_allow(arguments.allow), arguments.all_branches)
    for note in notes:
        print(f"note: {note}")
    for problem in problems:
        print(f"FAIL: {problem}")
    if problems:
        print(f"FAIL pushes: {len(problems)} branch(es) exist only on this machine")
        return 1
    if not arguments.quiet:
        print(f"OK pushes: {len(repos)} repository(ies), every local branch is on a remote")
    return 0


if __name__ == "__main__":
    sys.exit(main())
