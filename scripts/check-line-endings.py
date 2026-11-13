#!/usr/bin/env python3
"""Fail when an edit converts a LF file to CRLF.

Why: on 2026-11-14 an edit made from Windows converted AGENTS.md from LF to
CRLF, so a 37-line change appeared as 366 insertions and 366 deletions. That
buries the real change in review and makes every later merge conflict on the
whole file.

Seventy-odd files in this repository already carry CRLF from before this rule
existed. Rewriting them would create one enormous commit that touches nothing
else, so the gate only reports conversions: a file whose committed copy is LF but
whose working copy is CRLF. Legacy CRLF files stay quiet until somebody edits
them, at which point the edit must keep LF.

Exit status 1 on conversions, 0 when clean. --fix rewrites the conversions.
"""
import argparse
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]


def tracked_files():
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z"],
                         capture_output=True, check=True).stdout
    for raw in out.split(b"\0"):
        if raw:
            yield raw.decode("utf-8", "surrogateescape")


def head_bytes(rel):
    proc = subprocess.run(["git", "-C", str(REPO), "show", f"HEAD:{rel}"],
                          capture_output=True)
    return proc.stdout if proc.returncode == 0 else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fix", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    converted = []
    for rel in tracked_files():
        path = REPO / rel
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\r\n" not in data:
            continue
        if b"\0" in data[:4096]:
            continue
        committed = head_bytes(rel)
        if committed is None:
            continue
        # Only a conversion is a problem: HEAD was pure LF.
        if b"\r\n" in committed:
            continue
        converted.append((rel, path, data))

    if not converted:
        if not args.quiet:
            print("check-line-endings: no file converted LF -> CRLF")
        return 0

    if args.fix:
        for rel, path, data in converted:
            path.write_bytes(data.replace(b"\r\n", b"\n"))
        print(f"check-line-endings: rewrote {len(converted)} converted file(s) back to LF")
        for rel, _, _ in converted:
            print(f"  {rel}")
        return 0

    print(f"check-line-endings: {len(converted)} file(s) converted LF -> CRLF",
          file=sys.stderr)
    for rel, _, _ in converted:
        print(f"  {rel}", file=sys.stderr)
    print("check-line-endings: run --fix; an editor on Windows is the usual cause",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
