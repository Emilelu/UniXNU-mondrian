#!/usr/bin/env python3
"""check-readme.py — README must track STATUS and the strict-build gates (★36 / HR-71)

Why this exists (P-205): `check-docs.py` verifies links, INDEX coverage and the
eight-step markers, but three classes of README drift sailed through it:

  * dates      — README said "2026-11-12" while STATUS said "2026-11-14";
  * counts     — the README named "四个检查" / ★1-★35 / P-01-P-130 while the
                 strict build embedded nine checks, HARD-RULES reached ★37 and
                 PITFALLS reached P-204;
  * named sets — the gate table listed research-gate/porting-gate, neither of
                 which build-strict.sh runs, and omitted everything it does run.

A named list in prose drifts the moment reality changes; only a computed
reconciliation keeps it honest. This script checks:

  1. bilingual mutual links (README <-> README_EN);
  2. date parity: README 最后更新 >= STATUS 本轮更新时间, EN date == ZH date;
  3. range claims: the ★1-★N / P-01-P-M written in both READMEs equal the
     highest ★N / P-M headings actually present in HARD-RULES.md / PITFALLS.md;
  4. gate table: every script between the GATE-TABLE markers exists, the ZH and
     EN tables name the same set, and the set contains every gate embedded in
     build-strict.sh between the gate-table markers (so adding a gate without
     updating the READMEs fails);
  5. eight-step table: the EIGHT-STEP-TABLE block in both READMEs equals what
     render-eight-step-table.py would render from EIGHT-STEPS.toml (so a merge
     that adds a [hardware.*] line without regenerating the tables fails).

Usage: python3 scripts/check-readme.py   (exit 0 = consistent)
"""
import importlib.util
import io
import os
import argparse
import re
import sys
from datetime import date
from pathlib import Path

REPO = Path(os.environ.get('K60_REPO') or Path(__file__).resolve().parents[1])
README = REPO / 'README.md'
README_EN = REPO / 'README_EN.md'
STATUS = REPO / 'docs' / 'engineering' / 'STATUS.md'
HARD_RULES = REPO / 'docs' / 'engineering' / 'HARD-RULES.md'
PITFALLS = REPO / 'docs' / 'engineering' / 'PITFALLS.md'
BUILD_STRICT = REPO / 'scripts' / 'build-strict.sh'
EIGHT_STEPS = REPO / 'docs' / 'research' / 'EIGHT-STEPS.toml'

GATE_BEGIN = '<!-- GATE-TABLE:BEGIN -->'
GATE_END = '<!-- GATE-TABLE:END -->'
BASH_BEGIN = '# --- gate-table:BEGIN ---'
BASH_END = '# --- gate-table:END ---'
TABLE_BEGIN = 'EIGHT-STEP-TABLE:BEGIN'
TABLE_END = 'EIGHT-STEP-TABLE:END'

DATE_RE = re.compile(r'(20\d{2})-(\d{2})-(\d{2})')


def read(path):
    return io.open(path, encoding='utf-8', errors='ignore').read()


def _date_from(line):
    m = DATE_RE.search(line)
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def _find_line(text, needle, what):
    for ln in text.splitlines():
        if needle in ln:
            return ln
    return ''


def check_links():
    """Both files exist and link to each other."""
    problems = []
    for path in (README, README_EN):
        if not path.exists():
            problems.append('%s 不存在' % path.name)
    if not problems:
        zh = read(README)
        en = read(README_EN)
        if '[English](README_EN.md)' not in zh:
            problems.append('README.md 缺少 [English](README_EN.md) 链接')
        if '[中文版](README.md)' not in en:
            problems.append('README_EN.md 缺少 [中文版](README.md) 链接')
    return problems


def check_dates():
    """README date >= STATUS date; EN date == ZH date."""
    problems = []
    if README.exists() and STATUS.exists():
        zh = _find_line(read(README), '最后更新', 'README date')
        st = _find_line(read(STATUS), '本轮更新时间', 'STATUS date')
        d_zh, d_st = _date_from(zh), _date_from(st)
        if d_zh is None:
            problems.append('README.md 的「最后更新」行没有 YYYY-MM-DD 日期')
        elif d_st is None:
            problems.append('STATUS.md 的「本轮更新时间」行没有 YYYY-MM-DD 日期')
        else:
            if d_zh < d_st:
                problems.append('README 最后更新 %s 早于 STATUS 本轮更新时间 %s' % (d_zh, d_st))
            if README_EN.exists():
                en = _find_line(read(README_EN), 'Last updated', 'README_EN date')
                d_en = _date_from(en)
                if d_en is None:
                    problems.append('README_EN.md 的 Last updated 行没有 YYYY-MM-DD 日期')
                elif d_en != d_zh:
                    problems.append('README_EN 日期 %s != README 日期 %s' % (d_en, d_zh))
    return problems


def _max_heading(text, prefix_re):
    return max((int(m.group(1)) for m in prefix_re.finditer(text)), default=0)


def _range_claim(text, prefix_re, label):
    m = prefix_re.search(text)
    return int(m.group(1)) if m else None


def check_ranges(fix=False):
    """The ★1-★N / P-01-P-M claims equal the real highest headings.

    With fix=True the claim is rewritten instead of reported: the numbers are
    owned by HARD-RULES.md and PITFALLS.md, and a human retyping them is what
    P-259 was about.
    """
    problems = []
    if not (README.exists() and HARD_RULES.exists() and PITFALLS.exists()):
        return problems
    star_re = re.compile(r'^## ★(\d+)', re.M)
    pit_re = re.compile(r'^## P-(\d+)', re.M)
    actual_star = _max_heading(read(HARD_RULES), star_re)
    actual_pit = _max_heading(read(PITFALLS), pit_re)
    texts = {'README.md': read(README), 'README_EN.md': read(README_EN)}
    claims = [
        ('README.md', r'铁则 ★1–★(\d+)', actual_star, 'HARD-RULES'),
        ('README.md', r'坑记录 P-01–P-(\d+)', actual_pit, 'PITFALLS'),
        ('README_EN.md', r'Hard rules ★1–★(\d+)', actual_star, 'HARD-RULES'),
        ('README_EN.md', r'Pitfall log P-01–P-(\d+)', actual_pit, 'PITFALLS'),
    ]
    fixed = False
    for fname, pat, actual, doc in claims:
        text = texts[fname]
        m = re.compile(pat).search(text)
        if m is None:
            problems.append('%s 缺少 %s 的编号范围声明' % (fname, doc))
            continue
        if int(m.group(1)) == actual:
            continue
        replacement = m.group(0)[:m.start(1) - m.start(0)] + str(actual)
        if fix:
            texts[fname] = text[:m.start(0)] + replacement + text[m.end(0):]
            print('fixed %s: %s -> %s (%s.md 实际最大号 %s)'
                  % (fname, m.group(0), replacement, doc, actual))
            fixed = True
        else:
            problems.append('%s 声明 %s，但 %s.md 实际最大号是 %s'
                            % (fname, m.group(0), doc, actual))
    if fix and fixed:
        for fname, text in texts.items():
            path = REPO / fname
            if path.read_text() != text:
                path.write_text(text)
    return problems


def _names_in_block(text, begin, end, what):
    names = set()
    for seg in text.split(begin)[1:]:
        body = seg.split(end)[0]
        names |= set(re.findall(r'scripts/([A-Za-z0-9_.-]+\.(?:py|sh))', body))
    return names


def check_gate_table():
    """The README gate tables exist, name real scripts, and cover build-strict's gates."""
    problems = []
    zh, en = read(README), read(README_EN)
    if GATE_BEGIN not in zh or GATE_END not in zh:
        problems.append('README.md 缺少门禁表标记 %s/%s' % (GATE_BEGIN, GATE_END))
    if GATE_BEGIN not in en or GATE_END not in en:
        problems.append('README_EN.md 缺少门禁表标记 %s/%s' % (GATE_BEGIN, GATE_END))
    zh_names = _names_in_block(zh, GATE_BEGIN, GATE_END, 'README')
    en_names = _names_in_block(en, GATE_BEGIN, GATE_END, 'README_EN')
    if len(zh_names) < 3:
        problems.append('README 门禁表里识别到的脚本少于 3 个（%r）' % sorted(zh_names))
    if zh_names != en_names:
        problems.append('中英门禁表脚本集不一致：zh-only=%r en-only=%r'
                        % (sorted(zh_names - en_names), sorted(en_names - zh_names)))
    for name in sorted(zh_names | en_names):
        if not (REPO / 'scripts' / name).exists():
            problems.append('门禁表点名 scripts/%s，但文件不存在' % name)
    strict = read(BUILD_STRICT)
    if BASH_BEGIN not in strict:
        problems.append('build-strict.sh 缺少门禁标记 %s' % BASH_BEGIN)
    else:
        bash_names = _names_in_block(strict, BASH_BEGIN, BASH_END, 'build-strict')
        missing = bash_names - zh_names
        if missing:
            problems.append('build-strict.sh 内嵌门禁 %r 没有出现在 README 门禁表里'
                            % sorted(missing))
    return problems


def check_eight_step_table():
    """The EIGHT-STEP-TABLE blocks equal the freshly rendered tables."""
    problems = []
    if not (EIGHT_STEPS.exists() and README.exists() and README_EN.exists()):
        return problems  # no ledger means nothing to reconcile
    # Load the renderer from the gate's own scripts dir and point its DATA at
    # the repo under test (fixtures in the self-test run on a tmpdir). The
    # renderer reads no file at import time, so overriding DATA after loading
    # is enough -- and it keeps K60_REPO untouched for the other checks.
    spec = importlib.util.spec_from_file_location(
        'k60_render_eight_step',
        Path(__file__).resolve().parent / 'render-eight-step-table.py')
    if spec is None or spec.loader is None:
        return ['scripts/render-eight-step-table.py 无法加载']
    renderer = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(renderer)
    except Exception as exc:  # noqa: BLE001 - a broken renderer is a failure
        return ['render-eight-step-table.py 加载失败: %s' % exc]
    renderer.DATA = str(EIGHT_STEPS)
    for lang, path in (('zh', README), ('en', README_EN)):
        text = read(path)
        if TABLE_BEGIN not in text or TABLE_END not in text:
            problems.append('%s 缺少八步表标记（%s/%s），请用 '
                            'render-eight-step-table.py --apply 生成'
                            % (path.name, TABLE_BEGIN, TABLE_END))
            continue
        block = text.split(TABLE_BEGIN)[1].split(TABLE_END)[0]
        try:
            rendered = renderer.render(lang)
        except Exception as exc:  # noqa: BLE001 - a broken ledger is a failure
            problems.append('EIGHT-STEPS.toml 渲染失败: %s' % exc)
            continue
        if rendered.strip() not in block:
            problems.append('%s 的八步表格与 EIGHT-STEPS.toml 不一致，请运行 '
                            'render-eight-step-table.py --apply' % path.name)
    return problems


def run_checks(repo=None, fix=False):
    global REPO, README, README_EN, STATUS, HARD_RULES, PITFALLS, BUILD_STRICT, EIGHT_STEPS
    if repo is not None:
        REPO = Path(repo)
        README = REPO / 'README.md'
        README_EN = REPO / 'README_EN.md'
        STATUS = REPO / 'docs' / 'engineering' / 'STATUS.md'
        HARD_RULES = REPO / 'docs' / 'engineering' / 'HARD-RULES.md'
        PITFALLS = REPO / 'docs' / 'engineering' / 'PITFALLS.md'
        BUILD_STRICT = REPO / 'scripts' / 'build-strict.sh'
        EIGHT_STEPS = REPO / 'docs' / 'research' / 'EIGHT-STEPS.toml'
    problems = []
    problems += check_links()
    problems += check_dates()
    problems += check_ranges(fix=fix)
    problems += check_gate_table()
    problems += check_eight_step_table()
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--fix', action='store_true',
                    help='rewrite the ★/P range claims from the actual headings')
    ap.add_argument('--repo', help='repository root (default: the one holding this script)')
    args = ap.parse_args()
    run_checks(repo=args.repo, fix=args.fix)
    problems = run_checks(repo=args.repo)
    if problems:
        for p in problems:
            print('❌ %s' % p)
        print('README 与现状不一致：%d 处。请更新 README.md / README_EN.md' % len(problems))
        sys.exit(1)
    print('✅ README 与 STATUS、HARD-RULES/PITFALLS 编号、build-strict 门禁、八步表全部一致')
    sys.exit(0)


if __name__ == '__main__':
    main()
