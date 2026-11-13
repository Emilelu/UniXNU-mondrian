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

BUILD = Path(os.environ.get("K60_BUILD_TREE", "/opt/k60/trees/k60build"))
OUT = Path(os.environ.get("K60_OUT", str(BUILD / "out-baseline")))


def board_dir(out: Path) -> Path:
    """The directory `unixnu` builds this configuration into.

    It is named after the defconfig, not after the board: `mondrian_defconfig`
    builds into `mondrian/`, `mondrian_wifi_defconfig` into `mondrian_wifi/`.
    Hardcoding `mondrian` made every alternative configuration look like an
    unbuilt tree. Prefer an explicit K60_BOARD_DIR, then the only configured
    candidate, then the historical name.
    """
    explicit = os.environ.get("K60_BOARD_DIR")
    if explicit:
        return Path(explicit)
    candidates = sorted(
        p for p in out.glob("mondrian/ipados-*/*") if p.is_dir() and (p / ".config").is_file()
    )
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        return max(candidates, key=lambda p: (p / ".config").stat().st_mtime)
    return out / "mondrian/ipados-16.6.1-20G81/mondrian"


M = board_dir(OUT)
FAKEROOT = M / "tree/.cache/fakeroot"

# The Darwin tools Linux does not have. `xcodebuild` is the one that fails last
# and most confusingly (a bare 127 inside build-firehose.sh).
SHIMS = [
    "TargetConditionals.h", "cc", "clang", "clang++", "codesign", "gm4",
    "iig-port-darwin-target.patch", "install", "llvm-xnu-builtin-type.patch",
    "plutil", "prepare-xnu.py", "setup-toolchain.py", "xcrun",
]
# Written by build-firehose.sh / the XNU headers, not by the repository.
FAKEROOT_FILES = [
    "usr/local/lib/kernel/libfirehose_kernel.a",
    "usr/include/Availability.h",
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
                "{} has {} of {} shims; copy the rest from "
                "E:/hackios/UniXNU/scripts/linux".format(shims, len(have), len(SHIMS))
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
