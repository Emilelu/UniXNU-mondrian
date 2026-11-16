"""Regenerate patches/xnu/0612-k60-adsp-image.patch from the driver sources.

The kernel patch adds three new files to bsd/dev: the PAS image loader, its
contract and the generated segment table. Keeping one hand-written copy in the
patch and another in the driver is how the two drifted (the patch header had
lost K60AdspPartMissing and K60AdspReadBounds, and both copies disagreed about
what K60_ADSP_BASE means). This script makes the patch a projection of the
drivers; --check turns drift into a gate failure.

Run: python3 scripts/gen-adsp-image-patch.py [--check]
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PATCH = REPO / "patches" / "xnu" / "0612-k60-adsp-image.patch"

FILES = [
    ("drivers/PongPower/K60AdspImage.c", "bsd/dev/pong_adsp_image.c"),
    ("drivers/PongPower/K60AdspImage.h", "bsd/dev/pong_adsp_image.h"),
    ("drivers/PongPower/pong_adsp_table.h", "bsd/dev/pong_adsp_table.h"),
]

# The kernel file may not name a driver header it does not ship.
RENAMES = [
    ('#include "K60AdspImage.h"', '#include "pong_adsp_image.h"'),
]


def body_for(source):
    text = (REPO / source).read_text(encoding="utf-8")
    for old, new in RENAMES:
        text = text.replace(old, new)
    return text.splitlines()


def patch_text():
    lines = []
    for source, target in FILES:
        body = body_for(source)
        lines.append("diff --git a/%s b/%s" % (target, target))
        lines.append("new file mode 100644")
        lines.append("index 0000000..1111111")
        lines.append("--- /dev/null")
        lines.append("+++ b/%s" % target)
        lines.append("@@ -0,0 +1,%d @@" % len(body))
        lines.extend("+" + line for line in body)
    return "\n".join(lines) + "\n"


def main(argv):
    want_check = "--check" in argv[1:]
    text = patch_text()
    if want_check:
        current = PATCH.read_text(encoding="utf-8")
        if current == text:
            print("PATCH OK 0612 matches the driver sources (%d bytes)" % len(text))
            return 0
        have = current.splitlines()
        want = text.splitlines()
        for i in range(max(len(have), len(want))):
            a = have[i] if i < len(have) else "<missing>"
            b = want[i] if i < len(want) else "<missing>"
            if a != b:
                print("PATCH DRIFT at line %d\n  patch: %s\n  driver: %s" % (i + 1, a, b))
                break
        return 1
    PATCH.write_text(text, encoding="utf-8")
    print("wrote %s (%d bytes)" % (PATCH.relative_to(REPO), len(text)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
