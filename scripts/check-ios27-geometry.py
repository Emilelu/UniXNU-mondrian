#!/usr/bin/env python3
"""Check the payload memory geometry against the banks measured on this board.

Three numbers have to agree before a boot image is worth flashing:

* the DTS `/memory` node, which becomes the ADT's `dram-base`/`dram-size` —
  XNU's `arm_init.c` reads those as the DRAM iBoot reported and builds the
  physmap over all of it;
* `[payload].dram_size`, which the payload generator compares with that node
  and refuses to build when they differ;
* `[payload.adt].owned_memory_size`, the window `DarwinBoot.c` hands the kernel
  as *managed* memory (it can be smaller than the arena, never larger).

And the arena has to sit inside one contiguous region of real memory. The six
regions below are the live device tree this phone passed to the iOS 16 shim
(`/memory`, read on 2026-10-20 and reprinted by the PAC probe's FACT lines);
a window that spans a hole or a carve-out boots into nothing.

    python3 scripts/check-ios27-geometry.py

Exits nonzero with `error:` on the first disagreement.
"""
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIB = 0x100000
GIB = 0x40000000

# The live /memory regions, low to high. Bases are 64-bit; the shim prints
# only their low 32 bits, which is why they look truncated on the panel.
BANKS = [
    (0x80000000, 0x6A000000),
    (0xF4600000, 0x0BA00000),
    (0x800000000, 0x37500000),
    (0x837B00000, 0x01C00000),
    (0x840000000, 0xC0000000),
    (0x900000000, 0x180000000),
]


def merged_banks():
    """Adjacent regions are one run of memory to XNU (0x840000000+3 GiB and 0x900000000+6 GiB)."""
    runs = []
    for base, size in sorted(BANKS):
        if runs and runs[-1][0] + runs[-1][1] == base:
            runs[-1] = (runs[-1][0], runs[-1][1] + size)
        else:
            runs.append((base, size))
    return runs


def dts_memory():
    text = (ROOT / 'dts/mondrian.dts').read_text()
    match = re.search(r'reg\s*=\s*<\s*([^>]*)>\s*;', text[text.index('device_type = "memory"'):])
    if not match:
        raise ValueError('the /memory node has no reg')
    cells = [int(cell, 0) for cell in match.group(1).split()]
    if len(cells) != 4:
        raise ValueError(f'/memory reg has {len(cells)} cells, expected 2 address + 2 size')
    base, size = (cells[0] << 32) | cells[1], (cells[2] << 32) | cells[3]
    return base, size


def merge(base, overlay, remove):
    """Apply one os_overrides table the way scripts/unixnu/profiles.py does."""
    result = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value, [])
        else:
            result[key] = value
    for path in remove:
        parts = path.split('.')
        node, trail = result, []
        for part in parts[:-1]:
            if not isinstance(node, dict) or part not in node:
                node = None
                break
            trail.append((node, part))
            node = node[part]
        if isinstance(node, dict):
            node.pop(parts[-1], None)
    return result


def profiles_named(board):
    """The OS profile this board builds for, and the override table that goes with it."""
    name = board.get('board', {}).get('os_profile', '')
    overrides = board.get('os_overrides', {})
    return name, overrides.get(name, {})


def main():
    board = tomllib.loads((ROOT / 'board.toml').read_text())
    name, override = profiles_named(board)
    payload = merge(board.get('payload', {}), override.get('payload', {}),
                    override.get('remove', []))
    adt = payload.get('adt', {})
    if name:
        print(f'geometry: profile {name}')
    try:
        base, size = dts_memory()
    except ValueError as error:
        print(f'error: {error}', file=sys.stderr)
        return 1
    arena = int(str(payload.get('dram_size')), 0)
    if arena != size:
        print(f'error: /memory is {size:#x} bytes, [payload].dram_size is {arena:#x}', file=sys.stderr)
        return 1
    owned_text = adt.get('owned_memory_size')
    if not owned_text:
        print('error: [payload.adt].owned_memory_size is not set', file=sys.stderr)
        return 1
    owned = int(str(owned_text), 0)
    if not 0 < owned <= size:
        print(f'error: managed window {owned:#x} is outside the {size:#x}-byte arena', file=sys.stderr)
        return 1
    for label, value in (('arena base', base), ('arena size', size), ('managed size', owned)):
        if value % (2 * MIB):
            print(f'error: {label} {value:#x} is not a multiple of 2 MiB', file=sys.stderr)
            return 1
    host = next(((bank, length) for bank, length in merged_banks() if base >= bank and base + size <= bank + length), None)
    if host is None:
        print(f'error: arena {base:#x}+{size:#x} is not inside one contiguous bank', file=sys.stderr)
        for bank, length in merged_banks():
            print(f'  bank {bank:#x}+{length:#x}', file=sys.stderr)
        return 1
    seed = str(adt.get('random_seed', ''))
    if not seed:
        print(f'error: [payload.adt].random_seed is not pinned for {name or "this board"}; the physmap slide would be a coin flip', file=sys.stderr)
        return 1
    bank, length = host
    print(f'geometry: arena {base:#x}+{size:#x} ({size / GIB:.2f} GiB) in bank {bank:#x}+{length:#x}, '
          f'managed {owned:#x} ({owned / GIB:.2f} GiB), seed pinned')
    return 0


if __name__ == '__main__':
    sys.exit(main())
