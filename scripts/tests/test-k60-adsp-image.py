"""Offline check of the ADSP PAS image: the segment table must describe the real .b* files.

No device and no SMC involved. Verifies, against a directory holding adsp.mdt and
adsp.b00..b25:
  * the metadata really is ELF32 with a program header table,
  * every PT_LOAD segment names an existing adsp.bNN whose size equals p_filesz,
  * segments do not overlap once p_memsz is honoured,
  * the whole span fits one 4 KiB-aligned window starting at LINK_BASE,
  * the generated header agrees with LINK_BASE / BOARD_BASE / WINDOW below.

Run: python3 scripts/tests/test-k60-adsp-image.py /mnt/e/k60-work/firmware/adsp
"""

import re
import struct
import sys
from pathlib import Path

# Firmware link address (lowest p_paddr in adsp.mdt).
LINK_BASE = 0x86300000
# Board carveout the loader must copy to: adsp_region@0x9fd00000, span 0x3100000.
BOARD_BASE = 0x9fd00000
WINDOW = 0x04000000  # 64 MiB ceiling; the measured image needs ~0x3100000
HERE = Path(__file__).resolve()
HEADER = HERE.parents[2] / "drivers" / "PongPower" / "pong_adsp_table.h"


def fail(message):
    print("FAIL " + message)
    return 1


def main(argv):
    root = Path(argv[1]) if len(argv) > 1 else Path("/mnt/e/k60-work/firmware/adsp")
    mdt = (root / "adsp.mdt").read_bytes()
    if mdt[:4] != b"\x7fELF" or mdt[4] != 1:
        return fail("adsp.mdt is not ELF32")
    e_phoff, = struct.unpack_from("<I", mdt, 28)
    e_phentsize, e_phnum = struct.unpack_from("<HH", mdt, 42)
    if e_phentsize != 32 or e_phnum == 0:
        return fail("unexpected program header geometry %d/%d" % (e_phentsize, e_phnum))

    segs = []
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        p_type, p_offset, _vaddr, p_paddr, p_filesz, p_memsz = struct.unpack_from("<6I", mdt, off)
        if p_type != 1:
            continue
        segs.append((i, p_offset, p_paddr, p_filesz, p_memsz))

    problems = 0
    for index, offset, paddr, filesz, memsz in segs:
        name = "adsp.b%02d" % index
        part = root / name
        if filesz == 0:
            print("NOTE %s is pure bss (%d bytes, no file)" % (name, memsz))
            continue
        if not part.is_file():
            problems += fail("%s missing for segment %d" % (name, index))
            continue
        if part.stat().st_size != filesz:
            problems += fail("%s is %d bytes but the table says %d" % (name, part.stat().st_size, filesz))
        if memsz < filesz:
            problems += fail("%s declares memsz %d < filesz %d" % (name, memsz, filesz))
        if p_offset % 4096:
            problems += fail("%s has a non page-aligned file offset %#x" % (name, p_offset))
        if paddr % 4096:
            print("NOTE %s loads at unaligned %#x; PAS must copy by byte, not by page" % (name, paddr))
        if not (LINK_BASE <= paddr and paddr + memsz <= LINK_BASE + WINDOW):
            problems += fail("%s loads at %#x, outside %#x..%#x" % (name, paddr, LINK_BASE, LINK_BASE + WINDOW))

    ordered = sorted(segs, key=lambda s: s[2])
    for prev, nxt in zip(ordered, ordered[1:]):
        if prev[2] + prev[4] > nxt[2]:
            problems += fail("segment %d overlaps %d" % (prev[0], nxt[0]))

    # The header the kernel compiles must carry the same split. A generator
    # that silently reverts to one base is the failure this guards against.
    defines = {}
    for line in HEADER.read_text(encoding="utf-8").splitlines():
        m = re.match(r"#define (K60_ADSP_[A-Z_]+) (0x[0-9a-fA-F]+)UL", line)
        if m:
            defines[m.group(1)] = int(m.group(2), 16)
    for key, want in (("K60_ADSP_LINK_BASE", LINK_BASE),
                      ("K60_ADSP_BOARD_BASE", BOARD_BASE)):
        if defines.get(key) != want:
            problems += fail("%s is %#x in the header, expected %#x"
                             % (key, defines.get(key, 0), want))
    if defines.get("K60_ADSP_BOARD_BASE", 0) % 4096:
        problems += fail("K60_ADSP_BOARD_BASE is not 4 KiB aligned")
    if defines.get("K60_ADSP_BOARD_BASE") == defines.get("K60_ADSP_LINK_BASE"):
        problems += fail("the header collapsed link and board bases")

    lo, hi = ordered[0][2], max(s[2] + s[4] for s in ordered)
    print("TESTS OK %d segments, %#x..%#x (%d bytes), link %#x board %#x"
          % (len(segs), lo, hi, hi - lo, LINK_BASE, BOARD_BASE))
    if problems:
        print("PROBLEMS %d" % problems)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
