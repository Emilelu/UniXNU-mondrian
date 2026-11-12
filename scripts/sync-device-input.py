#!/usr/bin/env python3
"""把仓库镜像到构建输入，替代手工 cp。

为什么需要（2026-11-12）：repo / /opt/.../device / scratch 三份副本靠手工 cp 同步，
每轮都在漂移。0403 补丁曾经只在 device 里、DT 节点曾经只在 device 里、八步表去重
被 reset 丢掉 —— 都是"同一个东西存在于多个地方"的直接后果。

原则：仓库是唯一真源，构建输入是它的镜像。方向只有一个。
"""
import argparse
import filecmp
import os
import shutil
import subprocess
import sys


REPO = '/mnt/e/hackios/UniXNU-mondrian'
DEV = '/opt/k60/trees/usb-cdc-mainline/device'
SCRATCH_SERIES = '/mnt/e/k60-work/scratch/SERIES-FINAL.txt'

# 仓库里需要镜像到构建输入的条目（相对路径）
ITEMS = [
    'board.toml',
    'porting.toml',
    'local.toml',
    'dts',
    'patches',
    'drivers',
    'userland',
    'scripts',
    'kits',
    'configs',
]


def walk_files(root, rel):
    """返回 rel 下所有文件（相对 rel 的路径）。"""
    out = []
    base = os.path.join(root, rel)
    if os.path.isfile(base):
        return [rel]
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in ('.git', '__pycache__', 'build')]
        for f in filenames:
            full = os.path.join(dirpath, f)
            out.append(os.path.relpath(full, root))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check', action='store_true', help='只报告差异，不写')
    a = ap.parse_args()

    if not os.path.isdir(DEV):
        print('  构建输入不存在: %s' % DEV)
        return 1

    copied, same, missing = [], 0, []
    for item in ITEMS:
        src = os.path.join(REPO, item)
        if not os.path.exists(src):
            continue
        for rel in walk_files(REPO, item):
            s = os.path.join(REPO, rel)
            d = os.path.join(DEV, rel)
            if os.path.exists(d) and filecmp.cmp(s, d, shallow=False):
                same += 1
                continue
            if a.check:
                copied.append(rel)
                continue
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copyfile(s, d)
            copied.append(rel)

    # series 也镜像到 scratch（一份只读副本，供别的脚本查）
    try:
        s = open(os.path.join(REPO, 'patches/xnu/series'), encoding='utf-8').read()
        if not a.check:
            os.makedirs(os.path.dirname(SCRATCH_SERIES), exist_ok=True)
            open(SCRATCH_SERIES, 'w', encoding='utf-8', newline='\n').write(s)
    except OSError:
        pass

    # 构建输入里多出来的补丁，删掉（唯一真源是仓库）
    pa = os.path.join(REPO, 'patches/xnu')
    pb = os.path.join(DEV, 'patches/xnu')
    extra = []
    if os.path.isdir(pa) and os.path.isdir(pb):
        for f in sorted(os.listdir(pb)):
            if f.endswith('.patch') and not os.path.exists(os.path.join(pa, f)):
                extra.append(f)
                if not a.check:
                    os.unlink(os.path.join(pb, f))

    print('  %s: %d 个文件已一致' % ('检查' if a.check else '同步', same))
    if copied:
        print('  %s %d 个:' % ('待同步' if a.check else '已同步', len(copied)))
        for c in copied[:12]:
            print('    %s' % c)
        if len(copied) > 12:
            print('    ... 还有 %d 个' % (len(copied) - 12))
    if extra:
        print('  %s %d 个只在构建输入:' % ('发现' if a.check else '已删除', len(extra)))
        for e in extra:
            print('    %s' % e)

    if a.check and copied:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
