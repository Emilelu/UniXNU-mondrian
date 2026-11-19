#!/usr/bin/env python3
"""check-doc-citations.py — 文档里的 file:line 引用必须指向真实存在的文件与行

解决的问题（2026-11-17 移植疏漏审计 §5，docs/audits/PORTING-GAP-AUDIT-2026-11-16.md）：
文档用 `drivers/PongWifi/PongWifiPlatform.cpp:646` 这种写法当证据，但没有任何门禁
检查被引用的文件还在不在、行号还在不在范围内。审计实测 2,390 处 repo 路径引用中，
303 个目标在本仓库不存在、18 处行号越过文件末尾——读者无法分辨哪些证据已经失效。

判据：
  1. 目标文件必须存在（相对仓库根解析）；
  2. 带 :行号 的引用，行号不得超过该文件行数（范围 12-34 取上界）。
现存的历史欠账（多数是 UniXNU 框架仓 / sheng 仓的路径被当成 repo-local 引用）
写在 docs/engineering/DOC-CITATIONS-BASELINE.toml 里；基线内的放行，基线之外
新增一处就 FAIL。修好一条后跑 --update-baseline 收紧基线。

用法：
  python3 scripts/check-doc-citations.py                # 门禁
  python3 scripts/check-doc-citations.py --update-baseline
  python3 scripts/check-doc-citations.py --list         # 打印基线内容与新增问题
"""
import io
import os
import re
import sys

try:
    import tomllib
except ImportError:  # pragma: no cover - python < 3.11
    import tomli as tomllib

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE = os.path.join(REPO, 'docs', 'engineering', 'DOC-CITATIONS-BASELINE.toml')

PREFIXES = (
    'docs/research/', 'docs/engineering/', 'docs/plans/', 'docs/audits/',
    'docs/state/', 'docs/archive/', 'docs/ops/', 'docs/proposals/',
    'docs/reference/', 'patches/', 'drivers/', 'scripts/', 'configs/',
    'dts/', 'package/', 'blobs/', 'kits/',
)
EXACT = ('board.toml', 'porting.toml', 'docs/INDEX.md')
LOCAL_PREFIX = PREFIXES + EXACT

CITE_RE = re.compile(
    # `foo:drivers/x.cpp` 是别的仓库里的路径（pong:/zizhan:/mzyxsl: 等），不是本仓的
    r'(?<![\w/.-])(?<!:)('
    r'(?:docs|drivers|patches|scripts|configs|dts|package|blobs|kits)'
    r'/[A-Za-z0-9_./@+-]+?\.(?:md|py|cpp|cc|h|hpp|sh|c|toml|patch|json|plist|'
    r'txt|yml|yaml|dylib|xml|dtb|dtsi|inc|s)'
    r'|board\.toml|porting\.toml'
    r')(?::(\d+)(?:-(\d+))?)?')

SKIP_LINE = re.compile(r'^\s*(?:\`\`\`|\||\s*>)')


def doc_files():
    out = []
    docs = os.path.join(REPO, 'docs')
    for base, _dirs, names in os.walk(docs):
        for n in sorted(names):
            if n.endswith('.md'):
                out.append(os.path.join(base, n))
    for n in ('README.md', 'README_EN.md', 'AGENTS.md', 'CREDITS.md'):
        p = os.path.join(REPO, n)
        if os.path.isfile(p):
            out.append(p)
    return out


_line_cache = {}


def line_count(path):
    if path not in _line_cache:
        try:
            with io.open(path, encoding='utf-8', errors='ignore') as fh:
                _line_cache[path] = sum(1 for _ in fh)
        except OSError:
            _line_cache[path] = None
    return _line_cache[path]


def scan():
    """返回 (total, missing{target: [sites]}, overflow{'target|line': [sites]})"""
    total = 0
    missing = {}
    overflow = {}
    for f in doc_files():
        rel = os.path.relpath(f, REPO).replace(os.sep, '/')
        with io.open(f, encoding='utf-8', errors='ignore') as fh:
            for i, line in enumerate(fh, 1):
                if line.lstrip().startswith('```'):
                    continue
                for m in CITE_RE.finditer(line):
                    target = m.group(1)
                    if not target.startswith(LOCAL_PREFIX):
                        continue
                    total += 1
                    ap = os.path.join(REPO, target)
                    if not os.path.exists(ap):
                        missing.setdefault(target, []).append('%s:%d' % (rel, i))
                        continue
                    if not os.path.isfile(ap):
                        continue
                    hi = m.group(3) or m.group(2)
                    if not hi:
                        continue
                    n = line_count(ap)
                    if n is None:
                        continue
                    if int(hi) > n:
                        key = '%s|%s' % (target, hi)
                        overflow.setdefault(key, []).append(
                            '%s:%d (file has %d lines)' % (rel, i, n))
    return total, missing, overflow


def load_baseline():
    if not os.path.isfile(BASELINE):
        return [], []
    with open(BASELINE, 'rb') as fh:
        data = tomllib.load(fh)
    return (list(data.get('allowed_missing_targets', [])),
            list(data.get('allowed_line_overflow', [])))


def write_baseline(missing, overflow):
    def dump(items):
        return '\n'.join('  "%s",' % x for x in items)

    body = (
        '# check-doc-citations.py 的基线（自动生成，不要手改）\n'
        '#\n'
        '# 由来：2026-11-17 移植疏漏审计（docs/audits/PORTING-GAP-AUDIT-2026-11-16.md §5）\n'
        '# 实测文档里的 repo 路径引用大量指向框架仓 / sheng 仓 / 已搬走的研究文件，\n'
        '# 一次性修不完。这里把「今天已经存在」的欠账冻结，新增一处就 FAIL。\n'
        '# 修好一条后跑：python3 scripts/check-doc-citations.py --update-baseline\n'
        '#\n'
        '# allowed_missing_targets: 目标文件在本仓库不存在（相对仓库根）\n'
        '# allowed_line_overflow:   目标存在但行号越界，写成 "目标|行号"\n'
        '\n'
        'allowed_missing_targets = [\n%s\n]\n'
        '\n'
        'allowed_line_overflow = [\n%s\n]\n'
    ) % (dump(sorted(missing)), dump(sorted(overflow)))
    with io.open(BASELINE, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(body)


def main(argv):
    update = '--update-baseline' in argv
    listing = '--list' in argv
    total, missing, overflow = scan()

    if update:
        write_baseline(missing, overflow)
        print('基线已写入 %s' % os.path.relpath(BASELINE, REPO))
        print('  缺失目标 %d 个 / 行号越界 %d 个 / 引用 %d 处'
              % (len(missing), len(overflow), total))
        return 0

    allowed_missing, allowed_overflow = load_baseline()
    allowed_missing = set(allowed_missing)
    allowed_overflow = set(allowed_overflow)

    new_missing = {k: v for k, v in missing.items() if k not in allowed_missing}
    new_overflow = {k: v for k, v in overflow.items() if k not in allowed_overflow}
    fixed = (allowed_missing - set(missing)) | (allowed_overflow - set(overflow))

    total_sites = sum(len(v) for v in missing.values()) + sum(
        len(v) for v in overflow.values())

    print('  检查 %d 处 repo 路径引用' % total)
    print('  不在本仓库的目标 %d 个（基线放行 %d 个）'
          % (len(missing), len(missing) - len(new_missing)))
    print('  行号越界 %d 个（基线放行 %d 个）'
          % (len(overflow), len(overflow) - len(new_overflow)))
    if fixed:
        print('  基线里已有 %d 项被修好，可跑 --update-baseline 收紧' % len(fixed))

    if listing:
        for k in sorted(new_missing):
            print('    NEW missing: %s  <- %s' % (k, ', '.join(new_missing[k][:3])))
        for k in sorted(new_overflow):
            print('    NEW overflow: %s  <- %s' % (k, ', '.join(new_overflow[k][:3])))

    problems = []
    for k, sites in sorted(new_missing.items()):
        problems.append('引用目标不存在: %s（%s）' % (k, ', '.join(sites[:2])))
    for k, sites in sorted(new_overflow.items()):
        problems.append('行号越界: %s（%s）' % (k, ', '.join(sites[:2])))

    if problems:
        print('  新增问题 %d 处:' % len(problems))
        for p in problems[:15]:
            print('    - %s' % p)
        return 1
    print('  结论: ✅ 所有 repo 路径引用都在基线之内（基线共 %d 条）'
          % (len(allowed_missing) + len(allowed_overflow)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
