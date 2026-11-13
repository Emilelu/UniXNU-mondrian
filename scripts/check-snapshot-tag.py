#!/usr/bin/env python3
"""Snapshot gate: only tags that mark a proven state, and they must be pushed.

Why this changed (2026-11-13): the gate used to demand a fresh timestamped tag
before every change under a boot path. That produced 134 tags in a week, 126 of
them noise, so the useful anchors became unfindable (user: "打了一堆tag 到底哪些
有用的？没用的就删掉 后面也不要乱加 只加有用的").

Allowed tag kinds (AGENTS.md iron rule 7):
  boot-proven-YYYYMMDD  - an image from this commit reached SpringBoard
  snap-rN               - the commit registered as the main baseline (iron 9)
  vX.Y.Z-...            - a release milestone the READMEs point at

Checks:
  1. no tag outside those three patterns (catches per-commit/per-round spam)
  2. at least one boot-proven-* tag exists and is pushed
  3. every tag registered in MAIN-BASELINE.toml exists locally

`--tag` creates boot-proven-YYYYMMDD only when the tree is clean AND
MAIN-BASELINE.toml lists HEAD with state = "booted"; the tag message is the
evidence block from that entry.
"""
import argparse
import datetime
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWED = (
    re.compile(r'^boot-proven-\d{8}$'),
    re.compile(r'^snap-r\d+$'),
    re.compile(r'^v\d+\.\d+\.\d+'),
)


def git(*args):
    r = subprocess.run(['git'] + list(args), capture_output=True, text=True, cwd=REPO)
    return (r.stdout or '').strip()


def is_pushed(tag):
    r = subprocess.run(['git', 'ls-remote', '--tags', 'origin', 'refs/tags/' + tag],
                       capture_output=True, text=True, cwd=REPO)
    return bool((r.stdout or '').strip())


def baseline_entries():
    path = os.path.join(REPO, 'docs', 'engineering', 'MAIN-BASELINE.toml')
    if not os.path.isfile(path):
        return []
    entries, cur = [], {}
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        m = re.match(r'^\[\[(?:baseline|entry)\]\]', line)
        if m:
            if cur:
                entries.append(cur)
            cur = {}
            continue
        m = re.match(r'^(\w+)\s*=\s*"([^"]*)"', line)
        if m and cur is not None:
            cur[m.group(1)] = m.group(2)
    if cur:
        entries.append(cur)
    return entries


def make_tag():
    if git('status', '--porcelain'):
        print('  ❌ 工作区有未提交改动；tag 只能记住已提交的内容')
        return 1
    head = git('rev-parse', '--short', 'HEAD')
    entries = baseline_entries()
    match = [e for e in entries if e.get('sha', '').startswith(head) or head.startswith(e.get('sha', 'x'))]
    if not match or match[-1].get('state') not in ('booted', 'boot'):
        print('  ❌ 只有「上机验证过」的状态才能打 tag：MAIN-BASELINE.toml 里找不到')
        print('     sha=%s state="booted" 的条目（铁则 7 / 铁则 9）' % head)
        print('     先上机，把镜像与 console.log 证据写进 MAIN-BASELINE.toml，再打 tag。')
        return 1
    entry = match[-1]
    name = 'boot-proven-' + datetime.datetime.now().strftime('%Y%m%d')
    msg = ['boot-proven %s' % head, '']
    for key in ('image', 'image_sha256', 'console', 'note'):
        if entry.get(key):
            msg.append('%s: %s' % (key, entry[key]))
    msg.append('tagged: %s' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))
    args = ['tag', '-f', name]
    for line in msg:
        args += ['-m', line]
    git(*args)
    print('  ✅ 已打 tag %s' % name)
    r = subprocess.run(['git', 'push', '-f', 'origin', name], capture_output=True, text=True, cwd=REPO)
    print('  ✅ 已推送' if r.returncode == 0 else '  ⚠️ 推送失败（本地 tag 仍有效）')
    return 0


def check():
    tags = [t for t in git('tag').split('\n') if t.strip()]
    problems = []

    bad = [t for t in tags if not any(p.match(t) for p in ALLOWED)]
    if bad:
        problems.append('有 %d 个不属于「上机验证 / main 基线 / 版本里程碑」的 tag：' % len(bad))
        for t in bad[:8]:
            problems.append('    %s' % t)
        problems.append('    删掉它们：git tag -d TAG 与 git push origin --delete TAG')

    proven = [t for t in tags if t.startswith('boot-proven-')]
    if not proven:
        problems.append('没有 boot-proven-* tag：没有任何一个「上过机证明能启动」的锚点')
    else:
        latest = sorted(proven)[-1]
        if not is_pushed(latest):
            problems.append('%s 没有推到远端（丢了就没法回退）' % latest)

    for e in baseline_entries():
        tag = e.get('tag')
        if tag and tag not in tags:
            problems.append('MAIN-BASELINE.toml 登记的 tag %s 不在本地' % tag)

    if problems:
        print('  ❌ 快照不完整：')
        for p in problems:
            print('     %s' % p)
        print()
        print('     tag 规则见 AGENTS.md 铁则 7 与 docs/engineering/TAGS.md')
        return 1

    print('  ✅ 快照策略通过：%d 个 tag（boot-proven %d / 基线 %d / 版本 %d），最近 boot-proven %s 已推送'
          % (len(tags),
             len([t for t in tags if t.startswith('boot-proven-')]),
             len([t for t in tags if t.startswith('snap-r')]),
             len([t for t in tags if t.startswith('v')]),
             sorted(proven)[-1]))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--tag', action='store_true',
                    help='在 MAIN-BASELINE.toml 已登记 HEAD 且 state=booted 时打 boot-proven tag')
    a = ap.parse_args()
    return make_tag() if a.tag else check()


if __name__ == '__main__':
    sys.exit(main())
