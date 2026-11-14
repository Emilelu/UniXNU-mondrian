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
from pathlib import Path

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

# 仓库根：默认本脚本所在的检出（worktree 里跑就用 worktree），K60_REPO 可覆盖。
REPO = Path(os.environ.get('K60_REPO') or Path(__file__).resolve().parents[1])
DATA = os.path.join(REPO, 'docs', 'research', 'EIGHT-STEPS.toml')
README = os.path.join(REPO, 'README.md')
README_EN = os.path.join(REPO, 'README_EN.md')

STEPS = ['same_model', 'official', 'decompile', 'wide', 'plan', 'deep', 'verify', 'device']
HEADS_ZH = ['① 同型', '② 官方', '③ 反编译', '④ 广域', '⑤ 方案', '⑥ 深挖', '⑦ 核验', '⑧ 上机']
HEADS_EN = ['① Same model', '② Official', '③ Reverse', '④ Wide search', '⑤ Plan', '⑥ Deep dive', '⑦ Local verify', '⑧ On device']

# 未建立八步记录的硬件（诚实显示为 —，本身说明流程没走到）
# 只能放 EIGHT-STEPS.toml 里没有的项。2026-11-12：这里曾同时列着
# 「UFS / 存储 / 显示 / 固件启动 / 音频」，而 storage / display / bootchain /
# audio 早已进了 EIGHT-STEPS.toml，于是表格出现重复行。见铁则 5 与 P-148。
UNTRACKED = [
    ('CPU', 'device-verified'),
    ('电源', 'device-verified'),
    ('诊断', 'device-verified'),
    ('蓝牙', 'planned'),
    ('USB', 'planned'),
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


def render(lang='zh'):
    if tomllib is None:
        raise SystemExit('缺 tomllib')
    d = tomllib.load(open(DATA, 'rb'))
    hw = d.get('hardware', {})

    out = []
    HEADS = HEADS_ZH if lang == 'zh' else HEADS_EN
    first = '硬件' if lang == 'zh' else 'Hardware'
    last = '当前状态' if lang == 'zh' else 'Status'
    out.append('| %s | ' % first + ' | '.join(HEADS) + ' | %s |' % last)
    out.append('|' + '---|' * (len(HEADS) + 2))

    for name, body in hw.items():
        steps = body.get('step', {})
        cells = [cell(steps.get(st), st) for st in STEPS]
        # 状态推导
        if lang == 'zh':
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
        else:
            if all(c == '✅' for c in cells):
                status = '**All eight steps pass**'
            elif cells[7] == '✅':
                status = 'device-verified'
            elif cells[6] == '✅':
                status = 'Ready to flash (⑦ verified)'
            elif all(c in ('✅', '◐') for c in cells[:6]):
                status = '**Blocked at ⑦**'
            else:
                status = 'In progress'
        out.append('| **%s** | %s | %s |' % (body.get('name', name), ' | '.join(cells), status))

    for label, st in UNTRACKED:
        cells = ['—'] * len(STEPS)
        if st == 'device-verified':
            cells[7] = '✅'
            status = 'device-verified（未建八步记录）' if lang == 'zh' else 'device-verified (no record)'
        else:
            status = st
        out.append('| %s | %s | %s |' % (label, ' | '.join(cells), status))

    out.append('')
    if lang == 'zh':
        out.append('> ✅ 完成　◐ 部分　❌ 未完成　— 未建立记录')
    else:
        out.append('> ✅ done　◐ partial　❌ not done　— no record')
    out.append('>')
    out.append('> 表格由 `scripts/render-eight-step-table.py` 从 `docs/research/EIGHT-STEPS.toml` 生成，'
               '`--check` 可校验 README 是否与数据一致。')
    out.append('> 八步定义见 [`docs/engineering/EIGHT-STEP-SPEC.md`](docs/engineering/EIGHT-STEP-SPEC.md)。')
    return '\n'.join(out)


def apply_to_readme():
    for lang, path in (('zh', README), ('en', README_EN)):
        if not os.path.exists(path):
            continue
        table = render(lang)
        s = io.open(path, encoding='utf-8', errors='ignore').read()
        BEGIN = '<!-- EIGHT-STEP-TABLE:BEGIN -->'
        END = '<!-- EIGHT-STEP-TABLE:END -->'
        i = s.find(BEGIN)
        j = s.find(END)
        if i < 0 or j < 0:
            continue
        s = s[:i + len(BEGIN)] + '\n' + table + '\n' + s[j:]
        io.open(path, 'w', encoding='utf-8', newline='\n').write(s)
        print('✅ 已更新 %s' % os.path.basename(path))


if __name__ == '__main__':
    table = render()
    if '--apply' in sys.argv:
        apply_to_readme()
        sys.exit(0)
    if '--check' in sys.argv:
        readme = io.open(README, encoding='utf-8', errors='ignore').read()
        if table.strip() in readme:
            print('✅ README 的八步表格与 EIGHT-STEPS.toml 一致')
            sys.exit(0)
        else:
            print('❌ README 的八步表格与数据不一致，请重新生成')
            sys.exit(1)
    print(table)
