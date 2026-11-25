#!/usr/bin/env python3
"""Refuse a new driver that repeats an implementation this repository already has.

The check runs on the *added* files of a change (git diff --diff-filter=A). For each
new source file it reads the base classes the file derives from, then searches every
local and remote branch for another file deriving from the same base. A hit fails the
check unless `docs/engineering/CAPABILITY-REUSE.toml` records a decision for that
base (reuse / derived / not-applicable) with a pointer to the existing file.

This is the gate for the 2026-11-24 ShengUfs incident: the same IOBlockStorageDevice
subclass already existed in drivers/NativeUfs, but it lived on a branch whose
BRANCH-REGISTRY row said purpose="TBD", so nothing connected the capability to the
existing code.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(os.environ.get("K60_REPO") or Path(__file__).resolve().parents[1])
LEDGER = ROOT / "docs/engineering/CAPABILITY-REUSE.toml"
SCAN_PREFIXES = ("drivers/", "package/")
SOURCE_SUFFIXES = (".c", ".cc", ".cpp", ".h", ".hpp")

CLASS_RE = re.compile(r"class\s+([A-Za-z_]\w*)\s*:\s*(?:public\s+)?([A-Za-z_][\w:]*)")
META_RE = re.compile(r"OSDefineMetaClassAndStructors\s*\(\s*([A-Za-z_]\w*)\s*,\s*([A-Za-z_]\w*)\s*\)")


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return result.stdout if result.returncode == 0 else ""


def added_files(base: str) -> list[str]:
    out = git("diff", "--diff-filter=A", "--name-only", f"{base}...HEAD")
    return [line for line in out.splitlines() if line.endswith(SOURCE_SUFFIXES)
            and line.startswith(SCAN_PREFIXES)]


def bases_of(text: str) -> set[str]:
    found = {match.group(2).split("::")[-1] for match in CLASS_RE.finditer(text)}
    found |= {match.group(2) for match in META_RE.finditer(text)}
    found.discard("IOService")
    return found


def refs() -> list[str]:
    out = git("for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes")
    return [line for line in out.splitlines() if line and not line.endswith("/HEAD")]


def other_implementations(base: str, base_class: str, added: set[str], refs_list: list[str]) -> list[str]:
    pattern = rf"class\s+[A-Za-z_]\w*\s*:\s*(public\s+)?{re.escape(base_class)}\b"
    hits: list[str] = []
    for ref in refs_list:
        out = git("grep", "-n", "-E", pattern, ref, "--", *SCAN_PREFIXES)
        for line in out.splitlines():
            path = line.split(":", 2)[1] if line.count(":") >= 2 else ""
            if not path or path in added:
                continue
            if path.endswith(SOURCE_SUFFIXES) and (ref, path) not in [(h.split("|")[0], h.split("|")[1]) for h in hits]:
                hits.append(f"{ref}|{path}|{line.split(':', 2)[2].strip()[:120]}")
    return hits


def ledger() -> dict:
    if not LEDGER.is_file():
        return {"decision": []}
    return tomllib.loads(LEDGER.read_text(encoding="utf-8"))


def covered(base_class: str) -> bool:
    for item in ledger().get("decision", []):
        if item.get("base") == base_class and item.get("verdict") in ("reuse", "derived", "not-applicable"):
            if item.get("evidence"):
                return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="main")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    files = added_files(args.base)
    if not files:
        print("OK capability-reuse: no new driver sources in this change")
        return 0

    refs_list = refs()
    problems = 0
    for path in files:
        text = (ROOT / path).read_text(encoding="utf-8", errors="replace")
        added = set(files)
        for base_class in sorted(bases_of(text)):
            hits = other_implementations(path, base_class, added, refs_list)
            if not hits:
                continue
            if covered(base_class):
                if args.verbose:
                    print(f"note capability-reuse: {path} derives {base_class}; reuse recorded")
                continue
            problems += 1
            print(f"FAIL capability-reuse: {path} adds another {base_class} implementation")
            for hit in hits[:5]:
                ref, other, line = hit.split("|", 2)
                print(f"  existing: {ref}:{other}: {line}")
            print(f"  record a [[decision]] for base = \"{base_class}\" in {LEDGER.relative_to(ROOT)}")
    if problems:
        print(f"FAIL capability-reuse: {problems} new implementation(s) repeat code this repository already has")
        return 1
    print("OK capability-reuse: every new driver base class is new to this repository")
    return 0


if __name__ == "__main__":
    sys.exit(main())
