#!/usr/bin/env python3
"""Fixtures for scripts/extract-boot-img.py.

The point of the extractor is that a boot image on its own still yields the
kernel and payload hashes, so the test builds a real (small) boot image with a
real FAT volume in the ramdisk slot and re-derives every number from it.  A
parser that only agrees with the machine that produced the image proves
nothing, so nothing here reads a side file.
"""
import gzip
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / 'scripts' / 'extract-boot-img.py'
REAL = [Path('E:/k60-work/artifacts/power-conformance-20261119w11/boot.img'),
        Path('/mnt/e/k60-work/artifacts/power-conformance-20261119w11/boot.img')]
PAGE = 4096
CHECKS = []


def check(name, condition, detail=''):
    CHECKS.append((name, bool(condition), detail))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def lfn_checksum(short):
    total = 0
    for byte in short:
        total = (((total & 1) << 7) + (total >> 1) + byte) & 0xFF
    return total


def lfn_entries(name, short):
    """Build the long-file-name entries for one 8.3 name."""
    raw = name.encode('utf-16-le')
    units = [raw[i:i + 2] for i in range(0, len(raw), 2)]
    while len(units) % 13:
        units.append(b'\x00\x00')
    if len(units) % 13 == 0:
        units.append(b'\x00\x00')
        while len(units) % 13:
            units.append(b'\xff\xff')
    chunks = [units[i:i + 13] for i in range(0, len(units), 13)]
    checksum = lfn_checksum(short)
    out = []
    for index, chunk in enumerate(reversed(chunks)):
        order = len(chunks) - index
        entry = bytearray(32)
        entry[0] = order | (0x40 if index == 0 else 0)
        flat = b''.join(chunk).ljust(26, b'\xff')
        entry[1:11] = flat[0:10]
        entry[11] = 0x0F
        entry[13] = checksum
        entry[14:26] = flat[10:22]
        entry[26:28] = b'\x00\x00'
        entry[28:32] = flat[22:26]
        out.append(bytes(entry))
    return out


class Volume:
    """A FAT16 volume with directories, short names and long names."""

    def __init__(self, total_sectors=8192, reserved=1, nfats=1, root_entries=512):
        self.bps, self.spc = 512, 1
        self.reserved, self.nfats, self.root_entries = reserved, nfats, root_entries
        self.total = total_sectors
        self.root_sectors = (root_entries * 32 + self.bps - 1) // self.bps
        clusters = total_sectors
        while True:
            fat_sz = (clusters * 2 + self.bps - 1) // self.bps
            new = total_sectors - reserved - nfats * fat_sz - self.root_sectors
            if new == clusters:
                break
            clusters = new
        self.fat_sz = fat_sz
        self.fat_off = reserved * self.bps
        self.root_off = (reserved + nfats * fat_sz) * self.bps
        self.data_off = self.root_off + self.root_sectors * self.bps
        self.cluster_bytes = self.bps * self.spc
        self.image = bytearray(total_sectors * self.bps)
        self.next_free = 2
        self.fat = {}
        struct.pack_into('<H', self.image, 11, self.bps)
        self.image[13] = self.spc
        struct.pack_into('<H', self.image, 14, reserved)
        self.image[16] = nfats
        struct.pack_into('<H', self.image, 17, root_entries)
        struct.pack_into('<H', self.image, 19, total_sectors)
        struct.pack_into('<H', self.image, 22, self.fat_sz)
        self.image[21] = 0xF8
        struct.pack_into('<H', self.image, 24, 32)
        struct.pack_into('<H', self.image, 26, 64)
        self.image[510:512] = b'\x55\xaa'
        self.root_entries_list = []

    def alloc(self, data):
        count = max(1, (len(data) + self.cluster_bytes - 1) // self.cluster_bytes)
        first = self.next_free
        for index in range(count):
            cluster = first + index
            self.fat[cluster] = cluster + 1 if index + 1 < count else 0xFFFF
            start = self.data_off + (cluster - 2) * self.cluster_bytes
            self.image[start:start + self.cluster_bytes] = data[index * self.cluster_bytes:(index + 1) * self.cluster_bytes].ljust(self.cluster_bytes, b'\x00')
        self.next_free += count
        return first

    @staticmethod
    def short_name(name):
        stem, _, ext = name.partition('.')
        return (stem.upper()[:8].ljust(8) + ext.upper()[:3].ljust(3)).encode('ascii')

    def entry(self, name, attr, cluster, size, long_name=None):
        out = b''
        if long_name:
            out += b''.join(lfn_entries(long_name, self.short_name(name)))
        raw = bytearray(32)
        raw[0:11] = self.short_name(name)
        raw[11] = attr
        struct.pack_into('<H', raw, 26, cluster)
        struct.pack_into('<I', raw, 28, size)
        return out + bytes(raw)

    def build(self, files):
        """files maps 'dir/sub/NAME.EXT' to bytes."""
        tree = {}
        for path, data in files.items():
            parts = path.split('/')
            node = tree
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = data
        self._fill(tree, None)
        for index, (cluster, value) in enumerate(sorted(self.fat.items())):
            struct.pack_into('<H', self.image, self.fat_off + 2 * cluster, value)
        return bytes(self.image)

    def _fill(self, node, parent_cluster):
        entries = b''
        for name in sorted(node):
            value = node[name]
            if isinstance(value, dict):
                cluster = self.next_free
                self.next_free += 1
                self.fat[cluster] = 0xFFFF
                entries += self.entry(name, 0x10, cluster, 0)
                inner = self._fill(value, cluster)
                start = self.data_off + (cluster - 2) * self.cluster_bytes
                self.image[start:start + len(inner)] = inner
            else:
                cluster = self.alloc(value)
                entries += self.entry(name, 0x20, cluster, len(value), long_name=name)
        if parent_cluster is None:
            start = self.root_off
            limit = self.root_sectors * self.bps
        else:
            start = self.data_off + (parent_cluster - 2) * self.cluster_bytes
            limit = self.cluster_bytes
        if len(entries) > limit:
            raise SystemExit('fixture volume too small for %d entries' % (len(entries) // 32))
        padded = entries.ljust(limit, b'\x00')
        self.image[start:start + len(padded)] = padded
        return padded


def build_image(payload, fd=b'FD-CONTENT' * 40, dtb=b'\xd0\x0d\xfe\xed' + b'\x00' * 60):
    slot = gzip.compress(fd, mtime=0) + dtb
    header = bytearray(PAGE)
    header[0:8] = b'ANDROID!'
    struct.pack_into('<I', header, 8, len(slot))
    struct.pack_into('<I', header, 12, len(payload))
    struct.pack_into('<I', header, 20, 1584)
    struct.pack_into('<I', header, 40, 4)
    body = bytes(header) + slot
    body += b'\x00' * ((-len(body)) % PAGE)
    return body + payload, slot


def run(*args):
    done = subprocess.run([sys.executable, str(TOOL), *[str(a) for a in args]],
                          capture_output=True, text=True, encoding='utf-8', errors='replace',
                          env={**__import__('os').environ, 'PYTHONIOENCODING': 'utf-8'})
    return done.returncode, done.stdout, done.stderr


def main():
    work = ROOT / 'build' / ('extract-boot-img-tests-%d' % __import__('os').getpid())
    work.mkdir(parents=True, exist_ok=True)
    kernel = b'MACHO' + b'k' * 5000
    adt = b'ADT' + b'a' * 900
    volume = Volume()
    payload = volume.build({'EFI/UniXNU/Payloads/kernel.macho': kernel,
                            'EFI/UniXNU/Payloads/kernel.macho.adt': adt,
                            'unixnu.toml': b'version = 1\n'})
    image, slot = build_image(payload)
    img = work / 'boot.img'
    img.write_bytes(image)

    code, out, err = run('--img', img)
    check('roundtrip exits 0', code == 0, err.strip())
    check('image hash printed', sha(image) in out, out)
    check('kernel slot hash printed', sha(slot) in out, out)
    check('payload hash printed', sha(payload) in out, out)
    check('in-volume kernel hash printed', sha(kernel) in out, out)
    check('in-volume adt hash printed', sha(adt) in out, out)
    check('long names are reassembled', 'EFI/UniXNU/Payloads/kernel.macho ' in out, out)

    code, out, _ = run('--img', img, '--json')
    report = json.loads(out)
    check('json reports the same payload', report['payload']['sha256'] == sha(payload), out[:200])
    check('json reports the fat kind', report['payload']['fat'] == 'fat16', report['payload'].get('fat'))
    check('json reports the file sizes',
          report['files']['EFI/UniXNU/Payloads/kernel.macho']['bytes'] == len(kernel), '')

    outdir = work / 'parts'
    code, _, err = run('--img', img, '--out', outdir)
    check('--out exits 0', code == 0, err.strip())
    check('--out writes the slot', (outdir / 'kernel-slot.bin').read_bytes() == slot, '')
    check('--out writes the dtb', (outdir / 'hardware.dtb').read_bytes()[:4] == b'\xd0\x0d\xfe\xed', '')
    check('--out writes the payload', (outdir / 'payload.img').read_bytes() == payload, '')
    check('--out writes the volume file',
          (outdir / 'EFI/UniXNU/Payloads/kernel.macho').read_bytes() == kernel, '')

    code, _, err = run('--img', img, '--file', 'EFI/UniXNU/Payloads/missing.bin')
    check('a missing file is rc 2', code == 2, str(code))
    check('the missing file is named', 'missing.bin is not in the volume' in err, err)

    junk = work / 'junk.img'
    junk.write_bytes(b'NOTABOOT' + b'\x00' * 5000)
    code, _, err = run('--img', junk)
    check('a non-boot image is rc 3', code == 3, str(code))
    check('the magic is quoted', 'is not an Android boot image' in err, err)

    short = work / 'short.img'
    short.write_bytes(image[:PAGE + 100])
    code, _, err = run('--img', short)
    check('a truncated image is rc 3', code == 3, str(code))
    check('truncation says so', 'is truncated' in err, err)

    bare, _ = build_image(volume.build({'EFI/UniXNU/Payloads/kernel.macho': kernel}))
    bare_img = work / 'bare.img'
    bare_img.write_bytes(bare)
    code, _, err = run('--img', bare_img, '--json')
    check('a volume without the adt is rc 2', code == 2, str(code))
    check('the missing adt is named', 'kernel.macho.adt is not in the volume' in err, err)
    code, out, _ = run('--img', bare_img, '--file', 'EFI/UniXNU/Payloads/kernel.macho', '--json')
    check('asking only for the kernel succeeds', code == 0, str(code))
    check('the kernel hash is reported', json.loads(out)['files']['EFI/UniXNU/Payloads/kernel.macho']['sha256'] == sha(kernel), '')

    real = next((p for p in REAL if p.exists()), None)
    if real is None:
        print('note: no w11 boot image on this host; the real-image case is skipped')
    else:
        code, out, err = run('--img', real)
        check('the real image parses', code == 0, err.strip()[:200])
        check('the real image hash is the recorded one',
              '6db4e6b78bdab557d4f34b17aaf6a25caa9990d564faf94ef18853fbde589844' in out, '')
        check('the real payload hash is the recorded one',
              'bd8ed29dd420be2829d68f9b3887b29976a3b0b3f79a3bf1c9dd40bc0cf2e63f' in out, '')
        check('the real in-volume kernel is the probe-patched one',
              '30a058f274b3c4cbcfc88515ef4bbf6ef45adf47124af16aa0a54966b9345a90' in out, '')
        check('the real adt hash is the recorded one',
              '721fb484eb01800b5e1e0a94bb47db1edbdaf636d53ecdcff83659caa2be3853' in out, '')

    failed = [c for c in CHECKS if not c[1]]
    for name, ok, detail in CHECKS:
        if not ok:
            print('FAIL %s%s' % (name, (': ' + detail.strip()[:300]) if detail else ''))
    print('TESTS OK %d checks (%d failure(s))' % (len(CHECKS), len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
