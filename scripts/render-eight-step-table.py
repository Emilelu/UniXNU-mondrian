#!/usr/bin/env python3
"""render-eight-step-table.py — 从 EIGHT-STEPS.toml 生成 README 用的八步表格

用法：
    python3 scripts/render-eight-step-table.py            # 打印
    python3 scripts/render-eight-step-table.py --check    # 校验 README 里的表是否与数据一致

为什么用生成器：
表格手写会 drift。改了 TOML 忘了改 README，README 就会撒谎。
生成 + --check 可以让门禁在 drift 时报错。
"""
import io
import os
import sys

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

REPO = '/mnt/e/hackios/UniXNU-mondrian'
DATA = os.path.join(REPO, 'docs', 'research', 'EIGHT-STEPS.toml')
README = os.path.join(REPO, 'README.md')

STEPS = ['same_model', 'official', 'decompile', 'wide', 'plan', 'deep', 'verify', 'device']
HEADS = ['① 同型', '② 官方', '③ 反编译', '④ 广域', '⑤ 方案', '⑥ 深挖', '⑦ 核验', '⑧ 上机']

# 未建立八步记录的硬件（诚实显示为 —，本身说明流程没走到）
UNTRACKED = [
    ('CPU', 'device-verified'),
    ('UFS / 存储', 'device-verified'),
    ('显示', 'device-verified'),
    ('固件 / 启动', 'device-verified'),
    ('电源', 'device-verified'),
    ('诊断', 'device-verified'),
    ('WiFi / 蓝牙 / USB', 'planned'),
    ('音频', 'planned'),
    ('基带', 'planned'),
    ('DSP', 'planned'),
]

MARK = {'done_true': '✅', 'done_false': '❌', 'partial': '◐'}


def cell(entry, st):
    if not entry:
        return '—'
    if st == 'verify':
        if entry.get('local_verified') is True:
            kinds = ['static_check', 'unit_test', 'artifact_check']
            n = sum(1 for k in kinds if (entry.get(k) or '').strip())
            return '✅' if n == 3 else ('◐' if n else '❌')
        return '❌'
    if st == 'wide':
        if entry.get('catalog_checked') is True and (entry.get('catalog_result') or '').strip():
            return '✅' if entry.get('done') is True else '◐'
        return '◐' if entry.get('done') is True else '❌'
    return '✅' if entry.get('done') is True else '❌'


def render():
    if tomllib is None:
        raise SystemExit('缺 tomllib')
    d = tomllib.load(open(DATA, 'rb'))
    hw = d.get('hardware', {})

    out = []
    out.append('| 硬件 | ' + ' | '.join(HEADS) + ' | 当前状态 |')
    out.append('|' + '---|' * (len(HEADS) + 2))

    for name, body in hw.items():
        steps = body.get('step', {})
        cells = [cell(steps.get(st), st) for st in STEPS]
        # 状态推导
        if all(c == '✅' for c in cells):
            status = '**八步全通**'
        elif cells[7] == '✅':
            status = 'device-verified'
        elif cells[6] == '✅':
            status = '可刷机（⑦ 已核验）'
        elif all(c in ('✅', '◐') for c in cells[:6]):
            status = '**卡在 ⑦ 核验**'
        else:
            status = '进行中'
        out.append('| **%s** | %s | %s |' % (body.get('name', name), ' | '.join(cells), status))

    for label, st in UNTRACKED:
        cells = ['—'] * len(STEPS)
        if st == 'device-verified':
            cells[7] = '✅'
            status = 'device-verified（未建八步记录）'
        else:
            status = st
        out.append('| %s | %s | %s |' % (label, ' | '.join(cells), status))

    out.append('')
    out.append('> ✅ 完成　◐ 部分　❌ 未完成　— 未建立记录')
    out.append('>')
    out.append('> 表格由 `scripts/render-eight-step-table.py` 从 `docs/research/EIGHT-STEPS.toml` 生成，'
               '`--check` 可校验 README 是否与数据一致。')
    out.append('> 八步定义见 [`docs/engineering/EIGHT-STEP-SPEC.md`](docs/engineering/EIGHT-STEP-SPEC.md)。')
    return '\n'.join(out)


if __name__ == '__main__':
    table = render()
    if '--check' in sys.argv:
        readme = io.open(README, encoding='utf-8', errors='ignore').read()
        if table.strip() in readme:
            print('✅ README 的八步表格与 EIGHT-STEPS.toml 一致')
            sys.exit(0)
        else:
            print('❌ README 的八步表格与数据不一致，请重新生成')
            sys.exit(1)
    print(table)
