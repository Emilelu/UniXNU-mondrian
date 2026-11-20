#!/usr/bin/env python3
"""check-audio27-eight-step.py — 音频八步记录的可执行检查

只读。它检查 docs/research/eight-step/audio-27.toml：
  - 恰好七步（same_model/official/decompile/wide/plan/deep/verify），没有 device；
  - 每步 done=true、recorded_at=YYYY-MM-DDTHH:MM:SS、evidence 是非空字符串数组；
  - 每条 evidence 至少有一个可解析的 file:line 引用（仓库、UniXNU、sheng、adsp、
    /mnt/e/k60-work/evidence、/mnt/e/k60-work/reports）；
  - official 至少一条 docs/zh 引用并带 § 章节；
  - wide.catalog_checked=true 且 catalog_result 足够长；
  - verify.local_verified=true 且 static_check/unit_test/artifact_check 非空。

不做构建，不碰设备。引用无法解析时点名文件、行号和来源。
"""
import io
import os
import re
import sys

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = os.path.join(ROOT, 'docs', 'research', 'eight-step', 'audio-27.toml')
STEPS = ['same_model', 'official', 'decompile', 'wide', 'plan', 'deep', 'verify']
LABEL = {
    'same_model': '① 同型', 'official': '② 官方', 'decompile': '③ 反编译',
    'wide': '④ 广域', 'plan': '⑤ 方案', 'deep': '⑥ 深挖', 'verify': '⑦ 核验',
}
BASES = {
    'UniXNU': '/mnt/e/hackios/UniXNU',
    'sheng': '/mnt/e/k60-work/UniXNU-sheng',
    'adsp': '/mnt/e/hackios/k60-audio-adsp',
    'repo': ROOT,
}
REF = re.compile(
    r'(?<![\w/])('
    r'/mnt/e/k60-work/(?:evidence|reports)/[^\s`"\'，。；）)\]]+'
    r'|(?:UniXNU|sheng|adsp|repo):[^\s`"\'，。；）)\]]+'
    r'|(?:docs|drivers|scripts|patches|configs|dts|tests)/[^\s`"\'，。；）)\]]+'
    r')'
)
LINE = re.compile(r'^(.*?):(\d+)(?:-(\d+))?(?=$|[^0-9])')
STAMP = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$')


def text(value):
    if isinstance(value, (list, tuple)):
        return '\n'.join(str(x) for x in value)
    return str(value) if value is not None else ''


def resolve(token):
    m = LINE.match(token)
    if not m:
        return None, 'no :line'
    path, start, end = m.group(1), int(m.group(2)), m.group(3)
    if not os.path.isabs(path):
        if path.startswith('UniXNU:'):
            path = os.path.join(BASES['UniXNU'], path[len('UniXNU:'):])
        elif path.startswith('sheng:'):
            path = os.path.join(BASES['sheng'], path[len('sheng:'):])
        elif path.startswith('adsp:'):
            path = os.path.join(BASES['adsp'], path[len('adsp:'):])
        elif path.startswith('repo:'):
            path = os.path.join(ROOT, path[len('repo:'):])
        elif path.startswith('docs/zh/'):
            path = os.path.join(BASES['UniXNU'], path)
        else:
            path = os.path.join(ROOT, path)
    path = os.path.normpath(path)
    if not os.path.isfile(path):
        return None, 'missing file'
    try:
        total = sum(1 for _ in io.open(path, encoding='utf-8', errors='replace'))
    except OSError as e:
        return None, 'unreadable: %s' % e
    if start < 1 or start > total:
        return None, 'line %d out of 1..%d' % (start, total)
    if end is not None and (int(end) < start or int(end) > total):
        return None, 'range %s-%s out of 1..%d' % (start, end, total)
    return path, None


def main():
    path = DEFAULT
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--help', '-h'):
            print('usage: check-audio27-eight-step.py [--data FILE]')
            return 0
        if a == '--data':
            if i + 1 >= len(argv):
                print('usage: check-audio27-eight-step.py [--data FILE]', file=sys.stderr)
                return 2
            path = argv[i + 1]
            i += 1
        elif a.startswith('--data='):
            path = a.split('=', 1)[1]
        else:
            print('unknown argument: %s' % a, file=sys.stderr)
            return 2
        i += 1

    if tomllib is None:
        print('AUDIO27 EIGHT-STEP FAILED: no tomllib/tomli', file=sys.stderr)
        return 1
    try:
        d = tomllib.load(open(path, 'rb'))
    except Exception as e:
        print('AUDIO27 EIGHT-STEP FAILED: %s: %s' % (path, e), file=sys.stderr)
        return 1

    problems = []
    hw = d.get('hardware', {}).get('audio')
    if not isinstance(hw, dict):
        print('AUDIO27 EIGHT-STEP FAILED: no [hardware.audio] in %s' % path, file=sys.stderr)
        return 1
    for p in hw.get('paths', []):
        if not os.path.exists(os.path.join(ROOT, p)):
            problems.append('%s: paths entry does not exist: %s' % (path, p))
    steps = hw.get('step', {})
    missing = [s for s in STEPS if s not in steps]
    if missing:
        problems.append('missing step(s): %s' % ', '.join(missing))
    extra = [s for s in steps if s not in STEPS]
    if extra:
        problems.append('unexpected step(s): %s' % ', '.join(extra))

    refs = []
    for st in STEPS:
        entry = steps.get(st)
        if not isinstance(entry, dict):
            continue
        label = '%s :: %s' % ('audio', LABEL[st])
        if entry.get('done') is not True:
            problems.append('%s is not done=true' % label)
        stamp = entry.get('recorded_at')
        if not isinstance(stamp, str) or not STAMP.match(stamp):
            problems.append('%s has no recorded_at=YYYY-MM-DDTHH:MM:SS' % label)
        ev = entry.get('evidence')
        if not isinstance(ev, list) or not ev:
            problems.append('%s evidence is not a non-empty list' % label)
            continue
        for n, item in enumerate(ev, 1):
            if not isinstance(item, str) or len(item.strip()) < 30:
                problems.append('%s evidence[%d] is shorter than 30 chars' % (label, n))
                continue
            found = []
            for token in REF.findall(item):
                token = token.rstrip('.,;:')
                resolved, why = resolve(token)
                if resolved:
                    found.append(resolved)
                else:
                    problems.append('%s evidence[%d]: %s (%s)' % (label, n, token, why))
            if not found:
                problems.append('%s evidence[%d] has no resolvable file:line' % (label, n))
            refs.extend(found)
        if st == 'official':
            joined = text(ev)
            if 'docs/zh/' not in joined or '§' not in joined:
                problems.append('%s needs a docs/zh page and a § section' % label)
        if st == 'wide':
            if entry.get('catalog_checked') is not True:
                problems.append('%s is not catalog_checked=true' % label)
            if len(text(entry.get('catalog_result'))) < 40:
                problems.append('%s catalog_result is shorter than 40 chars' % label)
        if st == 'verify':
            if entry.get('local_verified') is not True:
                problems.append('%s is not local_verified=true' % label)
            for kind in ('static_check', 'unit_test', 'artifact_check'):
                if not text(entry.get(kind)).strip():
                    problems.append('%s has no %s' % (label, kind))

    if problems:
        print('AUDIO27 EIGHT-STEP FAILED: %d problem(s)' % len(problems), file=sys.stderr)
        for p in problems[:20]:
            print('  - %s' % p, file=sys.stderr)
        return 1
    roots = sorted(set(os.path.dirname(r) for r in refs))
    print('AUDIO27 EIGHT-STEP OK: 7 steps, %d evidence reference(s) resolve, %d root(s), no device step'
          % (len(refs), len(roots)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
