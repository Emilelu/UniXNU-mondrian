#!/usr/bin/env python3
"""Define the SPI availability family in a fakeroot whose Availability.h predates it.

The iOS 27 XNU headers use `__SPI_AVAILABLE(...)`. The fakeroot this line seeds is
assembled from a Darwin-24 era Availability.h, so the coverage runtime stopped at

    libsyscall/wrappers/gethostuuid.h:41: error: expected function body after
    function declarator

An undefined `__SPI_AVAILABLE(...)` is not "no attribute": it is a function
declarator followed by a parenthesised list, which is a parse error. Defining the
family empty is correct because availability attributes carry no codegen.

This is deliberately *not* a framework patch: the same argument list is rewritten
by `patches/unixnu-core/linux-arm64e-target.patch`, and two patches touching one
list make whichever applies second fail (P-155 family). The fakeroot is a product
of the build, so it is repaired at the point it is created.

    python3 scripts/fix-fakeroot-availability.py <fakeroot> [--check]

Exit: 0 = every Availability.h now defines the family (or already did),
1 = still missing after the edit, 2 = no Availability.h found (wrong path).
"""
from __future__ import annotations

import sys
from pathlib import Path

MACROS = ("__SPI_AVAILABLE", "__SPI_DEPRECATED", "__SPI_DEPRECATED_WITH_REPLACEMENT")

BLOCK = """

/* Added by scripts/fix-fakeroot-availability.py: this fakeroot's Availability.h
   predates the SPI availability family, and the iOS 27 XNU headers use it. An
   undefined macro of this shape is a parse error, not a missing attribute. */
#ifndef __SPI_AVAILABLE
#define __SPI_AVAILABLE(...)
#endif
#ifndef __SPI_DEPRECATED
#define __SPI_DEPRECATED(...)
#endif
#ifndef __SPI_DEPRECATED_WITH_REPLACEMENT
#define __SPI_DEPRECATED_WITH_REPLACEMENT(...)
#endif
"""


def availability_headers(fakeroot: Path) -> list[Path]:
    roots = [
        fakeroot / "usr/include",
        fakeroot / "System/Library/Frameworks",
    ]
    found: list[Path] = []
    for root in roots:
        if root.is_dir():
            found.extend(p for p in root.rglob("Availability.h") if p.is_file())
            found.extend(p for p in root.rglob("AvailabilityMacros.h") if p.is_file())
    return sorted(set(found))


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip().splitlines()[-3], file=sys.stderr)
        return 2
    fakeroot = Path(argv[0])
    check_only = "--check" in argv
    headers = availability_headers(fakeroot)
    if not headers:
        print(f"fix-fakeroot-availability: no Availability.h under {fakeroot}", file=sys.stderr)
        return 2

    edited, already, missing = [], [], []
    for header in headers:
        text = header.read_text(encoding="utf-8", errors="replace")
        if "__SPI_AVAILABLE" in text:
            already.append(header)
            continue
        if check_only:
            missing.append(header)
            continue
        header.write_text(text.rstrip("\n") + "\n" + BLOCK, encoding="utf-8")
        edited.append(header)

    for header in edited:
        print(f"defined the SPI availability family in {header}")
    if already:
        print(f"already present in {len(already)} header(s)")
    if missing:
        for header in missing:
            print(f"MISSING {header}", file=sys.stderr)
        return 1
    if check_only and not missing:
        print("check: every Availability.h defines the SPI availability family")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
