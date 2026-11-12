#!/usr/bin/env python3
"""Repair damaged com.apple.ResourceFork xattr streams in os-window.img.

Source of truth: the IPSW dmg (read via apfs.py, partition-relative blocks).
Destination: the raw APFS os-window.img (base 0), patched block by block.
"""
import sys, struct
sys.path.insert(0, '/root/k60/device/tools/apfs')
import apfs

SRC = 'ipsw/096-57366-083.dmg'
DST = 'windows/os-window.img'
BS = 4096

orig = apfs.Blocks.get
apfs.Blocks.get = lambda self, addr, verify=True: orig(self, addr, verify=False)

ci = apfs.Container(SRC)
vi = ci.volumes()[0]
cw = apfs.Container(DST)
vw = cw.volumes()[0]

print('dmg base (partition offset):', ci.image.base if hasattr(ci, 'image') else '?')
print('img size:', cw.image.size if hasattr(cw, 'image') else '?')


def rf(v, path):
    r = v.lookup(path)
    if not r:
        return None
    oid, _ = r
    xs = v.xattrs(oid)
    if 'com.apple.ResourceFork' not in xs:
        return None
    flags, xdata = xs['com.apple.ResourceFork']
    if flags & apfs.XATTR_DATA_EMBEDDED:
        return None
    xoid, size = struct.unpack_from('<QQ', xdata, 0)
    return v.extents(xoid), size


def listdir(v, path):
    r = v.lookup(path)
    if not r:
        return []
    oid, _ = r
    return [path + '/' + n for n, fid, t in v.dir_entries(oid) if t in (8, 0)]


paths = sys.argv[1:] or (listdir(vw, '/usr/libexec') + listdir(vw, '/usr/sbin')
                         + listdir(vw, '/usr/bin') + listdir(vw, '/bin'))

f = open(DST, 'r+b')
repaired = clean = 0
for p in paths:
    s = rf(vi, p)
    d = rf(vw, p)
    if s is None or d is None:
        continue
    (s_ext, s_size), (d_ext, d_size) = s, d
    if s_size != d_size:
        print(f'  SIZE MISMATCH {p}')
        continue
    # build source stream bytes
    src = bytearray(s_size)
    for logical, length, phys in s_ext:
        if logical >= s_size:
            continue
        n = min(length, s_size - logical)
        nb = (length + BS - 1) // BS
        raw = ci.blocks.raw(phys, nb)
        src[logical:logical + n] = raw[:n]
    # write into destination physical blocks
    # os-window.img is a GPT disk image: APFS blocks live at
    # image.base + phys * block_size, NOT phys * block_size.
    base = cw.image.base
    wrote = 0
    for logical, length, phys in d_ext:
        if phys == 0 or logical >= d_size:
            continue
        n = min(length, d_size - logical)
        f.seek(base + phys * BS)
        f.write(src[logical:logical + n])
        wrote += n
    if wrote:
        repaired += 1
    else:
        clean += 1
f.close()
print(f'repaired={repaired} already-clean={clean} of {len(paths)}')
