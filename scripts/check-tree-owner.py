#!/usr/bin/env python3
"""Refuse to work in a checkout that belongs to somebody else (P-184).

`git checkout --`, `git restore`, `git reset --hard`, `git clean` and
`git stash` destroy uncommitted work without a recovery path. On 2026-11-14 the
Lead ran `git checkout --` in the shared checkout while the touch agent had
eight files modified there; seven of them were unrecoverable.

This gate makes the ownership explicit instead of remembered:

  * `docs/engineering/TREE-OWNERS.toml` names the owner of every checkout.
  * The actor names itself with K60_AGENT_ID (default "lead").
  * If the checkout belongs to another actor AND has uncommitted changes, the
    gate fails and names the files. A clean tree is fine to read or build from.

Exit 0 = this checkout is safe for this actor.
Exit 1 = this checkout holds another actor's uncommitted work.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OWNERS = REPO / "docs/engineering/TREE-OWNERS.toml"
ACTOR = os.environ.get("K60_AGENT_ID", "lead")


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def main() -> int:
    if not OWNERS.is_file():
        print(f"❌ check-tree-owner: {OWNERS} is missing")
        return 1
    try:
        table = tomllib.loads(OWNERS.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        print(f"❌ check-tree-owner: {OWNERS} does not parse: {error}")
        return 1

    entries = table.get("tree", [])
    here = REPO.as_posix()
    owner = None
    note = ""
    for entry in entries:
        path = str(entry.get("path", "")).rstrip("/")
        if path and (here == path or here.startswith(path + "/")):
            owner = entry.get("owner")
            note = str(entry.get("note", ""))
            break

    if owner is None:
        print(f"❌ check-tree-owner: {here} is not registered in TREE-OWNERS.toml")
        print("   Add a [[tree]] entry naming its owner; an unregistered checkout has no protection.")
        return 1

    dirty = [line for line in git("status", "--porcelain").splitlines() if line.strip()]
    if owner == ACTOR:
        print(f"✅ check-tree-owner: {here} belongs to {owner} ({ACTOR}); {len(dirty)} uncommitted path(s)")
        return 0

    if not dirty:
        print(f"✅ check-tree-owner: {here} belongs to {owner}; the tree is clean, read-only use is fine")
        return 0

    print(f"❌ check-tree-owner: {here} belongs to {owner}, not {ACTOR}, and holds {len(dirty)} uncommitted path(s)")
    for line in dirty[:20]:
        print(f"   {line}")
    if len(dirty) > 20:
        print(f"   … and {len(dirty) - 20} more")
    if note:
        print(f"   {note}")
    print()
    print("   Work in your own checkout (`git worktree add <path> <branch>`), or ask the owner to")
    print("   commit. Never run git checkout --/restore/reset --hard/clean/stash here: P-184.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
