#!/usr/bin/env python3
"""快照门禁：改动前后必须有 tag，且 tag 必须已推送。

动机（2026-11-12）：`git reset --hard` 丢掉过八步表去重；`git pull --rebase`
把已回退的 0403 又拉了回来。两次都是"没有可回退的锚点"。
tag 是那个锚点，但只有在它被推送、且改动确实落在 tag 之后才有意义。

规则（AGENTS.md 铁则 7）：
  1. 任何会动构建产物的改动，动手前先打 tag 并 push
  2. tag 名带时间戳，一眼能看出先后
  3. 工作区脏的时候不许打 tag（否则 tag 里没有那些改动）
  4. 最近一次 tag 之后如果已经改了启动相关文件，必须有更新的 tag

用法：
  python3 scripts/check-snapshot-tag.py            # 构建前检查
  python3 scripts/check-snapshot-tag.py --tag      # 打一个带时间戳的 tag 并推送
退出码 0 通过，1 缺 tag 或有未快照的改动。
"""
import argparse
import datetime
import os
import subprocess
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 这些路径一改就可能影响能不能启动，改之前必须有 tag
BOOT_PATHS = (
    'patches/xnu/',
    'configs/',
    'board.toml',
    'dts/',
    'drivers/',
)


def git(*args, check=False):
    r = subprocess.run(['git'] + list(args), capture_output=True, text=True, cwd=REPO)
    if check and r.returncode != 0:
        raise SystemExit((r.stderr or r.stdout or '').strip()[:200])
    return (r.stdout or '').strip()


def make_tag(push=True):
    if git('status', '--porcelain'):
        print('  ❌ 工作区有未提交改动，先 commit 再打 tag')
        print('     （tag 只会记住已提交的内容，脏工作区打出来的 tag 是假的）')
        return 1
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    name = 'snap-' + stamp
    git('tag', '-f', name, check=True)
    print('  ✅ 已打 tag %s' % name)
    if push:
        r = subprocess.run(['git', 'push', '-f', 'origin', name],
                           capture_output=True, text=True, cwd=REPO)
        if r.returncode == 0:
            print('  ✅ 已推送 %s' % name)
        else:
            print('  ⚠️ 推送失败（本地 tag 仍有效）: %s' % (r.stderr or '')[:100])
    return 0


def check():
    # 最近一个 snap-* tag
    tags = git('tag', '--list', 'snap-*', '--sort=-creatordate').split('\n')
    tags = [t for t in tags if t.strip()]

    problems = []
    if not tags:
        problems.append('一个 snap-* tag 都没有')
    else:
        latest = tags[0]
        # 是否已推送
        r = subprocess.run(['git', 'ls-remote', '--tags', 'origin', 'refs/tags/' + latest],
                           capture_output=True, text=True, cwd=REPO)
        if not (r.stdout or '').strip():
            problems.append('最近的 tag %s 没有推到远端（丢了就没法回退）' % latest)

        # tag 之后有没有动启动相关文件
        changed = git('diff', '--name-only', '%s..HEAD' % latest).split('\n')
        boot_changed = [f for f in changed
                        if f.strip() and any(f.startswith(p) for p in BOOT_PATHS)]
        if boot_changed:
            problems.append(
                'tag %s 之后改了 %d 个启动相关文件，需要一个新 tag：'
                % (latest, len(boot_changed)))
            for f in boot_changed[:6]:
                problems.append('    %s' % f)

    if problems:
        print('  ❌ 快照不完整：')
        for p in problems:
            print('     %s' % p)
        print()
        print('     打 tag: python3 scripts/check-snapshot-tag.py --tag')
        print('     tag 是唯一能回退的锚点；没有它，reset --hard 就是单向操作。')
        return 1

    print('  ✅ 快照完整（最近 tag: %s，已推送，之后无启动相关改动）' % tags[0])
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--tag', action='store_true', help='打一个带时间戳的 tag 并推送')
    a = ap.parse_args()
    return make_tag() if a.tag else check()


if __name__ == '__main__':
    sys.exit(main())
