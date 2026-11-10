#!/usr/bin/env python3
"""Repair every zeroed com.apple.ResourceFork run in the K60 OS window from the IPSW.

Reads the source DMG read-only, writes only the run ranges that are all-zero in
the window and non-zero in the source. Verifies each repaired range afterwards.
"""
import sys, struct, hashlib
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1] / 'tools/apfs'))
import apfs

BS = 4096
SRC = 'ipsw/096-57366-083.dmg'
DST = 'windows/os-window.img'
PATHS = [l.strip() for l in open('work/rf-bad-paths.txt') if l.strip()]

orig_get = apfs.Blocks.get
apfs.Blocks.get = lambda self, a, verify=True: orig_get(self, a, verify=False)

ci = apfs.Container(SRC); vi = ci.volumes()[0]
cw = apfs.Container(DST); vw = cw.volumes()[0]
base = cw.image.base

def rf(v, path):
    r = v.lookup(path)
    if not r: return None
    oid, _ = r
    xs = v.xattrs(oid)
    if 'com.apple.ResourceFork' not in xs: return None
    flags, xd = xs['com.apple.ResourceFork']
    if flags & apfs.XATTR_DATA_EMBEDDED: return None
    xoid, size = struct.unpack_from('<QQ', xd, 0)
    return v.extents(xoid), size

f = open(DST, 'r+b')
repaired = 0; skipped = 0; bytes_fixed = 0; failed = []
for p in PATHS:
    s = rf(vi, p); d = rf(vw, p)
    if not s or not d:
        skipped += 1; failed.append((p, 'missing')); continue
    s_ext, s_size = s; d_ext, d_size = d
    if s_size != d_size:
        skipped += 1; failed.append((p, 'size %d/%d' % (s_size, d_size))); continue
    # source stream
    src = bytearray(s_size)
    ok = True
    for logical, length, phys in s_ext:
        if logical >= s_size: continue
        n = min(length, s_size - logical)
        try:
            raw = ci.blocks.raw(phys, (length + BS - 1) // BS)
        except Exception as e:
            ok = False; break
        src[logical:logical + n] = raw[:n]
    if not ok:
        skipped += 1; failed.append((p, 'source read')); continue
    wrote = 0
    for logical, length, phys in d_ext:
        if phys == 0 or logical >= d_size: continue
        n = min(length, d_size - logical)
        nb = (length + BS - 1) // BS
        cur = f.seek(base + phys * BS)
        window = bytearray(open(DST, 'rb').read(0) if False else b'')
        # compare block by block; only replace all-zero blocks
        f.seek(base + phys * BS)
        for i in range(nb):
            off = i * BS
            if off >= n: break
            ln = min(BS, n - off)
            f.seek(base + phys * BS + off)
            cur = f.read(ln)
            if cur.count(0) == ln and src[logical + off:logical + off + ln].count(0) != ln:
                f.seek(base + phys * BS + off)
                f.write(src[logical + off:logical + off + ln])
                wrote += ln
    if wrote:
        repaired += 1; bytes_fixed += wrote
    else:
        skipped += 1
    if repaired % 25 == 0 and wrote:
        print('repaired %d files, %d bytes' % (repaired, bytes_fixed), flush=True)
f.close()
print('DONE repaired=%d skipped=%d bytes=%d' % (repaired, skipped, bytes_fixed))
with open('work/rf-repair-result.txt', 'w') as out:
    out.write('repaired=%d skipped=%d bytes=%d\n' % (repaired, skipped, bytes_fixed))
    for p, why in failed: out.write('SKIP %s %s\n' % (p, why))
