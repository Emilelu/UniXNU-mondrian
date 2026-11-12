#!/usr/bin/env python3
"""Subagent 交付物门禁：调研必须落库，且由它派生的改动必须真的在树上。

动机（P-150）：只检查「文件写了」不够。写完之后被忘掉的情况在这个项目里
发生过四次 —— 调研结论在文档里躺着，改动一行没做。所以每条记录带一句
产出断言，门禁去验证它。断言不成立就是失败。

断言语法：
  file:<path>                     文件存在且 >0 字节
  git:<path>                      文件被 git 跟踪
  grep:<path>:<needle>            文件里含这行子串
  series:<patch-name>             patches/xnu/series 里有这条
  exists:<glob>                   glob 至少命中一个文件

用法：
  python3 scripts/check-subagent-ledger.py
  python3 scripts/check-subagent-ledger.py --add SA-04 "任务" <落库文件> <产出断言>
  python3 scripts/check-subagent-ledger.py --land SA-04 <sha>
"""
import argparse
import datetime
import glob
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(REPO, 'docs', 'research', 'SUBAGENT-DELIVERABLES.md')

MAX_AGE_HOURS = 6
MIN_BYTES = 400


def parse(text):
    rows = []
    for line in text.split('\n'):
        s = line.strip()
        if not s.startswith('|') or s.startswith('|---') or '落库文件' in s:
            continue
        cells = [c.strip() for c in s.strip('|').split('|')]
        if len(cells) < 7:
            continue
        if not re.match(r'^SA-\d+$', cells[0]):
            continue
        rows.append({
            'id': cells[0], 'task': cells[1], 'dispatched': cells[2],
            'file': cells[3].strip('`'), 'assert': cells[4].strip('`'),
            'status': cells[5], 'commit': cells[6],
        })
    return rows


def eval_assert(expr):
    """返回 (ok, detail)。"""
    if ':' not in expr:
        return False, '断言格式无效: %r' % expr
    kind, rest = expr.split(':', 1)

    if kind == 'file':
        p = os.path.join(REPO, rest)
        if not os.path.isfile(p):
            return False, '文件不存在: %s' % rest
        n = os.path.getsize(p)
        return (n > 0), '文件 %s %d 字节' % (rest, n)

    if kind == 'git':
        r = subprocess.run(['git', 'ls-files', '--error-unmatch', rest],
                           capture_output=True, text=True, cwd=REPO)
        return (r.returncode == 0), ('已被 git 跟踪' if r.returncode == 0 else '未被 git 跟踪: %s' % rest)

    if kind == 'grep':
        if ':' not in rest:
            return False, 'grep 断言需要 path:needle'
        path, needle = rest.split(':', 1)
        p = os.path.join(REPO, path)
        if not os.path.isfile(p):
            return False, '文件不存在: %s' % path
        t = open(p, encoding='utf-8', errors='ignore').read()
        return (needle in t), ('%s 含 %r' % (path, needle) if needle in t
                               else '%s 不含 %r' % (path, needle))

    if kind == 'series':
        p = os.path.join(REPO, 'patches', 'xnu', 'series')
        if not os.path.isfile(p):
            return False, 'series 不存在'
        names = [l.strip() for l in open(p, encoding='utf-8').read().split('\n') if l.strip()]
        return (rest in names), ('series 含 %s' % rest if rest in names else 'series 不含 %s' % rest)

    if kind == 'exists':
        hits = glob.glob(os.path.join(REPO, rest))
        return (len(hits) > 0), ('命中 %d 个' % len(hits) if hits else '无匹配: %s' % rest)

    return False, '未知断言类型 %r' % kind


def check():
    if not os.path.isfile(LEDGER):
        print('  ❌ 台账不存在: docs/research/SUBAGENT-DELIVERABLES.md')
        return 1

    rows = parse(open(LEDGER, encoding='utf-8').read())
    if not rows:
        print('  ✅ 台账为空（无派出记录）')
        return 0

    problems, warns = [], []
    now = datetime.datetime.now()

    for r in rows:
        if r['status'] == 'running':
            m = re.search(r'(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2})', r['dispatched'])
            if m:
                t = datetime.datetime.strptime('%s %s:%s' % m.groups(), '%Y-%m-%d %H:%M')
                age = (now - t).total_seconds() / 3600.0
                if age > MAX_AGE_HOURS:
                    problems.append('%s 派发 %.1f 小时仍未落库（%s）→ 写进 %s'
                                    % (r['id'], age, r['task'], r['file']))
        elif r['status'] == 'landed':
            p = os.path.join(REPO, r['file'])
            if not os.path.isfile(p):
                problems.append('%s 标记 landed 但落库文件不存在: %s' % (r['id'], r['file']))
            elif os.path.getsize(p) < MIN_BYTES:
                problems.append('%s 落库文件仅 %d 字节，可能只是占位: %s'
                                % (r['id'], os.path.getsize(p), r['file']))
            if not r['commit'] or r['commit'] == '—':
                problems.append('%s 标记 landed 但没填落库提交' % r['id'])
        else:
            problems.append('%s 状态非法: %r' % (r['id'], r['status']))

        # 断言始终检查 —— running 阶段也查，好让「该做的改动还没做」尽早可见
        if r['assert'] and r['assert'] != '—':
            ok, detail = eval_assert(r['assert'])
            if not ok:
                if r['status'] == 'landed':
                    problems.append('%s 产出断言不成立 —— %s' % (r['id'], detail))
                else:
                    warns.append('%s 产出断言尚未成立（还在进行中）—— %s' % (r['id'], detail))

    for w in warns:
        print('  ⚠️  %s' % w)

    if problems:
        print('  ❌ Subagent 交付物未闭环：')
        for p in problems:
            print('     %s' % p)
        print()
        print('     规则（铁则 8）：落库不够，由它派生的改动必须真的在树上。')
        print('     断言写不出成立的结果 → 要么把改动做完，要么把这条记录删掉。')
        return 1

    landed = sum(1 for r in rows if r['status'] == 'landed')
    running = len(rows) - landed
    print('  ✅ Subagent 台账通过（%d 落库并应用 / %d 进行中）' % (landed, running))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--add', nargs=4, metavar=('ID', 'TASK', 'FILE', 'ASSERT'))
    ap.add_argument('--land', nargs=2, metavar=('ID', 'SHA'))
    a = ap.parse_args()

    if not a.add and not a.land:
        return check()

    text = open(LEDGER, encoding='utf-8').read()

    if a.add:
        ident, task, path, expr = a.add
        stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        row = '| %s | %s | %s | `%s` | `%s` | running | — |' % (ident, task, stamp, path, expr)
        lines = text.split('\n')
        last = None
        for i, l in enumerate(lines):
            if re.match(r'^\|\s*SA-\d+', l.strip()):
                last = i
        if last is None:
            lines.append(row)
        else:
            lines.insert(last + 1, row)
        open(LEDGER, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines))
        print('  ✅ 已登记 %s（断言 %s）' % (ident, expr))
        return 0

    ident, sha = a.land
    pat = re.compile(r'(\|\s*%s\s*\|[^\n]*?\|\s*)running(\s*\|\s*)—(\s*\|)' % re.escape(ident))
    new = pat.sub(lambda m: m.group(1) + 'landed' + m.group(2) + sha + m.group(3), text)
    if new == text:
        print('  ⚠️ 没匹配到 %s 的 running 行' % ident)
        return 1
    open(LEDGER, 'w', encoding='utf-8', newline='\n').write(new)
    print('  ✅ %s 标记 landed (%s)' % (ident, sha))
    return 0


if __name__ == '__main__':
    sys.exit(main())
