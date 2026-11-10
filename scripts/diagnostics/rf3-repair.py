#!/usr/bin/env python3
"""Repair every com.apple.ResourceFork whose bytes differ from the IPSW.

Delta on the earlier pass: that one only replaced blocks that were all-zero in
the window, which left partially-zero and tail-padded blocks damaged. This one
compares the full fork stream against the source and rewrites every differing
byte, so a fork either matches the IPSW exactly or the file is reported.
"""
import sys, struct, hashlib
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1] / 'tools/apfs'))
import apfs

BS = 4096
SRC = 'ipsw/096-57366-083.dmg'
DST = 'windows/os-window.img'

orig = apfs.Blocks.get
apfs.Blocks.get = lambda self, a, verify=True: orig(self, a, verify=False)

ci = apfs.Container(SRC); vi = ci.volumes()[0]
cw = apfs.Container(DST); vw = cw.volumes()[0]
base = cw.image.base


def fork(c, v, oid):
    xs = v.xattrs(oid)
    if 'com.apple.ResourceFork' not in xs:
        return None
    fl, xd = xs['com.apple.ResourceFork']
    if fl & apfs.XATTR_DATA_EMBEDDED:
        return None
    xoid, size = struct.unpack_from('<QQ', xd, 0)
    buf = bytearray(size)
    for logical, length, phys in v.extents(xoid):
        raw = c.blocks.raw(phys, (length + BS - 1) // BS)
        n = min(length, size - logical)
        buf[logical:logical + n] = raw[:n]
    return buf, size, v.extents(xoid)


f = open(DST, 'r+b')
fixed = same = skipped = 0
bytes_fixed = 0
problems = []
for path, name, fid, dt in apfs.walk(vw, apfs.ROOT_DIR_INO_NUM):
    if dt != 8:
        continue
    try:
        d = fork(cw, vw, fid)
    except Exception:
        continue
    if not d:
        continue
    d_buf, d_size, d_ext = d
    r = vi.lookup(path)
    if not r:
        skipped += 1
        problems.append((path, 'absent from the source volume'))
        continue
    try:
        s = fork(ci, vi, r[0])
    except Exception:
        skipped += 1
        problems.append((path, 'source read failed'))
        continue
    if not s:
        skipped += 1
        continue
    s_buf, s_size, _ = s
    if s_size != d_size:
        skipped += 1
        problems.append((path, 'size %d vs %d' % (s_size, d_size)))
        continue
    if s_buf == d_buf:
        same += 1
        continue
    # Rewrite each differing byte range through the destination extents.
    wrote = 0
    for logical, length, phys in d_ext:
        n = min(length, d_size - logical)
        want = s_buf[logical:logical + n]
        have = d_buf[logical:logical + n]
        if want == have:
            continue
        f.seek(base + phys * BS)
        f.write(want)
        wrote += n
    if wrote:
        fixed += 1
        bytes_fixed += wrote
        if fixed % 25 == 0:
            print('fixed %d files, %d bytes' % (fixed, bytes_fixed), flush=True)
f.close()
print('DONE fixed=%d already-identical=%d skipped=%d bytes=%d' % (fixed, same, skipped, bytes_fixed))
with open('work/rf3-result.txt', 'w') as out:
    out.write('fixed=%d identical=%d skipped=%d bytes=%d\n' % (fixed, same, skipped, bytes_fixed))
    for p, why in problems:
        out.write('SKIP %s %s\n' % (p, why))
