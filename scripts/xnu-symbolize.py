#!/usr/bin/env python3
"""Resolve kernel virtual addresses against the prelinked kernel collection.

Stage 0 has no serial console, so a panic on the panel reports only
`pc=%p instr=%x`. This turns a pc into a symbol and a disassembly window, and
an instruction word into the addresses that contain it, using the prelinked
collection the boot image carries.

    python3 scripts/xnu-symbolize.py 0xfffffff00ad9d6a4
    python3 scripts/xnu-symbolize.py --find d51be220

The collection path defaults to $UNIXNU_OUT/mondrian/*/*/kernel/kernel.macho;
pass --kernel to point somewhere else. `llvm-nm` and `llvm-mc` must be on PATH,
and scripts/linux/setup-toolchain.py installs them.

The collection is a fileset whose inner kernel is not the first section, so
`llvm-objdump -d` silently prints nothing for kernel text. This reads the
segment table and decodes the bytes directly instead.
"""
import argparse
import bisect
import os
import pathlib
import struct
import subprocess
import sys

DEFAULT_GLOB = 'mondrian/*/*/kernel/kernel.macho'
LC_SEGMENT_64 = 0x19


def find_kernel(explicit):
    if explicit:
        return pathlib.Path(explicit)
    root = pathlib.Path(os.environ.get('UNIXNU_OUT', pathlib.Path.home() / 'ios27-out'))
    matches = sorted(root.glob(DEFAULT_GLOB))
    if not matches:
        sys.exit(f'no kernel collection under {root} (set UNIXNU_OUT or --kernel)')
    return matches[-1]


def segments(kernel):
    """Return (vmaddr, vmsize, fileoff, filesize) for every mapped segment."""
    data = kernel.read_bytes()
    magic, _, _, _, ncmds, _, _ = struct.unpack_from('<IiiIIII', data, 0)
    if magic != 0xfeedfacf:
        sys.exit(f'{kernel}: not a 64-bit Mach-O')
    out = []
    offset = 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', data, offset)
        if cmd == LC_SEGMENT_64:
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<QQQQ', data, offset + 24)
            if filesize:
                out.append((vmaddr, vmsize, fileoff, filesize))
        offset += size
    return data, out


def symbols(kernel):
    out = subprocess.run(['llvm-nm', '--defined-only', '--numeric-sort', str(kernel)],
                         check=True, capture_output=True, text=True).stdout
    addrs, names = [], []
    for line in out.splitlines():
        parts = line.split(maxsplit=2)
        if len(parts) != 3:
            continue
        try:
            addr = int(parts[0], 16)
        except ValueError:
            continue
        addrs.append(addr)
        names.append(parts[2])
    return addrs, names


def nearest(addrs, names, addr):
    index = bisect.bisect_right(addrs, addr) - 1
    if index < 0:
        return '?'
    return f'{names[index]} + {addr - addrs[index]:#x}'


def locate(segs, addr):
    for vmaddr, vmsize, fileoff, filesize in segs:
        if vmaddr <= addr < vmaddr + vmsize:
            return fileoff + (addr - vmaddr)
    return None


def read_words(data, segs, addr, count, before=0):
    offset = locate(segs, addr - before)
    if offset is None:
        sys.exit(f'{addr:#x} is not in any segment')
    raw = data[offset:offset + (before + count * 4)]
    return [struct.unpack_from('<I', raw, i * 4)[0] for i in range(len(raw) // 4)], addr - before


def decode(words):
    lines = '\n'.join('0x%02x 0x%02x 0x%02x 0x%02x' % tuple(struct.pack('<I', w))
                      for w in words)
    out = subprocess.run(['llvm-mc', '-triple=aarch64', '-disassemble'],
                         input=lines + '\n', capture_output=True, text=True).stdout
    return [line.strip() for line in out.splitlines()
            if line.strip() and not line.strip().startswith('.')]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('addresses', nargs='*', help='kernel virtual addresses, hex')
    parser.add_argument('--find', help='instruction word to locate, hex')
    parser.add_argument('--before', type=lambda x: int(x, 0), default=0x20,
                        help='bytes of context before an address (default 0x20)')
    parser.add_argument('--after', type=lambda x: int(x, 0), default=0x40,
                        help='bytes of context after an address (default 0x40)')
    parser.add_argument('--kernel', help='path to kernel.macho')
    args = parser.parse_args()
    if not args.addresses and not args.find:
        parser.error('give an address or --find')
    kernel = find_kernel(args.kernel)
    print(f'kernel: {kernel}')
    data, segs = segments(kernel)
    addrs, names = symbols(kernel)
    if args.find:
        word = int(args.find, 16)
        pattern = struct.pack('<I', word)
        hits = []
        for vmaddr, vmsize, fileoff, filesize in segs:
            blob = data[fileoff:fileoff + filesize]
            start = 0
            while True:
                hit = blob.find(pattern, start)
                if hit < 0:
                    break
                hits.append(vmaddr + hit)
                start = hit + 1
        print(f'{word:#010x}: {len(hits)} occurrence(s)')
        for addr in hits:
            print(f'  {addr:#x}  {nearest(addrs, names, addr)}')
    for text in args.addresses:
        addr = int(text, 16)
        before = (args.before // 4) * 4
        count = (before + args.after) // 4
        words, start = read_words(data, segs, addr, count, before)
        print(f'\n{addr:#x}: {nearest(addrs, names, addr)}')
        for index, (word, line) in enumerate(zip(words, decode(words))):
            here = start + index * 4
            mark = '>' if here == addr else ' '
            print(f'{mark}{here:#x}: {word:08x}  {line}')


if __name__ == '__main__':
    main()
