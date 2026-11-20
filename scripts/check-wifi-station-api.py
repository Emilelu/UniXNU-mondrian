#!/usr/bin/env python3
"""Check that the station tree defines every nw_wifi_* symbol the driver calls.

The 24A446 driver and the station archive are built separately: the kext calls
nw_wifi_start/step/connect/power/scan_frequencies/... and the kernel link only
succeeds when the station archive defines them all. The 16.6.1 station answers
nw_wifi_scan(ssid, length), the 24A446 station answers
nw_wifi_scan_frequencies(ssid, length, mhz, count) and adds nw_wifi_power, so a
driver built against the newer header and linked against the older station fails
on exactly those two names. Reading the station sources proves the contract
without building 126 translation units.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

PREFIX = "nw_wifi_"
DEFINITION = re.compile(r"^[A-Za-z_][\w \t\*]*?\b(nw_wifi_\w+)\s*\(", re.MULTILINE)


def undefined_symbols(archive: Path, nm: str) -> set:
    """nw_wifi_* names the archive references but does not define."""
    out = subprocess.check_output([nm, str(archive)], text=True)
    undefined, defined = set(), set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        kind, name = parts[-2], parts[-1].lstrip("_")
        if not name.startswith(PREFIX):
            continue
        if kind in ("U", "u"):
            undefined.add(name)
        elif kind not in ("w", "W", "v", "V"):
            defined.add(name)
    return undefined - defined


def defined_in_station(station: Path) -> set:
    """Function definitions in the station sources, by name."""
    names = set()
    for path in sorted((station / "src").glob("*.c")):
        names |= set(DEFINITION.findall(path.read_text(encoding="utf-8", errors="replace")))
    return names


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kext", type=Path, required=True, help="libPongWifiNative.a")
    p.add_argument("--station", type=Path, required=True, help="station tree with src/*.c")
    p.add_argument("--nm", default="llvm-nm-18")
    a = p.parse_args(argv)
    if not a.kext.is_file():
        print("wifi station api: %s is not a file" % a.kext, file=sys.stderr)
        return 2
    if not (a.station / "src").is_dir():
        print("wifi station api: %s has no src/ directory" % a.station, file=sys.stderr)
        return 2
    try:
        wanted = undefined_symbols(a.kext, a.nm)
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        print("wifi station api: cannot read %s (%s)" % (a.kext, error), file=sys.stderr)
        return 2
    have = defined_in_station(a.station)
    missing = sorted(wanted - have)
    for name in missing:
        print("wifi station api: the station does not define %s" % name, file=sys.stderr)
    print("wifi station api: %d referenced, %d defined by the station, %d missing"
          % (len(wanted), len(wanted & have), len(missing)))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())