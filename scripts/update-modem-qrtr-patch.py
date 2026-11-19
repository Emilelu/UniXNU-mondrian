#!/usr/bin/env python3
"""Regenerate the new-file hunks of 0622 from the local driver sources.

0622-k60-modem-qrtr.patch carries copies of five drivers/ files under bsd/dev/.
The kernel compiles the copies, while the host tests and the hardware-proven
build compile the originals, so the two must stay byte-identical apart from the
include names. 0622 keeps a private copy of the GLINK stack under the
k60m_glink_ prefix because the battery archive force-loads QcomGlink.o into the
same image and a second copy of qcom_glink_* fails the link (P-190).

scripts/tests/test-k60-modem-image.py compares the copies, but nothing
regenerated them: a source edit silently produced a kernel that ran a different
QRTR path than the one tested. This script rebuilds the five new-file hunks from
the sources, so the copies cannot drift again.

    python3 scripts/update-modem-qrtr-patch.py          # rewrite in place
    python3 scripts/update-modem-qrtr-patch.py --check   # fail if stale
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PATCH = REPO / "patches/xnu/0622-k60-modem-qrtr.patch"

# Every carried copy renames qcom_glink_ to k60m_glink_ (P-190), including
# QcomGlink.h/.c themselves; scripts/tests/test-k60-modem-image.py applies the
# same replacement to all five files before comparing.
RENAME = ("qcom_glink_", "k60m_glink_")

# The carried GLINK stack once diverged from drivers/PongPower/QcomGlink.c by
# one line.  On the k35 B flight the modem advertised its IPCRTR receive
# intents with ids starting at 0:
#     cmd=0x5 p1=0x1 p2=0x1 w2=0x80 w3=0x0   (next frame: w6=0x80 w7=0x1)
# Linux's qcom_glink_handle_intent() stores id 0 (idr_alloc(id, id + 1)) and
# hakios stores every pair unvalidated, so zero is a legal buffer number;
# calling it corruption stalled the handshake at poll 2.  The charger line has
# since adopted the fix on its own terms (QcomGlink.c:408 drops the placeholder
# and keeps the rest of the frame: `if (!size) {g->dropped++; continue;}`).
# The delta below therefore carries the adopted semantics into the pre-adoption
# file: an empty intent is dropped and the frame keeps being decoded, which is
# what scripts/tests/test-k60-glink-intent.py measures (the intent after the
# empty one must still be stored).  Once the source contains the adopted line
# the generator skips it, and the carried copy is the same bytes as
# drivers/PongPower/QcomGlink.c.  Delete this delta when the branch has rebased
# onto the merged line.
DELTA = {
    "drivers/PongPower/QcomGlink.c": (
        "            if (!size || !id) return QcomGlinkCorrupt;",
        "            if (!size) {g->dropped++; continue;}  /* id 0 is legal; an empty intent carries nothing */",
    ),
}

# What drivers/PongPower/QcomGlink.c looks like once the owning line adopts the
# fix (power line, commit 142706ad).  Its presence means the delta is spent.
ADOPTED = "if (!size) {g->dropped++; continue;}"

# (local source, carried path, {local include: carried include})
FILES = [
    ("drivers/PongCellular/K60ModemQrtr.h", "bsd/dev/pong_modem_qrtr.h", {}),
    ("drivers/PongCellular/K60ModemQrtr.c", "bsd/dev/pong_modem_qrtr.c",
     {'"K60ModemQrtr.h"': '"pong_modem_qrtr.h"'}),
    ("drivers/PongPower/QcomGlink.h", "bsd/dev/qcom_glink.h", {}),
    ("drivers/PongPower/QcomGlink.c", "bsd/dev/qcom_glink.c",
     {'"QcomGlink.h"': '"qcom_glink.h"'}),
    ("drivers/PongCellular/K60ModemLink.c", "bsd/dev/pong_modem_link.c",
     {'"K60ModemQrtr.h"': '"pong_modem_qrtr.h"', '"K60ModemRmtfs.h"': '"pong_modem_rmtfs.h"',
      '"K60ModemEfs.h"': '"pong_modem_efs.h"',
      '"K60Smem.h"': '"pong_smem.h"', '"QcomGlink.h"': '"qcom_glink.h"',
      '"K60PmicRail.h"': '"pong_pmic_rail.h"', '"K60ModemPas.h"': '"pong_modem_pas.h"'}),
    ("drivers/PongCellular/K60ModemRmtfs.h", "bsd/dev/pong_modem_rmtfs.h", {}),
    ("drivers/PongCellular/K60ModemRmtfs.c", "bsd/dev/pong_modem_rmtfs.c",
     {'"K60ModemRmtfs.h"': '"pong_modem_rmtfs.h"'}),
    ("drivers/PongCellular/K60ModemEfs.h", "bsd/dev/pong_modem_efs.h",
     {'"K60ModemRmtfs.h"': '"pong_modem_rmtfs.h"'}),
    ("drivers/PongCellular/K60ModemEfs.c", "bsd/dev/pong_modem_efs.c",
     {'"K60ModemEfs.h"': '"pong_modem_efs.h"', '"K60ModemRmtfs.h"': '"pong_modem_rmtfs.h"'}),
]


def body(source: Path, renames: dict) -> list:
    text = source.read_text(encoding="utf-8")
    if "\r" in text:
        sys.exit("%s has CR characters; the series is LF-only" % source)
    for old, new in renames.items():
        text = text.replace(old, new)
    text = text.replace(RENAME[0], RENAME[1])
    key = source.resolve().relative_to(REPO).as_posix()
    if key in DELTA:
        old, new = DELTA[key]
        if text.count(old) == 1:
            text = text.replace(old, new)
        elif ADOPTED in text:
            pass  # the owning line fixed it; the carried copy needs no delta
        else:
            sys.exit("%s: neither the pre-adoption line nor the adopted fix is "
                     "present; re-read the source before regenerating" % key)
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith('#include "K60') or stripped.startswith('#include "Qcom'):
            sys.exit("%s carries an include the renames leave behind: %s"
                     % (source.name, stripped))
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
    # A file added to FILES after the patch was first written still needs its
    # own new-file section; append it instead of failing the run.
    for source, carried, renames in FILES:
        if carried in seen:
            continue
        rebuilt.append(section_for(carried, body(REPO / source, renames)))
        seen.add(carried)
    missing = [c for _, c, _ in FILES if c not in seen]
    if missing:
        sys.exit("these carried files are not in %s: %s"
                 % (PATCH.name, ", ".join(missing)))
    new_text = "".join(rebuilt)
    if new_text == original:
        print("0622 OK: the carried files match the sources")
        return 0
    if args.check:
        sys.exit("0622 is stale; run scripts/update-modem-qrtr-patch.py")
    PATCH.write_bytes(new_text.encode("utf-8"))
    print("0622 rewritten: %d files, %d bytes" % (len(seen), len(new_text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())