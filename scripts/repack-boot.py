#!/usr/bin/env python3
"""Repack an existing fastboot boot image with a new payload and/or firmware.

The K60 candidates are Android v4 boot images: the header structure is 1584
bytes, but each section begins on a 4096-byte page. The kernel slot holds the
UniXNU shim plus a compressed firmware volume and appended DTB; the ramdisk
slot holds the FAT payload. Preserve the complete header page and unsigned
signature area while replacing the requested slots.

It never talks to the phone and never writes outside --output.
"""
import argparse
import json
import struct
from pathlib import Path
import zlib

MAGIC = b'ANDROID!'


HEADER_SIZE = 1584
PAGE_SIZE = 4096


def page(size):
    return (size + PAGE_SIZE - 1) // PAGE_SIZE * PAGE_SIZE


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--template', type=Path, required=True, help='existing boot image to copy the header from')
    ap.add_argument('--kernel', type=Path, help='new kernel slot (shim + firmware volume); keep the template one otherwise')
    ap.add_argument('--ramdisk', type=Path, help='new payload image; keep the template one otherwise')
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()

    template = a.template.read_bytes()
    if len(template) < PAGE_SIZE or template[:8] != MAGIC:
        raise SystemExit('template is not an Android boot image')
    kernel_size, ramdisk_size = struct.unpack_from('<2I', template, 8)
    header_size = struct.unpack_from('<I', template, 20)[0]
    header_version = struct.unpack_from('<I', template, 40)[0]
    if header_size != HEADER_SIZE or header_version != 4:
        raise SystemExit('expected an Android v4 boot header')
    signature_size = struct.unpack_from('<I', template, HEADER_SIZE - 4)[0]
    k_off = PAGE_SIZE
    r_off = k_off + page(kernel_size)
    s_off = r_off + page(ramdisk_size)
    if signature_size != PAGE_SIZE or len(template) != s_off + signature_size:
        raise SystemExit('template has truncated sections or an unexpected signature area')
    tail = template[s_off:]
    if any(tail):
        raise SystemExit('expected the K60 unsigned, zero-filled signature area')

    kernel = a.kernel.read_bytes() if a.kernel else template[k_off:k_off + kernel_size]
    ramdisk = a.ramdisk.read_bytes() if a.ramdisk else template[r_off:r_off + ramdisk_size]
    stream = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        stream.decompress(kernel)
    except zlib.error as exc:
        raise SystemExit(f'invalid compressed firmware: {exc}') from exc
    dtb = stream.unused_data
    if not stream.eof or len(dtb) < 8 or dtb[:4] != b'\xd0\x0d\xfe\xed' or struct.unpack_from('>I', dtb, 4)[0] != len(dtb):
        raise SystemExit('kernel slot lacks a complete gzip firmware and appended DTB')

    header = bytearray(template[:PAGE_SIZE])
    struct.pack_into('<2I', header, 8, len(kernel), len(ramdisk))

    image = bytes(header)
    for blob in (kernel, ramdisk):
        image += blob + b'\x00' * (page(len(blob)) - len(blob))
    image += tail
    a.output.write_bytes(image)

    report = {
        'template': str(a.template), 'output': str(a.output),
        'header_version': header_version, 'header_bytes': header_size,
        'page_size': PAGE_SIZE, 'kernel_offset': PAGE_SIZE,
        'ramdisk_offset': PAGE_SIZE + page(len(kernel)),
        'signature_offset': PAGE_SIZE + page(len(kernel)) + page(len(ramdisk)),
        'signature_bytes': signature_size,
        'kernel_bytes': len(kernel), 'ramdisk_bytes': len(ramdisk),
        'image_bytes': len(image),
        'replaced': [n for n, v in (('kernel', a.kernel), ('ramdisk', a.ramdisk)) if v],
    }
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
