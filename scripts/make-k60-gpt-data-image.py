#!/usr/bin/env python3
"""Wrap a bare APFS container in a GPT disk image for the UFS Data window.

PongUfsTransport publishes the Data window only when the window starts with a
GPT (it checks "EFI PART" at offset 512), and iOS keeps its Data volume inside a
partition for the same reason. Our seed is a bare APFS container, so this script
puts it in a partition and emits the disk image the window needs.

The APFS container bytes are copied verbatim: the volume UUID inside it is what
the kernel looks up, so wrapping must not move or rewrite any of it.
"""
import argparse
import binascii
import hashlib
import struct
import sys
from pathlib import Path

LBA = 512
GPT_ENTRIES = 128
GPT_ENTRY_SIZE = 128
GPT_ENTRY_SECTORS = GPT_ENTRIES * GPT_ENTRY_SIZE // LBA        # 32
APFS_TYPE = '7C3457EF-0000-11AA-AA11-00306543ECAC'
BASIC_DATA_TYPE = 'EBD0A0A2-B9E5-4433-87C0-68B6B72699C7'


def guid_bytes(text, mit_byte_order=True):
    """A GUID as the on-disk 16 bytes. GPT stores the first three fields
    little-endian, which is why the text form is reversed there."""
    h = text.replace('-', '')
    if len(h) != 32:
        raise SystemExit(f'bad GUID: {text}')
    raw = bytes.fromhex(h)
    if not mit_byte_order:
        return raw
    return (raw[0:4][::-1] + raw[4:6][::-1] + raw[6:8][::-1] + raw[8:])


def crc32(data):
    return binascii.crc32(data) & 0xFFFFFFFF


def protective_mbr(total_sectors):
    mbr = bytearray(LBA)
    # one partition, type 0xEE, spanning the disk as far as an MBR entry can say
    entry = bytearray(16)
    entry[0] = 0x00
    entry[1:4] = b'\x00\x02\x00'          # CHS start (unused)
    entry[4] = 0xEE                        # GPT protective
    entry[5:8] = b'\xff\xff\xff'           # CHS end (unused)
    entry[8:12] = struct.pack('<I', 1)     # first LBA
    entry[12:16] = struct.pack('<I', min(total_sectors - 1, 0xFFFFFFFF))
    mbr[446:462] = entry
    mbr[510:512] = b'\x55\xAA'
    return bytes(mbr)


def gpt_header(current_lba, backup_lba, first_usable, last_usable,
               entries_lba, disk_guid, entries_crc, header_size=92):
    header = bytearray(LBA)
    struct.pack_into('<8sIIIIQQQQ16sQIII', header, 0,
                     b'EFI PART',            # signature
                     0x00010000,             # revision 1.0
                     header_size,            # header size
                     0,                      # header CRC, filled later
                     0,                      # reserved
                     current_lba,
                     backup_lba,
                     first_usable,
                     last_usable,
                     guid_bytes(disk_guid),
                     entries_lba,
                     GPT_ENTRIES,
                     GPT_ENTRY_SIZE,
                     entries_crc)
    body = bytes(header[:header_size])
    struct.pack_into('<I', header, 16, crc32(body))
    return bytes(header)


def build(apfs, output, spare_mib=1):
    size = apfs.stat().st_size
    head = apfs.open('rb').read(36)
    if head[32:36] != b'NXSB':
        raise SystemExit(f'{apfs} is not an APFS container (no NXSB at offset 32)')
    apfs_sectors = -(-size // LBA)
    lead_sectors = 34                                    # GPT entry array only; the window has no spare MiB
    tail_sectors = (spare_mib * 1024 * 1024) // LBA
    total_sectors = lead_sectors + apfs_sectors + tail_sectors
    first_usable = 34
    last_usable = total_sectors - GPT_ENTRY_SECTORS - 2

    disk_guid = '4B363044-4154-4131-3030-000000000001'
    part_guid = '4B363044-4154-4131-3030-000000000002'

    entries = bytearray(GPT_ENTRIES * GPT_ENTRY_SIZE)
    first_lba = lead_sectors
    last_lba = lead_sectors + apfs_sectors - 1
    struct.pack_into('<16s16sQQQ72s', entries, 0,
                     guid_bytes(APFS_TYPE), guid_bytes(part_guid),
                     first_lba, last_lba, 0, 'K60 Data'.encode('utf-16-le'))
    entries_crc = crc32(bytes(entries))

    primary = gpt_header(1, total_sectors - 1, first_usable, last_usable,
                         2, disk_guid, entries_crc)
    backup_entries_lba = total_sectors - 1 - GPT_ENTRY_SECTORS
    backup = gpt_header(total_sectors - 1, 1, first_usable, last_usable,
                        backup_entries_lba, disk_guid, entries_crc)

    apfs_hash = hashlib.sha256()
    image_hash = hashlib.sha256()
    with output.open('wb') as out:
        def put(data):
            out.write(data); image_hash.update(data)
        put(protective_mbr(total_sectors))
        put(primary)
        put(bytes(entries))
        pad = lead_sectors * LBA - (2 + GPT_ENTRY_SECTORS) * LBA
        if pad: put(bytes(pad))
        with apfs.open('rb') as src:
            while True:
                chunk = src.read(8 * 1024 * 1024)
                if not chunk: break
                apfs_hash.update(chunk); put(chunk)
        rest = total_sectors * LBA - (lead_sectors * LBA + apfs_sectors * LBA)
        if rest: put(bytes(rest))
    # The backup entries and header live at the tail; rewrite them in place.
    with output.open('r+b') as out:
        out.seek(backup_entries_lba * LBA); out.write(bytes(entries))
        out.seek((total_sectors - 1) * LBA); out.write(backup)
    return dict(output=str(output), bytes=total_sectors * LBA, total_sectors=total_sectors,
                partition=dict(first_lba=first_lba, last_lba=last_lba,
                               type_guid=APFS_TYPE, name='K60 Data'),
                apfs_bytes=size, apfs_sha256=apfs_hash.hexdigest(),
                image_sha256=image_hash.hexdigest())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apfs', type=Path, required=True, help='bare APFS container')
    p.add_argument('--output', type=Path, required=True, help='GPT disk image to write')
    p.add_argument('--spare-mib', type=int, default=1,
                   help='tail space after the APFS partition, in MiB')
    a = p.parse_args()
    if a.output.exists():
        raise SystemExit(f'refusing to overwrite {a.output}')
    report = build(a.apfs, a.output, a.spare_mib)
    print('wrote', report['output'], report['bytes'], 'bytes')
    print('partition', report['partition'])
    print('image sha256', report['image_sha256'])
    print('apfs bytes', report['apfs_bytes'], 'sha256', report['apfs_sha256'])


if __name__ == '__main__':
    sys.exit(main())
