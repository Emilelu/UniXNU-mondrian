#!/usr/bin/env python3
"""Recompute the page table entry that 0244-k60-breadcrumbs.patch adds.

The K60 breadcrumb page (0xA73FF000) sits outside the V=P range that
_start() maps for the kernel, so start.s adds one 2 MiB Device-nGnRnE block
for 0xA7200000 to the V=P L1 table.  This script recomputes that entry from
first principles and compares it with what the patch hard-codes, so a bad
constant fails offline instead of on the board.

    python3 scripts/k60-bootstrap-pt-model.py
    python3 scripts/k60-bootstrap-pt-model.py --vbase 0xC7004000 --size 0x10000000
"""
import argparse
import sys

# proc_reg.h, 4 KiB granule
ARM_TT_L1_SHIFT = 30
ARM_TT_L2_SHIFT = 21
TTE_SHIFT = 3
TTE_PGENTRIES = 4096 >> TTE_SHIFT          # 512 entries per L2 page
PGBYTES = 4096
BOOTSTRAP_TABLE_BYTES = 0x20000            # 32 pages, native-4k-bootstrap-capacity.patch

ARM_TTE_VALID = 0x1
ARM_TTE_TYPE_TABLE = 0x2
ARM_TTE_BOOT_TABLE = ARM_TTE_TYPE_TABLE | ARM_TTE_VALID
ARM_TTE_BLOCK_L2_MASK = 0x0000FFFF_FFE00000
ARM_TTE_BLOCK_AF = 0x400
ARM_TTE_BLOCK_ATTRINDX = lambda x: x << 2
ARM_TTE_BLOCK_NX = 0x00400000_00000000
CACHE_ATTRINDX_DISABLE = 3                 # MAIR index 3: Device-nGnRnE

MARK_PA = 0xA73FF000
MARK_BLOCK = 0xA7200000
EXPECTED_L1_INDEX = 2                      # 0xA7200000 >> 30
EXPECTED_L2_INDEX = 313                    # (0xA7200000 >> 21) & 0x1FF


def block_entry(phys):
    return (ARM_TTE_BLOCK_NX | ARM_TTE_BLOCK_AF |
            ARM_TTE_BLOCK_ATTRINDX(CACHE_ATTRINDX_DISABLE) |
            ARM_TTE_VALID | (phys & ARM_TTE_BLOCK_L2_MASK))


def table_entry(l2_page_pa):
    return ARM_TTE_BOOT_TABLE | (l2_page_pa & 0x0000FFFF_FFFFF000)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--vbase', type=lambda s: int(s, 0), default=0xC7004000,
                    help='kernel window base, DarwinBoot places Base at align(window)+0x4000')
    ap.add_argument('--size', type=lambda s: int(s, 0), default=0x10000000,
                    help='kernel window size handed to create_bootstrap_mapping')
    args = ap.parse_args()

    # Pages consumed before the breadcrumb block: 1 V=P L1, 1 KVA L1, then the
    # L2 pages each create_bootstrap_mapping() allocates.
    l1_pages = 2
    vp_entries = args.size >> ARM_TT_L2_SHIFT
    vp_l2_pages = (vp_entries + (-vp_entries % TTE_PGENTRIES)) // TTE_PGENTRIES
    if vp_entries % TTE_PGENTRIES:
        vp_l2_pages += 1
    # The KVA mapping covers the same size, then the breadcrumb block adds one more.
    kva_l2_pages = vp_l2_pages

    l1_index = (MARK_BLOCK >> ARM_TT_L1_SHIFT) & 0x1FF
    l2_index = (MARK_BLOCK >> ARM_TT_L2_SHIFT) & 0x1FF
    l2_pages_used = l1_pages + vp_l2_pages + kva_l2_pages
    new_l2_page_offset = (l2_pages_used + 1) * PGBYTES
    block = block_entry(MARK_BLOCK)

    print(f'kernel window      : {args.vbase:#x} .. {args.vbase + args.size:#x}')
    print(f'bootstrap pool     : {BOOTSTRAP_TABLE_BYTES // PGBYTES} pages '
          f'({BOOTSTRAP_TABLE_BYTES:#x} B)')
    print(f'L2 pages before it : {l2_pages_used} (1 V=P L1, 1 KVA L1, '
          f'{vp_l2_pages} V=P L2, {kva_l2_pages} KVA L2)')
    print(f'breadcrumb block   : {MARK_BLOCK:#x}, page {MARK_PA:#x}')
    print(f'L1 index           : {l1_index} (expected {EXPECTED_L1_INDEX})')
    print(f'L2 index           : {l2_index} (expected {EXPECTED_L2_INDEX})')
    print(f'L2 page file off   : +{new_l2_page_offset:#x} from bootstrap_pagetables')
    print(f'L1 entry           : {table_entry(0):#018x} | L2 page PA')
    print(f'L2 block descriptor: {block:#018x}')

    failures = []
    if block != 0x00400000A720040D:
        failures.append(f'block entry {block:#x} != 0x00400000a720040d')
    if l1_index != EXPECTED_L1_INDEX:
        failures.append(f'L1 index {l1_index} != {EXPECTED_L1_INDEX}')
    if l2_index != EXPECTED_L2_INDEX:
        failures.append(f'L2 index {l2_index} != {EXPECTED_L2_INDEX}')
    if new_l2_page_offset + PGBYTES > BOOTSTRAP_TABLE_BYTES:
        failures.append(f'table pool exhausted at +{new_l2_page_offset:#x}')
    # The V=P mapping starts at vbase, so the breadcrumb block must fall outside it.
    if args.vbase <= MARK_BLOCK < args.vbase + args.size:
        failures.append('breadcrumb block already covered by the V=P mapping')

    for line in failures:
        print(f'FAIL {line}')
    print('OK' if not failures else 'FAILED')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
