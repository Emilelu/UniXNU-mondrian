#!/usr/bin/env python3
"""Check that a build tree has the environment the kernel build needs (P-185).

`git worktree` isolates code, not environment. A fresh checkout therefore fails
at `xcodebuild: command not found` or `Availability.h file not found` — neither
of which is a code defect. This check names the missing piece and how to get it,
before a 13-minute build discovers it.

Usage:
  python3 scripts/check-build-env.py                  # default trees
  K60_BUILD_TREE=... K60_OUT=... python3 scripts/check-build-env.py

Exit 0 = the tree can build. Exit 1 = something is missing (and printed).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("K60_REPO") or Path(__file__).resolve().parents[1])
# The framework checkout sits next to this one; K60_FRAMEWORK_REPO moves it (hard-39).
FW_REPO = Path(os.environ.get("K60_FRAMEWORK_REPO") or REPO.parent / "UniXNU")

BUILD = Path(os.environ.get("K60_BUILD_TREE", "/opt/k60/trees/k60build"))
OUT = Path(os.environ.get("K60_OUT", str(BUILD / "out-baseline")))


def os_profile() -> str:
    """The OS profile board.toml selects, so the gate grades the tree the build uses.

    P-206 was "do not hardcode the board directory"; this is the same defect one
    level up: the *profile* directory was hardcoded to iOS 16.6.1, so after the
    branch moved to iOS 27.0.1 the gate inspected a tree nobody builds (P-256).
    """
    import tomllib

    fallback = "ipados-16.6.1-20G81"
    path = Path(os.environ.get("K60_REPO") or Path(__file__).resolve().parents[1]) / "board.toml"
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, ValueError):
        return fallback
    profile = data.get("board", {}).get("os_profile")
    return profile if isinstance(profile, str) and profile else fallback


def find_board_dir(out: Path) -> Path | None:
    """Locate the board dir instead of assuming it is named 'mondrian'.

    The board dir is named after the defconfig (mondrian vs mondrian_wifi), so a
    hardcoded path silently checks the wrong tree: the wifi line's fresh
    mondrian_wifi tree failed its first build with 'Availability.h file not
    found' while this gate kept grading the old mondrian tree and staying green
    (P-206). Prefer the newest board dir that actually has a build layout; the
    legacy literal is the fallback, not the default.
    """
    candidates = [
        cand for cand in sorted(out.glob(f"*/{os_profile()}/*"),
                                key=lambda p: p.stat().st_mtime, reverse=True)
        if (cand / "tree").is_dir() or (cand / ".config").is_file()
    ]
    if candidates:
        return candidates[0]
    literal = out / "mondrian" / os_profile() / "mondrian"
    return literal if literal.is_dir() else None


M = find_board_dir(OUT) or OUT / "mondrian" / os_profile() / "mondrian"
FAKEROOT = M / "tree/.cache/fakeroot"

# The Darwin tools Linux does not have. `xcodebuild` is the one that fails last
# and most confusingly (a bare 127 inside build-firehose.sh).
SHIMS = [
    "TargetConditionals.h", "cc", "clang", "clang++", "codesign", "gm4",
    "iig-port-darwin-target.patch", "install", "llvm-xnu-builtin-type.patch",
    "plutil", "prepare-xnu.py", "setup-toolchain.py", "xcrun",
]
# Written by build-firehose.sh / the XNU headers, not by the repository.
# Measured 2026-11-15 on a fresh mondrian_wifi tree (P-206): all five are
# absent right after seeding, and the first build dies on Availability.h
# before it can self-heal the two firehose files.
FAKEROOT_FILES = [
    "usr/local/lib/kernel/libfirehose_kernel.a",
    "usr/local/include/kernel/os/firehose_buffer_private.h",
    "usr/include/Availability.h",
    "usr/include/AvailabilityInternal.h",
    "usr/include/TargetConditionals.h",
]


def main() -> int:
    problems: list[str] = []

    shims = BUILD / "scripts/linux"
    if not shims.is_dir():
        problems.append(
            "{} is missing: the Darwin tool shims are not in the device repo.\n"
            "    fix: python3 scripts/sync-device-input.py "
            "(FRAMEWORK_PAIRS covers scripts/linux)".format(shims)
        )
    else:
        have = {p.name for p in shims.iterdir() if p.is_file()}
        for name in SHIMS:
            if name not in have:
                problems.append("{} is missing (Darwin tool shim)".format(shims / name))
        if len(have) < len(SHIMS):
            problems.append(
                "{} has {} of {} shims; copy the rest from {}".format(
                    shims, len(have), len(SHIMS), FW_REPO / "scripts/linux"
                )
            )

    if not FAKEROOT.is_dir():
        problems.append(
            "{} is missing: this output tree has never been built.\n"
            "    fix: cp -a <known-good out>/.../tree/.cache/fakeroot {}".format(
                FAKEROOT, FAKEROOT
            )
        )
    else:
        for rel in FAKEROOT_FILES:
            if not (FAKEROOT / rel).exists():
                problems.append(
                    "{} is missing (fakeroot is incomplete).\n"
                    "    fix: cp -a <known-good out>/.../tree/.cache/fakeroot/. {}/".format(
                        FAKEROOT / rel, FAKEROOT
                    )
                )

    if problems:
        print("❌ check-build-env: {} cannot build as it stands".format(M))
        for item in problems:
            print("  - {}".format(item))
        print("  P-185: a fresh worktree has the code but not the environment.")
        return 1

    print(
        "✅ check-build-env: {} shims and the fakeroot are in place for {}".format(
            len(SHIMS), M
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
