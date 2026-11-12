#!/usr/bin/env python3
"""check-boot-procedure.py — 铁则 8：没有串口日志的 boot 是盲实验

为什么有这个门禁
----------------
2026-11-12 一次 boot 挂死在早启动，控制台一次都没出现，却没有留下任何日志：
当时靠人记得"先开 capture-k60-usblog.ps1 再 fastboot boot"，忘了就整轮只能盲猜
（那轮就是靠猜"是不是找不到 unixnu 分区"过去的）。

能被忘掉的流程不是流程。所以两件事一起做：
- `flash.sh` 无条件在 boot 前把 CDC-ACM 抓取挂上，并在结尾统一报"控制台出现没出现"；
- 本门禁反过来检查 `flash.sh` 还带着这段，防止有人"简化"掉它。

检查项
------
A  flash.sh 在 boot 之前启动 capture-k60-usblog.ps1
B  flash.sh 走的是 fastboot boot（经 boot-and-capture.ps1），不含 fastboot flash
C  docs/engineering/BOOT-PROCEDURE.md 存在且写明抓取脚本与证据目录
D  AGENTS.md 有对应铁则
E  文档被 docs/INDEX.md 收录

退出码 0 = 通过。
"""
import io
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLASH = '/mnt/e/k60-work/scripts/flash.sh'
CAPTURE = 'capture-k60-usblog.ps1'
BOOTER = 'boot-and-capture.ps1'
DOC = os.path.join(REPO, 'docs', 'engineering', 'BOOT-PROCEDURE.md')
AGENTS = os.path.join(REPO, 'AGENTS.md')
INDEX = os.path.join(REPO, 'docs', 'INDEX.md')

problems = []
notes = []


def read(path):
    if not os.path.exists(path):
        return None
    return io.open(path, encoding='utf-8', errors='ignore').read()


# A/B: the wrapper must attach the console itself and must only ever boot
src = read(FLASH)
if src is None:
    problems.append('A 找不到 %s（boot 入口不存在，铁则 8 无从保证）' % FLASH)
else:
    lines = src.split('\n')
    cap_at = next((i for i, l in enumerate(lines) if CAPTURE in l and not l.strip().startswith('#')), None)
    boot_at = next((i for i, l in enumerate(lines) if BOOTER in l and not l.strip().startswith('#')), None)
    if cap_at is None:
        problems.append('A flash.sh 没有启动 %s —— boot 会变成盲实验' % CAPTURE)
    else:
        notes.append('A flash.sh 第 %d 行启动串口抓取' % (cap_at + 1))
    if boot_at is None:
        problems.append('B flash.sh 没有调用 %s' % BOOTER)
    elif cap_at is not None and cap_at > boot_at:
        problems.append('B 串口抓取在第 %d 行，晚于 boot 的第 %d 行 —— 早启动的行会丢' % (cap_at + 1, boot_at + 1))
    else:
        notes.append('B 抓取先于 boot（%d < %d）' % (cap_at + 1, boot_at + 1))
    if re.search(r'^\s*[^#\n]*fastboot\s+flash', src, re.M):
        problems.append('B flash.sh 里出现 fastboot flash —— 本仓库只允许 fastboot boot')
    else:
        notes.append('B 没有 fastboot flash')

# C: the procedure itself must be written down
doc = read(DOC)
if doc is None:
    problems.append('C 缺 %s（流程没写下来就等于没有）' % os.path.relpath(DOC, REPO))
else:
    for needle, why in ((CAPTURE, '抓取脚本名'),
                        ('fastboot boot', '唯一允许的启动命令'),
                        ('evidence', '证据目录')):
        if needle not in doc:
            problems.append('C BOOT-PROCEDURE.md 没提 %s（%s）' % (needle, why))
    if 'unixnu' not in doc:
        problems.append('C BOOT-PROCEDURE.md 没说明 unixnu 分区不可整体覆写')
    notes.append('C BOOT-PROCEDURE.md 存在')

# D: and it must be an iron rule, not a docs page nobody reads
agents = read(AGENTS) or ''
if not re.search(r'^8\.\s+\*\*.*(serial|console|串口)', agents, re.M):
    problems.append('D AGENTS.md 没有第 8 条铁则（串口日志）')
else:
    notes.append('D AGENTS.md 第 8 条铁则存在')

# E: reachable from the docs index
index = read(INDEX) or ''
if 'BOOT-PROCEDURE' not in index:
    problems.append('E docs/INDEX.md 没有收录 BOOT-PROCEDURE.md')
else:
    notes.append('E INDEX 已收录')

print('检查项: 铁则 8（boot 必须带串口日志）')
for n in notes:
    print('  ✅ ' + n)
if problems:
    for p in problems:
        print('  ❌ ' + p)
    print('\n结论: ❌ 未通过')
    sys.exit(1)
print('\n结论: ✅ 通过')
