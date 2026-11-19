#!/usr/bin/env python3
"""P-162: every patch that changed must still be a valid diff.

A patch is a program: if `git apply --numstat` cannot parse it, the build dies
twelve minutes later with `corrupt patch at line N`, after the compiler has
already run. P-155 has now been seen in three shapes (hunk counts, trailing
newline, net-delete), and all three are caught by the same check.

Usage:
    python3 scripts/check-patch-apply.py            # patches changed vs HEAD
    python3 scripts/check-patch-apply.py --all      # every patch under patches/
    python3 scripts/check-patch-apply.py --base X   # compare against commit X
"""
import argparse
import subprocess
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(*args, check=False):
    return subprocess.run(
        ('git',) + args, cwd=ROOT, capture_output=True, text=True, check=check
    )


def changed_patches(base):
    out = git('diff', '--name-only', base, '--', 'patches/')
    paths = [p for p in out.stdout.splitlines() if p.endswith('.patch')]
    staged = git('diff', '--cached', '--name-only', base, '--', 'patches/')
    paths += [p for p in staged.stdout.splitlines() if p.endswith('.patch')]
    return sorted(set(paths))


def all_patches():
    paths = []
    for base, _dirs, files in os.walk(os.path.join(ROOT, 'patches')):
        for name in files:
            if name.endswith('.patch'):
                paths.append(os.path.relpath(os.path.join(base, name), ROOT))
    return sorted(paths)


def validate(path):
    res = git('apply', '--numstat', path)
    if res.returncode == 0:
        return None
    detail = (res.stderr or res.stdout).strip().splitlines()
    return detail[0] if detail else 'git apply --numstat failed'


def missing_from_series():
    """Patches a series names but that no longer exist.

    Folding a patch into the one that creates the same file deletes it; a series entry left
    behind then breaks a build after the compiler has run. This is the other half of P-155.
    """
    gone = []
    for base, _dirs, files in os.walk(os.path.join(ROOT, 'patches')):
        if 'series' not in files:
            continue
        series = os.path.join(base, 'series')
        with open(series, encoding='utf-8') as handle:
            for line in handle:
                name = line.strip()
                if not name or name.startswith('#'):
                    continue
                if not os.path.exists(os.path.join(base, name)):
                    gone.append(os.path.relpath(os.path.join(base, name), ROOT))
    return gone


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--all', action='store_true', help='check every patch')
    ap.add_argument('--base', default='HEAD', help='commit to diff against')
    args = ap.parse_args()

    paths = all_patches() if args.all else changed_patches(args.base)
    if not paths:
        print('✅ 没有改动过的补丁需要校验（P-162）')
        return 0

    bad = []
    absent = []
    for path in paths:
        if not os.path.exists(os.path.join(ROOT, path)):
            # A patch folded into the one that creates the file is deleted on purpose;
            # the series check below is what must not then point at it.
            absent.append(path)
            continue
        problem = validate(path)
        if problem:
            bad.append((path, problem))

    missing = missing_from_series()
    for path in missing:
        bad.append((path, 'listed in series but the file is gone'))

    if not bad:
        folded = f'，{len(absent)} 个已折入创建补丁' if absent else ''
        print(f'✅ {len(paths) - len(absent)} 个改动的补丁都能被 git apply 解析（P-162）{folded}')
        return 0

    print(f'❌ {len(bad)} 个补丁不是合法 diff，提交前必须修好（P-162）')
    for path, problem in bad:
        print(f'   - {path}: {problem}')
    print('   修法：用 scripts/recount_hunks.py 只重算 hunk 计数无效时，')
    print('   改用「新写一个独立补丁」而不是原地增删行（P-155 第三种形态）。')
    return 1


if __name__ == '__main__':
    sys.exit(main())
