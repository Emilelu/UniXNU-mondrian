#!/usr/bin/env python3
"""Check that the AOCI cognition index still names files that exist.

The index (``aoci.code.txt``) is a git-tracked map of the repository: one
``path[TAG]: F: ... | R: ... | A: ... | S: ...`` line per managed source.
It is only worth reading if its paths resolve, so this gate walks every entry,
applies the scope policy from ``.aoci/config.json``, and fails when an entry
names a file that is gone.

Scope rules honoured:
  * ``exclude_dirs`` / ``exclude_root_dirs`` (basename and first segment)
  * ``exclude_files`` (glob against the basename)
  * ``managed_scope.rules`` whose ``action`` is ``exclude`` (directory or glob)
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from pathlib import Path

INDEX = "aoci.code.txt"
META = "aoci.meta.txt"
ROOT_FILE = "aoci.txt"
CONFIG = ".aoci/config.json"

ENTRY = re.compile(r"^(?P<name>[^\[\]:]+)\[(?P<tags>[A-Z0-9+]*)\]:\s*F:")
SECTION = re.compile(r"^===\s*/<repository>/(?P<dir>.*?)\s*===$")


def load_policy(repo: Path) -> dict:
    path = repo / CONFIG
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"AOCI CONFIG unreadable: {path}: {exc}")


def glob_match(path: str, pattern: str) -> bool:
    """Match like the scope rules do, treating ``**/`` as zero or more directories.

    ``fnmatch`` alone makes ``patches/**/*.patch`` require a subdirectory, while
    the policy means "a patch anywhere under patches", so the collapsed form has
    to be tried as well.
    """
    if fnmatch.fnmatch(path, pattern):
        return True
    while "**/" in pattern:
        pattern = pattern.replace("**/", "", 1)
        if fnmatch.fnmatch(path, pattern):
            return True
    return False


def excluded(path: str, policy: dict) -> bool:
    parts = path.split("/")
    base = parts[-1]
    if parts and parts[0] in set(policy.get("exclude_root_dirs", [])):
        return True
    if any(part in set(policy.get("exclude_dirs", [])) for part in parts[:-1]):
        return True
    if any(fnmatch.fnmatch(base, pattern) for pattern in policy.get("exclude_files", [])):
        return True
    for rule in policy.get("managed_scope", {}).get("rules", []):
        if not rule.get("enabled", True) or rule.get("action") != "exclude":
            continue
        pattern = rule.get("pattern", "")
        kind = rule.get("pattern_kind", "glob")
        if kind == "directory":
            if pattern in parts[:-1] or (parts and parts[0] == pattern):
                return True
        elif glob_match(path, pattern):
            return True
    return False


def entries(repo: Path) -> list[tuple[int, str]]:
    """Return (line number, repository-relative path) for every entry.

    Entries are basenames grouped under ``===<repository>/<dir>/===`` section
    headers, so the path is the current section directory joined with the name.
    """
    found: list[tuple[int, str]] = []
    section = ""
    for number, line in enumerate((repo / INDEX).read_text(encoding="utf-8").splitlines(), 1):
        if not line:
            continue
        head = SECTION.match(line)
        if head:
            section = head.group("dir").strip("/")
            continue
        if line.startswith("#") or line.startswith("==="):
            continue
        match = ENTRY.match(line)
        if match:
            name = match.group("name")
            found.append((number, f"{section}/{name}" if section else name))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--max-missing", type=int, default=0,
                        help="how many missing paths are tolerated (default 0)")
    parser.add_argument("--list-limit", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo = args.repo.resolve()
    for name in (ROOT_FILE, META, INDEX):
        if not (repo / name).exists():
            message = f"FAIL aoci: {name} is missing from {repo}"
            print(json.dumps({"ok": False, "error": message}) if args.json else message)
            return 2

    policy = load_policy(repo)
    rows = entries(repo)
    if not rows:
        message = f"FAIL aoci: {INDEX} has no entries, the index was emptied"
        print(json.dumps({"ok": False, "error": message}) if args.json else message)
        return 1

    missing: list[tuple[int, str]] = []
    skipped = 0
    for number, path in rows:
        if excluded(path, policy):
            skipped += 1
            continue
        if not (repo / path).exists():
            missing.append((number, path))

    ok = len(missing) <= args.max_missing
    if args.json:
        print(json.dumps({
            "ok": ok,
            "entries": len(rows),
            "skipped": skipped,
            "missing": [{"line": n, "path": p} for n, p in missing],
        }, ensure_ascii=False))
    else:
        if ok:
            print(f"AOCI OK {len(rows)} entries, {skipped} outside scope, every indexed path resolves")
        else:
            print(f"FAIL aoci: {len(missing)} of {len(rows)} entries name a path that no longer exists")
            for number, path in missing[:args.list_limit]:
                print(f"  {INDEX}:{number}  {path}")
            if len(missing) > args.list_limit:
                print(f"  ... and {len(missing) - args.list_limit} more")
            print("  fix: re-run the aoci scan, or restore the path, or delete the stale entry")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())