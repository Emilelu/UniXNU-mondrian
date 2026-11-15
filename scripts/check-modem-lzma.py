#!/usr/bin/env python3
"""Check the LZMA payload files the modem carrier reads at boot.

Route D stores one .lzma file per firmware segment under
EFI/UniXNU/MODEM.  The firmware decompresses each file straight into the
modem window, so the gate has to prove three things before a boot is worth
attempting:

* every file is a LZMA-alone stream (5 B properties + 8 B declared size),
* the declared size equals the segment table's bytes for that segment,
* the properties byte is the one the compressor actually used (0x5D here),
  because a re-encoded stream would still decompress but no longer match the
  table the firmware validates against.

The tool reads the manifest produced by scripts/gen-modem-table.py
--manifest (one "name bytes" pair per line) and the extracted payload
directory, and prints one line per file.  Exit status is 0 only when every
file passes.

Usage:
    check-modem-lzma.py --dir DIR --manifest FILE [--sum]

--sum prints the total declared size, which must equal the copied number in
the boot log (109060761 for the current firmware).
"""

import argparse
import sys
from pathlib import Path

LZMA_HEADER_BYTES = 13
LZMA_PROPS_BYTES = 5
LZMA_SIZE_BYTES = 8
LZMA_PROPERTIES = 0x5D
UNKNOWN_SIZE = 0xFFFFFFFFFFFFFFFF
MAX_UINT32 = 0xFFFFFFFF


def read_manifest(path):
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            raise SystemExit("manifest line %d: expected name and bytes, got %r" % (number, line))
        name, size = parts
        rows.append((name, int(size, 0)))
    return rows


def check_file(path, expected_bytes):
    """Return (ok, message, declared) for one .lzma file."""
    data = path.read_bytes()
    if len(data) < LZMA_HEADER_BYTES:
        return False, "short file (%d B, header needs %d)" % (len(data), LZMA_HEADER_BYTES), None
    if data[0] != LZMA_PROPERTIES:
        return False, "properties %#04x, expected %#04x" % (data[0], LZMA_PROPERTIES), None
    declared = int.from_bytes(data[LZMA_PROPS_BYTES:LZMA_HEADER_BYTES], "little")
    if declared == UNKNOWN_SIZE:
        return False, "declared size is UNKNOWN (rewrite the 8 B field)", None
    if declared > MAX_UINT32:
        return False, "declared size %d exceeds UINT32" % declared, None
    if declared != expected_bytes:
        return False, "declared %d, table says %d" % (declared, expected_bytes), declared
    if len(data) <= LZMA_HEADER_BYTES:
        return False, "no payload after the header", declared
    return True, "ok", declared


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", required=True, type=Path, help="directory holding the extracted .lzma files")
    parser.add_argument("--manifest", required=True, type=Path, help="manifest from gen-modem-table.py --manifest")
    parser.add_argument("--sum", action="store_true", help="print the total declared size")
    args = parser.parse_args(argv)

    rows = read_manifest(args.manifest)
    if not rows:
        print("FAIL: manifest is empty")
        return 1

    failures = 0
    total = 0
    for name, expected in rows:
        path = args.dir / (name + ".lzma")
        if not path.is_file():
            print("FAIL %-14s missing" % path.name)
            failures += 1
            continue
        ok, message, declared = check_file(path, expected)
        if ok:
            total += declared
        else:
            failures += 1
        print("%s %-14s %s" % ("ok  " if ok else "FAIL", path.name, message))

    expected_names = {name + ".lzma" for name, _ in rows}
    for path in sorted(args.dir.iterdir()):
        if path.is_file() and path.suffix == ".lzma" and path.name not in expected_names:
            print("FAIL %-14s not in manifest" % path.name)
            failures += 1

    print("files=%d failures=%d" % (len(rows), failures))
    if args.sum:
        print("declared-total=%d" % total)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
