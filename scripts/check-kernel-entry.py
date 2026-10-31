#!/usr/bin/env python3
"""route-a-18: what does our darwin24 kernel's entry point actually contain?

DarwinBoot22 read `entry=0xC7404A00` but jumped to `entry pa 0xC74C04A0`, and the
first four words were 140006EF 00000000 00000000 00000000. Check the Mach-O entry
against the 16.6.1 kernel that boots fine.
"""
from pathlib import Path
import struct

CASES = {
    'darwin24 (route-a-18)': Path('/tmp/k60build/out/route-a18/Pong-iPadOS18-native/'
                                 'build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/'
                                 'mach.development.pong.unstripped.noctf'),
    'darwin22 (16.6.1, boots)': Path('/tmp/k60build/out/mondrian/ipados-16.6.1-20G81/mondrian/'
                                     'tree/build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/'
                                     'mach.development.pong.unstripped'),
}

for label, path in CASES.items():
    print('=' * 70)
    print(label)
    print(' path:', path)
    if not path.exists():
        print(' MISSING')
        continue
    data = path.read_bytes()
    print(' size:', len(data))
    if data[:4] == b'\xca\xfe\xba\xbe':
        count = struct.unpack('>I', data[4:8])[0]
        for i in range(count):
            cpu, sub, off, size, align = struct.unpack('>5I', data[8+20*i:28+20*i])
            if cpu == 0x0100000c:
                data = data[off:off+size]
    print(' mach-o magic:', data[:4].hex())

    ncmds = struct.unpack_from('<I', data, 16)[0]
    p = 32
    texts = {}
    entry = None
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from('<II', data, p)
        if cmd == 0x19:  # LC_SEGMENT_64
            name = data[p+8:p+24].split(b'\0')[0].decode()
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<QQQQ', data, p+24)
            texts[name] = (vmaddr, vmsize, fileoff, filesize)
        elif cmd == 0x80000028:  # LC_MAIN
            entryoff, stacksize = struct.unpack_from('<QQ', data, p+8)
            entry = ('LC_MAIN', entryoff, stacksize)
        elif cmd == 0x5:  # LC_UNIXTHREAD
            entry = ('LC_UNIXTHREAD', None, None)
        p += cmdsize

    print(' entry command:', entry)
    text = texts.get('__TEXT')
    print(' __TEXT vmaddr=0x%x fileoff=0x%x filesize=0x%x' % (text[0], text[2], text[3]))
    if entry and entry[0] == 'LC_MAIN':
        off = entry[1]
        va = text[0] + off
        print(' entryoff = 0x%x  ->  VA 0x%x' % (off, va))
        print(' file offset 0x%x; first 16 words:' % off)
        for i in range(4):
            w = struct.unpack_from('<I', data, off + 4*i)[0]
            print('   [%d] 0x%08X' % (i, w))
        # Disassemble the first instruction by hand for the branch form.
        w0 = struct.unpack_from('<I', data, off)[0]
        if (w0 >> 26) == 0b000101:
            imm26 = w0 & 0x03FFFFFF
            if imm26 & 0x02000000:
                imm26 -= 0x04000000
            print('   word0 = B %+#x' % (imm26 * 4))
    # Also show where __TEXT_EXEC begins, since kernels often branch there.
    if '__TEXT_EXEC' in texts:
        t = texts['__TEXT_EXEC']
        print(' __TEXT_EXEC vmaddr=0x%x fileoff=0x%x' % (t[0], t[2]))
