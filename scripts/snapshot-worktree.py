#!/usr/bin/env python3
"""Snapshot every uncommitted change before something irreversible happens.

`git checkout --`, `restore`, `reset --hard`, `clean -fd` and `stash` all discard
work with no recovery path. On 2026-11-14 that cost a teammate seven files.

This script writes a complete, restorable snapshot first:

  <dest>/<timestamp>/tracked.patch   git diff HEAD (binary-safe)
  <dest>/<timestamp>/staged.patch    git diff --cached
  <dest>/<timestamp>/untracked/      every untracked file, path preserved
  <dest>/<timestamp>/status.txt      git status --porcelain
  <dest>/<timestamp>/restore.sh      puts it all back

Destination defaults to E:/k60-work/scratch/snapshots (persistent, never /tmp —
iron rule 1). `scripts/git-safe.sh` calls this automatically before it lets a
destructive command through.

Usage:
  python3 scripts/snapshot-worktree.py                    # snapshot $PWD
  python3 scripts/snapshot-worktree.py --repo PATH
  python3 scripts/snapshot-worktree.py --dest PATH
  python3 scripts/snapshot-worktree.py --quiet            # print only the dir
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_DEST = Path(os.environ.get("K60_SNAPSHOT_DIR", "/mnt/e/k60-work/scratch/snapshots"))


def git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, check=False
    )
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=os.getcwd())
    parser.add_argument("--dest", default=str(DEFAULT_DEST))
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    top = git(repo, "rev-parse", "--show-toplevel").decode().strip()
    if not top:
        print(f"snapshot-worktree: {repo} is not inside a git checkout", file=sys.stderr)
        return 1
    repo = Path(top)

    status = git(repo, "status", "--porcelain").decode("utf-8", "replace")
    if not status.strip():
        if not args.quiet:
            print(f"snapshot-worktree: {repo} is clean, nothing to save")
        return 0

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    name = repo.name
    out = Path(args.dest) / f"{stamp}-{name}"
    out.mkdir(parents=True, exist_ok=True)

    (out / "tracked.patch").write_bytes(git(repo, "diff", "HEAD", "--binary"))
    (out / "staged.patch").write_bytes(git(repo, "diff", "--cached", "--binary"))
    (out / "status.txt").write_text(status, encoding="utf-8")
    (out / "HEAD.txt").write_text(
        git(repo, "rev-parse", "HEAD").decode().strip() + "\n", encoding="utf-8"
    )
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD").decode().strip()
    (out / "branch.txt").write_text(branch + "\n", encoding="utf-8")

    # Untracked files, path-preserving. `git ls-files -o --exclude-standard -z`
    # lists them without shell quoting.
    untracked_root = out / "untracked"
    count = 0
    raw = git(repo, "ls-files", "--others", "--exclude-standard", "-z")
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        rel = entry.decode("utf-8", "surrogateescape")
        src = repo / rel
        if not src.is_file():
            continue
        dst = untracked_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        count += 1

    restore = out / "restore.sh"
    restore.write_text(
        "#!/usr/bin/env bash\n"
        "# Restore the snapshot taken by scripts/snapshot-worktree.py.\n"
        "# Run from the repository root; it applies both patches and copies the\n"
        "# untracked files back. Nothing here is destructive to other files.\n"
        "set -euo pipefail\n"
        'HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)\n'
        'git checkout "$(cat "$HERE/HEAD.txt")" 2>/dev/null || true\n'
        'git apply --binary --3way "$HERE/staged.patch" 2>/dev/null || true\n'
        'git apply --binary --3way "$HERE/tracked.patch" 2>/dev/null || true\n'
        '[ -d "$HERE/untracked" ] && cp -a "$HERE/untracked/." ./\n'
        'echo "restored from $HERE"\n',
        encoding="utf-8",
    )
    restore.chmod(0o755)

    tracked_changed = len([l for l in status.splitlines() if not l.startswith("??")])
    if args.quiet:
        print(str(out))
    else:
        print(f"snapshot-worktree: saved {repo.name} @ {branch}")
        print(f"  dir        {out}")
        print(f"  tracked    {tracked_changed} path(s) -> tracked.patch + staged.patch")
        print(f"  untracked  {count} file(s) -> untracked/")
        print(f"  restore    bash {restore}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
