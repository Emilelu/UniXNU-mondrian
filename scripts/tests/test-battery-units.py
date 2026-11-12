#!/usr/bin/env python3
"""电池单位转换的离线单测（八步 ⑦ 的可离线部分）。

依据：官方 power 页第 4 节明确写出的参考实现转换
  - 电压 / 电流：微单位 -> 毫单位
  - 容量：0.01% -> 百分比
  - 时间：秒 -> 分钟
并强调「使用前确认目标协议的充电电流符号」。

本测试固定这些转换的边界行为，防止将来改单位时静默出错。
"""
import sys


# ---- 被测逻辑（照官方描述实现，供单测固定）----

def uv_to_mv(uv):
    """微伏 -> 毫伏。四舍五入到最近整数毫伏。"""
    return (uv + 500) // 1000 if uv >= 0 else -((-uv + 500) // 1000)


def ua_to_ma(ua):
    """微安 -> 毫安。"""
    return (ua + 500) // 1000 if ua >= 0 else -((-ua + 500) // 1000)


def capacity_centipercent_to_percent(cp):
    """0.01% -> 百分比。四舍五入。"""
    return (cp + 50) // 100 if cp >= 0 else -((-cp + 50) // 100)


def seconds_to_minutes(s):
    """秒 -> 分钟。向上取整（剩余时间宁可多报不可少报）。"""
    if s <= 0:
        return 0
    return (s + 59) // 60


def signed_current(raw, sign):
    """把无符号原始值套上协议规定的充电电流符号。

    sign = +1 表示正值是充电，-1 表示正值是放电。
    """
    return raw * sign


def run():
    cases = []
    fails = 0

    def check(name, got, want):
        nonlocal fails
        ok = got == want
        if not ok:
            fails += 1
        cases.append((name, got, want, ok))

    # 电压
    check('uv_to_mv(4200000) = 4200', uv_to_mv(4200000), 4200)
    check('uv_to_mv(3700500) = 3701', uv_to_mv(3700500), 3701)
    check('uv_to_mv(3700499) = 3700', uv_to_mv(3700499), 3700)
    check('uv_to_mv(0) = 0', uv_to_mv(0), 0)

    # 电流
    check('ua_to_ma(1500000) = 1500', ua_to_ma(1500000), 1500)
    check('ua_to_ma(500) = 1', ua_to_ma(500), 1)
    check('ua_to_ma(499) = 0', ua_to_ma(499), 0)
    check('ua_to_ma(-1500000) = -1500', ua_to_ma(-1500000), -1500)

    # 容量
    check('capacity(10000) = 100', capacity_centipercent_to_percent(10000), 100)
    check('capacity(5000) = 50', capacity_centipercent_to_percent(5000), 50)
    check('capacity(9950) = 100', capacity_centipercent_to_percent(9950), 100)
    check('capacity(49) = 0', capacity_centipercent_to_percent(49), 0)
    check('capacity(0) = 0', capacity_centipercent_to_percent(0), 0)

    # 时间
    check('seconds_to_minutes(0) = 0', seconds_to_minutes(0), 0)
    check('seconds_to_minutes(1) = 1', seconds_to_minutes(1), 1)
    check('seconds_to_minutes(60) = 1', seconds_to_minutes(60), 1)
    check('seconds_to_minutes(61) = 2', seconds_to_minutes(61), 2)
    check('seconds_to_minutes(-5) = 0', seconds_to_minutes(-5), 0)

    # 电流符号（官方强调必须先确认）
    check('sign=+1 充电 1500 -> +1500', signed_current(1500, +1), 1500)
    check('sign=-1 充电 1500 -> -1500', signed_current(1500, -1), -1500)
    check('sign=+1 放电 800 -> +800', signed_current(800, +1), 800)
    check('sign=-1 放电 800 -> -800', signed_current(800, -1), -800)

    # 关键不变量：符号翻转后绝对值不变
    for raw in (0, 1, 500, 1500, 3000):
        a, b = signed_current(raw, +1), signed_current(raw, -1)
        check('|sign(+1)| == |sign(-1)| for %d' % raw, abs(a), abs(b))

    print('=== 电池单位转换离线单测 ===')
    print()
    for name, got, want, ok in cases:
        print('  %s %-44s got=%r want=%r' % ('✅' if ok else '❌', name, got, want))
    print()
    print('  %d/%d 通过' % (len(cases) - fails, len(cases)))
    return 0 if fails == 0 else 1


if __name__ == '__main__':
    sys.exit(run())
