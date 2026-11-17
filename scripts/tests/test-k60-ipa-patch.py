#!/usr/bin/env python3
"""Offline guard for patch 0623: it must carry the exact PongCellular IPA M0 files.

The build consumes the patch, not drivers/PongCellular, so a stale patch would
silently compile a different skeleton. This gate mirrors the modem image gate.
"""

import pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]
PATCH = REPO / "patches/xnu/0623-k60-ipa.patch"
SERIES = REPO / "patches/xnu/series"
CONFFILES = REPO / "scripts/append-conffiles.py"


def added_lines(patch: str, target: str) -> str:
    collecting = False
    out = []
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            collecting = line.endswith(" b/" + target)
            continue
        if not collecting:
            continue
        if line.startswith(("+++ ", "--- ", "@@ ", "index ", "new file mode ")):
            continue
        if line.startswith("+"):
            out.append(line[1:])
    return "\n".join(out) + ("\n" if out else "")


def fail(message: str) -> int:
    print("FAIL " + message)
    return 1


def main() -> int:
    if not PATCH.is_file():
        return fail("patch 0623 is missing")
    patch = PATCH.read_text()
    header = (REPO / "drivers/PongCellular/K60Ipa.h").read_text()
    source = (REPO / "drivers/PongCellular/K60Ipa.c").read_text()
    source = source.replace('#include "K60Ipa.h"', '#include "pong_ipa.h"')

    if added_lines(patch, "bsd/dev/pong_ipa.h") != header:
        return fail("pong_ipa.h differs from K60Ipa.h")
    if added_lines(patch, "bsd/dev/pong_ipa.c") != source:
        return fail("pong_ipa.c differs from K60Ipa.c")
    if "0623-k60-ipa.patch" not in SERIES.read_text().splitlines():
        return fail("0623 is not in patches/xnu/series")
    if "bsd/dev/pong_ipa.c" not in CONFFILES.read_text():
        return fail("append-conffiles.py has no pong_ipa.c entry")
    print("K60 IPA PATCH PASS 0623 carries pong_ipa.h and pong_ipa.c")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
