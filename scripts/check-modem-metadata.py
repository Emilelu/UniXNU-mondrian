#!/usr/bin/env python3
"""Check the PAS metadata page against the kernel and the UEFI carrier.

The metadata blob is embedded in ImageCarrierLib (K60ModemMetadata.h) rather
than shipped as a 28th payload file: the framework payload step copies only
the names listed in MODEM_MANIFEST, so a payload file would need a framework
change.  This gate pins the blob, proves the two constants agree and proves
the page lies inside ABL staging and below Display Reserved.

Run from the k60-cellular checkout:
    python3 scripts/check-modem-metadata.py
"""

import hashlib
import os
import pathlib
import re
import sys
import zlib

REPO = pathlib.Path(__file__).resolve().parents[1]
UEFI = pathlib.Path(os.environ.get("K60_UEFI_REPO") or REPO.parent / "uefi-mondrian")
KERNEL = REPO / "drivers/PongCellular/K60ModemBoot.c"
LIB = UEFI / "Platforms/Xiaomi/DarwinBootPkg/Library/ImageCarrierLib"
CARRIER = LIB / "ImageCarrierLib.c"
HEADER = LIB / "K60ModemMetadata.h"
INF = LIB / "ImageCarrierLib.inf"

METADATA_ADDRESS = 0xB7FF0000
METADATA_BYTES = 5884
ABL_STAGING_BASE = 0xA8300000
ABL_STAGING_END = 0xB8000000
EXPECTED_CRC32 = 0xAC600B5D
EXPECTED_SHA256 = "78d5f2f45aefeab7d2920bc5753009ade0371aa7d9be5eb0f2d21a72704c1fb8"

failures = []


def check(name, condition, detail=""):
    print(("PASS " if condition else "FAIL ") + name + ((" " + detail) if detail else ""))
    if not condition:
        failures.append(name)


def read(path):
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        check(f"read {path}", False, str(error))
        return ""


def match(text, pattern, name, base=16):
    found = re.search(pattern, text)
    if not found:
        check(name, False, "pattern not found")
        return None
    return int(found.group(1), base)


kernel = read(KERNEL)
carrier = read(CARRIER)
header = read(HEADER)
inf = read(INF)

kernel_address = match(kernel, r"#define\s+K60_MODEM_METADATA\s+0x([0-9A-Fa-f]+)u", "kernel metadata address defined")
kernel_bytes = match(kernel, r"#define\s+K60_MODEM_METADATA_BYTES\s+(\d+)u", "kernel metadata size defined", 10)
uefi_address = match(carrier, r"#define\s+K60_MODEM_METADATA_ADDRESS\s+0x([0-9A-Fa-f]+)ULL", "UEFI metadata address defined")
header_bytes = match(header, r"#define\s+K60_MODEM_METADATA_BYTES\s+(\d+)U", "header metadata size defined", 10)

check("kernel address 0x%08x" % METADATA_ADDRESS, kernel_address == METADATA_ADDRESS, str(kernel_address))
check("kernel size %d" % METADATA_BYTES, kernel_bytes == METADATA_BYTES, str(kernel_bytes))
check("UEFI address 0x%08x" % METADATA_ADDRESS, uefi_address == METADATA_ADDRESS, str(uefi_address))
check("header size %d" % METADATA_BYTES, header_bytes == METADATA_BYTES, str(header_bytes))
check("kernel and UEFI address agree", kernel_address == uefi_address)
check("kernel and header size agree", kernel_bytes == header_bytes)
check("metadata page inside ABL staging", ABL_STAGING_BASE <= METADATA_ADDRESS and METADATA_ADDRESS + METADATA_BYTES <= ABL_STAGING_END)
check("metadata page is 4 KiB aligned", METADATA_ADDRESS % 4096 == 0)

array = re.search(r"gK60ModemMetadata\[\] = \{(.*?)\};", header, re.S)
check("embedded array is present", array is not None)
raw = bytes(int(value, 16) for value in re.findall(r"0x([0-9A-Fa-f]{2})", array.group(1) if array else ""))
check("embedded array length %d" % METADATA_BYTES, len(raw) == METADATA_BYTES, str(len(raw)))
check("embedded array starts with ELF magic", raw[:4] == b"\x7fELF", raw[:4].hex())
check("embedded array crc32 0x%08x" % EXPECTED_CRC32, (zlib.crc32(raw) & 0xFFFFFFFF) == EXPECTED_CRC32, "0x%08x" % (zlib.crc32(raw) & 0xFFFFFFFF))
check("embedded array sha256", hashlib.sha256(raw).hexdigest() == EXPECTED_SHA256, hashlib.sha256(raw).hexdigest()[:16])
check("header is listed in ImageCarrierLib.inf", "K60ModemMetadata.h" in inf)

if failures:
    print(f"\n{len(failures)} failure(s)")
    sys.exit(1)
print("\nMETADATA OK")
