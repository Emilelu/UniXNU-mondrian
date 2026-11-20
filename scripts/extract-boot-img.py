#!/usr/bin/env python3
"""Re-derive a K60 boot image's parts from the image alone.

Why this exists: the w11 probe image is archived as a single boot.img, while
docs/research/power/01-EPSS-PROBE.md cites a kernel.macho that no longer sits
next to it.  A citation to a file that is gone cannot be re-checked, and a hash
that only one machine ever computed is not evidence.  Everything below is
derivable from the image: the kernel slot (gzip of the UEFI FD behind the
112-byte shim, followed by hardware.dtb), the payload in the ramdisk slot, and
any file inside the payload's FAT volume.

  python3 scripts/extract-boot-img.py --img boot.img
  python3 scripts/extract-boot-img.py --img boot.img --out build/w11-parts
  python3 scripts/extract-boot-img.py --img boot.img --file Payloads/kernel.macho.adt --json

The kernel slot is NOT the XNU kernel: on darwin22+ the kernel lives inside the
payload volume, and boot.json's kernel_sha256 names the slot, not the kernel
(P-200 measured that field and found it identical across eleven different
images).  Both numbers are printed here, so a citation can say which one it
means.
Exit 0 on success, 2 when a requested file is not in the volume, 3 when the
image is not a boot image or is truncated.
"""
import argparse
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path

MAGIC = b'ANDROID!'
PAGE = 4096
DEFAULT_FILES = ('EFI/UniXNU/Payloads/kernel.macho',
                 'EFI/UniXNU/Payloads/kernel.macho.adt')


def digest(data):
    return hashlib.sha256(data).hexdigest()


class VolumeError(Exception):
    """The payload volume cannot be read."""


class Fat:
    """Read files out of a FAT12/16/32 volume held in memory."""

    def __init__(self, vol):
        if len(vol) < 512:
            raise VolumeError('payload is smaller than one sector')
        self.vol = vol
        self.bps, = struct.unpack_from('<H', vol, 11)
        self.spc = vol[13]
        self.reserved, = struct.unpack_from('<H', vol, 14)
        self.nfats = vol[16]
        self.root_entries, = struct.unpack_from('<H', vol, 17)
        total16, = struct.unpack_from('<H', vol, 19)
        fat16, = struct.unpack_from('<H', vol, 22)
        total32, = struct.unpack_from('<I', vol, 32)
        fat32, = struct.unpack_from('<I', vol, 36)
        self.root_cluster, = struct.unpack_from('<I', vol, 44)
        total = total16 or total32
        fat_sz = fat16 or fat32
        if self.bps not in (512, 1024, 2048, 4096) or self.spc == 0 or fat_sz == 0 or total == 0:
            raise VolumeError('not a FAT volume (bps %d, spc %d, fat %d, sectors %d)'
                              % (self.bps, self.spc, fat_sz, total))
        root_sectors = ((self.root_entries * 32) + self.bps - 1) // self.bps
        self.fat_off = self.reserved * self.bps
        self.root_off = (self.reserved + self.nfats * fat_sz) * self.bps
        self.data_off = self.root_off + root_sectors * self.bps
        self.cluster_bytes = self.bps * self.spc
        clusters = (total - (self.reserved + self.nfats * fat_sz + root_sectors)) // self.spc
        self.kind = 'fat12' if clusters < 4085 else ('fat16' if clusters < 65525 else 'fat32')

    def next_cluster(self, cluster):
        if self.kind == 'fat32':
            value, = struct.unpack_from('<I', self.vol, self.fat_off + 4 * cluster)
            return value & 0x0FFFFFFF
        if self.kind == 'fat16':
            value, = struct.unpack_from('<H', self.vol, self.fat_off + 2 * cluster)
            return value
        offset = self.fat_off + cluster + cluster // 2
        value, = struct.unpack_from('<H', self.vol, offset)
        return (value >> 4) if cluster & 1 else (value & 0x0FFF)

    def is_end(self, cluster):
        if self.kind == 'fat12':
            return cluster >= 0x0FF8
        if self.kind == 'fat16':
            return cluster >= 0xFFF8
        return cluster >= 0x0FFFFFF8

    def chain(self, first):
        out, cluster, seen = [], first, set()
        while 2 <= cluster and not self.is_end(cluster):
            if cluster in seen or len(out) > 1 << 20:
                raise VolumeError('cluster chain loops at %d' % cluster)
            seen.add(cluster)
            out.append(cluster)
            cluster = self.next_cluster(cluster)
        return out

    def cluster_bytes_at(self, cluster):
        start = self.data_off + (cluster - 2) * self.cluster_bytes
        return self.vol[start:start + self.cluster_bytes]

    def read(self, first, size=None):
        data = b''.join(self.cluster_bytes_at(c) for c in self.chain(first))
        return data[:size] if size is not None else data

    def entries(self, first, fixed=False):
        raw = self.vol[self.root_off:self.root_off + self.root_entries * 32] if fixed else self.read(first)
        long_name, out = [], []
        for index in range(0, len(raw) - 31, 32):
            entry = raw[index:index + 32]
            if entry[0] == 0x00:
                break
            if entry[0] == 0xE5:
                long_name = []
                continue
            attr = entry[11]
            if attr == 0x0F:
                chunk = (entry[1:11] + entry[14:26] + entry[28:32]).decode('utf-16-le', 'replace')
                long_name.append(chunk.replace('\x00', '').replace('\uffff', ''))
                continue
            short = bytearray(entry[0:11])
            if short[0] == 0x05:
                short[0] = 0xE5
            base = bytes(short[0:8]).decode('latin-1').rstrip()
            ext = bytes(short[8:11]).decode('latin-1').rstrip()
            name = (base + '.' + ext) if ext else base
            high, = struct.unpack_from('<H', entry, 20)
            low, = struct.unpack_from('<H', entry, 26)
            size, = struct.unpack_from('<I', entry, 28)
            long = ''.join(reversed(long_name)) if long_name else ''
            long_name = []
            out.append({'name': long or name, 'short': name, 'attr': attr,
                        'cluster': (high << 16) | low, 'size': size})
        return out

    def find(self, path):
        parts = [p for p in path.replace('\\', '/').split('/') if p]
        if not parts:
            raise VolumeError('empty path')
        first, fixed = self.root_cluster, self.kind != 'fat32'
        for index, want in enumerate(parts):
            match = None
            for entry in self.entries(first, fixed=fixed):
                if entry['name'].lower() == want.lower() or entry['short'].lower() == want.lower():
                    match = entry
                    break
            if match is None:
                raise VolumeError('%s is not in the volume' % '/'.join(parts[:index + 1]))
            if index + 1 == len(parts):
                if match['attr'] & 0x10:
                    raise VolumeError('%s is a directory, not a file' % path)
                return self.read(match['cluster'], match['size'])
            if not match['attr'] & 0x10:
                raise VolumeError('%s is a file, not a directory' % '/'.join(parts[:index + 1]))
            first, fixed = match['cluster'], False
        raise VolumeError('%s is not in the volume' % path)


def split_kernel_slot(slot):
    """Return (gzip stream, trailing dtb) by letting zlib report unused_data."""
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    inflated = decompressor.decompress(slot)
    if not decompressor.eof:
        raise ValueError('the kernel slot does not hold a complete gzip stream')
    stream = len(slot) - len(decompressor.unused_data)
    return slot[:stream], slot[stream:], inflated


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--img', type=Path, required=True)
    parser.add_argument('--out', type=Path, help='write the parts under this directory')
    parser.add_argument('--file', action='append', default=[],
                        help='file inside the payload volume (repeatable; default %s)'
                             % ', '.join(DEFAULT_FILES))
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()

    data = args.img.read_bytes()
    if len(data) < PAGE or data[:8] != MAGIC:
        print('extract-boot-img: %s is not an Android boot image (magic %r)'
              % (args.img, data[:8]), file=sys.stderr)
        return 3
    kernel_size, = struct.unpack_from('<I', data, 8)
    ramdisk_size, = struct.unpack_from('<I', data, 12)
    header_size, = struct.unpack_from('<I', data, 20)
    header_version, = struct.unpack_from('<I', data, 40)
    kernel_off = PAGE
    ramdisk_off = PAGE + ((kernel_size + PAGE - 1) // PAGE) * PAGE
    if kernel_size == 0 or ramdisk_off + ramdisk_size > len(data):
        print('extract-boot-img: %s is truncated (kernel %d B at %d, ramdisk %d B at %d, file %d B)'
              % (args.img, kernel_size, kernel_off, ramdisk_size, ramdisk_off, len(data)),
              file=sys.stderr)
        return 3
    slot = data[kernel_off:kernel_off + kernel_size]
    try:
        stream, dtb, inflated = split_kernel_slot(slot)
    except ValueError as error:
        print('extract-boot-img: %s' % error, file=sys.stderr)
        return 3
    payload = data[ramdisk_off:ramdisk_off + ramdisk_size]

    report = {
        'image': str(args.img),
        'image_bytes': len(data),
        'image_sha256': digest(data),
        'header_version': header_version,
        'header_size': header_size,
        'kernel_slot': {'bytes': len(slot), 'sha256': digest(slot),
                        'gzip_bytes': len(stream), 'dtb_bytes': len(dtb),
                        'dtb_sha256': digest(dtb), 'inflated_bytes': len(inflated)},
        'payload': {'offset': ramdisk_off, 'bytes': len(payload), 'sha256': digest(payload)},
        'files': {},
    }

    if payload:
        try:
            volume = Fat(payload)
        except VolumeError as error:
            print('extract-boot-img: the ramdisk slot holds no readable volume: %s' % error,
                  file=sys.stderr)
            return 3
        report['payload']['fat'] = volume.kind
        for name in (args.file or list(DEFAULT_FILES)):
            try:
                blob = volume.find(name)
            except VolumeError as error:
                print('extract-boot-img: %s' % error, file=sys.stderr)
                return 2
            report['files'][name] = {'bytes': len(blob), 'sha256': digest(blob)}
            if args.out is not None:
                target = args.out / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(blob)

    if args.out is not None:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / 'kernel-slot.bin').write_bytes(slot)
        (args.out / 'hardware.dtb').write_bytes(dtb)
        if payload:
            (args.out / 'payload.img').write_bytes(payload)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print('%s  %d B  sha256 %s' % (args.img.name, len(data), report['image_sha256']))
        print('kernel slot  %d B  sha256 %s  (gzip %d B + dtb %d B, inflated %d B)'
              % (len(slot), report['kernel_slot']['sha256'], len(stream), len(dtb), len(inflated)))
        print('payload      %d B at %d  sha256 %s'
              % (len(payload), ramdisk_off, report['payload']['sha256']))
        for name, item in report['files'].items():
            print('%-34s %d B  sha256 %s' % (name, item['bytes'], item['sha256']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
