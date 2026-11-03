#!/usr/bin/env python3
"""Compare the LC_UNIXTHREAD payload of the darwin22 kernel (boots) and the
darwin24 kernel (does not print), since DarwinBoot22 gets the entry PC from it.

arm64 LC_UNIXTHREAD layout (xnu/LLVM):
  cmd, cmdsize, flavor=ARM_THREAD_STATE64(6), count, then the state words:
  x[29], fp, lr, sp, pc, cpsr  (34 * 8 bytes for the GPR part)
"""
from pathlib import Path
import struct

CASES = {
    'darwin24': Path('/tmp/k60build/out/route-a18/Pong-iPadOS18-native/build/xnu/'
                     'ios-obj/DEVELOPMENT_ARM64_PONG/mach.development.pong.unstripped.noctf'),
    'darwin22': Path('/tmp/k60build/out/mondrian/ipados-16.6.1-20G81/mondrian/tree/build/xnu/'
                     'ios-obj/DEVELOPMENT_ARM64_PONG/mach.development.pong.unstripped'),
}

for label, path in CASES.items():
    print('=' * 72)
    print(label, path.stat().st_size, 'bytes' if path.exists() else 'MISSING')
    data = path.read_bytes()
    ncmds = struct.unpack_from('<I', data, 16)[0]
    sizeofcmds = struct.unpack_from('<I', data, 20)[0]
    print('ncmds', ncmds, 'sizeofcmds', sizeofcmds)
    p = 32
    for idx in range(ncmds):
        cmd, cmdsize = struct.unpack_from('<II', data, p)
        if cmd == 0x5:  # LC_UNIXTHREAD
            flavor, count = struct.unpack_from('<II', data, p+8)
            print(f'LC_UNIXTHREAD at cmd#{idx}: cmdsize={cmdsize} flavor={flavor} count={count}')
            state = data[p+16:p+cmdsize]
            print('  state bytes:', len(state))
            # Print as qwords and pick out the pc (index 32 in arm_thread_state64).
            qwords = [struct.unpack_from('<Q', state, 8*i)[0] for i in range(len(state)//8)]
            for i, q in enumerate(qwords):
                tag = ''
                if i == 29: tag = '  <- fp'
                elif i == 30: tag = '  <- lr'
                elif i == 31: tag = '  <- sp'
                elif i == 32: tag = '  <- PC'
                elif i == 33: tag = '  <- cpsr'
                print(f'   [{i:2d}] 0x{q:016X}{tag}' if i >= 28 else '', end='')
                if i >= 28:
                    print()
        p += cmdsize
