#!/usr/bin/env python3
"""用官方 checksum_cmp 算法验证真实帧。

官方 goodix_ts_utils.c:67-87:
    U8_LE:  cal = sum(data[0..size-3]);  r = data[size-2] | (data[size-1]<<8)
    U16_LE: cal = sum(u16 at data[0..size-5]); r = u16 at data[size-4..size-1]
    返回 0 表示通过。
"""
frame = bytes([0x80, 0x19, 0x00, 0xe8, 0x08, 0xe8, 0x08, 0x01,
               0x07, 0x00, 0x00, 0x19, 0x00, 0x00, 0x9a, 0x02,
               0xca, 0x01, 0x00, 0x03, 0xf0, 0x00, 0x02, 0x00,
               0x00, 0x00, 0x00, 0x38, 0x01, 0x00, 0x00, 0x00])


def checksum_u8_le(data, size):
    """官方 CHECKSUM_MODE_U8_LE。"""
    if size < 2:
        return False
    cal = sum(data[:size - 2]) & 0xFFFF
    r = data[size - 2] | (data[size - 1] << 8)
    return cal == r, cal, r


def checksum_u16_le(data, size):
    """官方 CHECKSUM_MODE_U16_LE。"""
    if size < 4:
        return False, 0, 0
    cal = 0
    for i in range(0, size - 4, 2):
        cal += data[i] | (data[i + 1] << 8)
    cal &= 0xFFFF
    r = (data[size - 4] | (data[size - 3] << 8)) + ((data[size - 2] | (data[size - 1] << 8)) << 16)
    return cal == (r & 0xFFFF), cal, r & 0xFFFF


print('=== 真实帧结构 ===')
print('  frame_head (16 字节): %s' % ' '.join('%02x' % b for b in frame[:16]))
print('    sync            = 0x%02x' % frame[0])
print('    frame_index     = 0x%04x' % (frame[1] | (frame[2] << 8)))
print('    cur_frame_len   = 0x%04x = %d' % (frame[3] | (frame[4] << 8), frame[3] | (frame[4] << 8)))
print('    next_frame_len  = 0x%04x = %d' % (frame[5] | (frame[6] << 8), frame[5] | (frame[6] << 8)))
print('    data_en         = 0x%08x' % (frame[7] | (frame[8] << 8) | (frame[9] << 16) | (frame[10] << 24)))
print('    touch_pack_index= 0x%02x' % frame[11])
print('    stylus_pack_idx = 0x%02x' % frame[12])
print('    res             = 0x%02x' % frame[13])
print('    checksum        = 0x%04x' % (frame[14] | (frame[15] << 8)))
print()

print('=== 头部校验（U8_LE, size=16）===')
ok, cal, r = checksum_u8_le(frame, 16)
print('  cal = 0x%04x   r = 0x%04x   %s' % (cal, r, '✅ 通过' if ok else '❌ 不通过'))
print()

print('=== 帧体校验（U16_LE, size=cur_frame_len=%d）===' % (frame[3] | (frame[4] << 8)))
cur = frame[3] | (frame[4] << 8)
if cur <= len(frame):
    ok2, cal2, r2 = checksum_u16_le(frame, cur)
    print('  cal = 0x%04x   r = 0x%04x   %s' % (cal2, r2, '✅ 通过' if ok2 else '❌ 不通过'))
else:
    print('  cur_frame_len=%d 超出实际读到的 %d 字节' % (cur, len(frame)))
print()

print('=== 与我们的实现对比 ===')
print('  我们按 8 字节做"和为零"校验 -> 0x7a != 0 -> 判定无效')
print('  官方按 16 字节做"和==末尾u16"校验 -> %s' % ('通过' if ok else '不通过'))
print()
if ok:
    print('  → 这是一帧**合法的 frame_head**！')
    print('  → sync=0x%02x 含 0x80 位，表示有数据' % frame[0])
    print('  → data_en=0x%08x' % (frame[7] | (frame[8] << 8) | (frame[9] << 16) | (frame[10] << 24)))
    print('  → 但这是 **framedata（rawdata）**，不是触点报告！')
    print()
    print('  官方 brld_get_framedata 是给 rawdata 用的。')
    print('  触点报告走的是另一条路径：goodix_brl_hw.c 的 brl_read_touch_data / event_handler。')
