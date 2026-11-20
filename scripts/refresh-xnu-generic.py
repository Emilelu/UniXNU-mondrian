#!/usr/bin/env python3
"""Refresh scripts/build-xnu-generic.sh from a UniXNU checkout.

    python3 scripts/refresh-xnu-generic.py [UniXNU checkout]

The vendored copy exists because a device file named build-xnu-4k-baseline.sh
shadows the framework's builder in the assembled tree (P-255). Run this after
updating the framework so the two do not drift.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TARGET = REPO / "scripts" / "build-xnu-generic.sh"


EARLY_HOOK = """
# K60: conf/files entries for in-tree drivers cannot be anchored in a patch (P-171);
# the build driver supplies a hook that runs after every patch is applied.
if [ -n "${K60_CONF_FILES_HOOK:-}" ] && [ -f "${K60_CONF_FILES_HOOK}" ]; then
  python3 "${K60_CONF_FILES_HOOK}" "$ROOT" || echo "K60: conf/files hook failed"
fi
"""

LATE_HOOK_ANCHOR = 'EXTRA_CFLAGS="$EXTRA_CFLAGS -DXNU_BOOT_PROGRESS=$BOOT_PROGRESS"\n'

LATE_HOOK_BLOCK = """
# K60: conf/files entries for in-tree drivers cannot be anchored in a patch
# (P-171), and this call has to run here rather than at the top of the file: at
# the top .cache/xnu-work does not exist yet, so every appender reports "tree not
# seeded" and the failure reads as a log line instead of a missing driver.
if [ -n "${K60_CONF_FILES_HOOK:-}" ] && [ -f "${K60_CONF_FILES_HOOK}" ]; then
  python3 "${K60_CONF_FILES_HOOK}" "$ROOT" || {
    echo "build-xnu: conf-files hook failed" >&2
    exit 1
  }
fi
"""


def main(argv: list[str]) -> int:
    framework = Path(argv[1]) if len(argv) > 1 else REPO.parent / "UniXNU"
    source = framework / "scripts" / "build-xnu-4k-baseline.sh"
    if not source.is_file():
        print(f"no framework builder at {source}", file=sys.stderr)
        return 2
    commit = subprocess.run(["git", "-C", str(framework), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip() or "unknown"
    body = source.read_text(encoding="utf-8")
    header = f"""#!/usr/bin/env bash
# Verbatim copy of the UniXNU generic kernel builder (framework {commit}).
#
# It is vendored under a different name because a device file named
# build-xnu-4k-baseline.sh shadows the framework's copy in the assembled tree,
# and the iOS 27 line needs that generic builder while the 16.6.1 line needs the
# Pong one. scripts/pick-xnu-builder.sh chooses; scripts/tests/test-build-xnu-
# dispatch.py drives it. Refresh with scripts/refresh-xnu-generic.py.
"""
    merged = header + body.split("\n", 1)[1]
    # The framework calls K60_CONF_FILES_HOOK at the top of the file, before
    # .cache/xnu-work is cloned, so every appender reports "tree not seeded" and
    # the driver sources are never listed (P-266). Put the call where the tree
    # exists -- the same place build-xnu-4k-baseline.sh does it.
    if EARLY_HOOK in merged:
        merged = merged.replace(EARLY_HOOK, "\n", 1)
    if merged.count(LATE_HOOK_ANCHOR) != 1:
        raise SystemExit(f"refresh-xnu-generic: no single EXTRA_CFLAGS anchor in {source}")
    merged = merged.replace(LATE_HOOK_ANCHOR, LATE_HOOK_BLOCK + LATE_HOOK_ANCHOR, 1)
    TARGET.write_text(merged, encoding="utf-8")
    print(f"refreshed {TARGET.relative_to(REPO)} from framework {commit}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
