#!/usr/bin/env python3
"""check-boot-procedure.py — 铁则 8：没有串口日志的 boot 是盲实验

为什么有这个门禁
----------------
2026-11-12 一次 boot 挂死在早启动，控制台一次都没出现，却没有留下任何日志：
当时靠人记得"先开 capture-k60-usblog.ps1 再 fastboot boot"，忘了就整轮只能盲猜
（那轮就是靠猜"是不是找不到 unixnu 分区"过去的）。

当天晚些时候又发现第二个缺陷：`flash.sh` 自己起了一个抓取进程，`boot-and-capture.ps1`
里面又起了一个，两个进程抢同一个 COM 口，各写一个时间戳目录。主判据检查的是第一个
目录里的 0 字节文件，于是把"其实正在正常启动、Data 已经挂上"的一轮误判成
"内核早死"。**单写者**和**单一证据目录**因此变成门禁的一部分。

检查项
------
A  flash.sh 只经由 boot-and-capture.ps1 启动，不再自己起抓取进程（单写者）
B  boot-and-capture.ps1 在 `fastboot boot` 之前启动 capture-k60-usblog.ps1，
   并把 -OutDir / -ReadyFile 传下去（同一证据目录 + 就绪握手）
B2 机器级 boot claim（2026-11-18 改为先到先得）：supervisor 必须在启动前取得
   单写者 claim、在 finally 里释放，flash.sh 必须在 adb reboot 之前拒绝竞争
C  capture-k60-usblog.ps1 持有命名互斥体，并把"端口没出现 / 打开失败 / 零字节 /
   截断"分开记进 capture.json（判据不再是"文件存在吗"）
D  没有脚本出现 `fastboot flash`
E  docs/engineering/BOOT-PROCEDURE.md 存在、写明单一抓取进程、证据目录与 unixnu 不可覆写
F  AGENTS.md 有第 8 条铁则
G  docs/INDEX.md 收录 BOOT-PROCEDURE.md

退出码 0 = 通过。
"""
import io
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WRAPPER = os.path.join(REPO, 'scripts', 'flash.sh')
SUPERVISOR = os.path.join(REPO, 'scripts', 'boot-and-capture.ps1')
COLLECTOR = os.path.join(REPO, 'scripts', 'capture-k60-usblog.ps1')
CLASSIFIER = os.path.join(REPO, 'scripts', 'k60-capture-state.ps1')
DOC = os.path.join(REPO, 'docs', 'engineering', 'BOOT-PROCEDURE.md')
AGENTS = os.path.join(REPO, 'AGENTS.md')
INDEX = os.path.join(REPO, 'docs', 'INDEX.md')

CAPTURE = 'capture-k60-usblog.ps1'
BOOTER = 'boot-and-capture.ps1'

problems = []
notes = []


def read(path):
    if not os.path.exists(path):
        return None
    return io.open(path, encoding='utf-8', errors='ignore').read()


def live_lines(src):
    """Lines that are not comments, so a doc comment cannot satisfy a check.

    PowerShell block comments (<# … #>) matter here: boot-and-capture.ps1 says
    "This supervisor NEVER opens SerialPort" inside one, and a naive substring
    test reads that sentence as a violation.
    """
    in_block = False
    for i, line in enumerate(src.split('\n')):
        s = line.strip()
        if in_block:
            if '#>' in s:
                in_block = False
            continue
        if s.startswith('<#'):
            if '#>' not in s:
                in_block = True
            continue
        if not s or s.startswith('#'):
            continue
        yield i, line


def live_text(src):
    return '\n'.join(line for _, line in live_lines(src))


def first_line(src, needle):
    for i, line in live_lines(src):
        if needle in line:
            return i
    return None


# A: the wrapper delegates. Two readers on one COM port is the defect this gate exists for.
wrapper = read(WRAPPER)
if wrapper is None:
    problems.append('A 找不到 %s（boot 入口不存在，铁则 8 无从保证）' % os.path.relpath(WRAPPER, REPO))
else:
    boot_at = first_line(wrapper, BOOTER)
    cap_at = first_line(wrapper, CAPTURE)
    if boot_at is None:
        problems.append('A flash.sh 没有调用 %s —— boot 会变成盲实验' % BOOTER)
    else:
        notes.append('A flash.sh 第 %d 行调用 supervisor' % (boot_at + 1))
    if cap_at is not None:
        problems.append('A flash.sh 第 %d 行自己起 %s —— 会和 supervisor 抢 COM 口（单写者）' % (cap_at + 1, CAPTURE))
    if 'fastboot ' in wrapper and re.search(r'^\s*[^#\n]*fastboot\s+flash', wrapper, re.M):
        problems.append('A flash.sh 里出现 fastboot flash —— 本仓库只允许 fastboot boot')

# B: the supervisor arms the collector before it boots, into the same directory.
sup = read(SUPERVISOR)
if sup is None:
    problems.append('B 找不到 %s' % os.path.relpath(SUPERVISOR, REPO))
else:
    cap_at = first_line(sup, CAPTURE)
    boot_at = first_line(sup, "'boot'")
    if cap_at is None:
        problems.append('B supervisor 没有启动 %s' % CAPTURE)
    if boot_at is None:
        problems.append('B supervisor 没有发出 fastboot boot（找不到 "-s $Serial boot"）')
    if cap_at is not None and boot_at is not None and cap_at > boot_at:
        problems.append('B 抓取在第 %d 行，晚于 boot 的第 %d 行 —— 早启动的行会丢' % (cap_at + 1, boot_at + 1))
    if cap_at is not None and boot_at is not None and cap_at < boot_at:
        notes.append('B 抓取先于 boot（%d < %d）' % (cap_at + 1, boot_at + 1))
    for needle, why in (('-ReadyFile', '就绪握手'), ('-OutDir', '同一证据目录')):
        if needle not in sup:
            problems.append('B supervisor 没有把 %s 传给抓取（%s）' % (needle, why))
    if 'SerialPort' in live_text(sup):
        problems.append('B supervisor 自己打开了 SerialPort —— 只能由 collector 打开（单写者）')
    if 'Booting\\s+OKAY' not in sup and 'Booting' not in sup:
        problems.append('B supervisor 没有核对 fastboot 的 "Booting OKAY"')

# B2: one machine-wide claim. 2026-11-18 the user changed the policy from
# "only Lead boots" to "first claimant wins", so the requirement is no longer
# exclusivity by actor but a single writer with attributed ownership: the
# supervisor must take the claim before touching the device, release it in
# `finally`, and the wrapper must refuse a competitor *before* it reboots the
# phone into fastboot (a reboot outside the claim breaks another actor's capture).
LOCK = os.path.join(REPO, 'scripts', 'k60-boot-lock.ps1')
lock_src = read(LOCK)
if lock_src is None:
    problems.append('B2 缺 %s（机器级 boot claim 没有实现）' % os.path.relpath(LOCK, REPO))
else:
    for needle, why in (('FileShare]::None', '独占句柄才是锁'), ('K60_BOOT_BUSY:', '竞争者要被明确告知'),
                        ('Exit-K60BootLock', '释放函数')):
        if needle not in lock_src:
            problems.append('B2 k60-boot-lock.ps1 没有 %s（%s）' % (needle, why))
    notes.append('B2 k60-boot-lock.ps1 用独占句柄实现机器级 claim')
if sup is not None:
    acquire = first_line(sup, 'Enter-K60BootLock')
    release = first_line(sup, 'Exit-K60BootLock')
    reset = first_line(sup, "'boot'")
    if acquire is None:
        problems.append('B2 supervisor 没有取得机器级 boot claim —— 多 agent 会重叠 boot')
    if release is None:
        problems.append('B2 supervisor 没有释放 boot claim —— 一次崩溃会让设备永久不可用')
    if acquire is not None and reset is not None and acquire > reset:
        problems.append('B2 boot claim 在 fastboot boot 之后才取（第 %d 行 > 第 %d 行）' % (acquire + 1, reset + 1))
    if acquire is not None and release is not None and release < acquire:
        problems.append('B2 释放（第 %d 行）早于获取（第 %d 行）' % (release + 1, acquire + 1))
    if acquire is not None and release is not None and acquire < release:
        notes.append('B2 supervisor 先取 claim（第 %d 行）、后在 finally 释放（第 %d 行）' % (acquire + 1, release + 1))
    reboot = first_line(sup, "'reboot','bootloader'")
    if reboot is None:
        problems.append('B2 supervisor 没有实现 claim 内的 adb reboot bootloader —— flash.sh 已经不自己重启了')
    elif acquire is not None and acquire > reboot:
        problems.append('B2 supervisor 在取 claim 之前就重启设备（第 %d 行 > 第 %d 行）' % (acquire + 1, reboot + 1))
    else:
        notes.append('B2 supervisor 在 claim 之内重启到 fastboot（第 %d 行）' % (reboot + 1))
if wrapper is not None:
    # A `flock` probe in the wrapper was the first attempt and it was WRONG: POSIX
    # advisory locks and the supervisor's FileShare::None handle are different
    # lock domains, so `flock -n` always looked free while another agent held the
    # claim — a false pass on the one property that matters. The wrapper must not
    # probe or reboot at all; the supervisor reboots inside the claim.
    if 'reboot bootloader' in live_text(wrapper):
        problems.append('B2 flash.sh 自己 adb reboot bootloader —— 重启必须在 claim 之内由 supervisor 做')
    else:
        notes.append('B2 flash.sh 不自己重启设备，重启由 supervisor 在 claim 内完成')
    if 'flock' in live_text(wrapper):
        problems.append('B2 flash.sh 用 flock 探测 claim —— 与 FileShare::None 不同锁域，永远看到「空闲」')
    if '-RebootToFastboot' not in live_text(wrapper):
        problems.append('B2 flash.sh 没有把重启职责交给 supervisor（缺 -RebootToFastboot）')
    if 'K60_AGENT_ID' not in wrapper:
        problems.append('B2 flash.sh 没有要求 K60_AGENT_ID —— claim 无法署名')
    if '-Actor' not in live_text(wrapper):
        problems.append('B2 flash.sh 没有把 -Actor 传给 supervisor')

# C: the collector must classify, not just create a file, and must hold the lock.
col = read(COLLECTOR)
if col is None:
    problems.append('C 找不到 %s' % os.path.relpath(COLLECTOR, REPO))
else:
    for needle, why in (('Mutex', '命名互斥体'), ('capture.json', '结构化判据'),
                        ('$ReadyFile', '就绪握手（supervisor 等它出现才 boot）')):
        if needle not in col:
            problems.append('C collector 没有 %s（%s）' % (needle, why))
    if 'DtrEnable' not in col:
        problems.append('C collector 没有设置 DtrEnable —— 内核不会排空 console ring')
cls = read(CLASSIFIER)
if cls is None:
    problems.append('C 缺少可离线测试的分类器 %s' % os.path.relpath(CLASSIFIER, REPO))
else:
    for needle, why in (('port-not-observed', '端口没出现'), ('port-open-failed', '打开失败'),
                        ('opened-no-data', '打开但零字节'), ('captured-truncated', '截断')):
        if needle not in cls:
            problems.append('C 分类器没有 %s 状态（%s）' % (needle, why))

# D: nothing may flash a partition.
for path in (WRAPPER, SUPERVISOR, COLLECTOR):
    src = read(path) or ''
    if re.search(r'^\s*[^#\n]*fastboot\s+flash', src, re.M):
        problems.append('D %s 里出现 fastboot flash' % os.path.relpath(path, REPO))
if not any(p.startswith('D ') for p in problems):
    notes.append('D 三个脚本都没有 fastboot flash')

# E: the procedure must be written down.
doc = read(DOC)
if doc is None:
    problems.append('E 缺 %s（流程没写下来就等于没有）' % os.path.relpath(DOC, REPO))
else:
    for needle, why in ((CAPTURE, '抓取脚本名'), (BOOTER, 'supervisor'),
                        ('fastboot boot', '唯一允许的启动命令'),
                        ('capture.json', '判据文件'), ('evidence', '证据目录')):
        if needle not in doc:
            problems.append('E BOOT-PROCEDURE.md 没提 %s（%s）' % (needle, why))
    if 'unixnu' not in doc:
        problems.append('E BOOT-PROCEDURE.md 没说明 unixnu 分区不可整体覆写')
    notes.append('E BOOT-PROCEDURE.md 存在')

# F: and it must be an iron rule, not a docs page nobody reads.
agents = read(AGENTS) or ''
if not re.search(r'^8\.\s+\*\*.*(serial|console|串口)', agents, re.M):
    problems.append('F AGENTS.md 没有第 8 条铁则（串口日志）')
else:
    notes.append('F AGENTS.md 第 8 条铁则存在')

# G: reachable from the docs index.
index = read(INDEX) or ''
if 'BOOT-PROCEDURE' not in index:
    problems.append('G docs/INDEX.md 没有收录 BOOT-PROCEDURE.md')
else:
    notes.append('G INDEX 已收录')

print('检查项: 铁则 8（boot 必须带串口日志；单一写者、单一证据目录）')
for n in notes:
    print('  ✅ ' + n)
if problems:
    for p in problems:
        print('  ❌ ' + p)
    print('\n结论: ❌ 未通过')
    sys.exit(1)
print('\n结论: ✅ 通过')
