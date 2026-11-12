#!/usr/bin/env python3
"""范围冻结门禁：用户明确说「不要动 X」时，X 相关文件不能被改动。

动机（2026-11-12）：用户明确说过不要碰触摸和 GPU，但我仍然改了
dts/mondrian.dts 的 pong-touch 节点和触摸补丁。仓库里没有任何机制阻止这件事，
「不要动」只存在于对话里，构建门禁看不见。

做法：docs/SCOPE-FREEZE.toml 记录冻结范围，本脚本对比 git 基线，
发现被冻结的路径有改动就失败。要改必须显式加 --propose，写进提案文件而不是直接改。

用法：
  python3 scripts/check-scope-freeze.py            # 构建前跑，失败即停
  python3 scripts/check-scope-freeze.py --propose  # 输出待批准的改动清单
退出码 0 通过，1 有违规改动。
"""
import argparse
import fnmatch
import io
import os
import subprocess
import sys
import tomllib


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FREEZE = os.path.join(REPO, 'docs', 'SCOPE-FREEZE.toml')


def changed_files(base):
    """返回自 base 以来改动的文件列表（含未提交）。"""
    out = set()
    r = subprocess.run(['git', 'diff', '--name-only', base], capture_output=True, text=True, cwd=REPO)
    out |= {l.strip() for l in (r.stdout or '').split('\n') if l.strip()}
    r = subprocess.run(['git', 'diff', '--name-only', 'HEAD'], capture_output=True, text=True, cwd=REPO)
    out |= {l.strip() for l in (r.stdout or '').split('\n') if l.strip()}
    r = subprocess.run(['git', 'ls-files', '--others', '--exclude-standard'], capture_output=True, text=True, cwd=REPO)
    out |= {l.strip() for l in (r.stdout or '').split('\n') if l.strip()}
    return sorted(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--propose', action='store_true', help='只输出待批准清单，不判失败')
    a = ap.parse_args()

    if not os.path.isfile(FREEZE):
        print('  ✅ 无冻结文件，跳过')
        return 0

    cfg = tomllib.load(open(FREEZE, 'rb'))
    areas = cfg.get('frozen', {})
    if not areas:
        print('  ✅ 冻结表为空')
        return 0

    violations = []
    for name, spec in areas.items():
        base = spec.get('baseline', 'HEAD')
        paths = spec.get('paths', [])
        if not paths:
            continue
        changed = changed_files(base)
        hit = []
        for f in changed:
            for p in paths:
                if fnmatch.fnmatch(f, p) or f == p or f.startswith(p.rstrip('*')):
                    hit.append(f)
                    break
        if hit:
            violations.append((name, spec.get('reason', ''), sorted(set(hit))))

    if not violations:
        print('  ✅ 冻结范围未被改动（%d 个区域）' % len(areas))
        return 0

    print('  ❌ 冻结范围被改动：' if not a.propose else '  待批准的改动（冻结范围）：')
    for name, reason, files in violations:
        print('     [%s] %s' % (name, reason))
        for f in files:
            print('        %s' % f)
    print()
    print('     要让改动生效：在 docs/SCOPE-FREEZE.toml 里移除该区域，')
    print('     或先在对话里取得用户明确同意。冻结存在的理由就是不要靠记忆。')
    return 0 if a.propose else 1


if __name__ == '__main__':
    sys.exit(main())
