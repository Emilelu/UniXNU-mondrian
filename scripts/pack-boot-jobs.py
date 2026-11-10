#!/usr/bin/env python3
"""Pack a directory tree into the compact archive the kernel deployer expands.

The kernel side is C with no libarchive, so the format is deliberately trivial:
a header, then for each entry a fixed 96-byte record followed by the name and,
for regular files, the data. Everything is little endian and 4 KiB aligned so
the deployer can write with plain vn_rdwr calls.

  magic  8 bytes  "PONGJOB1"
  count  u32
  then `count` records:
    mode   u32   (S_IFMT | permission bits)
    uid    u32
    gid    u32
    size   u32   (data length; 0 for directories and symlinks)
    nlen   u32   (name length, no trailing NUL)
    dlen   u32   (link target length; 0 unless S_IFLNK)
    name   nlen bytes (relative path, no leading slash)
    data   size bytes (only when S_IFREG)

usage: pack-boot-jobs.py --src DIR --out FILE
"""
import argparse
import os
import stat
import struct
from pathlib import Path

MAGIC = b'PONGJOB1'
HEADER = struct.Struct('<8sI')
RECORD = struct.Struct('<IIIII I')  # mode uid gid size nlen dlen


def entries(root):
    root = Path(root)
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root).as_posix()
        info = path.lstat()
        mode = info.st_mode
        if stat.S_ISDIR(mode):
            yield rel, mode, info.st_uid, info.st_gid, b'', b''
        elif stat.S_ISLNK(mode):
            target = os.readlink(path).encode()
            yield rel, mode, info.st_uid, info.st_gid, b'', target
        elif stat.S_ISREG(mode):
            yield rel, mode, info.st_uid, info.st_gid, path.read_bytes(), b''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    args = ap.parse_args()

    items = list(entries(args.src))
    blob = bytearray(HEADER.pack(MAGIC, len(items)))
    for name, mode, uid, gid, data, link in items:
        raw = name.encode()
        blob += RECORD.pack(mode & 0xffff, uid & 0xffffffff, gid & 0xffffffff,
                            len(data), len(raw), len(link))
        blob += raw + link + data
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(bytes(blob))
    print(f'packed {len(items)} entries into {len(blob)} bytes -> {args.out}')


if __name__ == '__main__':
    main()
