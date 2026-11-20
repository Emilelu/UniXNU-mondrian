#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Do the system headers the glue includes still exist in the 27 tree?

The stub headers in scripts/tests/portability prove the declarations are
enough; they say nothing about whether bsd/, osfmk/ and pexpert/ still
carry those files. This check reads the two sources, takes every <...>
include and resolves it through the roots a 27 build puts on the include
path, so a rename shows up here instead of as a failing build.

  python3 scripts/check-audio27-includes.py /opt/k60/trees/ios27-out/feeds/xnu-3199e8bc
"""
import argparse
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
SOURCES = ["drivers/PongAudio/PongAudioAmp.c", "drivers/PongAudio/PongAudioGeniI2c.c"]
ROOTS = ["bsd", "osfmk", "osfmk/arm", "osfmk/arm64", "pexpert", "libkern", "iokit",
         "EXTERNAL_HEADERS", "libsa"]
INCLUDE = re.compile(r'^\s*#\s*include\s*<([^>]+)>', re.MULTILINE)


def wanted():
    """[(header, source, line)] in the order the sources mention them."""
    found = []
    for name in SOURCES:
        path = REPO / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in INCLUDE.finditer(text):
            line = text.count(chr(10), 0, match.start()) + 1
            found.append((match.group(1), name, line))
    unique = []
    seen = set()
    for header, source, line in found:
        if header in seen:
            continue
        seen.add(header)
        unique.append((header, source, line))
    return unique


def resolve(root, header):
    for base in ROOTS:
        candidate = root / base / header
        if candidate.is_file():
            return base + "/" + header
    return None


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("tree", help="XNU source tree whose include path matters")
    args = parser.parse_args(argv[1:])
    root = pathlib.Path(args.tree)
    if not (root / "bsd").is_dir():
        print("INCLUDES FAILED: %s has no bsd/; that is not an XNU tree" % root)
        return 1
    headers = wanted()
    if not headers:
        print("INCLUDES FAILED: no <...> includes found in %s" % ", ".join(SOURCES))
        return 1
    missing = []
    places = []
    for header, source, line in headers:
        where = resolve(root, header)
        if where is None:
            missing.append("%s (from %s:%d)" % (header, source, line))
        else:
            places.append("%s -> %s" % (header, where))
    if missing:
        print("INCLUDES FAILED: %s" % ", ".join(missing))
        return 1
    print("INCLUDES OK %d headers resolve in %s: %s" % (len(headers), root.name, ", ".join(places)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
