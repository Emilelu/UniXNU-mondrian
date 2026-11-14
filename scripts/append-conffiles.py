#!/usr/bin/env python3
"""Add the in-tree driver sources to bsd/conf/files after the tree is seeded.

P-171: a conf/files hunk cannot be anchored at patch time (the tree is rebuilt),
so the entries are appended by the build driver once the anchor exists.
Idempotent per entry: a source already listed is never listed twice.
"""

import pathlib
import sys

ANCHOR = "bsd/dev/pong_buttons.c\t\t\tstandard"
ENTRIES = [
    "bsd/dev/pong_smem.c\t\t\tstandard",
    "bsd/dev/pong_handoff.c\t\t\tstandard",
    "bsd/dev/pong_adsp_boot.c\t\t\tstandard",
    "bsd/dev/pong_adsp_pas.c\t\t\tstandard",
    "bsd/dev/pong_adsp_image.c\t\t\tstandard",
    "bsd/dev/pong_modem_image.c\t\t\tstandard",
    "bsd/dev/pong_fat.c\t\t\tstandard",
    "bsd/dev/pong_pmic_rail.c\t\t\tstandard",
]


def main() -> int:
    tree = pathlib.Path(sys.argv[1])
    print("conffiles: hook start tree=%s" % tree)
    conf = tree / ".cache/xnu-work/bsd/conf/files"
    if not conf.is_file():
        print("conffiles: %s missing" % conf)
        return 1

    text = conf.read_text()
    if ANCHOR not in text:
        print("conffiles: anchor missing, entries not added")
        return 1

    added = []
    block = ANCHOR
    dropped = []
    for entry in ENTRIES:
        name = entry.split("\t")[0]
        if not (tree / ".cache/xnu-work" / name).is_file():
            if name in text:
                lines = [ln for ln in text.splitlines() if ln.split("\t")[0] != name]
                text = "\n".join(lines) + "\n"
                dropped.append(name)
            continue
        if name in text:
            continue
        block = block + "\n" + entry
        added.append(name)

    if dropped:
        print("conffiles: dropped absent %s" % ", ".join(dropped))
    if not added:
        if dropped:
            conf.write_text(text)
        print("conffiles: all entries already listed")
        return 0

    conf.write_text(text.replace(ANCHOR, block, 1))
    print("conffiles: listed %s" % ", ".join(added))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
