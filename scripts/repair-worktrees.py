#!/usr/bin/env python3
"""repair-worktrees.py — rebuild the admin directory of a linked worktree (P-203).

Why this exists
===============
"git worktree prune" decides what to drop from the *main* checkout's
.git/worktrees/, but it can be run from anywhere. Run inside a linked
worktree it deletes every admin directory it can no longer resolve, and the
worktree keeps a .git file that points at nothing:

    fatal: gitfile does not point to a valid repository: E:/hackios/k60-bt/.git

"git worktree add" will not rebuild the entry (the path already exists), and
"git worktree prune" only makes it worse. On 2026-11-15 one such command took
nineteen trees down at once (P-203).

Restoring a tree by hand is four steps: name the branch it was on, rebuild
.git/worktrees/<name>/{HEAD,gitdir,commondir}, rebuild the index, verify.
This script does that for every tree it finds broken. The branch is recovered
by matching the files that are in the worktree against the blobs of every
branch — a tree carrying uncommitted work still matches the branch it came
from on the files it never touched.

It also rewrites the Windows path forms that "git worktree add" writes when it
runs from PowerShell; that half is what scripts/repair-worktrees.sh did.

Safety
======
* it never deletes anything and never runs a pruning verb;
* it never runs "git checkout" — "git read-tree" rebuilds the index and leaves
  uncommitted files exactly as they were;
* it only adopts a broken sibling directory whose .git file still points into
  this main checkout (or that git itself lists), so another repository's
  worktree is never rewritten by mistake;
* a tree that already resolves is reported and left untouched;
* --check is read-only, so a gate can call it.

Usage
=====
    python3 scripts/repair-worktrees.py                 # repair everything broken
    python3 scripts/repair-worktrees.py --check         # exit 1 if anything is broken
    python3 scripts/repair-worktrees.py --dry-run       # say what would change
    python3 scripts/repair-worktrees.py --main DIR      # another main checkout
    python3 scripts/repair-worktrees.py --worktree DIR  # one tree outside the parent dir

The main checkout is --main, else the repository this script lives in, else
K60_REPO (hard-39: never a literal checkout path).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

SKIP_PREFIXES = ("archive/", "backup/")
SAMPLE_FILES = 40
SHORTLIST = 3


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=False)


def write_pointer(path: Path, text: str) -> None:
    """Write a .git pointer file.

    Windows marks these files hidden, and the C runtime refuses to open a
    hidden file for writing, so a plain write fails with EACCES. Removing it
    first works, and a pointer file is ours to replace.
    """
    if path.exists():
        try:
            os.remove(path)
        except OSError:
            os.chmod(path, 0o666)
            os.remove(path)
    path.write_text(text, encoding="utf-8")


def repo_root() -> Path:
    return Path(os.environ.get("K60_REPO") or Path(__file__).resolve().parents[1])


def main_checkout(repo: Path) -> Path:
    """The main checkout that owns this repository's common git directory."""
    common = git(repo, "rev-parse", "--git-common-dir")
    if common.returncode != 0:
        raise SystemExit("repair-worktrees: {} is not a git repository ({})".format(
            repo, common.stderr.strip()))
    path = Path(common.stdout.strip())
    if not path.is_absolute():
        path = (repo / path).resolve()
    return path.parent


def git_dir(main: Path) -> Path:
    out = git(main, "rev-parse", "--absolute-git-dir")
    if out.returncode != 0:
        raise SystemExit("repair-worktrees: cannot resolve the git directory of {}".format(main))
    return Path(out.stdout.strip())


def listed_worktrees(main: Path) -> dict:
    """name -> path, from git's own list (git may not list a tree whose admin dir is gone)."""
    found: dict = {}
    out = git(main, "worktree", "list", "--porcelain")
    for line in out.stdout.splitlines():
        if not line.startswith("worktree "):
            continue
        path = Path(line[len("worktree "):].strip())
        if path.resolve() == main.resolve() or not path.is_dir():
            continue
        found[path.resolve().name] = path.resolve()
    return found


def pointer_is_ours(worktree: Path, main: Path) -> bool:
    """True when the .git file still names <main>/.git/worktrees/<name>.

    That is the case after a prune accident: the admin directory is gone but
    the pointer text was never rewritten. A pointer into another repository
    must never be adopted.
    """
    pointer = worktree / ".git"
    if not pointer.is_file():
        return False
    try:
        text = pointer.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return False
    if not text.startswith("gitdir:"):
        return False
    parts = [p for p in text[len("gitdir:"):].strip().replace("\\", "/").split("/") if p]
    return (len(parts) >= 4 and parts[-1] == worktree.name
            and parts[-2] == "worktrees" and parts[-3] == ".git"
            and parts[-4] == main.name)


def candidates(main: Path, extra: list) -> list:
    """Every linked worktree of the main checkout that this script may touch."""
    found = listed_worktrees(main)
    if main.parent.is_dir():
        for entry in sorted(main.parent.iterdir()):
            if entry == main or not entry.is_dir():
                continue
            if not (entry / ".git").is_file():
                continue
            if entry.name in found or pointer_is_ours(entry, main):
                found[entry.name] = entry
    for path in extra:
        found[path.resolve().name] = path.resolve()
    return [found[name] for name in sorted(found)]


def resolves(worktree: Path) -> bool:
    return (git(worktree, "rev-parse", "--git-dir").returncode == 0
            and git(worktree, "rev-parse", "--verify", "HEAD").returncode == 0)


def branch_names(main: Path) -> list:
    out = git(main, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    return [b for b in out.stdout.split() if b and not b.startswith(SKIP_PREFIXES)]


def tree_blobs(main: Path, branch: str) -> dict:
    out = git(main, "ls-tree", "-r", branch)
    blobs: dict = {}
    for line in out.stdout.splitlines():
        meta, _, path = line.partition("\t")
        fields = meta.split()
        if len(fields) >= 3:
            blobs[path] = fields[2]
    return blobs


def score_branches(main: Path, worktree: Path) -> list:
    """(matched/compared, matched, branch), best first, over every branch that tracks a file here."""
    trees = {b: tree_blobs(main, b) for b in branch_names(main)}
    trees = {b: blobs for b, blobs in trees.items() if blobs}
    order = sorted(trees)
    per_branch = {b: sorted(trees[b]) for b in order}

    sample: list = []
    seen: set = set()
    depth = 0
    while len(sample) < SAMPLE_FILES:
        grew = False
        for branch in order:
            paths = per_branch[branch]
            if depth >= len(paths):
                continue
            grew = True
            path = paths[depth]
            if path in seen or not (worktree / path).is_file():
                continue
            seen.add(path)
            sample.append(path)
            if len(sample) >= SAMPLE_FILES:
                break
        if not grew:
            break
        depth += 1

    hashes: dict = {}
    for path in sample:
        out = git(main, "hash-object", "--", str(worktree / path))
        hashes[path] = out.stdout.strip()

    ranked: list = []
    for branch in order:
        blobs = trees[branch]
        compared = sum(1 for p in sample if p in blobs)
        if not compared:
            continue
        matched = sum(1 for p in sample
                      if p in blobs and hashes.get(p) and hashes[p] == blobs[p])
        ranked.append((matched / compared, matched, branch))
    ranked.sort(key=lambda row: (-row[0], -row[1], row[2]))
    return ranked


def write_admin(admin: Path, worktree: Path, gitdir: Path, head: str) -> None:
    """Rebuild the admin trio and point the worktree at it."""
    admin.mkdir(parents=True, exist_ok=True)
    (admin / "logs").mkdir(exist_ok=True)
    (admin / "HEAD").write_text(head + "\n", encoding="utf-8")
    (admin / "gitdir").write_text(str(worktree / ".git") + "\n", encoding="utf-8")
    (admin / "commondir").write_text(os.path.relpath(gitdir, admin) + "\n", encoding="utf-8")
    write_pointer(worktree / ".git",
                  "gitdir: {}\n".format(os.path.relpath(admin, worktree).replace("\\", "/")))


def stored_head(admin: Path, main: Path) -> str:
    path = admin / "HEAD"
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return ""
    ref = text[5:] if text.startswith("ref: ") else text
    return text if git(main, "rev-parse", "--verify", "--quiet", ref).returncode == 0 else ""


def repair(main: Path, gitdir: Path, worktree: Path, dry_run: bool) -> dict:
    name = worktree.name
    admin = gitdir / "worktrees" / name
    report: dict = {"name": name, "worktree": str(worktree)}

    if not worktree.is_dir() or not (worktree / ".git").is_file():
        report["status"] = "missing-worktree"
        return report

    head = stored_head(admin, main)
    if head:
        heads = [head]
    else:
        ranked = score_branches(main, worktree)
        if not ranked:
            report["status"] = "unknown-branch"
            return report
        heads = ["ref: refs/heads/{}".format(branch) for _, _, branch in ranked[:SHORTLIST]]
        report["scores"] = [(round(ratio, 2), matched, branch) for ratio, matched, branch in ranked[:SHORTLIST]]

    if dry_run:
        report.update(status="would-repair", head=heads[0])
        return report

    best = None
    for head in heads:
        write_admin(admin, worktree, gitdir, head)
        if git(worktree, "read-tree", "HEAD").returncode != 0:
            continue
        status = git(worktree, "status", "--porcelain")
        files = [line for line in status.stdout.splitlines() if line.strip()]
        if best is None or len(files) < best[0]:
            best = (len(files), head, files)
        if not files:
            break
    if best is None:
        report["status"] = "failed"
        return report

    write_admin(admin, worktree, gitdir, best[1])
    git(worktree, "read-tree", "HEAD")
    report.update(status="repaired", head=best[1], dirty=best[0], files=best[2][:5])
    return report


def describe(branch_head: str) -> str:
    return branch_head[len("ref: refs/heads/"):] if branch_head.startswith("ref: ") else branch_head[:12]


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild linked worktree admin directories (P-203).")
    parser.add_argument("--main", help="the main checkout to scan (default: this repository)")
    parser.add_argument("--worktree", action="append", default=[],
                        help="an extra worktree directory to check (repeatable)")
    parser.add_argument("--check", action="store_true", help="report only, exit 1 if a tree is broken")
    parser.add_argument("--dry-run", action="store_true", help="say what would change, change nothing")
    args = parser.parse_args()

    repo = Path(args.main).resolve() if args.main else repo_root()
    main_dir = main_checkout(repo)
    gitdir = git_dir(main_dir)
    worktrees_dir = gitdir / "worktrees"

    worktrees = candidates(main_dir, [Path(p) for p in args.worktree])
    broken = repaired = stuck = 0
    for worktree in worktrees:
        admin = worktrees_dir / worktree.name
        if resolves(worktree):
            branch = git(worktree, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
            dirty = len([l for l in git(worktree, "status", "--porcelain").stdout.splitlines() if l.strip()])
            print("ok      {}: {}, {} uncommitted file(s)".format(worktree.name, branch, dirty))
            continue
        broken += 1
        if args.check:
            reason = "admin directory missing" if not admin.is_dir() else "admin directory does not resolve"
            print("BROKEN  {}: {} ({})".format(worktree.name, reason, worktree))
            continue
        report = repair(main_dir, gitdir, worktree, args.dry_run)
        status = report["status"]
        if status == "repaired":
            repaired += 1
            print("fixed   {}: restored {}, {} uncommitted file(s) preserved{}".format(
                worktree.name, describe(report["head"]), report["dirty"],
                "".join(" " + line for line in report["files"])))
        elif status == "would-repair":
            print("dry     {}: would restore {}".format(worktree.name, describe(report["head"])))
        else:
            stuck += 1
            print("BROKEN  {}: {} ({})".format(worktree.name, status, worktree))

    print("repair-worktrees: {} checked, {} broken, {} repaired".format(
        len(worktrees), broken, repaired))
    if args.check:
        return 1 if broken else 0
    return 1 if stuck else 0


if __name__ == "__main__":
    sys.exit(main())
