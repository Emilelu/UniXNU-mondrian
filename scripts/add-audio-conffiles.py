#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""List the two audio driver sources in bsd/conf/files once the tree is seeded.

P-171: a conf/files hunk cannot survive the tree being rebuilt, so the entries
are added after seeding rather than patched. P-245 is the failure this script
exists to prevent - the shared hook prints "anchor missing, entries not added",
an outer "|| true" swallows it, and the build goes green with no audio in it.
So the verdict here is a count, not a message: how many lines name the driver
sources before and after the write, and a non-zero exit when it did not grow.

  python3 scripts/add-audio-conffiles.py <tree>           # append, exit 1 if it did not
  python3 scripts/add-audio-conffiles.py --check <tree>   # report the count only

The anchor is the button driver, which a seeded tree carries from its own line;
without it the tree is not seeded and nothing is written.
"""
import argparse
import pathlib
import sys

ANCHOR = "bsd/dev/pong_buttons.c\t\t\tstandard"
ENTRIES = [
    "bsd/dev/PongAudioGeniI2c.c\t\t\tstandard",
    "bsd/dev/PongAudioAmp.c\t\t\tstandard",
]
MARKER = "PongAudio"
SOURCES = [entry.split("\t")[0] for entry in ENTRIES]


def count(text):
    """Lines that name an audio source. The whole point: a number, not a log line."""
    return sum(1 for line in text.splitlines() if MARKER in line)


def report(before, after):
    print("audio conffiles: pong_audio lines %d -> %d" % (before, after))


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("tree")
    parser.add_argument("--check", action="store_true",
                        help="do not write; fail when the entries are not listed")
    args = parser.parse_args(argv[1:])

    tree = pathlib.Path(args.tree)
    work = tree / ".cache/xnu-work"
    conf = work / "bsd/conf/files"
    if not conf.is_file():
        print("audio conffiles: no conf/files at %s (tree not seeded)" % conf)
        return 1

    text = conf.read_text()
    before = count(text)
    missing = [name for name in SOURCES if not (work / name).is_file()]
    if missing:
        report(before, before)
        print("audio conffiles: not in the tree, so not listed: %s" % ", ".join(missing))
        return 1

    if args.check:
        report(before, before)
        if before < len(SOURCES):
            print("audio conffiles: %d of %d entries listed" % (before, len(SOURCES)))
            return 1
        print("audio conffiles: both entries listed")
        return 0

    if ANCHOR not in text:
        report(before, before)
        print("audio conffiles: anchor bsd/dev/pong_buttons.c missing, entries not added")
        return 1

    block = ANCHOR
    for entry in ENTRIES:
        if entry.split("\t")[0] in text:
            continue
        block = block + "\n" + entry
    if block != ANCHOR:
        conf.write_text(text.replace(ANCHOR, block, 1))

    after = count(conf.read_text())
    report(before, after)
    if after < len(SOURCES):
        print("audio conffiles: entries did not take (want %d, have %d)"
              % (len(SOURCES), after))
        return 1
    print("audio conffiles: both entries listed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
