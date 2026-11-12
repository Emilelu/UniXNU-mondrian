#!/usr/bin/env python3
"""上游 pick 执行器：把 yibiya 分支上的新提交按文件提取进来。

为什么是文件级而不是 cherry-pick（2026-11-12 实测）：
  我们仓库和 yibiya 的三个仓库**没有共同祖先**（git merge-base 返回空）。
  cherry-pick 需要一个共同基线，这里没有。所以唯一可行的做法是
  对每个提交 `git show <sha>:<path>` 取出文件内容，写到我们的树上。

规则（铁则 6）：**默认全 pick**。只有两类跳过：
  - 纯文档 / 纯 CI（没有任何非 .md / 非 .github 文件）
  - 路径落在 SKIP_PATHS 里（构建产物、许可证等）

用法：
  python3 scripts/pick-upstream.py --plan            # 只列出会做什么
  python3 scripts/pick-upstream.py --apply           # 执行
  python3 scripts/pick-upstream.py --apply --commit  # 执行并提交
  python3 scripts/pick-upstream.py --apply --only boot,touch,gpu
"""
import argparse
import datetime
import io
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = '/mnt/e/k60-work'


# 三个目标树：每个上游仓库的文件要写到对应的本地仓库，而不是全塞进设备仓库。
# 2026-11-12 之前只写了设备仓库，导致 yibiya 对 UniXNU 框架和 uefi-mondrian
# 的提交从来没有进过我们的工作树 —— 镜像在跟，但 pick 没跟。
TARGETS = {
    'UniXNU-mondrian': '/mnt/e/hackios/UniXNU-mondrian',
    'UniXNU':          '/mnt/e/hackios/UniXNU',
    'uefi-mondrian':   '/mnt/e/hackios/uefi-mondrian',
}

REPOS = {
    'UniXNU-mondrian': os.path.join(WORK, 'references/yibiya-upstream'),
    'UniXNU':          os.path.join(WORK, 'references/yibiya-unixnu-upstream'),
    'uefi-mondrian':   os.path.join(WORK, 'references/yibiya-uefi-upstream'),
}

# 分支不再硬编码。yibiya 随时新建分支，写死的列表必然漏。
# discover_branches() 每次从镜像的 refs/remotes/origin/ 里枚举。


# 永不覆盖的路径（构建产物 / 许可证 / 我们自己的门禁与文档）
SKIP_PATHS = (
    'LICENSE', 'COPYING',
    'scripts/check-', 'scripts/tests/', 'scripts/watch-upstream.py',
    'scripts/pick-upstream.py', 'scripts/sync-device-input.py',
    'docs/research/', 'docs/engineering/', 'docs/proposals/',
    'AGENTS.md', 'README.md', 'README_EN.md', 'CREDITS.md',
    'docs/SCOPE-FREEZE.toml', '.gitignore',
)

DOC_EXT = ('.md', '.txt', '.rst')
CI_PREFIX = '.github/'

# 类别（用于 --only 过滤）
CATS = [
    ('boot',    ('patches/xnu/', 'configs/', 'board.toml')),
    ('touch',   ('pong-touch', 'touch.c', 'touch.h', 'goodix')),
    ('gpu',     ('PongAdreno', 'PongMetal', 'NativeMetal', 'adreno', 'metal')),
    ('battery', ('PongPower', 'Battmgr', 'PmicGlink', 'QcomGlink', 'Smem')),
    ('audio',   ('audio', 'Adsp', 'Gpr', 'Wcd', 'aw8')),
    ('input',   ('pong_input', 'pong_buttons', 'physical-keys')),
    ('ufs',     ('NativeUfs', 'RootCommands')),
    ('build',   ('scripts/', 'unixnu/')),
    ('adt',     ('devicetree', 'dts/', 'adt')),
]

SEEN = os.path.join(WORK, '.pick-upstream-seen.json')



def discover_branches():
    """枚举三个镜像当前所有分支。新分支自动纳入，不需要改代码。"""
    out = []
    for key, d in REPOS.items():
        if not os.path.isdir(os.path.join(d, '.git')):
            continue
        r = subprocess.run(['git', 'for-each-ref', '--format=%(refname:short)',
                            'refs/remotes/origin/'], capture_output=True, text=True, cwd=d)
        for ref in (r.stdout or '').strip().split('\n'):
            if not ref.strip() or ref.endswith('/HEAD'):
                continue
            out.append((key, ref.replace('origin/', '')))
    return sorted(out)


def git(d, *args):
    r = subprocess.run(['git'] + list(args), capture_output=True, text=True, cwd=d)
    return (r.stdout or '').strip()


def classify(path):
    for cat, pats in CATS:
        if any(p in path for p in pats):
            return cat
    return 'other'


def is_skippable(files):
    """纯文档或纯 CI 才跳过。"""
    if not files:
        return True
    real = [f for f in files if not (f.endswith(DOC_EXT) or f.startswith(CI_PREFIX))]
    return not real


def load_seen():
    import json
    if os.path.isfile(SEEN):
        try:
            return json.load(open(SEEN))
        except Exception:
            pass
    return {}


def save_seen(d):
    import json
    json.dump(d, open(SEEN, 'w'), indent=2, sort_keys=True)


def collect(fetch=True):
    """返回 (entry 列表, 基线字典)。首次运行时基线为当前 HEAD，不报历史。"""
    seen = load_seen()
    out = []
    baseline = {}
    for key, branch in discover_branches():
        d = REPOS[key]
        if not os.path.isdir(os.path.join(d, '.git')):
            continue
        if fetch:
            subprocess.run(['git', 'config', 'remote.origin.fetch',
                            '+refs/heads/*:refs/remotes/origin/*'], cwd=d)
            subprocess.run(['git', 'fetch', '--all', '--prune', '--quiet'],
                           cwd=d, capture_output=True)
        ref = 'origin/' + branch
        head = git(d, 'rev-parse', ref)
        if not head:
            continue
        k = '%s/%s' % (key, branch)
        old = seen.get(k)
        if old is None:
            # 新分支：按「文件收敛」而不是重放历史。
            # 重放历史会把 yibiya 的 Initial import 等 700+ 提交全部走一遍，
            # 而且会把我们删掉的文件复活。正确目标只有一个：让这个分支的
            # 尖端状态出现在我们的树里，只写真正不同的文件。
            baseline[k] = head
            target = TARGETS.get(key, REPO)
            differ = []
            r2 = subprocess.run(['git', 'ls-tree', '-r', '--name-only', ref],
                                capture_output=True, text=True, cwd=d)
            for f in (r2.stdout or '').split('\n'):
                f = f.strip()
                if not f:
                    continue
                if any(f == p or f.startswith(p) for p in SKIP_PATHS):
                    continue
                op = os.path.join(target, f)
                r3 = subprocess.run(['git', 'show', '%s:%s' % (ref, f)],
                                    capture_output=True, cwd=d)
                if r3.returncode != 0:
                    continue
                if os.path.isdir(op):
                    continue          # submodule
                if not os.path.exists(op):
                    differ.append(f)
                else:
                    try:
                        if open(op, 'rb').read() != r3.stdout:
                            differ.append(f)
                    except OSError:
                        differ.append(f)
            if differ:
                date = git(d, 'log', '-1', '--format=%ci', ref) or ''
                out.append((key, branch, head, date, 'sync branch tip: %d files' % len(differ), differ))
            continue
        if old == head:
            continue
        log = git(d, 'log', '--reverse', '--format=%H|%ci|%s', '%s..%s' % (old, head))
        for line in log.split('\n'):
            if not line.strip():
                continue
            p = line.split('|', 2)
            if len(p) < 3:
                continue
            sha, date, subj = p
            files = [f for f in git(d, 'show', '--name-only', '--format=', sha).split('\n') if f.strip()]
            out.append((key, branch, sha, date, subj, files))
    return out, baseline


def plan(entries, only=None):
    """返回 [(entry, files_to_write)]，已过滤。"""
    result = []
    for key, branch, sha, date, subj, files in entries:
        if is_skippable(files):
            continue
        keep = []
        for f in files:
            if any(f == p or f.startswith(p) for p in SKIP_PATHS):
                continue
            if only and classify(f) not in only:
                continue
            keep.append(f)
        if keep:
            result.append(((key, branch, sha, date, subj, files), keep))
    return result


def apply_plan(plan_items, do_commit=False):
    written, skipped = [], []
    for (key, branch, sha, date, subj, all_files), files in plan_items:
        d = REPOS[key]
        target = TARGETS.get(key, REPO)
        for f in files:
            # submodule（gitlink）不能按文件写：git show 只会返回子模块的 commit
            # SHA，写进去就把目录变成一个文本文件。这类改动要单独做
            # git submodule update，这里只记录。
            if os.path.isdir(os.path.join(target, f)) and not os.path.islink(os.path.join(target, f)):
                skipped.append((f, 'submodule，需 git submodule update'))
                continue
            r = subprocess.run(['git', 'show', '%s:%s' % (sha, f)], capture_output=True, cwd=d)
            if r.returncode != 0:
                skipped.append((f, 'show failed'))
                continue
            dst = os.path.join(target, f)
            os.makedirs(os.path.dirname(dst) or REPO, exist_ok=True)
            io.open(dst, 'wb').write(r.stdout)
            written.append((f, len(r.stdout), sha[:9]))
    return written, skipped



TRIAGE = os.path.join(REPO, 'docs', 'research', 'UPSTREAM-TRIAGE.toml')


def record_triage(entries, applied_shas):
    """把本轮抓到/应用的提交写进研判台账，并推进 watermark。

    两套水位必须同源，否则 pick 走了但台账没走，门禁就会一直报「未研判」。
    """
    if not os.path.isfile(TRIAGE):
        return
    t = io.open(TRIAGE, encoding='utf-8', errors='ignore').read()
    orig = t

    # 推进 watermark
    for key, branch, sha, date, subj, files in entries:
        repo_name = 'yibiya/' + key
        pat = re.compile(
            r'(\[\[branch\]\]\nrepo = "%s"\nmirror = "[^"]*"\nbranch = "%s"\nwatermark = ")([0-9a-f]+)(")'
            % (re.escape(repo_name), re.escape(branch)))
        def repl(m, sha=sha):
            return m.group(1) + sha + m.group(3)
        t = pat.sub(repl, t, count=1)

    # 为未在台账里的提交补记录
    existing = set(re.findall(r'sha = "([0-9a-f]+)"', t))
    blocks = []
    for key, branch, sha, date, subj, files in entries:
        short = sha[:9]
        if short in existing or sha in existing:
            continue
        doc_only = all(f.endswith(('.md', '.txt', '.rst')) or f.startswith('.github/') for f in files)
        verdict = 'not-applicable' if doc_only else 'picked'
        how = ('纯文档' if doc_only else '文件级提取（pick-upstream.py）')
        blocks.append(
            '\n[[commit]]\nsha = "%s"\nsubject = "%s"\nverdict = "%s"\nhow = "%s"\n'
            'reason = "自动记录：%s 分支 %s"\ndate = "%s"\n'
            % (short, subj.replace('"', "'")[:80], verdict, how, key, branch, date[:10]))

    if blocks:
        t = t.rstrip() + '\n' + ''.join(blocks)

    if t != orig:
        io.open(TRIAGE, 'w', encoding='utf-8', newline='\n').write(t)



def converge(target_key, mirror, target_tree, dry_run=True):
    """把镜像所有分支里「每个文件的最新版本」收敛进目标树。

    为什么不是按分支：最新代码散落在各个分支上。同一个文件可能在
    fix/touch-gpu-bringup 上最新，另一个在 fix/boot-v4-repack 上最新。
    按分支取任何单个分支都会漏。正确模型是逐文件取所有分支里的最新提交。

    返回 (写入列表, 跳过列表)。
    """
    # 1) 收集所有分支的 ref
    r = subprocess.run(['git', 'for-each-ref', '--format=%(refname:short)',
                        'refs/remotes/origin/'], capture_output=True, text=True, cwd=mirror)
    refs = [x.strip() for x in (r.stdout or '').split('\n')
            if x.strip() and not x.endswith('/HEAD')]
    if not refs:
        return [], []

    # 2) 每个文件 -> (时间戳, ref, 路径)
    newest = {}
    for ref in refs:
        # 一次 log 拿到该分支上每个文件最近一次被改的时间，而不是每个文件跑一次 log。
        r2 = subprocess.run(['git', 'log', '--format=@%ct', '--name-only', ref],
                            capture_output=True, text=True, cwd=mirror)
        ts = 0
        for line in (r2.stdout or '').split('\n'):
            line = line.strip()
            if not line:
                continue
            if line.startswith('@'):
                try:
                    ts = int(line[1:])
                except ValueError:
                    ts = 0
                continue
            f = line
            if any(f == p or f.startswith(p) for p in SKIP_PATHS):
                continue
            cur = newest.get(f)
            if cur is None or ts > cur[0]:
                newest[f] = (ts, ref, f)

    # 3) 逐个比内容
    written, skipped = [], []
    for f, (ts, ref, path) in sorted(newest.items()):
        dst = os.path.join(target_tree, f)
        if os.path.isdir(dst):
            skipped.append((f, 'submodule'))
            continue
        r4 = subprocess.run(['git', 'show', '%s:%s' % (ref, path)], capture_output=True, cwd=mirror)
        if r4.returncode != 0:
            skipped.append((f, 'show failed'))
            continue
        if os.path.exists(dst):
            try:
                if open(dst, 'rb').read() == r4.stdout:
                    continue
            except OSError:
                pass
        if not dry_run:
            os.makedirs(os.path.dirname(dst) or target_tree, exist_ok=True)
            io.open(dst, 'wb').write(r4.stdout)
        written.append((f, len(r4.stdout), ref.replace('origin/', '')[:24]))
    return written, skipped


def main_converge(dry_run):
    total = 0
    for key, mirror in REPOS.items():
        target = TARGETS.get(key)
        if not target or not os.path.isdir(os.path.join(mirror, '.git')):
            continue
        written, skipped = converge(key, mirror, target, dry_run=dry_run)
        if not written and not skipped:
            continue
        print()
        print('  === %s -> %s ===' % (key, target))
        print('    %s %d 个文件' % ('待写入' if dry_run else '已写入', len(written)))
        for f, n, ref in written[:12]:
            print('      %-58s %7d  (%s)' % (f[:56], n, ref))
        if len(written) > 12:
            print('      ... 还有 %d' % (len(written) - 12))
        for f, why in skipped[:4]:
            print('      跳过 %-52s %s' % (f[:50], why))
        total += len(written)
    return total


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--plan', action='store_true')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--commit', action='store_true')
    ap.add_argument('--only', default='')
    ap.add_argument('--no-fetch', action='store_true')
    ap.add_argument('--mark', action='store_true', help='只推进水位，不写文件')
    ap.add_argument('--converge', action='store_true', help='所有分支逐文件最新版收敛')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    only = set(x.strip() for x in a.only.split(',') if x.strip()) or None
    if a.converge:
        n = main_converge(dry_run=a.dry_run or not a.apply)
        print()
        print('  合计 %d 个文件%s' % (n, '（dry-run）' if (a.dry_run or not a.apply) else ''))
        return 0
    entries, baseline = collect(fetch=not a.no_fetch)
    if baseline:
        seen0 = load_seen()
        seen0.update(baseline)
        save_seen(seen0)
        print('  首次运行：记录 %d 个分支的基线' % len(baseline))

    if not entries:
        print('  没有新提交')
        return 0

    items = plan(entries, only)
    print('  新提交 %d 个，其中需 pick %d 个' % (len(entries), len(items)))
    if not items:
        if a.mark:
            seen = load_seen()
            for key, branch, sha, date, subj, files in entries:
                seen['%s/%s' % (key, branch)] = sha
            save_seen(seen)
            print('  已推进水位')
        return 0

    if a.plan or not a.apply:
        for (key, branch, sha, date, subj, all_files), files in items:
            print()
            print('  %s  %s/%s  %s' % (sha[:9], key[:10], branch[:20], date[:16]))
            print('    %s' % subj[:88])
            for f in files[:8]:
                print('      %s' % f[:76])
            if len(files) > 8:
                print('      ... 还有 %d 个' % (len(files) - 8))
        return 0

    written, skipped = apply_plan(items, a.commit)
    print()
    print('  写入 %d 个文件' % len(written))
    for f, n, sha in written[:20]:
        print('    %-60s %7d B  (%s)' % (f[:58], n, sha))
    if skipped:
        print('  跳过 %d 个: %s' % (len(skipped), skipped[:4]))

    if a.commit:
        stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        # 按目标树分组提交 —— 三个树是独立的 git 仓库
        by_target = {}
        for (k, b, sha, dt, s, _), files in items:
            by_target.setdefault(k, []).append((sha, b, s, files))
        for key, group in by_target.items():
            target = TARGETS.get(key, REPO)
            body = '\n'.join('  %s %s %s' % (sha[:9], b[:22], subj[:60])
                             for sha, b, subj, _ in group[:30])
            msg = ('feat(upstream): pick %d commits from yibiya/%s\n\n'
                   'Applied by scripts/pick-upstream.py at %s. File-level extraction,\n'
                   'because the two histories share no ancestor.\n\n%s'
                   % (len(group), key, stamp, body))
            subprocess.run(['git', 'add', '-A'], cwd=target, capture_output=True)
            r = subprocess.run(['git', '-c', 'user.name=Emilelu',
                                '-c', 'user.email=kimiuso@vip.qq.com',
                                'commit', '-q', '-m', msg], cwd=target,
                               capture_output=True, text=True)
            status = '已提交' if r.returncode == 0 else ('无变化' if 'nothing to commit' in (r.stdout or '') else '失败')
            print('  %-18s %s' % (key, status))

    # 推进水位
    seen = load_seen()
    for key, branch, sha, date, subj, files in entries:
        seen['%s/%s' % (key, branch)] = sha
    save_seen(seen)
    record_triage(entries, [e[2] for e in entries])
    print('  水位已推进（研判台账已同步）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
