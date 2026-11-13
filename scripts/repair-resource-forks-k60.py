#!/usr/bin/env python3
"""Repair damaged com.apple.ResourceFork xattr streams in the OS window.

来源：yibiya/UniXNU-mondrian commit 96008141（scripts/repair-resource-forks.py）
本文件仅把硬编码路径改成本机路径，算法与判据完全一致。

背景（原文）：
  297 files in the installed OS window lost their decmpfs chunk tables
  (com.apple.ResourceFork zeroed by an earlier partial window write), so
  chunked-zlib executables failed to decompress and every affected daemon
  died with ENOMEM -> EACCES at exec.

用法：
  python3 repair-resource-forks-k60.py <os-window.img> [目标路径...]
  （不给路径时扫描 /usr/libexec /usr/sbin /usr/bin /bin）

Source of truth: the IPSW dmg (read via apfs.py, partition-relative blocks).
Destination: the raw APFS os-window.img, patched block by block.
"""
import sys, struct, os

APFS_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools', 'apfs')
sys.path.insert(0, APFS_TOOLS)
import apfs

SRC = '/mnt/e/hackios/UniXNU/out/ipsw/20G81/096-57366-083.dmg'
BS = 4096

if len(sys.argv) < 2:
    print(__doc__)
    raise SystemExit(2)
DST = sys.argv[1]
extra_paths = sys.argv[2:]

if not os.path.exists(DST):
    raise SystemExit('目标镜像不存在: %s' % DST)
if not os.path.exists(SRC):
    raise SystemExit('源 IPSW dmg 不存在: %s' % SRC)

orig = apfs.Blocks.get
apfs.Blocks.get = lambda self, addr, verify=True: orig(self, addr, verify=False)

ci = apfs.Container(SRC)
vi = ci.volumes()[0]
cw = apfs.Container(DST)
vw = cw.volumes()[0]

print('dmg base (partition offset):', ci.image.base if hasattr(ci, 'image') else '?')
print('img size:', cw.image.size if hasattr(cw, 'image') else '?')
print('img base:', cw.image.base if hasattr(cw, 'image') else '?')


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
    return [path.rstrip('/') + '/' + n for n, fid, t in v.dir_entries(oid) if t in (8, 0)]


if extra_paths:
    paths = extra_paths
else:
    paths = (listdir(vw, '/usr/libexec') + listdir(vw, '/usr/sbin') +
             listdir(vw, '/usr/bin') + listdir(vw, '/bin'))

print('待检查路径数: %d' % len(paths))

f = open(DST, 'r+b')
repaired = clean = skipped = 0
for p in paths:
    s = rf(vi, p)
    d = rf(vw, p)
    if s is None or d is None:
        skipped += 1
        continue
    (s_ext, s_size), (d_ext, d_size) = s, d
    if s_size != d_size:
        print('  SIZE MISMATCH %s (src=%d dst=%d)' % (p, s_size, d_size))
        skipped += 1
        continue
    # 组装源流
    src = bytearray(s_size)
    for logical, length, phys in s_ext:
        if logical >= s_size:
            continue
        n = min(length, s_size - logical)
        nb = (length + BS - 1) // BS
        raw = ci.blocks.raw(phys, nb)
        src[logical:logical + n] = raw[:n]
    # 写入目标物理块。os-window.img 是 GPT 磁盘镜像，
    # APFS 块在 image.base + phys*block_size，不是 phys*block_size。
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
print('repaired=%d already-clean=%d skipped=%d of %d' % (repaired, clean, skipped, len(paths)))
