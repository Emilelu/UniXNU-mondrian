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

BEGIN = "# K60_PLATFORM_SLEEP_REPORT: begin"
END = "# K60_PLATFORM_SLEEP_REPORT: end"
BLOCK = """
# K60_PLATFORM_SLEEP_REPORT: begin
# The iOS 27 profile is not PONG. A PONG guard compiles both sleep reports
# away and the platform-sleep judge can never see REPORT; keep the switch a
# driver define that the defconfig reaches through XNU_K60_PLATFORM_SLEEP_REPORT.
# Absent means on, matching the patch's own default.
SLEEP_REPORT_MODE=${XNU_K60_PLATFORM_SLEEP_REPORT:-1}
if [ "$SLEEP_REPORT_MODE" != 0 ] && [ "$SLEEP_REPORT_MODE" != 1 ]; then
  echo "XNU_K60_PLATFORM_SLEEP_REPORT must be 0 or 1" >&2
  exit 1
fi
EXTRA_CFLAGS="$EXTRA_CFLAGS -DK60_PLATFORM_SLEEP_REPORT=$SLEEP_REPORT_MODE"
# K60_PLATFORM_SLEEP_REPORT: end
"""
BLOCK = BLOCK.strip("\n")


def with_sleep_switch(text: str) -> str:
    lines = text.split("\n")
    if BEGIN in lines and END in lines:
        start = lines.index(BEGIN)
        stop = lines.index(END)
        if stop < start:
            raise SystemExit("sleep-report block ends before it begins")
        del lines[start:stop + 1]
    elif BEGIN in lines or END in lines:
        raise SystemExit("sleep-report block is only half present")
    anchors = [i for i, line in enumerate(lines)
               if line.startswith("EXTRA_CFLAGS=") and "XNU_EXTRA_CFLAGS" in line]
    if len(anchors) != 1:
        raise SystemExit(f"expected one EXTRA_CFLAGS anchor, found {len(anchors)}")
    lines[anchors[0] + 1:anchors[0] + 1] = BLOCK.split("\n")
    return "\n".join(lines)


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
    TARGET.write_text(with_sleep_switch(header + body.split("\n", 1)[1]), encoding="utf-8")
    print(f"refreshed {TARGET.relative_to(REPO)} from framework {commit}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
