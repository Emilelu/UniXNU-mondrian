#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Count the PongWifi symbols a linked kernel actually carries.

A -force_load archive whose objects were compiled out still links: the kernel
builds, the gates stay green, and the image boots without a driver. That is how
a machine-config macro that the 27 line does not define would fail here, so a
successful link is not the pass condition for B2 -- a non-zero PongWifi symbol
count in the linked image is.

    python3 scripts/check-wifi-symbols.py <kernel-image> [--nm <nm>]

Exit 0 when the image defines at least one WiFi symbol, 1 when it defines none,
2 when nm could not read the image.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

# Everything drivers/PongWifi exports keeps one of these stems, across the two
# Apple80211 generations and the station archive the VHCI shim talks to.
SYMBOL = re.compile(r"pong_wifi|PongWifi|pong_kev|pong_scan|pong_assoc|pong_sae")


def parse_nm(text: str) -> dict[str, int]:
    """Count defined symbols per matched stem in nm output."""
    counts: dict[str, int] = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        # "addr T name", "addr t name", "addr D name"; "U name" is undefined.
        kind, name = (fields[0], fields[1]) if len(fields) == 2 else (fields[1], fields[2])
        if kind == "U":
            continue
        if not SYMBOL.search(name):
            continue
        stem = SYMBOL.search(name).group(0)
        counts[stem] = counts.get(stem, 0) + 1
    return counts


def count_symbols(image: str, nm: str) -> dict[str, int]:
    result = subprocess.run([nm, image], capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(2)
    return parse_nm(result.stdout)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Count the PongWifi symbols a kernel carries.")
    parser.add_argument("image", help="linked kernel image (or any Mach-O/archive)")
    parser.add_argument("--nm", default=os.environ.get("K60_NM", "llvm-nm"))
    args = parser.parse_args(argv)
    counts = count_symbols(args.image, args.nm)
    total = sum(counts.values())
    detail = ", ".join(f"{stem}={n}" for stem, n in sorted(counts.items())) or "none"
    print(f"wifi symbols: {total} ({detail})")
    if total == 0:
        print("FAIL: the image carries no PongWifi symbol; -force_load linked nothing", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
