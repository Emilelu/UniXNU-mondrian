#!/usr/bin/env python3
"""上游增量跟进：只处理「上次看到之后的新提交」，带摘要和分类。

为什么需要（2026-11-12）：yibiya 几分钟提交一次，全量扫描一遍要几分钟，
扫完又有新的。做法改成：
  1. 用 .upstream-seen.json 记住每个分支已处理到哪个 SHA
  2. 只拉增量（git log old..new）
  3. 按路径自动分类：启动链 / 触摸 / GPU / 电池 / 音频 / 文档 / 构建
  4. 文档类直接标 trivial 不占注意力，硬件类才要求研判

用法：
  python3 scripts/watch-upstream.py            # 增量报告
  python3 scripts/watch-upstream.py --mark     # 把当前 SHA 记为已处理
  python3 scripts/watch-upstream.py --loop 300 # 每 300 秒轮询一次
"""
import argparse
import json
import os
import subprocess
import sys
import time


WORK = '/mnt/e/k60-work'
SEEN = os.path.join(WORK, '.upstream-seen.json')

REPOS = {
    'UniXNU-mondrian': os.path.join(WORK, 'references/yibiya-upstream'),
    'UniXNU':          os.path.join(WORK, 'references/yibiya-unixnu-upstream'),
    'uefi-mondrian':   os.path.join(WORK, 'references/yibiya-uefi-upstream'),
}

# 路径 -> 类别。顺序有意义：先匹配先生效。
RULES = [
    ('boot',    ('patches/xnu/04', 'patches/xnu/039', 'patches/xnu/0600', 'configs/', 'board.toml')),
    ('touch',   ('pong-touch', 'touch.c', 'touch.h', 'goodix')),
    ('gpu',     ('PongAdreno', 'PongMetal', 'NativeMetal', 'adreno', 'metal')),
    ('battery', ('PongPower', 'battery', 'Battmgr', 'PmicGlink', 'QcomGlink', 'Smem')),
    ('audio',   ('audio', 'Adsp', 'Gpr', 'Wcd')),
    ('input',   ('pong_input', 'pong_buttons', 'physical-keys')),
    ('build',   ('scripts/', 'unixnu/', 'Makefile', '.github/')),
    ('docs',    ('.md', 'docs/')),
]

WEIGHT = {'boot': 5, 'touch': 4, 'gpu': 4, 'battery': 4, 'audio': 3,
          'input': 3, 'build': 2, 'docs': 1, 'other': 2}


def git(d, *args):
    r = subprocess.run(['git'] + list(args), capture_output=True, text=True, cwd=d)
    return (r.stdout or '').strip()


def classify(files):
    cats = set()
    for f in files:
        hit = None
        for cat, pats in RULES:
            if any(p in f for p in pats):
                hit = cat
                break
        cats.add(hit or 'other')
    return cats


def load_seen():
    if os.path.isfile(SEEN):
        try:
            return json.load(open(SEEN))
        except Exception:
            pass
    return {}


def save_seen(d):
    json.dump(d, open(SEEN, 'w'), indent=2, sort_keys=True)


def poll(fetch=True, verbose=True):
    seen = load_seen()
    findings = []

    for name, d in REPOS.items():
        if not os.path.isdir(os.path.join(d, '.git')):
            continue
        if fetch:
            subprocess.run(['git', 'config', 'remote.origin.fetch',
                            '+refs/heads/*:refs/remotes/origin/*'], cwd=d)
            subprocess.run(['git', 'fetch', '--all', '--prune', '--quiet'],
                           cwd=d, capture_output=True)

        branches = git(d, 'for-each-ref', '--format=%(refname:short)',
                       'refs/remotes/origin/').split('\n')
        for ref in branches:
            if not ref.strip() or ref.endswith('/HEAD'):
                continue
            br = ref.replace('origin/', '')
            key = '%s/%s' % (name, br)
            head = git(d, 'rev-parse', ref)
            old = seen.get(key)

            if old is None:
                # 首次：只记基线，不报历史
                seen[key] = head
                continue
            if old == head:
                continue

            log = git(d, 'log', '--format=%H|%ci|%s', '%s..%s' % (old, head))
            for line in log.split('\n'):
                if not line.strip():
                    continue
                p = line.split('|', 2)
                if len(p) < 3:
                    continue
                sha, date, subj = p
                files = git(d, 'show', '--name-only', '--format=', sha).split('\n')
                files = [f for f in files if f.strip()]
                cats = classify(files)
                weight = max(WEIGHT.get(c, 2) for c in cats)
                findings.append({
                    'repo': name, 'branch': br, 'sha': sha[:9], 'date': date[:16],
                    'subject': subj, 'cats': sorted(cats), 'weight': weight,
                    'files': files[:8], 'nfiles': len(files),
                })
            seen[key] = head

    save_seen(seen)

    if verbose:
        if not findings:
            print('  没有新提交')
            return 0
        findings.sort(key=lambda x: (-x['weight'], x['date']))
        hi = [f for f in findings if f['weight'] >= 3]
        lo = [f for f in findings if f['weight'] < 3]
        print('  新提交 %d 个（高价值 %d / 低价值 %d）' % (len(findings), len(hi), len(lo)))
        if hi:
            print()
            print('  === 需要研判 ===')
            for f in hi:
                print('  %s %s/%s  %s' % (f['sha'], f['repo'][:8], f['branch'][:18], f['date']))
                print('      %s' % f['subject'][:88])
                print('      类别 %s  %d 个文件' % (','.join(f['cats']), f['nfiles']))
                for x in f['files'][:4]:
                    print('        %s' % x[:76])
        if lo:
            print()
            print('  === 可略过 ===')
            for f in lo:
                print('  %s %s/%s  %s' % (f['sha'], f['repo'][:8], f['branch'][:18], f['subject'][:60]))
    return len(findings)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mark', action='store_true', help='把当前 SHA 记为已处理，不报告')
    ap.add_argument('--loop', type=int, default=0, help='每 N 秒轮询一次')
    ap.add_argument('--no-fetch', action='store_true')
    a = ap.parse_args()

    if a.mark:
        n = poll(fetch=not a.no_fetch, verbose=False)
        print('  已记录当前状态')
        return 0

    if a.loop:
        while True:
            print('\n=== %s ===' % time.strftime('%H:%M:%S'))
            poll(fetch=not a.no_fetch)
            sys.stdout.flush()
            time.sleep(a.loop)

    poll(fetch=not a.no_fetch)
    return 0


if __name__ == '__main__':
    sys.exit(main())
