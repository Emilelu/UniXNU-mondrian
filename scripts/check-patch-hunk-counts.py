#!/usr/bin/env python3
"""Verify every patch's hunk headers against its own body.

Why this exists (P-257): when a patch is assembled by hand — a three-way merge
resolved file by file, a splice of two branches' hunks — the hunk header counts
are easy to leave behind.  Neither gate in this repository noticed:

  * `git apply --numstat` answers "does this parse", not "is it consistent",
    so check-patch-apply.py (P-162) passes;
  * `git apply` itself applies the hunk, consumes the declared number of
    lines, and silently drops the rest of the body.

The build then fails on a C file that ends in the middle of a declaration, and
the error points at the file, not at the patch that truncated it.  On
2026-11-20 the carrier merge trial shipped a 0613 whose pong_adsp_pas.c hunk
declared 90 added lines and carried 96; the applied file lost
k60_adsp_scm_tried() and the tail of the file.

The check is textual and cheap: for every hunk, count the lines git would count
(' ' context, '-' removed, '+' added, ignoring "\\ No newline" markers) and
compare with the header.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
NO_NEWLINE = "\\ No newline at end of file"


def hunk_problems(path: pathlib.Path) -> list[str]:
    problems: list[str] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    index = 0
    while index < len(lines):
        match = HUNK.match(lines[index])
        if not match:
            index += 1
            continue
        header_line = index + 1
        old_count = int(match.group(2)) if match.group(2) is not None else 1
        new_count = int(match.group(4)) if match.group(4) is not None else 1
        index += 1
        removed = added = context = 0
        while index < len(lines):
            line = lines[index]
            if line.startswith("@@") or line.startswith("diff --git "):
                break
            # plain unified diffs carry no "diff --git" line: the next file starts
            # at "--- a/..." followed by "+++ b/..."
            if line.startswith("--- ") and index + 1 < len(lines) and lines[index + 1].startswith("+++ "):
                break
            if line.startswith(NO_NEWLINE):
                index += 1
                continue
            if line.startswith("-"):
                kind = "removed"
            elif line.startswith("+"):
                kind = "added"
            elif line.startswith(" ") or line == "":
                kind = "context"
            elif line.startswith("\\"):
                index += 1
                continue
            else:
                break
            # A blank line with no prefix is either a context line whose trailing
            # space a tool stripped, or the separator git writes before the next
            # file section.  Inside the declared window it is context; past it, it
            # is the separator.
            if kind == "context" and line == "" and (context + removed >= old_count
                                                     or context + added >= new_count):
                break
            if kind == "removed":
                removed += 1
            elif kind == "added":
                added += 1
            else:
                context += 1
            index += 1
        if old_count != removed + context:
            problems.append(
                f"{path}: hunk at line {header_line} declares -{old_count} but carries "
                f"{removed + context} ({removed} removed + {context} context)")
        if new_count != added + context:
            problems.append(
                f"{path}: hunk at line {header_line} declares +{new_count} but carries "
                f"{added + context} ({added} added + {context} context)")
    return problems


def patches(explicit: list[str]) -> list[pathlib.Path]:
    if explicit:
        return [pathlib.Path(item) for item in explicit]
    return sorted(p for p in (ROOT / "patches").rglob("*.patch") if p.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="patch files (default: every patches/**/*.patch)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    files = patches(args.paths)
    problems: list[str] = []
    for path in files:
        problems.extend(hunk_problems(path))

    if problems:
        for problem in problems:
            print(f"❌ {problem}")
        print(f"patch-hunk-counts: {len(problems)} problem(s) in {len(files)} patch file(s)")
        return 1
    if not args.quiet:
        print(f"✅ patch-hunk-counts: {len(files)} patch file(s) agree with their hunk headers (P-257)")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main())
