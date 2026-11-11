#!/usr/bin/env python3
"""触摸 ⑦ 核验 #1：BRL 报告解析离线单测

被测逻辑来自 patches/xnu/zzzz...-pong-touch-console.patch 的 goodix_poll()：
    if (!report[0]) return true;                       # 无事件
    if (report[0] & 0x80) {                            # GOODIX_STATUS_TOUCH
        count = report[2] & 0x0f;                      # 触点计数
        if (count > 2) 续读 8*(count-2)
        goodix_checksum_ok(report+8, 8*count+2)
    }

关键：**头部校验覆盖 report[0..7]，校验字节是 report[7]**（不是帧尾）。
"""
GOODIX_STATUS_TOUCH = 0x80
GOODIX_STATUS_REQUEST = 0x40
GOODIX_MAX_TOUCHES = 10


def checksum8(data):
    """Goodix 校验：字节和取反加一。整段（含校验字节）求和应为 0。"""
    return (-sum(data)) & 0xFF


def make_header(status, count):
    """构造 8 字节头部，report[7] 是校验字节。"""
    h = bytearray(8)
    h[0] = status
    h[1] = 0x00
    h[2] = count & 0x0F
    h[3] = 0x00
    h[4] = 0x00
    h[5] = 0x00
    h[6] = 0x00
    h[7] = checksum8(h[:7])
    return bytes(h)


def parse_report_header(report):
    """复刻 goodix_poll 的头部解析。返回 (ok, count, reset)。"""
    if not report:
        return True, 0, False
    if report[0] == 0:
        return True, 0, False

    # 头部校验：前 8 字节求和为 0
    if checksum8(report[:8]) != 0:
        return False, 0, False

    count = 0
    reset = False
    if report[0] & GOODIX_STATUS_TOUCH:
        count = report[2] & 0x0F
        if count > GOODIX_MAX_TOUCHES:
            return False, count, False
    if report[0] & GOODIX_STATUS_REQUEST:
        reset = (report[2] == 0x01)
    return True, count, reset


def run():
    cases = []
    fails = 0

    def check(name, got, want):
        nonlocal fails
        ok = (got == want)
        if not ok:
            fails += 1
        cases.append((name, got, want, ok))

    check('全零帧 -> 无事件', parse_report_header(bytes(8)), (True, 0, False))
    check('空帧 -> 无事件', parse_report_header(b''), (True, 0, False))

    for n in (1, 2, 5, 10):
        h = make_header(GOODIX_STATUS_TOUCH, n)
        check('%d 触点 -> count=%d' % (n, n), parse_report_header(h)[1], n)

    # 超上限
    h = make_header(GOODIX_STATUS_TOUCH, 15)
    check('超上限 15 -> 拒绝', parse_report_header(h)[0], False)

    # 头部校验错
    h = bytearray(make_header(GOODIX_STATUS_TOUCH, 1))
    h[1] ^= 0xFF
    check('头部校验错 -> 拒绝', parse_report_header(bytes(h))[0], False)

    # RESET
    h = make_header(GOODIX_STATUS_REQUEST, 1)
    check('RESET 请求 -> reset=True', parse_report_header(h)[2], True)

    # TOUCH | REQUEST
    h = make_header(GOODIX_STATUS_TOUCH | GOODIX_STATUS_REQUEST, 2)
    check('TOUCH|REQUEST -> count=2 reset=True',
          parse_report_header(h), (True, 2, True))

    # 真实日志里的字节（usblog-20261111-233246 FRAME-EVENT）
    # 80 19 00 e8 08 e8 08 01 —— byte2=0x00 表示 0 触点
    real = bytes([0x80, 0x19, 0x00, 0xe8, 0x08, 0xe8, 0x08, 0x01])
    s = sum(real) & 0xFF
    check('真实帧 80 19 00 ... -> count=0（byte2=0）',
          parse_report_header(real)[1], 0)
    print('  [真实帧校验和 = 0x%02x，%s]' % (s, '合法' if s == 0 else '非法（说明这帧本身校验不过）'))

    print()
    print('=== BRL 报告解析离线单测 ===')
    print()
    for name, got, want, ok in cases:
        print('  %s %-38s got=%r want=%r' % ('✅' if ok else '❌', name, got, want))
    print()
    print('  %d/%d 通过' % (len(cases) - fails, len(cases)))
    return 0 if fails == 0 else 1


if __name__ == '__main__':
    import sys
    sys.exit(run())
