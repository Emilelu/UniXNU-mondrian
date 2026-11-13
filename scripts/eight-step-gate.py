#!/usr/bin/env python3
"""eight-step-gate.py — 八步流程硬门禁

用户要求（2026-11-12）：
  "每个硬件修复都必须按八步流程走，每步操作都要有可靠依据，
   一旦没有100%能成功的依据就禁止继续推进，直到有为止。实现这个门禁"

八步（EIGHT-STEP-EVIDENCE.md 定义）：
  ① 同型   —— 同型号机型的实现（本机最优先）
  ② 官方   —— 官方文档/官方驱动
  ③ 反编译 —— 反编译/取证（DT、固件、反汇编、实机寄存器）
  ④ 广域   —— 广域交叉验证（同 SoC、同外设芯片、多来源）
  ⑤ 方案   —— 明确的实现方案
  ⑥ 深挖   —— 深挖未解点（源码/汇编级）
  ⑦ 核验   —— 本地可验证的核验（不刷机就能证明）
  ⑧ 上机   —— 真机验证

门禁语义：
  - build：①②③④⑤⑥ 必须有依据（研究+方案完整）
  - flash：①~⑦ 全部 + ⑧ 的「预测」必须声明（成功看哪行、失败看哪行）
            否则拒绝刷机

「100% 能成功的依据」的机器表达：
  - 每条依据必须有 reference（文件:行号 / URL / 日志名:行号），不能只写结论
  - ⑦ 核验必须有 local_verified = true 且给出本地验证方法
  - ⑧ 必须有 prediction.success / prediction.failure 两行
"""
import io
import os
import re
import sys

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, 'docs', 'research', 'EIGHT-STEPS.toml')

STEPS = ['same_model', 'official', 'decompile', 'wide', 'plan', 'deep', 'verify', 'device']
LABEL = {
    'same_model': '① 同型',
    'official': '② 官方',
    'decompile': '③ 反编译',
    'wide': '④ 广域',
    'plan': '⑤ 方案',
    'deep': '⑥ 深挖',
    'verify': '⑦ 核验',
    'device': '⑧ 上机',
}
# build 需要前 6 步；flash 需要前 7 步 + 第 8 步的预测
BUILD_STEPS = STEPS[:6]
FLASH_STEPS = STEPS[:7]


def has_reference(text):
    """依据里必须有一个可核查的引用锚点"""
    if not text:
        return False
    pats = [
        r'[\w./-]+\.(c|h|mm|cpp|py|sh|md|toml|dts|dtsi|log|txt):\d+',  # file:line（最强）
        r'[\w./-]+\.(c|h|mm|cpp|py|sh|md|toml|dts|dtsi|log|txt)\b',     # 文件路径
        r'https?://',                                                   # URL
        r'unixnu\.com/[\w/.-]+',                                       # 站内链接
        r'usblog-\d{8}-\d{6}(:\d+)?',                                   # 日志名[:行]
        r'0x[0-9a-fA-F]{2,}',                                           # 寄存器/地址
        r'[A-Z]-\d{2,3}',                                               # 坑编号
        r'★\d+',                                                        # 铁则编号
        r'sha256\s*[0-9a-f]{8,}',                                       # 构建哈希
    ]
    return any(re.search(p, text) for p in pats)


def validate(mode='build', verbose=True):
    """mode: 'build' | 'flash'"""
    if tomllib is None:
        return False, ['缺 tomllib/tomli']
    if not os.path.exists(DATA):
        return False, ['docs/research/EIGHT-STEPS.toml 不存在']

    d = tomllib.load(open(DATA, 'rb'))
    problems = []
    need = BUILD_STEPS if mode == 'build' else FLASH_STEPS
    checked = 0

    hw_all = d.get('hardware', {})
    # 只有 status=active 的硬件做硬检查。parked/planned 如实记录但不阻断构建：
    # 八步流程约束的是「正在做的修复」，不是历史清单。
    hw = {k: v for k, v in hw_all.items() if v.get('status', 'active') == 'active'}
    _parked = {k: v.get('status') for k, v in hw_all.items()
               if v.get('status', 'active') != 'active'}
    if not hw:
        return False, ['EIGHT-STEPS.toml 里没有 [hardware.*] 条目']

    for name, body in hw.items():
        steps = body.get('step', {})
        for st in need:
            entry = steps.get(st)
            label = '%s :: %s' % (name, LABEL[st])
            if not entry:
                problems.append('%s 缺失' % label)
                continue
            ev = (entry.get('evidence') or '').strip()
            if len(ev) < 30:
                problems.append('%s 依据太短（需 >=30 字）' % label)
                continue
            if not has_reference(ev):
                problems.append('%s 依据缺可核查引用（需 file:line / URL / usblog-… / 0x… / P-xx / ★xx）' % label)
                continue
            if entry.get('done') is not True:
                problems.append('%s 未标记 done=true' % label)
                continue
            # ⑦ 核验额外要求本地已验证 + 三类验证齐全
            if st == 'verify':
                if entry.get('local_verified') is not True:
                    problems.append('%s 未 local_verified=true（不能在没本地证明前推进）' % label)
                    continue
                for kind in ('static_check', 'unit_test', 'artifact_check'):
                    if not (entry.get(kind) or '').strip():
                        problems.append('%s 缺 %s（⑦ 要求静态对照/离线单测/产物检查三类齐全）'
                                        % (label, kind))
                        continue
            # ④ 广域额外要求：官方组件目录必须查过
            if st == 'wide':
                if entry.get('catalog_checked') is not True:
                    problems.append('%s 未 catalog_checked=true（必须先查 UniXNU/components.toml，避免重复造轮子）' % label)
                    continue
                cr = (entry.get('catalog_result') or '').strip()
                if len(cr) < 40:
                    problems.append('%s catalog_result 太短（要逐个说明官方组件能不能用）' % label)
                    continue
            checked += 1

        # flash 模式额外检查第 8 步的预测
        if mode == 'flash':
            dev = steps.get('device') or {}
            pred = dev.get('prediction') or {}
            if not (pred.get('success') or '').strip():
                problems.append('%s :: ⑧ 上机 未声明 prediction.success（成功看哪一行日志）' % name)
            elif not (pred.get('failure') or '').strip():
                problems.append('%s :: ⑧ 上机 未声明 prediction.failure（失败看哪一行日志）' % name)
            else:
                checked += 1


    # --- README 表格一致性（防止 README 与 EIGHT-STEPS.toml drift）---
    try:
        import subprocess as _sp
        _r = _sp.run(['python3', os.path.join(REPO, 'scripts', 'render-eight-step-table.py'), '--check'],
                     capture_output=True, text=True, timeout=60)
        if _r.returncode != 0:
            problems.append('README 八步表格与 EIGHT-STEPS.toml 不一致，'
                            '跑 scripts/render-eight-step-table.py 重新生成并覆盖 README 的「八步流程进度」段')
        elif verbose:
            print('  README 八步表格: ✅ 与数据一致')
    except Exception as _e3:
        problems.append('README 表格一致性检查失败: %s' % str(_e3)[:50])

    if verbose:
        print('  模式: %s' % mode)
        print('  硬件项: %d 个（%s）' % (len(hw), ', '.join(hw.keys())))
        print('  通过 %d 项检查' % checked)
        if problems:
            print('  问题 %d 处:' % len(problems))
            for p in problems[:12]:
                print('    - %s' % p)

    return len(problems) == 0, problems


if __name__ == '__main__':
    mode = 'flash'
    for a in sys.argv[1:]:
        if a in ('--build', 'build'):
            mode = 'build'
        elif a in ('--flash', 'flash'):
            mode = 'flash'
    ok, probs = validate(mode)
    print()
    print('结论: %s' % ('✅ 八步流程通过（可以%s）' % ('构建' if mode == 'build' else '刷机')
                        if ok else '❌ 八步流程未通过，禁止%s' % ('构建' if mode == 'build' else '刷机')))
    sys.exit(0 if ok else 1)

# ============ W. STATUS.md 与 EIGHT-STEPS.toml 的硬件覆盖一致 ============
# 2026-11-12: STATUS.md 列了 10 项硬件，EIGHT-STEPS.toml 之前只跟踪 2 项。
# 做了不记录 = 下次重复踩坑，所以这里强制两边覆盖一致。
sec('W', 'STATUS.md 与 EIGHT-STEPS.toml 硬件覆盖一致')

# STATUS.md 的中文硬件名 -> EIGHT-STEPS.toml 的 key
_MAP = {
    'Boot chain': 'bootchain',
    'UFS': 'storage',
    '显示': 'display',
    '背光': 'display',
    '实体键': 'buttons',
    '触摸': 'touch',
    'GPU': 'gpu',
    'WiFi': 'wifi',
    '音频': 'audio',
    '电池': 'battery',
}

_tracked = set()
try:
    _steps = tomllib.load(io.open(ROOT + '/docs/research/EIGHT-STEPS.toml', 'rb'))
    _tracked = set(_steps.get('hardware', {}).keys())
except Exception as _e:
    bad('W', 'EIGHT-STEPS.toml 可读', str(_e)[:60])

_seen = set()
_missing = []
try:
    for _line in io.open(ROOT + '/docs/engineering/STATUS.md', encoding='utf-8', errors='ignore'):
        if not _line.startswith('|'):
            continue
        for _cn, _key in _MAP.items():
            if _cn in _line:
                if _key in _tracked:
                    _seen.add(_key)
                elif _key not in _missing:
                    _missing.append(_key)
except Exception as _e:
    bad('W', 'STATUS.md 可读', str(_e)[:60])

if _missing:
    bad('W', 'STATUS.md 的硬件都有八步记录',
        '缺: ' + ', '.join(sorted(_missing)) + '（见 docs/research/EIGHT-STEPS.toml）')
else:
    ok('W', 'STATUS.md 的硬件都有八步记录', '%d 项' % len(_seen))

_untracked = sorted(_tracked - _seen)
if _untracked:
    warn('W', 'EIGHT-STEPS.toml 有 STATUS.md 未列的硬件', ', '.join(_untracked))
