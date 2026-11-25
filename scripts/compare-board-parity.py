#!/usr/bin/env python3
"""Compare the effective board configuration of two device repositories.

Reads board.toml from each side, applies [os_overrides."<profile>"] when the
repository has one, and prints the set differences for the keys that decide
what the kernel is built from: component includes, kernel archives, kernel
arguments, prelink roots and the CONFIG_* keys of the defconfig.

Read-only: it never builds, writes or touches a tree.
"""
from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path


def load_board(repo: Path) -> dict:
    with (repo / 'board.toml').open('rb') as handle:
        return tomllib.load(handle)


def effective(board: dict, profile: str | None) -> dict:
    """Return the board sections with the OS override merged in."""
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


def defconfig_keys(repo: Path, name: str | None) -> dict[str, str]:
    if not name:
        return {}
    path = repo / 'configs' / name
    if not path.is_file():
        return {}
    keys: dict[str, str] = {}
    for line in path.read_text(errors='replace').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        if key.startswith('CONFIG_'):
            keys[key] = value
    return keys


def arg_keys(values: list[str]) -> set[str]:
    keys = set()
    for value in values:
        keys.add(value.split('=', 1)[0])
    return keys


def report(name: str, ours: set[str], theirs: set[str]) -> None:
    print(f'\n== {name}: ours={len(ours)} sheng={len(theirs)}')
    only_ours = sorted(ours - theirs)
    only_theirs = sorted(theirs - ours)
    if only_ours:
        print('  only ours   : ' + ', '.join(only_ours))
    if only_theirs:
        print('  only sheng  : ' + ', '.join(only_theirs))
    if not only_ours and not only_theirs:
        print('  identical')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--ours', required=True, type=Path)
    parser.add_argument('--theirs', required=True, type=Path)
    parser.add_argument('--profile', default=None)
    args = parser.parse_args()

    ours_board = load_board(args.ours)
    theirs_board = load_board(args.theirs)
    theirs_profile = theirs_board.get('board', {}).get('os_profile')
    ours_profiles = ours_board.get('os_overrides', {})
    # Use the reference's profile only when our board actually overrides it;
    # otherwise our own profile describes the configuration under test.
    profile = args.profile or (theirs_profile if theirs_profile in ours_profiles
                               else ours_board.get('board', {}).get('os_profile'))
    ours = effective(ours_board, profile)
    theirs = effective(theirs_board, None)

    report('components.include',
           set(ours['components'].get('include', [])),
           set(theirs['components'].get('include', [])))
    report('kernel.archives',
           set(ours['kernel'].get('archives', [])),
           set(theirs['kernel'].get('archives', [])))
    report('kernel_args (keys)',
           arg_keys(ours['payload'].get('kernel_args', [])),
           arg_keys(theirs['payload'].get('kernel_args', [])))
    report('kernel.prelink.roots',
           set(ours['kernel'].get('prelink', {}).get('roots', [])),
           set(theirs['kernel'].get('prelink', {}).get('roots', [])))

    ours_def = ours['kernel'].get('defconfig')
    theirs_def = theirs['kernel'].get('defconfig')
    ours_keys = defconfig_keys(args.ours, ours_def)
    theirs_keys = defconfig_keys(args.theirs, theirs_def)
    print(f'\n== defconfig: ours={ours_def} sheng={theirs_def}')
    for key in sorted(set(ours_keys) | set(theirs_keys)):
        left, right = ours_keys.get(key), theirs_keys.get(key)
        if left == right:
            continue
        print(f'  {key}: ours={left or "-"} sheng={right or "-"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
