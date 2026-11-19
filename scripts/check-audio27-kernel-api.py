#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Check the four kernel interfaces the audio glue names, in a real XNU tree.

scripts/tests/portability/run-deps.sh proves the glue needs nothing beyond the
six names in IOS27-WIRING.md section 1, but it proves that against stub headers
this repository writes. The other half - that those four kernel interfaces still
exist in the 27 baseline - cannot be faked: it is a fact about the tree.

  python3 scripts/check-audio27-kernel-api.py <xnu-tree>
  # API OK 4/4 xnu-12377.121.6 (ac9718f)

The tree may be the seeded repository or the XNU sources themselves; both are
searched. Generated headers, the wiring's own files and other architectures are
skipped, and a header that calls the name counts before one that only mentions
it, so the line printed is the declaration the port will use.
"""
import pathlib
import re
import subprocess
import sys

# name -> why the wiring table names it (IOS27-WIRING.md section 1)
API = {
    "ml_io_map": "maps a physical window for the pad and I2C registers",
    "ml_io_map_wcomb": "the write-combining map the playback buffer needs",
    "PE_parse_boot_argn": "reads pong_audio_probe=1, the probe gate",
    "delay_for_interval": "the write-then-read settling delay",
}
SEARCH = ("bsd", "osfmk", "pexpert", "libkern")
SKIP_DIRS = ("i386", "x86", "x86_64")
SKIP_FILES = ("static_if.h",)
SKIP_PREFIX = ("PongAudio", "K60")


def resolve(tree):
    """The XNU sources for either layout: a seeded repo, or the sources themselves."""
    for root in (tree / ".cache/xnu-work", tree):
        if (root / "bsd/conf/files").is_file():
            return root
    return None


def declarations(root, name):
    """Where the name lives, declarations first; one hit per header."""
    word = re.compile(r"\b%s\b" % re.escape(name))
    call = re.compile(r"\b%s\s*\(" % re.escape(name))
    calls, mentions = [], []
    for part in SEARCH:
        base = root / part
        if not base.is_dir():
            continue
        for path in base.rglob("*.h"):
            if path.name in SKIP_FILES or path.name.startswith(SKIP_PREFIX):
                continue
            if any(part_name in SKIP_DIRS for part_name in path.parts):
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as handle:
                    for number, line in enumerate(handle, 1):
                        if word.search(line):
                            where = "%s:%d" % (path.relative_to(root), number)
                            (calls if call.search(line) else mentions).append(where)
                            break
            except OSError:
                continue
    return calls + mentions


def version(root):
    try:
        done = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%s %h"],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              universal_newlines=True)
        if done.returncode == 0 and done.stdout.strip():
            return done.stdout.strip()
    except OSError:
        pass
    return "unknown revision"


def main(argv):
    if len(argv) < 2:
        sys.stderr.write("usage: check-audio27-kernel-api.py <xnu-tree>\n")
        return 2
    root = resolve(pathlib.Path(argv[1]))
    if root is None:
        print("API: no bsd/conf/files under %s (neither .cache/xnu-work nor the "
              "tree itself)" % argv[1])
        return 1

    missing = []
    for name in sorted(API):
        hits = declarations(root, name)
        if hits:
            print("  %-20s %s  (%s)" % (name, hits[0], API[name]))
        else:
            missing.append(name)
    if missing:
        print("API FAILED: %d of %d names absent from %s: %s"
              % (len(missing), len(API), root, ", ".join(missing)))
        return 1
    print("API OK %d/%d %s" % (len(API), len(API), version(root)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
