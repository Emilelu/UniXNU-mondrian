#!/usr/bin/env python3
"""Regenerate the new-file hunks of 0621 from the local driver sources.

0621-k60-modem-pas.patch carries copies of three drivers/PongCellular files
under bsd/dev/. The kernel compiles the copies, while the host tests compile
the originals, so the two must be byte-identical apart from the include names.
scripts/tests/test-k60-modem-image.py compares them, but nothing regenerates
them: a hand-edited line count already made the patch unappliable once (the
header hunk said 113 lines for a 112-line file). This script rebuilds the three
new-file hunks from the sources, so the count cannot drift again. The
kern_exec.c call-site hunk is left untouched -- it is context-relative to
patches applied earlier in the series.

    python3 scripts/update-modem-pas-patch.py          # rewrite in place
    python3 scripts/update-modem-pas-patch.py --check   # fail if stale
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PATCH = REPO / "patches/xnu/0621-k60-modem-pas.patch"

# (local source, carried path, {local include: carried include})
FILES = [
    ("drivers/PongCellular/K60ModemPas.h", "bsd/dev/pong_modem_pas.h", {}),
    ("drivers/PongCellular/K60ModemPas.c", "bsd/dev/pong_modem_pas.c",
     {'"K60ModemPas.h"': '"pong_modem_pas.h"'}),
    ("drivers/PongCellular/K60ModemBoot.c", "bsd/dev/pong_modem_boot.c",
     {'"K60ModemPas.h"': '"pong_modem_pas.h"',
      '"K60ModemImage.h"': '"pong_modem_image.h"'}),
]


def body(source: Path, renames: dict) -> list:
    text = source.read_text(encoding="utf-8")
    if "\r" in text:
        sys.exit("%s has CR characters; the series is LF-only" % source)
    for old, new in renames.items():
        text = text.replace(old, new)
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def section_for(path: str, lines: list) -> str:
    head = [
        "diff --git a/%s b/%s" % (path, path),
        "new file mode 100644",
        "index 0000000..1111111",
        "--- /dev/null",
        "+++ b/%s" % path,
        "@@ -0,0 +1,%d @@" % len(lines),
    ]
    head.extend("+" + line for line in lines)
    return "\n".join(head) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="report drift instead of rewriting")
    args = parser.parse_args()

    if not PATCH.is_file():
        sys.exit("%s missing" % PATCH)
    original = PATCH.read_text(encoding="utf-8")
    # The call-site hunk has no "diff --git" header of its own: it follows the
    # last new file directly, so it is preserved as the tail verbatim.
    tail_at = original.find("\n--- a/bsd/kern/kern_exec.c\n")
    if tail_at < 0:
        sys.exit("%s has no kern_exec.c hunk" % PATCH.name)
    tail_at += 1
    original, tail = original[:tail_at], original[tail_at:]
    sections = original.split("diff --git ")
    rebuilt = [sections[0]]
    seen = set()
    for section in sections[1:]:
        target = section.split("\n", 1)[0].split(" b/")[-1].strip()
        replacement = None
        for source, carried, renames in FILES:
            if target == carried:
                replacement = section_for(carried, body(REPO / source, renames))
                seen.add(carried)
                break
        rebuilt.append(replacement if replacement is not None
                       else "diff --git " + section)
    missing = [c for _, c, _ in FILES if c not in seen]
    if missing:
        sys.exit("these carried files are not in %s: %s"
                 % (PATCH.name, ", ".join(missing)))
    new_text = "".join(rebuilt) + tail
    if new_text == PATCH.read_text(encoding="utf-8"):
        print("0621 OK: the carried files match the sources")
        return 0
    if args.check:
        sys.exit("0621 is stale; run scripts/update-modem-pas-patch.py")
    PATCH.write_bytes(new_text.encode("utf-8"))
    print("0621 rewritten: %d files, %d bytes" % (len(seen), len(new_text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
