#!/usr/bin/env python3
"""DT 断言覆盖检查：驱动 configuration() 断言的每个 DT 属性，节点里必须真的存在。

动机（P-147）：pong_goodix 的 configuration() 断言 avdd_gpio==71、max_x==14400、
max_y==32000，而 DTS 里没有 avdd-gpio、max-x 是 1080。于是 configuration() 恒返回
false，十几轮加进去的七层触摸诊断一行都没执行 —— 全在内核里，全都不可达。

这个检查在构建之前跑：解析驱动补丁里的 property(entry,"X"...) 调用，
对照 dts 里对应节点的属性，缺一个就失败。

用法：python3 scripts/check-dt-asserts.py [--repo DIR]
退出码 0 通过，1 有缺失。
"""
import argparse
import io
import os
import re
import sys


# 驱动查的节点名 -> dts 里的节点块名（同一个名字，留扩展点）
try:
    import fnmatch
    import tomllib
except ImportError:
    fnmatch = None
    tomllib = None


def frozen_areas(repo):
    """读出冻结区域，返回 {name: [patterns]}。冻结区只警告不失败。"""
    if tomllib is None:
        return {}
    p = os.path.join(repo, 'docs', 'SCOPE-FREEZE.toml')
    if not os.path.isfile(p):
        return {}
    try:
        cfg = tomllib.load(open(p, 'rb'))
    except Exception:
        return {}
    return {k: v.get('paths', []) for k, v in cfg.get('frozen', {}).items()}


def is_frozen(node, areas):
    """DT 节点名是否落在冻结区（看有没有任何路径模式匹配得上）。"""
    if fnmatch is None:
        return False
    for name, pats in areas.items():
        if name == node:
            return True
        for p in pats:
            if fnmatch.fnmatch('dts/mondrian.dts', p):
                return True
    return False




def profile_properties(repo, node):
    """框架 OS profile 里 [adt.arm-io.<node>] 的属性集合。

    2026-11-12 三方分工确立后，SoC 级契约由 profile.toml 提供：
      profile.toml   SoC 级（pong-touch 基础字段、pong-buttons）
      board.toml     板级覆盖（avdd-gpio、compatible、max-x/y）
      dts            板级独有（pong-audio、ufshc）
    profile 是框架仓库的一部分，路径按优先级查找。
    """
    # 框架检出与本仓库同级；K60_FRAMEWORK_REPO 可覆盖（hard-39）
    fw = os.environ.get('K60_FRAMEWORK_REPO') or os.path.join(repo, '..', 'UniXNU')
    CANDIDATES = [
        '/opt/k60/trees/k60build/profiles/os',
        os.path.join(fw, 'profiles', 'os'),
    ]
    try:
        import tomllib
    except ImportError:
        return set()
    for base in CANDIDATES:
        if not os.path.isdir(base):
            continue
        for prof in sorted(os.listdir(base)):
            p = os.path.join(base, prof, 'profile.toml')
            if not os.path.isfile(p):
                continue
            try:
                cfg = tomllib.load(open(p, 'rb'))
            except Exception:
                continue
            table = cfg.get('adt', {}).get('arm-io', {}).get(node)
            if isinstance(table, dict):
                props = set()
                for typed, vals in table.items():
                    if isinstance(vals, dict):
                        props |= set(vals.keys())
                if props:
                    return props
    return set()


def board_properties(repo, node):
    """board.toml 里 [adt.arm-io.<node>] 的属性集合。

    2026-11-12 起 board.toml 是唯一真源（1e1a70e 让 [adt.arm-io.*] 真正生效），
    DTS 里不再重复声明这些节点。所以属性可能来自两处之一。
    """
    try:
        import tomllib
    except ImportError:
        return set()
    p = os.path.join(repo, 'board.toml')
    if not os.path.isfile(p):
        return set()
    try:
        cfg = tomllib.load(open(p, 'rb'))
    except Exception:
        return set()
    table = cfg.get('adt', {}).get('arm-io', {}).get(node)
    if not isinstance(table, dict):
        return set()
    props = set()
    for typed, vals in table.items():
        if isinstance(vals, dict):
            props |= set(vals.keys())
    return props


def dts_properties(text, node):
    """返回 dts 里 <node> { ... } 块的属性名集合。"""
    m = re.search(r'^\t%s\s*\{(.*?)^\t\};' % re.escape(node), text, re.M | re.S)
    if not m:
        return None
    body = m.group(1)
    props = set()
    for line in body.split('\n'):
        line = line.strip()
        if '=' in line and not line.startswith('/*') and not line.startswith('*'):
            props.add(line.split('=')[0].strip())
    return props


def driver_dt_reads(patch_text):
    """从驱动补丁里提取必需和可选两类 DT 属性。

    判据（P-147 修正）：`property()` 出现在 `configuration()` 的 return 链里
    才是必需的 —— 缺了它整个函数返回 false，后面的诊断全不执行。
    出现在赋值语句里的是可选 —— 例如 bitbang-pins 是 GPIO 回退路径的开关，
    缺了只是关掉那条路，不影响其余流程。

    必需：
        return property(entry,"spi-base",&se_phys,8) && property(entry,"pins",...)
    可选：
        bitbang_wiring = property(entry, "bitbang-pins", bitbang_pins, sizeof(...));
    """
    required, optional = set(), set()
    # 找 configuration() 函数体
    m = re.search(r'^\+?configuration\s*\([^)]*\)\s*\n?\{', patch_text, re.M)
    body = patch_text
    if m:
        start = m.end()
        # 到下一个顶层函数为止
        m2 = re.search(r'\n\+?\}', patch_text[start:])
        body = patch_text[start:start + (m2.end() if m2 else 8000)]

    for line in body.split('\n'):
        raw = line[1:] if line.startswith('+') else line
        if 'property(' not in raw:
            continue
        # 赋值形式 -> 可选
        is_assign = bool(re.match(r'\s*\w+\s*=\s*property\s*\(', raw))
        for mm in re.finditer(r'property\s*\(\s*\w+\s*,\s*"([^"]+)"', raw):
            (optional if is_assign else required).add(mm.group(1))
    return required, optional


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument('-v', '--verbose', action='store_true')
    a = ap.parse_args()
    repo = a.repo

    dts_path = os.path.join(repo, 'dts', 'mondrian.dts')
    if not os.path.isfile(dts_path):
        print('  跳过：%s 不存在' % dts_path)
        return 0
    dts = io.open(dts_path, encoding='utf-8', errors='ignore').read()

    # 驱动补丁：pong-touch / pong-buttons 等
    pairs = [
        ('pong-touch', 'zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch'),
        ('pong-buttons', 'zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-physical-keys.patch'),
    ]

    problems = []
    warns = []
    checked = 0
    areas = frozen_areas(repo)
    for node, patch in pairs:
        p = os.path.join(repo, 'patches', 'xnu', patch)
        if not os.path.isfile(p):
            if a.verbose:
                print('  %-14s 补丁不存在，跳过' % node)
            continue
        text = io.open(p, encoding='utf-8', errors='ignore').read()
        reads, optional = driver_dt_reads(text)
        if not reads and not optional:
            if a.verbose:
                print('  %-14s 补丁里没有 property(...) 调用' % node)
            continue
        from_dts = dts_properties(dts, node) or set()
        from_toml = board_properties(repo, node)
        from_prof = profile_properties(repo, node)
        props = from_dts | from_toml | from_prof
        if not props:
            problems.append('%s: dts / board.toml / profile.toml 三处都没有，但驱动会查它' % node)
            continue
        checked += 1
        missing = sorted(reads - props)
        missing_opt = sorted(optional - props)
        if missing:
            if is_frozen(node, areas):
                warns.append('%s: 缺属性 %s（该区域已冻结，只警告）' % (node, ', '.join(missing)))
            else:
                problems.append('%s: dts 节点缺属性 %s' % (node, ', '.join(missing)))
        elif a.verbose:
            print('  %-14s 必需 %d / 可选 %d（dts %d + board %d + profile %d）' % (node, len(reads), len(optional), len(from_dts), len(from_toml), len(from_prof)))
            if missing_opt:
                print('              可选属性未声明（不影响启动）: %s' % ', '.join(missing_opt))

    for w in warns:
        print('  ⚠️  %s' % w)
    if problems:
        print('  ❌ DT 断言覆盖不足：')
        for x in problems:
            print('     %s' % x)
        print()
        print('     驱动在 configuration() 里断言这些属性；缺一个就返回 false，')
        print('     该硬件写在函数里的全部诊断一行都不会执行（P-147）。')
        return 1

    print('  ✅ DT 断言覆盖通过（检查 %d 个节点）' % checked)
    return 0


if __name__ == '__main__':
    sys.exit(main())
