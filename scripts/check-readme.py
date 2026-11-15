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


def check_ranges():
    """The ★1-★N / P-01-P-M claims equal the real highest headings."""
    problems = []
    if not (README.exists() and HARD_RULES.exists() and PITFALLS.exists()):
        return problems
    zh, en = read(README), read(README_EN)
    star_re = re.compile(r'^## ★(\d+)', re.M)
    pit_re = re.compile(r'^## P-(\d+)', re.M)
    actual_star = _max_heading(read(HARD_RULES), star_re)
    actual_pit = _max_heading(read(PITFALLS), pit_re)
    claims = [
        ('README.md', zh, r'铁则 ★1–★(\d+)', actual_star, 'HARD-RULES'),
        ('README.md', zh, r'坑记录 P-01–P-(\d+)', actual_pit, 'PITFALLS'),
        ('README_EN.md', en, r'Hard rules ★1–★(\d+)', actual_star, 'HARD-RULES'),
        ('README_EN.md', en, r'Pitfall log P-01–P-(\d+)', actual_pit, 'PITFALLS'),
    ]
    for fname, text, pat, actual, doc in claims:
        claimed = _range_claim(text, re.compile(pat), doc)
        if claimed is None:
            problems.append('%s 缺少 %s 的编号范围声明' % (fname, doc))
        elif claimed != actual:
            problems.append('%s 声明 %s，但 %s.md 实际最大号是 %s'
                            % (fname, re.search(pat, text).group(0), doc, actual))
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


def run_checks(repo=None):
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
    problems += check_ranges()
    problems += check_gate_table()
    problems += check_eight_step_table()
    return problems


def main():
    problems = run_checks()
    if problems:
        for p in problems:
            print('❌ %s' % p)
        print('README 与现状不一致：%d 处。请更新 README.md / README_EN.md' % len(problems))
        sys.exit(1)
    print('✅ README 与 STATUS、HARD-RULES/PITFALLS 编号、build-strict 门禁、八步表全部一致')
    sys.exit(0)


if __name__ == '__main__':
    main()
