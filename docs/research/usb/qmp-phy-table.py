#!/usr/bin/env python3
"""qmp-phy-table.py - extract and check the K60 QMP USB3/DP combo PHY tables.

The K60 (mondrian / SM8475) QMP PHY lives at 0x088e8000 (size 0x3000).  Its
register offsets and its 164-entry initialisation sequence are only published as
device-tree properties, so a driver that hardcodes them cannot be reviewed.  This
script turns those properties into a C table and checks them against the only
authority that exists for this silicon.

Inputs
  --dts PATH   a device tree source (dtc -I dtb -O dts output) that contains the
               ssphy node.  Default: the vendor DT decompiled from the UEFI blob.
  --emit-c     write a C header fragment (registers + init table) to --out.
  --check      validate the tables and exit non-zero on any inconsistency.

Decode authority (see docs/research/usb/QMP-PHY.md section 2):
  * the 13 qcom,qmp-phy-reg-offset values map 1:1 onto enum qmp_phy_rev_reg in
    the downstream SM8450 driver (phy-msm-ssusb-qmp-sm8450.c:82-101);
  * the block base offsets (serdes 0x1000, txa 0x1200, rxa 0x1400, txb 0x1600,
    rxb 0x1800, pcs 0x1c00, pcs_usb 0x1f00) come from mainline
    phy-qcom-qmp-combo.c:1476-1490 (qmp_combo_offsets_v3).
"""

import argparse
import re
import sys

# enum qmp_phy_rev_reg, phy-msm-ssusb-qmp-sm8450.c:82-101 (13 real entries).
REG_NAMES = [
    'PCS_STATUS',              # 0x1c14
    'AUTONOMOUS_MODE_CTRL',    # 0x1f08
    'LFPS_RXTERM_IRQ_CLEAR',   # 0x1f14
    'POWER_DOWN_CONTROL',      # 0x1c40
    'SW_RESET',                # 0x1c00
    'START',                   # 0x1c44
    'PCS_MISC_TYPEC_CTRL',     # 0xffff (sentinel: this PHY has no such register)
    'DP_COM_POWER_DOWN_CTRL',  # 0x08
    'DP_COM_SW_RESET',         # 0x04
    'DP_COM_RESET_OVRD_CTRL',  # 0x1c
    'DP_COM_PHY_MODE_CTRL',    # 0x00
    'DP_COM_TYPEC_CTRL',       # 0x10
    'PCS_MISC_CLAMP_ENABLE',   # 0x1e00 (K60 value; mainline pcs_misc+0x0c = 0x1a0c)
]

# mainline qmp_combo_offsets_v3 block bases (phy-qcom-qmp-combo.c:1476-1490).
BLOCKS = [
    ('serdes',  0x1000, 0x0200),
    ('txa',     0x1200, 0x0200),
    ('rxa',     0x1400, 0x0200),
    ('txb',     0x1600, 0x0200),
    ('rxb',     0x1800, 0x0200),
    ('pcs_misc', 0x1a00, 0x0200),
    ('pcs',     0x1c00, 0x0200),
    ('pcs_usb', 0x1f00, 0x0100),
]

SENTINEL = 0xffff


def parse_node(text):
    """Return (reg_base, reg_size, reg_offsets, init_pairs) for the ssphy node."""
    m = re.search(r'ssphy@[0-9a-f]+ \{(.*?)\n\t\t\};', text, re.S)
    if not m:
        raise SystemExit('ssphy node not found in the given dts')
    node = m.group(1)

    reg = re.search(r'reg = <(0x[0-9a-f]+) (0x[0-9a-f]+)>;', node)
    if not reg:
        raise SystemExit('ssphy reg property not found')
    base, size = int(reg.group(1), 16), int(reg.group(2), 16)

    off = re.search(r'qcom,qmp-phy-reg-offset = <(.*?)>;', node, re.S)
    if not off:
        raise SystemExit('qcom,qmp-phy-reg-offset not found')
    offsets = [int(v, 16) for v in off.group(1).split()]

    seq = re.search(r'qcom,qmp-phy-init-seq = <(.*?)>;', node, re.S)
    if not seq:
        raise SystemExit('qcom,qmp-phy-init-seq not found')
    raw = [int(v, 16) for v in seq.group(1).split()]
    if len(raw) % 2:
        raise SystemExit('qcom,qmp-phy-init-seq has an odd number of cells')
    pairs = [(raw[i], raw[i + 1]) for i in range(0, len(raw), 2)]

    return base, size, offsets, pairs


def block_of(offset):
    for name, start, span in BLOCKS:
        if start <= offset < start + span:
            return name
    return None


def check(base, size, offsets, pairs):
    problems = []
    notes = []

    if len(offsets) != len(REG_NAMES):
        problems.append('qcom,qmp-phy-reg-offset has %d entries, the downstream enum has %d'
                        % (len(offsets), len(REG_NAMES)))

    # Offsets outside the register window can never be written.
    for name, value in zip(REG_NAMES, offsets):
        if value == SENTINEL:
            continue
        if value >= size:
            problems.append('%s = 0x%x is outside the 0x%x-byte window' % (name, value, size))

    # Cross-check the 12 non-sentinel offsets against the mainline layout.
    expected = {
        'PCS_STATUS': 0x1c00 + 0x014,
        'AUTONOMOUS_MODE_CTRL': 0x1f00 + 0x008,
        'LFPS_RXTERM_IRQ_CLEAR': 0x1f00 + 0x014,
        'POWER_DOWN_CONTROL': 0x1c00 + 0x040,
        'SW_RESET': 0x1c00 + 0x000,
        'START': 0x1c00 + 0x044,
        'DP_COM_POWER_DOWN_CTRL': 0x0000 + 0x08,
        'DP_COM_SW_RESET': 0x0000 + 0x04,
        'DP_COM_RESET_OVRD_CTRL': 0x0000 + 0x1c,
        'DP_COM_PHY_MODE_CTRL': 0x0000 + 0x00,
        'DP_COM_TYPEC_CTRL': 0x0000 + 0x10,
    }
    for name, value in zip(REG_NAMES, offsets):
        if name not in expected:
            continue
        if value != expected[name]:
            problems.append('%s = 0x%x, mainline layout says 0x%x'
                            % (name, value, expected[name]))

    clamp = dict(zip(REG_NAMES, offsets)).get('PCS_MISC_CLAMP_ENABLE')
    if clamp is not None and clamp != SENTINEL and clamp != 0x1a00 + 0x0c:
        notes.append('PCS_MISC_CLAMP_ENABLE = 0x%x differs from mainline 0x%x; '
                     'the DT value wins for K60' % (clamp, 0x1a00 + 0x0c))

    # Every init entry must land in a known block, and addresses must be unique.
    seen = {}
    counts = {}
    for offset, value in pairs:
        blk = block_of(offset)
        if blk is None:
            problems.append('init entry 0x%04x 0x%02x is outside every known block'
                            % (offset, value))
            continue
        if offset in seen:
            problems.append('init entry 0x%04x appears twice' % offset)
        seen[offset] = value
        counts[blk] = counts.get(blk, 0) + 1

    if not pairs:
        problems.append('init sequence is empty')

    # The sequence must be monotonic inside each block; the driver writes it in
    # order and a later duplicate would silently override an earlier value.
    order = [offset for offset, _ in pairs]
    for i in range(1, len(order)):
        if block_of(order[i]) == block_of(order[i - 1]) and order[i] < order[i - 1]:
            problems.append('init entries are not ascending inside %s: 0x%04x after 0x%04x'
                            % (block_of(order[i]), order[i], order[i - 1]))

    return problems, notes, counts


def emit_c(base, offsets, pairs, counts, out):
    lines = []
    lines.append('/* Generated by docs/research/usb/qmp-phy-table.py. Do not edit. */')
    lines.append('/* QMP USB3/DP combo PHY, base 0x%08x. */' % base)
    lines.append('')
    lines.append('enum {')
    for name, value in zip(REG_NAMES, offsets):
        lines.append('    kQmp%s = 0x%04x,%s' % (
            ''.join(p.capitalize() for p in name.split('_')), value,
            '  /* no such register on this PHY */' if value == SENTINEL else ''))
    lines.append('};')
    lines.append('')
    lines.append('/* %d entries: %s. */' % (
        len(pairs), ', '.join('%s %d' % (k, counts[k]) for k, _, _ in BLOCKS if k in counts)))
    lines.append('static const struct { unsigned short offset; unsigned char value; } kK60QmpInit[] = {')
    for offset, value in pairs:
        lines.append('    { 0x%04x, 0x%02x },  /* %s */' % (offset, value, block_of(offset)))
    lines.append('};')
    text = '\n'.join(lines) + '\n'
    with open(out, 'w', encoding='utf-8') as fh:
        fh.write(text)
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dts', default='/mnt/e/k60-work/scratch/usb/mondrian.dts')
    ap.add_argument('--emit-c', action='store_true')
    ap.add_argument('--out', default='/mnt/e/k60-work/scratch/usb/kQmpPhyK60.h')
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()

    with open(args.dts, encoding='utf-8', errors='replace') as fh:
        text = fh.read()

    base, size, offsets, pairs = parse_node(text)
    problems, notes, counts = check(base, size, offsets, pairs)

    print('node base 0x%08x size 0x%x' % (base, size))
    print('reg offsets %d, init entries %d' % (len(offsets), len(pairs)))
    print('per block: ' + ', '.join('%s %d' % (k, counts[k]) for k, _, _ in BLOCKS if k in counts))
    for note in notes:
        print('note: ' + note)
    for problem in problems:
        print('FAIL: ' + problem)

    if args.emit_c:
        emit_c(base, offsets, pairs, counts, args.out)
        print('wrote ' + args.out)

    if args.check and problems:
        print('RESULT: FAIL (%d problems)' % len(problems))
        return 1
    print('RESULT: OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
