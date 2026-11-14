#!/usr/bin/env python3
"""构建新鲜度门禁：三个组件都必须是当前代码，不能是旧副本/旧产物。

动机（2026-11-12 用户要求）：「后续重新构建 unixnu / xnu / uefi 以及 unixnu
分区镜像都要确保都是用最新的代码来进行的」。

三个组件各有各的「旧」法：
  uniXNU 框架  /opt/k60/trees/k60build 是 E:\\hackios\\UniXNU 的副本，会漂移
  xnu 内核      由 framework + series 决定，series 变了但没重建就是旧的
  uefi 固件     .fd 是编译产物，uefi-mondrian 变了但没重编就是旧的

判据（机器可验，不靠自觉）：
  F1 框架副本与仓库的 scripts/unixnu 完全一致
  F2 框架副本不比仓库旧（按 mtime）
  F3 固件 .fd 比 uefi-mondrian 最后一次提交新
  F4 记录 kernel / payload / fd 的 sha256 到 build-manifest.json

用法：
  python3 scripts/check-build-freshness.py            # 检查
  python3 scripts/check-build-freshness.py --manifest # 生成构建清单
退出码 0 通过，1 有陈旧组件。
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys

REPO = os.path.abspath(os.environ.get('K60_REPO')
                      or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 兄弟检出与本仓库同级；K60_FRAMEWORK_REPO / K60_UEFI_REPO 可覆盖（hard-39）
FW_REPO = os.path.abspath(os.environ.get('K60_FRAMEWORK_REPO')
                          or os.path.join(os.path.dirname(REPO), 'UniXNU'))
FW_COPY = '/opt/k60/trees/k60build'
UEFI = os.path.abspath(os.environ.get('K60_UEFI_REPO')
                       or os.path.join(os.path.dirname(REPO), 'uefi-mondrian'))
FD = UEFI + '/Build/mondrianPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd'
BUILD = '/opt/k60/trees/k60build/out-baseline/mondrian/ipados-16.6.1-20G81/mondrian'
MANIFEST = REPO + '/build-manifest.json'

FRAMEWORK_DIRS = ['scripts/unixnu']


def sha(p):
    try:
        return hashlib.sha256(open(p, 'rb').read()).hexdigest()
    except OSError:
        return None


def last_commit_time(d):
    r = subprocess.run(['git', 'log', '-1', '--format=%ct'], capture_output=True, text=True, cwd=d)
    try:
        return int((r.stdout or '0').strip() or 0)
    except ValueError:
        return 0



def check_packages():
    """board.toml 的 [firmware].packages 每个 {tree} 路径必须真实存在。

    为什么加（2026-11-12 第三次同类事故）：board.toml 引用
    {tree}/drivers/DarwinBoot22，但构建树里没有那个目录，EDK2 报
    "error 000E: One Path in PACKAGES_PATH doesn't exist" 然后失败。
    文件在仓库里有，参与构建的副本里没有 —— 和 scripts/unixnu、
    drivers/PongPower 是同一个模式。
    """
    try:
        import tomllib
    except ImportError:
        return []
    p = os.path.join(REPO, 'board.toml')
    if not os.path.isfile(p):
        return []
    try:
        cfg = tomllib.load(open(p, 'rb'))
    except Exception as exc:
        return ['P board.toml 解析失败: %s' % exc]

    packages = cfg.get('firmware', {}).get('packages', [])
    if not packages:
        return []

    problems = []
    for item in packages:
        s = str(item)
        if '{tree}' not in s:
            continue
        rel = s.replace('{tree}/', '').replace('{tree}', '')
        target = os.path.join(BUILD + "/tree", rel)
        if not os.path.exists(target):
            problems.append('P packages 路径不存在: {tree}/%s（构建树缺这个目录/文件）' % rel)
    return problems

def check():
    problems = []

    # F1/F2 框架副本
    for sub in FRAMEWORK_DIRS:
        a = os.path.join(FW_REPO, sub)
        b = os.path.join(FW_COPY, sub)
        if not os.path.isdir(a) or not os.path.isdir(b):
            problems.append('F1 %s 一侧不存在（repo=%s copy=%s）' % (sub, os.path.isdir(a), os.path.isdir(b)))
            continue
        fa = sorted(f for f in os.listdir(a) if f.endswith('.py'))
        diff = []
        for f in fa:
            pa, pb = os.path.join(a, f), os.path.join(b, f)
            if not os.path.exists(pb) or sha(pa) != sha(pb):
                diff.append(f)
        if diff:
            problems.append('F1 %s 有 %d 个文件与仓库不一致: %s' % (sub, len(diff), diff[:5]))
        # mtime
        for f in fa:
            pa, pb = os.path.join(a, f), os.path.join(b, f)
            if os.path.exists(pb) and os.path.getmtime(pb) < os.path.getmtime(pa):
                problems.append('F2 %s/%s 副本比仓库旧' % (sub, f))
                break

    # F3 固件
    if not os.path.exists(FD):
        problems.append('F3 固件不存在: %s' % FD)
    else:
        fd_t = os.path.getmtime(FD)
        u_t = last_commit_time(UEFI)
        if fd_t < u_t:
            problems.append('F3 固件比 uefi-mondrian 最后一次提交旧（fd %.0f < commit %d）'
                            % (fd_t, u_t))

    # P 检查 packages 路径
    problems.extend(check_packages())

    # F4 构建产物存在
    for rel in ('kernel/kernel.macho', 'payload/payload.img'):
        p = os.path.join(BUILD, rel)
        if not os.path.exists(p):
            problems.append('F4 构建产物不存在: %s' % rel)

    if problems:
        print('  ❌ 构建新鲜度不足：')
        for p in problems:
            print('     %s' % p)
        print()
        print('     修法：python3 scripts/sync-device-input.py 同步框架副本；')
        print('     或 ./unixnu build firmware / kernel / payload 重建对应部分。')
        return 1

    print('  ✅ 构建新鲜度通过（框架副本一致、固件不旧、产物齐备）')
    return 0


def manifest():
    items = {
        'framework_unixnu_devicetree': sha(os.path.join(FW_COPY, 'scripts/unixnu/devicetree.py')),
        'kernel_macho': sha(os.path.join(BUILD, 'kernel/kernel.macho')),
        'payload_img': sha(os.path.join(BUILD, 'payload/payload.img')),
        'payload_json': json.load(open(os.path.join(BUILD, 'payload/payload.json')))
        if os.path.exists(os.path.join(BUILD, 'payload/payload.json')) else None,
        'firmware_fd': sha(FD),
        'series': [l.strip() for l in open(os.path.join(REPO, 'patches/xnu/series'), encoding='utf-8').read().split('\n') if l.strip()],
    }
    # 三个仓库的 HEAD
    for name, d in (('UniXNU-mondrian', REPO), ('UniXNU', FW_REPO), ('uefi-mondrian', UEFI)):
        r = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, cwd=d)
        items['head_' + name] = (r.stdout or '').strip()

    json.dump(items, open(MANIFEST, 'w'), indent=2, sort_keys=True)
    print('  ✅ 构建清单已写入 %s' % MANIFEST.replace(REPO, '.'))
    print('     kernel %s' % (items['kernel_macho'] or '?')[:16])
    print('     payload %s' % (items['payload_img'] or '?')[:16])
    print('     fd      %s' % (items['firmware_fd'] or '?')[:16])
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest', action='store_true')
    a = ap.parse_args()
    return manifest() if a.manifest else check()


if __name__ == '__main__':
    sys.exit(main())
