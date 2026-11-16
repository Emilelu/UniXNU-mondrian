#!/usr/bin/env python3
"""Generate the C array for the PAS metadata page.

The blob is the ELF header and hash section of modem.mdt, built by
scripts/build-modem-metadata.py.  It is embedded in ImageCarrierLib rather
than shipped in the payload because the framework's payload step copies only
the names listed in MODEM_MANIFEST; a 28th file would need a framework change.
"""

import argparse
import hashlib
import pathlib
import zlib


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("blob", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    args = parser.parse_args()

    data = args.blob.read_bytes()
    if len(data) != 5884:
        raise SystemExit(f"{args.blob}: {len(data)} bytes, expected 5884")
    if data[:4] != b"\x7fELF":
        raise SystemExit(f"{args.blob}: not an ELF header")

    digest = hashlib.sha256(data).hexdigest()
    crc = zlib.crc32(data) & 0xFFFFFFFF
    lines = [
        "/** @file",
        "  Generated from modem-metadata.bin; do not edit by hand.",
        "",
        f"  size    {len(data)}",
        f"  crc32   0x{crc:08x}",
        f"  sha256  {digest}",
        "",
        "  Regenerate with k60-cellular scripts/gen-modem-metadata-header.py.",
        "**/",
        "",
        "#ifndef K60_MODEM_METADATA_H_",
        "#define K60_MODEM_METADATA_H_",
        "",
        f"#define K60_MODEM_METADATA_BYTES  {len(data)}U",
        "",
        "STATIC CONST UINT8  gK60ModemMetadata[] = {",
    ]
    for offset in range(0, len(data), 12):
        chunk = data[offset:offset + 12]
        lines.append("  " + ", ".join(f"0x{byte:02x}" for byte in chunk) + ",")
    lines += ["};", "", "#endif", ""]
    args.output.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"{args.output}: {len(data)} bytes crc32 0x{crc:08x} sha256 {digest[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
