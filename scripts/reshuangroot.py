#!/usr/bin/env python3
"""Rebuild the SHNGROOT manifest header with a new Data window size.

Layout (drivers/NativeUfs/RootLayout.h:162-215):
  version@8 count@12 imageBytes@16, entries @24 step 128
    name[32] offset u64 size u64 block u32 flags u32 sha256[32] reserved[40]
  header sha256 over the first 4064 bytes, stored at 4064.

The entry sha256 field covers the window content; UEFI only checks the
header checksum, so the entry digest is recomputed over the new window
bytes at write time (the installer streams and hashes as it goes).
"""
import hashlib
import struct
import sys


def reshuangroot(path, new_data_size, out_path):
    raw = bytearray(open(path, 'rb').read())
    assert len(raw) == 4096 and raw[:8] == b'SHNGROOT', 'bad header'
    version, count, total = struct.unpack_from('<IIQ', raw, 8)
    assert version == 1 and 2 <= count <= 4, 'unsupported manifest'
    assert hashlib.sha256(raw[:4064]).digest() == raw[4064:], 'checksum'
    changed = None
    for i in range(count):
        o = 24 + 128 * i
        name = raw[o:o + 32].split(b'\0', 1)[0]
        off, size = struct.unpack_from('<QQ', raw, o + 32)
        if name == b'Data':
            if new_data_size < size:
                raise SystemExit(f'refusing to shrink Data {size} -> {new_data_size}')
            struct.pack_into('<Q', raw, o + 40, new_data_size)
            changed = (off, size, new_data_size)
    if changed is None:
        raise SystemExit('no Data entry')
    # imageBytes grows by the delta
    struct.pack_into('<Q', raw, 16, total + (changed[2] - changed[1]))
    # partition bounds check lives with the caller
    digest = hashlib.sha256(raw[:4064]).digest()
    raw[4064:4096] = digest
    open(out_path, 'wb').write(raw)
    print(f'Data: offset={changed[0]} size {changed[1]} -> {changed[2]}')
    print(f'imageBytes: {total} -> {total + changed[2] - changed[1]}')


if __name__ == '__main__':
    reshuangroot(sys.argv[1], int(sys.argv[2]), sys.argv[3])
