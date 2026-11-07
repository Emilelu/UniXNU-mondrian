#!/usr/bin/env python3
"""route-a-22: verify the rebuilt loader carries the Darwin 24 boot_args size.

Chain of evidence:
  1. BootArgs.h asserts sizeof == 0x480 and the build compiled it, so the compiler
     itself confirmed the layout
  2. the freshly built DarwinBoot.obj should contain the 0x480 immediate
  3. the FD hash changed
"""
from pathlib import Path
import struct

R = Path('/home/emilelu/hackios/uefi-mondrian')
CANDIDATES = [
    R / 'Build/mondrianPkg/DEBUG_CLANGPDB/AARCH64/DarwinBootPkg/Driver/DarwinBoot/OUTPUT/DarwinBoot.obj',
    R / 'Build/mondrianPkg/DEBUG_CLANGPDB/AARCH64/DarwinBootPkg/Driver/DarwinBoot/OUTPUT/DarwinBoot.efi',
    R / 'Build/mondrianPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd',
]

VALUES = [
    ('Darwin22 sizeof 0x2e0', 0x2e0),
    ('Darwin24 sizeof 0x480', 0x480),
    ('Darwin22 flags  0x2d0', 0x2d0),
    ('Darwin24 flags  0x470', 0x470),
    ('Darwin22 mem    0x2d8', 0x2d8),
    ('Darwin24 mem    0x478', 0x478),
    ('Darwin22 cmdline 608', 608),
    ('Darwin24 cmdline 1024', 1024),
]

for f in CANDIDATES:
    print('=' * 70)
    if not f.exists():
        print(f, 'MISSING')
        continue
    data = f.read_bytes()
    print(f'{f.name}  ({len(data)} bytes)')
    for label, val in VALUES:
        needle = struct.pack('<I', val)
        n = data.count(needle)
        if n:
            print(f'  {label:24s} {n:5d} occurrence(s)')
    # Also look for the 64-bit form, which is how a size reaches a printf %lx.
    print('  --- as 64-bit immediates ---')
    for label, val in (('Darwin22 sizeof 0x2e0', 0x2e0), ('Darwin24 sizeof 0x480', 0x480)):
        needle = struct.pack('<Q', val)
        n = data.count(needle)
        if n:
            print(f'  {label:24s} {n:5d} occurrence(s)')
