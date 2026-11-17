#!/usr/bin/env python3
"""Host-only gate for the K60 IPA firmware memory pairing (no device, no kernel).

The IPA firmware is an ELF32 QDSP6 image loaded through PAS 15.  The DT pairs
`firmware-names = "ipa_fws"` with the first `memory-regions` phandle, which on
K60 is the 40 KiB ipa_gsi_region at 0x8b910000.  The separate
ipa_fw_region at 0x8b900000 is 64 KiB.  If the sum of every PT_LOAD p_memsz
exceeds 0xa000, a PAS load into the first region can never succeed.

Usage:
    python3 scripts/tests/test-k60-modem-ipa-fw.py --mdt <ipa_fws.mdt>
    python3 scripts/tests/test-k60-modem-ipa-fw.py --selftest

Without arguments the script runs the synthetic self-test, so the host suite
can exercise the parser before the real firmware is available.
"""

import struct
import sys
from pathlib import Path

PT_LOAD = 1
GSI_REGION_SIZE = 0xA000
FW_REGION_SIZE = 0x10000


class ElfError(ValueError):
    pass


def parse_loads(data: bytes):
    if len(data) < 52 or data[:4] != b"\x7fELF":
        raise ElfError("not an ELF file")
    if data[4] != 1 or data[5] != 1:
        raise ElfError("expected ELF32 little-endian")
    e_phoff, = struct.unpack_from("<I", data, 28)
    e_phentsize, e_phnum = struct.unpack_from("<HH", data, 42)
    if e_phentsize < 32:
        raise ElfError("program header entry too small: %d" % e_phentsize)
    if e_phoff + e_phentsize * e_phnum > len(data):
        raise ElfError("program header table outside the file")
    rows = []
    for index in range(e_phnum):
        off = e_phoff + index * e_phentsize
        p_type, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz = \
            struct.unpack_from("<IIIIII", data, off)
        if p_type != PT_LOAD:
            continue
        if p_memsz < p_filesz:
            raise ElfError("segment %d: p_memsz %d < p_filesz %d"
                           % (index, p_memsz, p_filesz))
        rows.append({"index": index, "offset": p_offset, "vaddr": p_vaddr,
                     "paddr": p_paddr, "filesz": p_filesz, "memsz": p_memsz})
    if not rows:
        raise ElfError("no PT_LOAD segments")
    return rows


def classify(total: int) -> str:
    if total <= GSI_REGION_SIZE:
        return "gsi"
    if total <= FW_REGION_SIZE:
        return "fw"
    return "overflow"


def report(rows, total: int) -> int:
    for row in rows:
        print("PT_LOAD %2d paddr=0x%08x filesz=0x%x memsz=0x%x"
              % (row["index"], row["paddr"], row["filesz"], row["memsz"]))
    verdict = classify(total)
    print("PT_LOAD total=0x%x (%d), ipa_gsi_region=0x%x, ipa_fw_region=0x%x"
          % (total, total, GSI_REGION_SIZE, FW_REGION_SIZE))
    if verdict == "gsi":
        print("VERDICT: current DT memory-region (40 KiB ipa_gsi_region) can hold it")
        return 0
    if verdict == "fw":
        print("VERDICT: 40 KiB region is too small; DT must use ipa_fw_region@8b900000")
        return 1
    print("VERDICT: firmware exceeds even the 64 KiB ipa_fw_region")
    return 2


def make_elf(memsz: int) -> bytes:
    """A minimal ELF32 LE with one PT_LOAD header and no payload bytes."""
    buf = bytearray(52 + 32)
    buf[:4] = b"\x7fELF"
    buf[4] = 1  # ELFCLASS32
    buf[5] = 1  # ELFDATA2LSB
    buf[6] = 1  # EV_CURRENT
    struct.pack_into("<HH", buf, 16, 2, 0xA4)  # ET_EXEC, QDSP6
    struct.pack_into("<I", buf, 20, 1)         # e_version
    struct.pack_into("<I", buf, 28, 52)        # e_phoff
    struct.pack_into("<HH", buf, 40, 52, 32)   # e_ehsize, e_phentsize
    struct.pack_into("<H", buf, 44, 1)         # e_phnum
    struct.pack_into("<IIIIII", buf, 52, PT_LOAD, 0, 0, 0, 0, memsz)
    return bytes(buf)


def selftest() -> int:
    failures = 0
    for memsz, want in ((0x9000, "gsi"), (0xC000, "fw"), (0x11000, "overflow")):
        rows = parse_loads(make_elf(memsz))
        got = classify(sum(r["memsz"] for r in rows))
        if got != want:
            print("FAIL memsz=0x%x got %s want %s" % (memsz, got, want))
            failures += 1
    try:
        parse_loads(b"not an elf")
    except ElfError:
        pass
    else:
        print("FAIL malformed input accepted")
        failures += 1
    if failures:
        print("IPA FW LAYOUT: FAIL")
        return 1
    print("IPA FW LAYOUT: PASS (3 synthetic sizes + malformed reject)")
    return 0


def main() -> int:
    if "--selftest" in sys.argv or len(sys.argv) == 1:
        return selftest()
    if "--mdt" not in sys.argv:
        print("usage: %s --mdt <ipa_fws.mdt> | --selftest" % sys.argv[0], file=sys.stderr)
        return 64
    path = Path(sys.argv[sys.argv.index("--mdt") + 1])
    try:
        rows = parse_loads(path.read_bytes())
    except (OSError, ElfError) as error:
        print("ERROR: %s" % error, file=sys.stderr)
        return 66
    return report(rows, sum(row["memsz"] for row in rows))


if __name__ == "__main__":
    raise SystemExit(main())
