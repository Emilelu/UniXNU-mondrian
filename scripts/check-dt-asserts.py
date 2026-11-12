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
    """从驱动补丁里提取 (节点路径, 属性名) 对。

    识别两种写法：
      property(entry,"avdd-gpio",&avdd_gpio,4)
      property(e,"core-base",&c,8)
    """
    reads = set()
    for m in re.finditer(r'property\s*\(\s*\w+\s*,\s*"([^"]+)"', patch_text):
        reads.add(m.group(1))
    return reads


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
        reads = driver_dt_reads(text)
        if not reads:
            if a.verbose:
                print('  %-14s 补丁里没有 property(...) 调用' % node)
            continue
        props = dts_properties(dts, node)
        if props is None:
            problems.append('%s: dts 里没有这个节点，但驱动会查它' % node)
            continue
        checked += 1
        missing = sorted(reads - props)
        if missing:
            if is_frozen(node, areas):
                warns.append('%s: 缺属性 %s（该区域已冻结，只警告）' % (node, ', '.join(missing)))
            else:
                problems.append('%s: dts 节点缺属性 %s' % (node, ', '.join(missing)))
        elif a.verbose:
            print('  %-14s 断言 %d 个属性，dts 全部具备' % (node, len(reads)))

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
