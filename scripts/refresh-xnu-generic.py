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
    TARGET.write_text(header + body.split("\n", 1)[1], encoding="utf-8")
    print(f"refreshed {TARGET.relative_to(REPO)} from framework {commit}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
