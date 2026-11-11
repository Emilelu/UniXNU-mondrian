#!/usr/bin/env python3
"""验证 config 切片假设：应该发 1609 字节，不是 1486 字节。

容器结构（goodix_cfg_group_m11a.bin, 1627 B）：
  0   u32 total_len  = 1627
  4   u32 checksum   = 14044
  8   u32 version    = 256
  12  u32 reserved   = 0
  16  u16 sub_offset = 18      ← 子包起始偏移
  18  u32 sub_len    = 1609    ← 1627 - 18，子包长度
  22  "Berlin" (16 B chip name)
  38  sensor id 0xff
  39  "9916R" (fw_pid)
  141 ← 我们之前切片的起点（错）

假设：brl_send_config 应收到 容器[18:1627] = 1609 字节。
"""
import struct

C = '/mnt/e/k60-work/scratch/goodix-fw/goodix_cfg_group_m11a.bin'
OURS = '/mnt/e/k60-work/scratch/goodix-fw/cfg_pkg0_sensor255_type1.bin'

d = open(C, 'rb').read()
ours = open(OURS, 'rb').read()

print('=== 容器 ===')
print('  %d B' % len(d))
print()

sub_offset = struct.unpack('<H', d[16:18])[0]
sub_len = struct.unpack('<I', d[18:22])[0]
print('=== 子包定位 ===')
print('  sub_offset (u16@16) = %d' % sub_offset)
print('  sub_len    (u32@18) = %d' % sub_len)
print('  total_len - sub_offset = %d' % (len(d) - sub_offset))
print('  与 sub_len 一致: %s' % ('✅' if sub_len == len(d) - sub_offset else '❌'))
print()

print('=== 三种切片对比 ===')
candidates = [
    ('我们现在的（错？）', ours, 141),
    ('从 18 开始（假设正确）', d[18:], 18),
    ('从 22 开始（Berlin 处）', d[22:], 22),
]
for name, data, off in candidates:
    print('  %-24s 偏移 %-4d 长度 %-5d 前 8: %s' % (
        name, off, len(data), ' '.join('%02x' % b for b in data[:8])))
print()

print('=== 检查 fw_buffer_max_len 限制 ===')
print('  官方 brl_send_config: if (len > misc->fw_buffer_max_len) return -EINVAL;')
print('  日志里 fw_buffer_max_len = 4200（CFG-DL 那行）')
for name, data, off in candidates:
    print('  %-24s %d B  %s' % (name, len(data),
          '✅ 未超' if len(data) <= 4200 else '❌ 超限'))
print()

print('=== 关键差异 ===')
print('  1486 vs 1609 = %d 字节' % (1609 - 1486))
print('  差的正好是偏移 18..141 这一段：')
print('    %s' % ' '.join('%02x' % b for b in d[18:141]))
print()
print('  这段包含：')
print('    - sub_len (4 B)')
print('    - chip name "Berlin" + padding (16 B)')
print('    - sensor id 0xff (1 B)')
print('    - fw_pid "9916R" + padding (16 B)')
print('    - 若干配置字段')
print()

print('=== 结论 ===')
print('  如果官方把「整个子包」写给芯片，那我们少发了 123 字节的头部，')
print('  芯片解析 config 时会从错误的偏移读字段 —— 这完全可能解释')
print('  "config 下载 ack 通过但不上报触点"。')
print()
print('  但也要注意：如果芯片期望的就是「裸配置区」（不含 chip name 等元数据），')
print('  那 1486 是对的。两种可能都需要设备验证。')
print()
print('  决定性判据：从 Android 提取 goodix_cfg_group.cfg（ASCII），')
print('  跑 convert_0x_data 后的长度是 1486 还是 1609。')
