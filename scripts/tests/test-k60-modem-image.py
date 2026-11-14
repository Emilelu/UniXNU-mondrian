"""Offline check of the modem (MSS) PAS image and of the table generated from it.

No device, no SMC, no kernel build. Verifies, against a directory holding
modem.mdt and modem.b00..b31 pulled with 'adb exec-out':

  * the metadata really is ELF32 with 32 program headers, 30 of them PT_LOAD,
  * every PT_LOAD segment with bytes names an existing modem.bNN whose size
    equals p_filesz, and every segment without bytes has no file at all,
  * segments are page aligned, do not overlap once p_memsz is honoured, and the
    span is exactly the mpss_region carveout from the DT,
  * drivers/PongCellular/pong_modem_table.h says the same thing as the firmware,
  * patches/xnu/0620-k60-modem-image.patch carries the same three files the repo
    keeps under drivers/PongCellular/, so the kernel copy cannot drift.

Why the last two matter: the table is the only thing the kernel believes, and the
patch is the only thing the kernel compiles. A host test that only checked the
firmware would pass while both copies were stale.

Run: python3 scripts/tests/test-k60-modem-image.py /mnt/e/k60-work/firmware/modem
"""

import re
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# From the live Android DT: /reserved-memory/mpss_region@8bc00000
MODEM_BASE = 0x8BC00000
WINDOW = 0x13200000          # 306 MiB, exactly the DT reg value
EXPECTED_LOAD = 30
EXPECTED_PHNUM = 32
PATCH = REPO / "patches/xnu/0620-k60-modem-image.patch"
PATCH_PAS = REPO / "patches/xnu/0621-k60-modem-pas.patch"
PATCH_QRTR = REPO / "patches/xnu/0622-k60-modem-qrtr.patch"
TABLE = REPO / "drivers/PongCellular/pong_modem_table.h"


def fail(message):
    print("FAIL " + message)
    return 1


def find(root, name):
    """Prefer name.bin: the byte-exact dump is written with that suffix."""
    for candidate in (root / (name + ".bin"), root / name):
        if candidate.is_file():
            return candidate
    return None


def load_segments(root):
    mdt_path = find(root, "modem.mdt")
    if mdt_path is None:
        raise SystemExit("modem.mdt is missing from %s" % root)
    mdt = mdt_path.read_bytes()
    if mdt[:4] != b"\x7fELF" or mdt[4] != 1:
        raise SystemExit("modem.mdt is not ELF32")
    e_phoff, = struct.unpack_from("<I", mdt, 28)
    e_phentsize, e_phnum = struct.unpack_from("<HH", mdt, 42)
    if e_phentsize != 32:
        raise SystemExit("unexpected e_phentsize %d" % e_phentsize)
    if e_phnum != EXPECTED_PHNUM:
        raise SystemExit("e_phnum is %d, expected %d" % (e_phnum, EXPECTED_PHNUM))
    segs = []
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        p_type, p_offset, _vaddr, p_paddr, p_filesz, p_memsz = struct.unpack_from("<6I", mdt, off)
        if p_type != 1:
            continue
        segs.append((i, p_offset, p_paddr, p_filesz, p_memsz))
    return segs


def parse_table(text):
    """Return (base, window, segments, rows) from the generated header."""
    base = window = segments = None
    for line in text.splitlines():
        m = re.match(r"#define K60_MODEM_BASE (0x[0-9a-fA-F]+)UL", line)
        if m:
            base = int(m.group(1), 16)
        m = re.match(r"#define K60_MODEM_WINDOW (0x[0-9a-fA-F]+)UL", line)
        if m:
            window = int(m.group(1), 16)
        m = re.match(r"#define K60_MODEM_SEGMENTS (\d+)", line)
        if m:
            segments = int(m.group(1))
    rows = []
    for line in text.splitlines():
        m = re.match(r"\s*\{ (0x[0-9a-fA-F]+)UL,\s*(\d+),\s*(\d+),\s*(.+?) \}, /\* segment (\d+) \*/", line)
        if not m:
            continue
        part = m.group(4).strip()
        name = part[1:-1] if part.startswith('"') else None
        rows.append((int(m.group(5)), int(m.group(1), 16), int(m.group(2)), int(m.group(3)), name))
    return base, window, segments, rows


def added_files(patch_text):
    """Map 'bsd/dev/x' -> body text for every new file in a series patch."""
    files = {}
    current = None
    body = []
    for line in patch_text.splitlines():
        m = re.match(r"\+\+\+ b/(\S+)$", line)
        if m:
            if current:
                files[current] = "\n".join(body)
            current = m.group(1)
            body = []
            continue
        if current is None:
            continue
        if line.startswith("@@"):
            continue
        if line.startswith("+"):
            body.append(line[1:])
    if current:
        files[current] = "\n".join(body)
    return files


def normalise(text, include_map):
    for src, dst in include_map.items():
        text = text.replace(src, dst)
    return text.rstrip("\n")


def main(argv):
    root = Path(argv[1]) if len(argv) > 1 else Path("/mnt/e/k60-work/firmware/modem")
    problems = 0

    segs = load_segments(root)
    if len(segs) != EXPECTED_LOAD:
        problems += fail("%d PT_LOAD segments, expected %d" % (len(segs), EXPECTED_LOAD))

    for index, offset, paddr, filesz, memsz in segs:
        name = "modem.b%02d" % index
        part = find(root, name)
        if filesz == 0:
            print("NOTE %s is pure bss (%d bytes, no file)" % (name, memsz))
            if part is not None:
                problems += fail("%s exists but the table declares 0 bytes" % name)
            if memsz == 0:
                problems += fail("%s declares neither bytes nor bss" % name)
            continue
        if part is None:
            problems += fail("%s missing for segment %d" % (name, index))
            continue
        if part.stat().st_size != filesz:
            problems += fail("%s is %d bytes but the table says %d"
                             % (name, part.stat().st_size, filesz))
        if memsz < filesz:
            problems += fail("%s declares memsz %d < filesz %d" % (name, memsz, filesz))
        if offset % 4096:
            problems += fail("%s has a non page-aligned file offset %#x" % (name, offset))
        if paddr % 4096:
            problems += fail("%s loads at unaligned %#x; PAS copies by byte, but the "
                             "carveout base is page aligned" % (name, paddr))
        if not (MODEM_BASE <= paddr and paddr + memsz <= MODEM_BASE + WINDOW):
            problems += fail("%s loads at %#x, outside %#x..%#x"
                             % (name, paddr, MODEM_BASE, MODEM_BASE + WINDOW))

    ordered = sorted(segs, key=lambda s: s[2])
    for prev, nxt in zip(ordered, ordered[1:]):
        if prev[2] + prev[4] > nxt[2]:
            problems += fail("segment %d overlaps %d" % (prev[0], nxt[0]))

    lo, hi = ordered[0][2], max(s[2] + s[4] for s in ordered)
    # The modem image fills its carveout exactly; that is what makes the DT reg
    # value and the ELF segment table independent evidence for the same region.
    if lo != MODEM_BASE:
        problems += fail("first segment at %#x, carveout starts at %#x" % (lo, MODEM_BASE))
    if hi != MODEM_BASE + WINDOW:
        problems += fail("last segment ends at %#x, carveout ends at %#x" % (hi, MODEM_BASE + WINDOW))

    # --- the generated table must describe this firmware ----------------------
    if not TABLE.is_file():
        problems += fail("%s missing; run scripts/gen-modem-table.py" % TABLE.relative_to(REPO))
    else:
        base, window, segments, rows = parse_table(TABLE.read_text(encoding="utf-8"))
        if base != MODEM_BASE or window != WINDOW:
            problems += fail("table declares %#x/%#x, firmware says %#x/%#x"
                             % (base, window, MODEM_BASE, WINDOW))
        if segments != len(segs) or len(rows) != len(segs):
            problems += fail("table has %s rows / declares %s, firmware has %d"
                             % (len(rows), segments, len(segs)))
        by_index = {r[0]: r for r in rows}
        for index, _offset, paddr, filesz, memsz in segs:
            row = by_index.get(index)
            if row is None:
                problems += fail("table has no row for segment %d" % index)
                continue
            _i, t_paddr, t_bytes, t_bss, t_part = row
            if t_paddr != paddr:
                problems += fail("row %d paddr %#x != %#x" % (index, t_paddr, paddr))
            if t_bytes != filesz:
                problems += fail("row %d bytes %d != %d" % (index, t_bytes, filesz))
            if t_bss != memsz - filesz:
                problems += fail("row %d bss %d != %d" % (index, t_bss, memsz - filesz))
            want = "modem.b%02d" % index if filesz else None
            if t_part != want:
                problems += fail("row %d part %s != %s" % (index, t_part, want))

    # --- the patch must carry the same three files the repo keeps -------------
    if not PATCH.is_file():
        problems += fail("%s missing" % PATCH.relative_to(REPO))
    else:
        carried = added_files(PATCH.read_text(encoding="utf-8"))
        pairs = [
            ("drivers/PongCellular/pong_modem_table.h", "bsd/dev/pong_modem_table.h", {}),
            ("drivers/PongCellular/K60ModemImage.h", "bsd/dev/pong_modem_image.h", {}),
            ("drivers/PongCellular/K60ModemImage.c", "bsd/dev/pong_modem_image.c",
             {'"K60ModemImage.h"': '"pong_modem_image.h"'}),
        ]
        for repo_rel, patch_rel, include_map in pairs:
            local = REPO / repo_rel
            if patch_rel not in carried:
                problems += fail("%s does not add %s" % (PATCH.name, patch_rel))
                continue
            if not local.is_file():
                problems += fail("%s missing" % repo_rel)
                continue
            if normalise(local.read_text(encoding="utf-8"), include_map) != normalise(carried[patch_rel], {}):
                problems += fail("%s and %s differ; the kernel would compile a "
                                 "different loader than the one tested here"
                                 % (repo_rel, patch_rel))

    # --- 0621 must carry the same PAS sources, including the call site ------
    if not PATCH_PAS.is_file():
        problems += fail("%s missing" % PATCH_PAS.relative_to(REPO))
    else:
        pas_text = PATCH_PAS.read_text(encoding="utf-8")
        carried = added_files(pas_text)
        pas_pairs = [
            ("drivers/PongCellular/K60ModemPas.h", "bsd/dev/pong_modem_pas.h", {}),
            ("drivers/PongCellular/K60ModemPas.c", "bsd/dev/pong_modem_pas.c",
             {'"K60ModemPas.h"': '"pong_modem_pas.h"'}),
            ("drivers/PongCellular/K60ModemBoot.c", "bsd/dev/pong_modem_boot.c",
             {'"K60ModemPas.h"': '"pong_modem_pas.h"',
              '"K60ModemImage.h"': '"pong_modem_image.h"'}),
        ]
        for repo_rel, patch_rel, include_map in pas_pairs:
            local = REPO / repo_rel
            if patch_rel not in carried:
                problems += fail("%s does not add %s" % (PATCH_PAS.name, patch_rel))
                continue
            if not local.is_file():
                problems += fail("%s missing" % repo_rel)
                continue
            if normalise(local.read_text(encoding="utf-8"), include_map) != normalise(carried[patch_rel], {}):
                problems += fail("%s and %s differ; the kernel would compile a "
                                 "different PAS shim than the one tested here"
                                 % (repo_rel, patch_rel))
        # The call site is the only thing that makes the code reachable, and it
        # must hang off a line an earlier patch already put in kern_exec.c.
        if "bsd/kern/kern_exec.c" not in pas_text:
            problems += fail("%s carries no kern_exec.c call site" % PATCH_PAS.name)
        if "k60_modem_probe_from_handoff" not in pas_text:
            problems += fail("%s never calls the modem probe" % PATCH_PAS.name)
        if "\tnative_owner_data_stage = 3;" not in pas_text:
            problems += fail("%s does not anchor on native_owner_data_stage = 3;"
                             % PATCH_PAS.name)
    # --- 0622 must carry the QRTR codec, its transport and the GLINK stack ---
    if not PATCH_QRTR.is_file():
        problems += fail("%s missing" % PATCH_QRTR.relative_to(REPO))
    else:
        carried = added_files(PATCH_QRTR.read_text(encoding="utf-8"))
        qrtr_pairs = [
            ("drivers/PongCellular/K60ModemQrtr.h", "bsd/dev/pong_modem_qrtr.h", {}),
            ("drivers/PongCellular/K60ModemQrtr.c", "bsd/dev/pong_modem_qrtr.c",
             {'"K60ModemQrtr.h"': '"pong_modem_qrtr.h"'}),
            ("drivers/PongPower/QcomGlink.h", "bsd/dev/qcom_glink.h", {}),
            ("drivers/PongPower/QcomGlink.c", "bsd/dev/qcom_glink.c",
             {'"QcomGlink.h"': '"qcom_glink.h"'}),
            ("drivers/PongCellular/K60ModemLink.c", "bsd/dev/pong_modem_link.c",
             {'"K60ModemQrtr.h"': '"pong_modem_qrtr.h"', '"K60Smem.h"': '"pong_smem.h"',
              '"QcomGlink.h"': '"qcom_glink.h"'}),
        ]
        for repo_rel, patch_rel, include_map in qrtr_pairs:
            local = REPO / repo_rel
            if patch_rel not in carried:
                problems += fail("%s does not add %s" % (PATCH_QRTR.name, patch_rel))
                continue
            if not local.is_file():
                problems += fail("%s missing" % repo_rel)
                continue
            if normalise(local.read_text(encoding="utf-8"), include_map) != normalise(carried[patch_rel], {}):
                problems += fail("%s and %s differ; the kernel would compile a "
                                 "different QRTR path than the one tested here"
                                 % (repo_rel, patch_rel))

    print("TESTS OK %d segments, %#x..%#x (%d bytes), base %#x, table+p patch agree"
          % (len(segs), lo, hi, hi - lo, MODEM_BASE))
    if problems:
        print("PROBLEMS %d" % problems)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
