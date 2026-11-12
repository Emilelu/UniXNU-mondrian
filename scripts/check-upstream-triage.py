#!/usr/bin/env python3
"""上游提交研判门禁：每个分支要有水位，水位之后每个提交要有判定。

动机（2026-11-12）：跟踪脚本只报告"有新提交"，报告完就结束了。
同样的提交被反复发现、反复讨论、永远不落地，因为没有任何机制要求
"每个提交都被判过一次"。台账 + 这个门禁就是那个机制。

判定三选一：
  picked          已取（含手工重写），必须写 how
  not-applicable  不适用，必须写 reason
  deferred        暂缓，必须写 reason + review_after

用法：python3 scripts/check-upstream-triage.py [--fetch]
退出码 0 通过，1 有未研判提交或台账缺项。
"""
import argparse
import os
import subprocess
import sys
import tomllib


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(REPO, 'docs', 'research', 'UPSTREAM-TRIAGE.toml')
REF = '/mnt/e/k60-work/references'
VALID = {'picked', 'not-applicable', 'deferred'}


def git(d, *args):
    r = subprocess.run(['git'] + list(args), capture_output=True, text=True, cwd=d)
    return (r.stdout or '').strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--fetch', action='store_true', help='先 fetch 全分支')
    a = ap.parse_args()

    if not os.path.isfile(LEDGER):
        print('  ❌ 台账不存在: %s' % os.path.relpath(LEDGER, REPO))
        print('     铁则 6 要求每个上游分支都有水位记录。')
        return 1

    cfg = tomllib.load(open(LEDGER, 'rb'))
    branches = cfg.get('branch', [])
    commits = cfg.get('commit', [])

    if not branches:
        print('  ❌ 台账里没有 [[branch]] 记录')
        return 1

    # 已研判的 sha 集合
    triaged = {}
    for c in commits:
        sha = c.get('sha', '').strip()
        verdict = c.get('verdict', '').strip()
        if not sha:
            continue
        if verdict not in VALID:
            print('  ❌ 提交 %s 的 verdict 非法: %r（只能是 %s）'
                  % (sha[:9], verdict, ' / '.join(sorted(VALID))))
            return 1
        if verdict == 'picked' and not c.get('how'):
            print('  ❌ 提交 %s 判定 picked 但没写 how' % sha[:9])
            return 1
        if verdict in ('not-applicable', 'deferred') and not c.get('reason'):
            print('  ❌ 提交 %s 判定 %s 但没写 reason' % (sha[:9], verdict))
            return 1
        if verdict == 'deferred' and not c.get('review_after'):
            print('  ❌ 提交 %s 判定 deferred 但没写 review_after（等于忘记）' % sha[:9])
            return 1
        triaged[sha] = verdict

    # 逐分支检查水位之后有没有未研判提交
    problems = []
    checked = 0
    for b in branches:
        mirror = os.path.join('/mnt/e/k60-work', b['mirror'].replace('references/', 'references/'))
        if not os.path.isdir(os.path.join(mirror, '.git')):
            problems.append('%s: 镜像不存在 %s' % (b['branch'], b['mirror']))
            continue
        if a.fetch:
            subprocess.run(['git', 'fetch', '--all', '--prune', '--quiet'],
                           cwd=mirror, capture_output=True)
        ref = 'origin/' + b['branch']
        if subprocess.run(['git', 'rev-parse', '--verify', ref], cwd=mirror,
                          capture_output=True).returncode != 0:
            problems.append('%s: 镜像里没有分支 %s' % (b['branch'], b['branch']))
            continue
        wm = b.get('watermark', '')
        if subprocess.run(['git', 'cat-file', '-e', wm + '^{commit}'], cwd=mirror,
                          capture_output=True).returncode != 0:
            problems.append('%s: 水位 %s 在镜像里不存在' % (b['branch'], wm[:9]))
            continue
        checked += 1
        log = git(mirror, 'log', '--format=%H', '%s..%s' % (wm, ref))
        new = [x for x in log.split('\n') if x.strip()]
        for sha in new:
            if sha in triaged or sha[:9] in triaged:
                continue
            subj = git(mirror, 'log', '-1', '--format=%s', sha)
            problems.append('%s: 未研判 %s %s' % (b['branch'], sha[:9], subj[:60]))

    if problems:
        print('  ❌ 上游跟进未闭环：')
        for p in problems:
            print('     %s' % p)
        print()
        print('     每个水位之后的新提交都要在 docs/research/UPSTREAM-TRIAGE.toml')
        print('     里写一条 [[commit]]。默认 verdict 是 picked；')
        print('     只有纯文档用 not-applicable，只有物理上套不上我们的树才用 deferred。')
        return 1

    picked = sum(1 for v in triaged.values() if v == 'picked')
    deferred = sum(1 for v in triaged.values() if v == 'deferred')
    na = sum(1 for v in triaged.values() if v == 'not-applicable')
    print('  ✅ 上游跟进已闭环（%d 个分支 / %d 个提交：取 %d、不适用 %d、暂缓 %d）'
          % (checked, len(triaged), picked, na, deferred))
    return 0


if __name__ == '__main__':
    sys.exit(main())
