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

REPOS = {
    'UniXNU-mondrian': os.path.join(WORK, 'references/yibiya-upstream'),
    'UniXNU':          os.path.join(WORK, 'references/yibiya-unixnu-upstream'),
    'uefi-mondrian':   os.path.join(WORK, 'references/yibiya-uefi-upstream'),
}

# 分支 -> (mirror repo key, git ref)
BRANCHES = [
    ('UniXNU-mondrian', 'main'),
    ('UniXNU-mondrian', 'fix/boot-v4-repack'),
    ('UniXNU-mondrian', 'fix/touch-gpu-bringup'),
    ('UniXNU-mondrian', 'fix/ui-startup-blob'),
    ('UniXNU-mondrian', 'fix/k60-measured-high-window'),
    ('UniXNU-mondrian', 'feat/first-frame-20261107'),
    ('UniXNU-mondrian', 'upstream-fix'),
    ('UniXNU-mondrian', 'chore/archive-darwin24-main-20261103'),
    ('UniXNU', 'main'),
    ('UniXNU', 'fix/k60-input-adt'),
    ('UniXNU', 'fix/ufs-data-payload'),
    ('UniXNU', 'feat/smp-0340'),
    ('uefi-mondrian', 'main'),
]

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
    for key, branch in BRANCHES:
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
            baseline[k] = head      # 首次：记基线，不报历史
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
        for f in files:
            r = subprocess.run(['git', 'show', '%s:%s' % (sha, f)], capture_output=True, cwd=d)
            if r.returncode != 0:
                skipped.append((f, 'show failed'))
                continue
            dst = os.path.join(REPO, f)
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


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--plan', action='store_true')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--commit', action='store_true')
    ap.add_argument('--only', default='')
    ap.add_argument('--no-fetch', action='store_true')
    ap.add_argument('--mark', action='store_true', help='只推进水位，不写文件')
    a = ap.parse_args()

    only = set(x.strip() for x in a.only.split(',') if x.strip()) or None
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
        body = '\n'.join('  %s %s/%s %s' % (sha[:9], k[:10], b[:20], s[:60])
                         for (k, b, sha, dt, s, _), _ in items[:30])
        msg = ('feat(upstream): pick %d commits from yibiya branches\n\n'
               'Applied by scripts/pick-upstream.py at %s. File-level extraction,\n'
               'because the two histories share no ancestor.\n\n%s'
               % (len(items), stamp, body))
        subprocess.run(['git', 'add', '-A'], cwd=REPO)
        subprocess.run(['git', '-c', 'user.name=Emilelu',
                        '-c', 'user.email=kimiuso@vip.qq.com',
                        'commit', '-q', '-m', msg], cwd=REPO)
        print('  已提交')

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
