#!/usr/bin/env python3
"""Audit the kernel arguments that the reference board passes and we do not.

`compare-board-parity.py` answers "which keys differ".  This script answers the
next question, which is the only one that matters before copying a key over:
*does anything in our kernel read it?*  A key with no reader is not a gap; it is
a string the reference wastes bytes on.  A key with a reader is a real candidate
and the output names the file and line.

Read-only: it reads board.toml files and source files, and writes nothing.
"""
from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

def effective(board: dict, profile: str | None) -> dict:
    base = {
        'components': dict(board.get('components', {})),
        'kernel': dict(board.get('kernel', {})),
        'payload': dict(board.get('payload', {})),
    }
    if profile:
        override = board.get('os_overrides', {}).get(profile, {})
        for section in ('components', 'kernel', 'payload'):
            if section in override:
                base[section].update(override[section])
    return base


def arg_keys(values: list[str]) -> set[str]:
    return {value.split('=', 1)[0] for value in values}


PARSE = re.compile(r'PE_parse_boot_argn\s*\(\s*"([^"]+)"')
STRING = re.compile(r'"([A-Za-z0-9_.-]+)"')
SOURCE_SUFFIXES = {'.c', '.cc', '.cpp', '.h', '.hpp', '.m', '.mm'}


def load_board(repo: Path) -> dict:
    with (repo / 'board.toml').open('rb') as handle:
        return tomllib.load(handle)


def board_args(board: dict, profile: str | None) -> list[str]:
    section = effective(board, profile)['payload']
    values = section.get('kernel_args', [])
    if isinstance(values, str):
        return values.split()
    return list(values)


def index_tree(tree: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Return (parse sites, plain mentions) keyed by boot-arg name."""
    parses: dict[str, list[str]] = {}
    mentions: dict[str, list[str]] = {}
    for path in tree.rglob('*'):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        try:
            text = path.read_text(errors='ignore')
        except OSError:
            continue
        if 'boot_arg' not in text and 'boot-args' not in text:
            continue
        relative = str(path.relative_to(tree))
        for number, line in enumerate(text.splitlines(), start=1):
            for match in PARSE.finditer(line):
                parses.setdefault(match.group(1), []).append(f'{relative}:{number}')
            for match in STRING.finditer(line):
                mentions.setdefault(match.group(1), []).append(f'{relative}:{number}')
    return parses, mentions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--ours', required=True, help='our device repository')
    parser.add_argument('--theirs', required=True, help='reference device repository')
    parser.add_argument('--tree', required=True, help='assembled XNU source tree')
    parser.add_argument('--profile', default=None)
    args = parser.parse_args()

    ours = set(arg_keys(board_args(load_board(Path(args.ours)), args.profile)))
    theirs = set(arg_keys(board_args(load_board(Path(args.theirs)), args.profile)))
    candidates = sorted(theirs - ours)

    tree = Path(args.tree)
    if not tree.is_dir():
        print(f'ARGS: {tree} is not a directory')
        return 2
    parses, mentions = index_tree(tree)

    rows = []
    for key in candidates:
        sites = parses.get(key, [])
        if sites:
            verdict = 'reader'
        elif mentions.get(key):
            verdict = 'mention'
        else:
            verdict = 'absent'
        rows.append((verdict, key, sites or mentions.get(key, [])))

    order = {'reader': 0, 'mention': 1, 'absent': 2}
    rows.sort(key=lambda row: (order[row[0]], row[1]))

    print(f'ARGS candidates={len(candidates)} '
          f'reader={sum(1 for r in rows if r[0] == "reader")} '
          f'mention={sum(1 for r in rows if r[0] == "mention")} '
          f'absent={sum(1 for r in rows if r[0] == "absent")}')
    print()
    print('| verdict | key | first site |')
    print('|---|---|---|')
    for verdict, key, sites in rows:
        first = sites[0] if sites else '-'
        print(f'| {verdict} | `{key}` | `{first}` |')
    return 0


if __name__ == '__main__':
    sys.exit(main())
