#!/usr/bin/env python3
"""Refuse -enable_kprintf_spam on the 27 line.

`pexpert/arm/pe_kprintf.c:26-27` starts with both gates true, and in this
DEVELOPMENT build only `-enable_kprintf_spam` clears `disable_kprintf_output`
(P-308).  It is still forbidden: while `vc_initialize()` runs, `v_rows` is not
set yet, so the newline path computes `scrreg_bottom = 0 - 1` and the scroll
writes past the framebuffer mapping -- the panel goes black and the kernel
hangs without resetting (xNekom IOS27.md, commit c3c89df).

Stage-0 evidence comes from the direct framebuffer witnesses (0554/0556), which
never call kprintf.  A dedicated debug image may set K60_ALLOW_KPRINT_SPAM=1.

Usage:
    check-kprintf-enabled.py [--device .] [--image boot.img]
Exit 0 when the argument is absent (or explicitly allowed by the environment).
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys
import tomllib

MARKER = '-enable_kprintf_spam'
OS_RE = re.compile(r'(?:ios|ipados|macos)-27\.')


def effective_args(device: pathlib.Path) -> tuple[str, list[str]]:
    data = tomllib.loads((device / 'board.toml').read_text(encoding='utf-8'))
    profile = str(data.get('board', {}).get('os_profile', ''))
    overrides = data.get('os_overrides', {})
    section = overrides.get(profile, {}) if profile in overrides else {}
    payload = section.get('payload') or data.get('payload') or {}
    return profile, [str(a) for a in payload.get('kernel_args', [])]


def judge(profile: str, args: list[str]) -> list[str]:
    problems: list[str] = []
    if not OS_RE.search(profile):
        # A 16 build is DEBUG (MACHINE_CONFIGS=... PONG, KERNEL_CONFIGS=DEBUG) and
        # clears the flag unconditionally, so this rule has nothing to say there.
        return problems
    if MARKER in args and os.environ.get('K60_ALLOW_KPRINT_SPAM') != '1':
        problems.append(
            'kernel_args carries ' + MARKER + ': printing before v_rows exists makes the '
            'scroll write past the framebuffer mapping and the board hangs without resetting '
            '(xNekom IOS27.md c3c89df). Use the direct framebuffer witnesses; set '
            'K60_ALLOW_KPRINT_SPAM=1 only for a dedicated debug image.')
    return problems


def image_args(image: pathlib.Path) -> list[str] | None:
    """Read the payload's unixnu.toml argument list out of a boot image, if given."""
    import subprocess
    try:
        out = subprocess.run(['python3', str(pathlib.Path(__file__).with_name('check-image-args.py')),
                              '--image', str(image), '--print-args'], capture_output=True, text=True)
    except OSError:
        return None
    if out.returncode != 0:
        return None
    return out.stdout.split()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', default='.')
    parser.add_argument('--image')
    options = parser.parse_args(argv)

    profile, args = effective_args(pathlib.Path(options.device))
    if not OS_RE.search(profile):
        print(f'skip kprintf: {profile!r} is not a 27 profile (16 builds are DEBUG and clear the gate themselves)')
        return 0
    problems = judge(profile, args)
    if problems:
        for problem in problems:
            print('FAIL: ' + problem)
        return 1
    print(f'ok kprintf: {profile} does not carry {MARKER} ({len(args)} arguments)')
    if options.image:
        found = image_args(pathlib.Path(options.image))
        if found is None:
            print('note image: could not read the argument list; the board value was judged, not the image')
        elif MARKER not in found:
            print('FAIL: the image does not carry ' + MARKER + '; the board has it but the build did not')
            return 1
        else:
            print('ok image: the image carries ' + MARKER)
    return 0


if __name__ == '__main__':
    sys.exit(main())
