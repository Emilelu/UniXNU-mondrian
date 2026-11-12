#!/usr/bin/env python3
"""验证 boot.img 的 v4 布局与 kernel 区内容。

动机（P-149）：镜像起不来时，我先怀疑固件、kernel、boot-arg，全错。
真相是 `--dtb` 传了 480 KB 的 UEFI 全量 DTB 而不是 2.9 KB 的内核 DTB。
如果当时有一条测试说"kernel 区尾部 DTB 应该是几百字节"，一分钟就能定位。

这个测试固定四件事：
  1. v4 头部：header_size=1584，但 section 从 4096 开始
  2. 各 section 偏移 = 前一 section 长度按 4096 向上取整
  3. kernel 区 = gzip(shim+firmware) + 完整 DTB（fdt 长度字段自洽）
  4. 签名区 4096 字节且全零

用法：
  python3 scripts/test-bootimg-layout.py <boot.img> [<boot.img> ...]
  python3 scripts/test-bootimg-layout.py --selftest
退出码 0 通过，1 有问题。
"""
import argparse
import os
import gzip
import struct
import sys
import zlib

MAGIC = b'ANDROID!'
HEADER_SIZE_V4 = 1584
PAGE = 4096
FDT_MAGIC = b'\xd0\x0d\xfe\xed'

# kernel 区尾部 DTB 的合理上限。超过这个值几乎肯定是把 UEFI 的全量
# DTB 打进来了 —— 那正是 P-149。
MAX_KERNEL_DTB = 65536


def page(size):
    return (size + PAGE - 1) // PAGE * PAGE


def check(path, verbose=True):
    problems = []
    data = open(path, 'rb').read()
    name = os.path.basename(path)

    if len(data) < PAGE or data[:8] != MAGIC:
        return ['%s: 不是 Android boot 镜像' % name]

    ksize, rsize = struct.unpack_from('<2I', data, 8)
    hsize = struct.unpack_from('<I', data, 20)[0]
    hver = struct.unpack_from('<I', data, 40)[0]

    if hver != 4:
        problems.append('%s: header_version=%d，本测试只覆盖 v4' % (name, hver))
        return problems
    if hsize != HEADER_SIZE_V4:
        problems.append('%s: header_size=%d，v4 应为 %d' % (name, hsize, HEADER_SIZE_V4))

    sig_size = struct.unpack_from('<I', data, hsize - 4)[0]
    k_off = PAGE
    r_off = k_off + page(ksize)
    s_off = r_off + page(rsize)

    if sig_size != PAGE:
        problems.append('%s: signature_size=%d，应为 %d' % (name, sig_size, PAGE))
    if s_off + sig_size != len(data):
        problems.append('%s: 期望长度 %d，实际 %d（差 %+d）'
                        % (name, s_off + sig_size, len(data), len(data) - s_off - sig_size))
    if any(data[s_off:]):
        problems.append('%s: 签名区不是全零' % name)

    # kernel 区：gzip + 追加 DTB
    blob = data[k_off:k_off + ksize]
    dec = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        raw = dec.decompress(blob) + dec.flush()
    except zlib.error as exc:
        problems.append('%s: kernel 区 gzip 解压失败: %s' % (name, exc))
        return problems
    if not dec.eof:
        problems.append('%s: kernel 区 gzip 流不完整' % name)
    tail = dec.unused_data

    if len(tail) < 8 or tail[:4] != FDT_MAGIC:
        problems.append('%s: kernel 区尾部不是 DTB（%d 字节，魔数 %s）'
                        % (name, len(tail), tail[:4].hex()))
    else:
        fdt_len = struct.unpack_from('>I', tail, 4)[0]
        if fdt_len != len(tail):
            problems.append('%s: DTB 长度字段 %d != 实际尾部 %d' % (name, fdt_len, len(tail)))
        if len(tail) > MAX_KERNEL_DTB:
            problems.append(
                '%s: kernel 区尾部 DTB %d 字节，超过 %d 上限 —— 很可能打进了 UEFI '
                '全量 DTB（P-149），应该用 out-baseline/.../device-tree/hardware.dtb'
                % (name, len(tail), MAX_KERNEL_DTB))

    if verbose:
        print('  %-28s kernel=%d ramdisk=%d 解压=%d DTB=%d %s'
              % (name, ksize, rsize, len(raw), len(tail),
                 'OK' if not problems else '问题 %d' % len(problems)))
    return problems


def selftest():
    """构造两个合成镜像：一个正确，一个复现 P-149。"""
    import tempfile
    problems = []
    fw = bytes(range(256)) * 64
    good_dtb = struct.pack('>10I', 0xd00dfeed, 40, 40, 40, 40, 17, 16, 0, 0, 0)
    big_dtb = good_dtb + b'\x00' * (480 * 1024 - 40)

    def make(dtb, ramdisk=b'payload' * 100):
        kernel = gzip.compress(fw, mtime=0) + dtb
        header = bytearray(PAGE)
        header[:8] = MAGIC
        struct.pack_into('<2I', header, 8, len(kernel), len(ramdisk))
        struct.pack_into('<I', header, 20, HEADER_SIZE_V4)
        struct.pack_into('<I', header, 40, 4)
        struct.pack_into('<I', header, HEADER_SIZE_V4 - 4, PAGE)
        out = bytes(header) + kernel.ljust(page(len(kernel)), b'\x00')
        out += ramdisk.ljust(page(len(ramdisk)), b'\x00')
        out += b'\x00' * PAGE
        return out

    with tempfile.TemporaryDirectory() as d:
        p1 = os.path.join(d, 'good.img')
        open(p1, 'wb').write(make(good_dtb))
        r1 = check(p1, verbose=False)
        if r1:
            problems.append('自检：正确镜像被误报: %s' % r1)

        p2 = os.path.join(d, 'p149.img')
        open(p2, 'wb').write(make(big_dtb))
        r2 = check(p2, verbose=False)
        if not any('P-149' in x or '超过' in x for x in r2):
            problems.append('自检：P-149 形态没有被抓到（%s）' % r2)

    print('  自检: %s' % ('✅ 正确镜像通过、P-149 形态被抓到' if not problems
                          else '❌ %s' % problems))
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('images', nargs='*')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()

    if a.selftest:
        return 0 if not selftest() else 1
    if not a.images:
        ap.error('需要至少一个 boot.img，或 --selftest')

    allp = []
    for p in a.images:
        if not os.path.exists(p):
            allp.append('%s: 不存在' % p)
            continue
        allp.extend(check(p))

    if allp:
        print('  ❌ boot.img 布局问题：')
        for x in allp:
            print('     %s' % x)
        return 1
    print('  ✅ boot.img 布局全部正确（%d 个）' % len(a.images))
    return 0


if __name__ == '__main__':
    sys.exit(main())
