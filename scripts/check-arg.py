#!/usr/bin/env python3
"""Prove that a capture's image carries the kernel argument the flight isolates.

Why this is separate from the judge: the judge reads the console and nothing
else, so it cannot tell a control flight from a forgotten flag.  cellular-l3-
20261114d recorded kernel_args_requested = [''] and the driver took its default
and returned; a verdict on that image would be a verdict on nothing.

Two sources, in this order:
  1. the build manifest's kernel_args_requested -- what the build says it asked
     for.  Read from the artifact directory that boot.json points at, because
     the capture directory itself has no manifest.
  2. the bytes of boot.img -- what the image actually carries.  This is the
     authoritative one: trial builds keep only four manifest keys and have no
     kernel_args_requested at all (wifi-20261116a2).

boot.json writes the image as a Windows path (like E:/iOS Port/Work/...).  Under WSL
that path does not exist, so find_image also tries its /mnt/e/... mount;
under MSYS python the raw path resolves natively and the mount is skipped.

Exit 0 when the bytes carry the expected argument, 4 otherwise (4 = not a
verdict, never "silent").  A manifest that disagrees with the bytes is reported
but does not decide: the bytes are what the phone runs.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys


def load_boot(d: pathlib.Path) -> dict:
    p = d / "boot.json"
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def wsl_of(raw: str) -> pathlib.Path | None:
    """Map a Windows path (E:/dir/file) to its WSL mount (/mnt/e/dir/file)."""
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", raw)
    if not m:
        return None
    drive, rest = m.group(1).lower(), m.group(2).replace("\\", "/")
    return pathlib.Path("/mnt/%s/%s" % (drive, rest))


def find_image(d: pathlib.Path, boot: dict) -> pathlib.Path | None:
    for cand in (d / "boot.img",):
        if cand.exists():
            return cand
    raw = boot.get("image")
    if raw:
        for cand in (pathlib.Path(raw), wsl_of(raw)):
            if cand is not None and cand.exists():
                return cand
    return None


def manifest_for(img: pathlib.Path, d: pathlib.Path) -> tuple[str, dict] | None:
    """The manifest sits beside the image, not beside the capture."""
    for base in (img.parent, d):
        for name in ("build-manifest.json", "manifest.json"):
            p = base / name
            if p.exists():
                try:
                    return name, json.loads(p.read_text(encoding="utf-8-sig"))
                except Exception as exc:
                    return name, {"__error__": str(exc)}
    return None


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: check-arg.py <capture-dir> <arg>", file=sys.stderr)
        return 4
    d = pathlib.Path(sys.argv[1])
    expect = sys.argv[2]
    if not expect:
        print("   skipped (--expect-arg '')")
        return 0

    boot = load_boot(d)
    img = find_image(d, boot)
    if img is None:
        print("   boot.img not found: cannot verify the argument in the bytes")
        return 4

    found = manifest_for(img, d)
    if found is None:
        print("   manifest: none beside the image (trial build?) -- bytes decide")
    else:
        name, m = found
        if "__error__" in m:
            print("   manifest %s: unreadable (%s)" % (name, m["__error__"]))
        elif "kernel_args_requested" in m:
            print("   manifest %s: kernel_args_requested = %r"
                  % (name, m["kernel_args_requested"]))
        else:
            print("   manifest %s: no kernel_args_requested field "
                  "(trial build keeps four keys) -- bytes decide" % name)

    blob = img.read_bytes()
    seen: dict[str, int] = {}
    for hit in re.finditer(rb"pong_[a-z_]+=[0-9]+", blob):
        key = hit.group(0).decode()
        seen[key] = seen.get(key, 0) + 1
    if not seen:
        print("   bytes %s: no pong_<name>=<n> argument anywhere" % img.name)
        return 4
    shown = ", ".join("%s x%d" % (k, v) for k, v in sorted(seen.items()))
    print("   bytes %s: %s" % (img.name, shown))

    if seen.get(expect):
        print("   OK: the image carries %s" % expect)
        return 0
    print("   MISSING: the image does not carry %s" % expect)
    return 4


if __name__ == "__main__":
    sys.exit(main())
