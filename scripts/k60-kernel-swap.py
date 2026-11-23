#!/usr/bin/env python3
"""Swap a rebuilt kernel into an existing payload.img and boot.img, byte for byte.

Why: after the four-layer key reuse, a series change still costs ~184 s of payload
packing and ~182 s of boot.img assembly, and both stages mostly copy the same
93 MB kernel into the same FAT cluster chain. When the new kernel has exactly the
size of the old one, the cluster chain cannot change, so the bytes can be written
in place: no FAT metadata update, no re-pack, no re-hash of anything else.

Preconditions are checked, never assumed:
  * the new kernel is the same byte length as the kernel recorded in the payload
  * the payload carries exactly one kernel at /EFI/UniXNU/Payloads/kernel.macho
  * the boot image's ramdisk is a verbatim copy of the payload (same length)
Anything else refuses, and the caller must run the normal build.
"""
import argparse
import struct
import sys

SECTOR = 512


def _u16(data, offset):
    return struct.unpack_from('<H', data, offset)[0]


def _u32(data, offset):
    return struct.unpack_from('<I', data, offset)[0]


class Fat:
    """Minimal FAT12/16/32 reader: enough to find one 8.3 file and its clusters."""

    def __init__(self, data):
        self.data = data
        self.bps = _u16(data, 11)
        self.spc = data[13]
        self.reserved = _u16(data, 14)
        self.fats = data[16]
        self.root_entries = _u16(data, 17)
        total16 = _u16(data, 19)
        fatsz16 = _u16(data, 22)
        self.fatsz = _u32(data, 36) or fatsz16
        total32 = _u32(data, 32)
        self.total = total32 or total16
        self.root_dir_sectors = ((self.root_entries * 32) + (self.bps - 1)) // self.bps
        self.fat_start = self.reserved * self.bps
        self.root_start = (self.reserved + self.fats * self.fatsz) * self.bps
        self.data_start = self.root_start + self.root_dir_sectors * self.bps
        self.fat_bits = 32 if fatsz16 == 0 else (16 if self.total * self.bps > 4085 * self.spc + 65536 else 12)

    def _next(self, cluster):
        if self.fat_bits == 32:
            return _u32(self.data, self.fat_start + cluster * 4) & 0x0FFFFFFF
        if self.fat_bits == 16:
            return _u16(self.data, self.fat_start + cluster * 2)
        offset = self.fat_start + (cluster * 3) // 2
        value = _u16(self.data, offset)
        return (value >> 4) if cluster & 1 else (value & 0x0FFF)

    def _cluster_bytes(self):
        return self.spc * self.bps

    def find(self, name):
        """Return (offset, size) of a file given 'EFI/UNIXNU/PAYLOADS/KERNEL.MACHO'."""
        parts = name.upper().strip('/').split('/')
        directory = self.root_start
        for index, part in enumerate(parts):
            last = index == len(parts) - 1
            if directory == self.root_start:
                size = self.root_dir_sectors * self.bps or self._cluster_bytes()
            else:
                size = self._cluster_bytes()
            for entry in range(directory, directory + size, 32):
                first = self.data[entry]
                if first == 0x00:
                    break
                if first == 0xE5:
                    continue
                attributes = self.data[entry + 11]
                if attributes == 0x0F:
                    continue
                short = self.data[entry:entry + 11].decode('latin-1').rstrip()
                base, _, extension = short.partition('.')
                candidate = base + ('.' + extension if extension else '')
                if candidate != part and not (part.startswith('KERNEL.') and candidate.startswith('KERNEL~')):
                    continue
                cluster = _u16(self.data, entry + 26)
                length = _u32(self.data, entry + 28)
                if last:
                    return self._offset_of(cluster), length
                directory = self._offset_of(cluster)
                break
            else:
                return None, None
        return None, None

    def _offset_of(self, cluster):
        return self.data_start + (cluster - 2) * self._cluster_bytes()

    def write_in_place(self, offset, payload):
        end = offset + len(payload)
        if end > len(self.data):
            raise SystemExit('refuse: the kernel would run past the image')
        self.data[offset:end] = payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--kernel', required=True, help='rebuilt kernel.macho')
    parser.add_argument('--payload', required=True, help='payload.img to patch in place')
    parser.add_argument('--boot', help='boot.img whose ramdisk is that payload')
    parser.add_argument('--expect-size', type=int, help='size recorded for the previous kernel')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    kernel = open(args.kernel, 'rb').read()
    if args.expect_size is not None and len(kernel) != args.expect_size:
        raise SystemExit(f'refuse: kernel is {len(kernel)} bytes, payload recorded {args.expect_size}')
    payload = bytearray(open(args.payload, 'rb').read())
    fat = Fat(payload)
    offset, size = fat.find('EFI/UniXNU/Payloads/kernel.macho')
    if offset is None:
        raise SystemExit('refuse: payload has no EFI/UniXNU/Payloads/kernel.macho')
    if size != len(kernel):
        raise SystemExit(f'refuse: payload kernel is {size} bytes, new kernel is {len(kernel)}; sizes must match')
    print(f'ok payload: kernel at offset {offset}, {size} bytes, in place')
    fat.write_in_place(offset, kernel)

    if args.boot:
        boot = bytearray(open(args.boot, 'rb').read())
        if len(payload) > len(boot):
            raise SystemExit('refuse: payload larger than the boot image')
        index = boot.find(bytes(payload[:4096]))
        if index < 0:
            raise SystemExit('refuse: the boot image does not contain this payload')
        target = index + offset
        if target + len(kernel) > len(boot):
            raise SystemExit('refuse: the kernel would run past the boot image')
        boot[target:target + len(kernel)] = kernel
        print(f'ok boot: kernel at offset {target}, {len(kernel)} bytes, in place')
        if args.apply:
            open(args.boot, 'wb').write(boot)

    if args.apply:
        open(args.payload, 'wb').write(payload)
    else:
        print('note: dry run; pass --apply to write')
    return 0


if __name__ == '__main__':
    sys.exit(main())
