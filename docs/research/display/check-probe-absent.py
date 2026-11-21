#!/usr/bin/env python3
"""Assert the K60 clamp probe is compiled out of a release kernel.

The probe (patches/proposed/0003) is a build-time switch, so "it is off" has to
be a property of the binary, not of a promise in a document. The probe's
failure path carries one string that exists nowhere else:

    K60 BACKLIGHT: probe request not built

With K60_BACKLIGHT_PROBE at its default 0 the whole block is not compiled, so
that string cannot be in the image; a release image that contains it was built
with -DK60_BACKLIGHT_PROBE=1 by mistake. The script also checks that the file
really is the backlight service (the request-line format string is there), so
"marker absent" cannot be satisfied by passing the wrong file.

Usage:
    python3 docs/research/display/check-probe-absent.py --release kernel.macho
    python3 docs/research/display/check-probe-absent.py \
        --release release/kernel.macho --diagnostic diagnostic/kernel.macho

Exit code 0 = every requested check passed. Every invocation prints the
sha256 of each file it read, because the evidence record needs it.
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import sys

MARKER = b"K60 BACKLIGHT: probe request not built"
# Present in every build of K60Backlight.cpp (the 0001 patch only changes the
# argument passed to it, not the format string).
REQUEST_FORMAT = b"K60 BACKLIGHT: brightness level %u -> level %u dbv 0x%x"


def read(path: str) -> bytes:
    data = pathlib.Path(path).read_bytes()
    print("sha256 %s  %s  %d bytes" % (hashlib.sha256(data).hexdigest(),
                                       path, len(data)))
    return data


def check_release(data: bytes, path: str) -> list[str]:
    problems = []
    count = data.count(MARKER)
    if count:
        problems.append(
            "%s: release image carries the probe marker %d time(s); it was "
            "built with -DK60_BACKLIGHT_PROBE=1" % (path, count))
    if not data.count(REQUEST_FORMAT):
        problems.append(
            "%s: the backlight request format string is absent, so this file "
            "cannot prove anything about the probe (wrong image?)" % path)
    return problems


def check_diagnostic(data: bytes, path: str) -> list[str]:
    problems = []
    count = data.count(MARKER)
    if count != 1:
        problems.append(
            "%s: diagnostic image carries the probe marker %d time(s), "
            "expected exactly 1 (was -DK60_BACKLIGHT_PROBE=1 passed?)"
            % (path, count))
    if not data.count(REQUEST_FORMAT):
        problems.append(
            "%s: the backlight request format string is absent; the probe "
            "could not have been linked here" % path)
    return problems


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--release", required=True,
                        help="kernel image built without the probe (must not "
                             "contain the marker)")
    parser.add_argument("--diagnostic",
                        help="optional kernel image built with "
                             "-DK60_BACKLIGHT_PROBE=1 (must contain it once)")
    args = parser.parse_args(argv)

    problems = check_release(read(args.release), args.release)
    if args.diagnostic:
        problems += check_diagnostic(read(args.diagnostic), args.diagnostic)
    elif not problems:
        print("note: --diagnostic not given; the positive half of the "
              "assertion was skipped")

    for problem in problems:
        print("FAIL " + problem)
    if problems:
        return 1
    print("OK probe absent from the release image"
          + (", present once in the diagnostic image"
             if args.diagnostic else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
