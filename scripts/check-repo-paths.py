#!/usr/bin/env python3
"""check-repo-paths.py — scripts/ 里禁止硬编码检出路径（hard-39）。

为什么有这条规则
================
2026-11-14：usb / audio / refmine 三条线各自踩过同一个坑 —— 脚本把主检出的
绝对路径写死在源码里，于是在 worktree 里跑的时候改了 A 树、门禁看的却是 B 树。
三条线各打了一份补丁，补丁互不相同。现在统一成：

    REPO = Path(os.environ.get('K60_REPO') or Path(__file__).resolve().parents[1])

shell 脚本对应：

    REPO="${K60_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

不设 K60_REPO 时根就是脚本所在的检出，所以在主检出里跑与写死主检出时逐字相同；
在 worktree 里跑就用 worktree。

判据
====
* ERROR —— 本仓库的检出路径写死在代码里（UniXNU-mondrian，或 k60-* worktree）。
  它只能来自 K60_REPO 或 __file__。
* WARN  —— 兄弟检出（UniXNU / uefi-mondrian）的路径。它没法从本仓库根推出来，
  允许保留默认值，但必须一眼看见；--strict 时 WARN 也算失败。
* 放行 —— 注释、Python 的 docstring（module / class / def）、shell 注释行、
  行尾注释、heredoc 正文。文档必须能写「这里以前写死过」。

用法
====
    python3 scripts/check-repo-paths.py             # 查本仓库 scripts/
    python3 scripts/check-repo-paths.py --repo DIR  # 查另一个检出
    python3 scripts/check-repo-paths.py --strict    # WARN 也算失败
"""
from __future__ import annotations

import argparse
import ast
import io
import os
import re
import sys
import tokenize
from pathlib import Path

REPO = Path(os.environ.get('K60_REPO') or Path(__file__).resolve().parents[1])
SELF = Path(__file__).resolve()

NEWLINE = chr(10)
TAB = chr(9)
QUOTES = chr(34) + chr(39)
BACKSLASH = chr(92)

# 路径片段拼出来，免得本文件自己的正文撞上自己的规则。
_HACKIOS = 'hackios' + '/'
_SEP_RE = '[' + '/' + re.escape(BACKSLASH) + ']'
PATTERN = re.compile(
    r'(?i)(?:/mnt/[a-z]/' + _HACKIOS
    + r'|(?<![A-Za-z0-9_])/[a-z]/' + _HACKIOS
    + r'|[a-z]:' + _SEP_RE + 'hackios' + _SEP_RE + ')'
)
DEVICE_CHECKOUTS = ('UniXNU-mondrian',)
DEVICE_PREFIXES = ('k60-',)
HEREDOC = re.compile('<<-?[ ' + TAB + ']*[' + QUOTES + ']?([A-Za-z_][A-Za-z0-9_]*)')


def line_starts(text):
    """每一行第一个字符的字符偏移。"""
    starts = [0]
    for index, char in enumerate(text):
        if char == NEWLINE:
            starts.append(index + 1)
    return starts


def _offset(starts, row, col):
    if 0 < row <= len(starts):
        return starts[row - 1] + col
    return 0


def _byte_col_to_char(line, byte_col):
    """ast 的 col_offset 是 UTF-8 字节偏移，tokenize 用的是字符偏移。"""
    return len(line.encode('utf-8')[:byte_col].decode('utf-8', 'replace'))


def py_docstrings(text):
    """(行, 字符列) —— module / class / def 的第一条语句若是字符串。"""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    lines = text.splitlines()
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, 'body', [])
        if not body:
            continue
        first = body[0]
        value = getattr(first, 'value', None)
        if (isinstance(first, ast.Expr) and isinstance(value, ast.Constant)
                and isinstance(value.value, str)):
            line = lines[value.lineno - 1] if value.lineno - 1 < len(lines) else ''
            found.add((value.lineno, _byte_col_to_char(line, value.col_offset)))
    return found


def prose_spans_py(text):
    """注释与 docstring 的字符区间。"""
    starts = line_starts(text)
    docstrings = py_docstrings(text)
    spans = []
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return spans
    for token in tokens:
        if token.type == tokenize.COMMENT:
            spans.append((_offset(starts, *token.start), _offset(starts, *token.end)))
        elif token.type == tokenize.STRING and token.start in docstrings:
            spans.append((_offset(starts, *token.start), _offset(starts, *token.end)))
    return spans


def _comment_start(line):
    """行尾注释 '#' 的列号；引号里的 '#' 不算，没有就返回 None。"""
    single = double = False
    index = 0
    while index < len(line):
        char = line[index]
        if char == BACKSLASH and not single:
            index += 2
            continue
        if char == "'" and not double:
            single = not single
        elif char == chr(34) and not single:
            double = not double
        elif char == '#' and not single and not double:
            if index == 0 or line[index - 1] in ' ' + TAB + ';':
                return index
        index += 1
    return None


def prose_spans_sh(text):
    """shell 注释行、行尾注释、heredoc 正文的字符区间。"""
    starts = line_starts(text)
    spans = []
    heredoc = None
    for number, line in enumerate(text.splitlines(), start=1):
        begin = starts[number - 1]
        if heredoc is not None:
            spans.append((begin, begin + len(line)))
            if line.strip().strip(QUOTES) == heredoc:
                heredoc = None
            continue
        match = HEREDOC.search(line)
        if match:
            heredoc = match.group(1)
        if line.lstrip().startswith('#'):
            spans.append((begin, begin + len(line)))
            continue
        column = _comment_start(line)
        if column is not None:
            spans.append((begin + column, begin + len(line)))
    return spans


def checkout_name(text, end):
    match = re.match(r'[A-Za-z0-9._-]+', text[end:])
    return match.group(0) if match else ''


def classify(name):
    if name in DEVICE_CHECKOUTS or name.startswith(DEVICE_PREFIXES):
        return 'device'
    return 'sibling'


def _inside(position, spans):
    for begin, end in spans:
        if begin <= position < end:
            return True
    return False


def scan(scripts, root):
    files = 0
    errors = []
    warnings = []
    for path in sorted(scripts.rglob('*')):
        if not path.is_file() or path.resolve() == SELF:
            continue
        suffix = path.suffix.lower()
        if suffix == '.py':
            spans_of = prose_spans_py
        elif suffix in ('.sh', '.bash'):
            spans_of = prose_spans_sh
        else:
            continue
        files += 1
        text = path.read_text(encoding='utf-8', errors='replace')
        spans = spans_of(text)
        try:
            shown = path.resolve().relative_to(root)
        except ValueError:
            shown = path.resolve()
        for match in PATTERN.finditer(text):
            if _inside(match.start(), spans):
                continue
            name = checkout_name(text, match.end())
            line = text.count(NEWLINE, 0, match.start()) + 1
            snippet = text[match.start():match.end() + len(name)]
            if classify(name) == 'device':
                errors.append('%s:%d: hardcoded checkout path %s' % (shown, line, snippet))
            else:
                warnings.append('%s:%d: sibling checkout path %s' % (shown, line, snippet))
    return files, errors, warnings


def main(argv=None):
    parser = argparse.ArgumentParser(description='scripts/ 里禁止硬编码检出路径（hard-39）')
    parser.add_argument('--repo', help='检出的根目录（默认本脚本所在检出，或 K60_REPO）')
    parser.add_argument('--strict', action='store_true', help='WARN（兄弟检出）也算失败')
    args = parser.parse_args(argv)

    root = Path(args.repo).resolve() if args.repo else REPO
    scripts = root / 'scripts'
    if not scripts.is_dir():
        print('❌ 没有 scripts/ 目录: %s' % scripts)
        return 2

    files, errors, warnings = scan(scripts, root)
    for row in errors:
        print('ERROR %s' % row)
    for row in warnings:
        print('warn  %s' % row)
    failed = bool(errors) or (bool(warnings) and args.strict)
    print('%s repo-paths: %d file(s), %d error(s), %d warning(s) — %s%s'
          % ('❌' if failed else '✅', files, len(errors), len(warnings), root,
             ' (--strict)' if args.strict else ''))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
