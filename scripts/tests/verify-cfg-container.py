#!/usr/bin/env python3
"""验证 goodix_cfg_group_m11a.bin 的容器结构。

官方 goodix_cfg_bin.c:149 goodix_parse_cfg_bin：
  struct goodix_cfg_bin_head {
      u32 bin_len;                          // +0
      u8  checksum;                         // +4
      u8  bin_version[TS_BIN_VERSION_LEN];  // +5
      u8  pkg_num;                          // +5+VER
  };
  校验：checksum == sum(bin_data[TS_BIN_VERSION_START_INDEX .. bin_len-1]) & 0xFF
"""
import struct

P = '/mnt/e/k60-work/scratch/goodix-fw/goodix_cfg_group_m11a.bin'
d = open(P, 'rb').read()

print('=== 文件 ===')
print('  大小: %d B' % len(d))
print()

bin_len = struct.unpack('<I', d[0:4])[0]
checksum = d[4]
print('=== 容器头 ===')
print('  bin_len  = %d  %s' % (bin_len, '✅ 与文件等长' if bin_len == len(d) else '❌'))
print('  checksum = 0x%02x' % checksum)
print('  d[5..15] = %s' % ' '.join('%02x' % b for b in d[5:16]))
print()

# 找哪个 TS_BIN_VERSION_START_INDEX 能让校验和成立
print('=== 穷举 TS_BIN_VERSION_START_INDEX（使 checksum 成立）===')
found = []
for start in range(5, 20):
    s = sum(d[start:]) & 0xFF
    if s == checksum:
        found.append(start)
        print('  start=%d -> sum=0x%02x == checksum ✅' % (start, s))
if not found:
    print('  ❌ 没有任何 start 能让校验和成立')
    print('  各 start 的 sum:')
    for start in range(5, 20):
        print('    start=%-3d sum=0x%02x' % (start, sum(d[start:]) & 0xFF))
print()

# 用找到的 start 反推头部布局
if found:
    start = found[0]
    print('=== 头部布局推断（TS_BIN_VERSION_START_INDEX=%d）===' % start)
    print('  bin_len:        d[0..3]  = %d' % bin_len)
    print('  checksum:       d[4]     = 0x%02x' % checksum)
    ver_len = start - 5
    print('  bin_version[%d]: d[5..%d] = %s' % (ver_len, start - 1,
          ' '.join('%02x' % b for b in d[5:start])))
    print('  pkg_num:        d[%d]    = %d' % (start, d[start]))
    print()

    pkg_num = d[start]
    head_len = start + 1
    print('=== 子包偏移表（头 %d 字节之后，每项 4 字节）===' % head_len)
    for i in range(min(pkg_num, 8)):
        off = head_len + i * 4
        if off + 4 > len(d):
            break
        o1, o2 = struct.unpack('<HH', d[off:off+4])
        print('  pkg[%d]: offset1=%d offset2=%d' % (i, o1, o2))
    print()

    print('=== 子包内容探测 ===')
    for i in range(min(pkg_num, 4)):
        off = head_len + i * 4
        o1 = struct.unpack('<H', d[off:off+2])[0]
        if i + 1 < pkg_num:
            o2 = struct.unpack('<H', d[off+2:off+4])[0]
        else:
            o2 = len(d)
        if o1 < len(d):
            print('  pkg[%d] @%d..%d (%d B): %s' % (
                i, o1, o2, o2 - o1, ' '.join('%02x' % b for b in d[o1:min(o1+16, o2)])))
