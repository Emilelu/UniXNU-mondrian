#!/usr/bin/env python3
"""The kprintf flag and the print trap must travel together.

`pexpert/arm/pe_kprintf.c:26-27` starts with both print gates true, and this
DEVELOPMENT build only lets `-enable_kprintf_spam` clear `disable_kprintf_output`
(P-308).  Printing is therefore the only way to see kernel text -- but
`initialize_screen()` used to print before `v_rows` existed, so the newline path
computed `scrreg_bottom = 0 - 1` and the scroll wrote past the framebuffer
mapping: the panel went black and the board hung (xNekom IOS27.md, c3c89df).

`0557-k60-fb-print-after-rows.patch` removes that print and re-prints the same
geometry after `gc_initialize()`.  The two facts are one switch:

  * 0557 in the series and no flag  -> no text will ever appear (waste a boot)
  * flag without 0557               -> the pre-rows print hangs the board

Usage:
    check-kprintf-enabled.py [--device .] [--series PATH] [--image boot.img]
Exit 0 only when both halves are present (16 builds are skipped).
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys
import tomllib

MARKER = '-enable_kprintf_spam'
TRAP_FIX = '0557-k60-fb-print-after-rows.patch'
OS_RE = re.compile(r'(?:ios|ipados|macos)-27\.')
DEFAULT_SERIES = pathlib.Path(__file__).resolve().parent.parent / 'patches/xnu-12377/series'


def effective_args(device: pathlib.Path) -> tuple[str, list[str]]:
    data = tomllib.loads((device / 'board.toml').read_text(encoding='utf-8'))
    profile = str(data.get('board', {}).get('os_profile', ''))
    overrides = data.get('os_overrides', {})
    section = overrides.get(profile, {}) if profile in overrides else {}
    payload = section.get('payload') or data.get('payload') or {}
    return profile, [str(a) for a in payload.get('kernel_args', [])]


def series_has_trap_fix(path: pathlib.Path) -> bool:
    try:
        return TRAP_FIX in path.read_text(encoding='utf-8')
    except OSError:
        return False


def judge(profile: str, args: list[str], trap_fix: bool) -> list[str]:
    if not OS_RE.search(profile):
        return []
    carried = MARKER in args
    if carried and not trap_fix and os.environ.get('K60_ALLOW_KPRINT_SPAM') != '1':
        return ['kernel_args carries ' + MARKER + ' but the series has no ' + TRAP_FIX +
                ': the pre-rows print in initialize_screen() makes the scroll write past the '
                'framebuffer mapping and the board hangs without resetting (xNekom c3c89df).']
    if trap_fix and not carried:
        return ['the series carries ' + TRAP_FIX + ' but kernel_args does not carry ' + MARKER +
                ': nothing clears disable_kprintf_output, so no kernel text can appear (P-308).']
    return []


def image_args(image: pathlib.Path) -> list[str] | None:
    import subprocess
    try:
        out = subprocess.run(['python3', str(pathlib.Path(__file__).with_name('check-image-args.py')),
                              '--image', str(image), '--print-args'], capture_output=True, text=True)
    except OSError:
        return None
    return out.stdout.split() if out.returncode == 0 else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', default='.')
    parser.add_argument('--series', default=str(DEFAULT_SERIES))
    parser.add_argument('--image')
    options = parser.parse_args(argv)

    profile, args = effective_args(pathlib.Path(options.device))
    if not OS_RE.search(profile):
        print(f'skip kprintf: {profile!r} is not a 27 profile (16 builds are DEBUG and clear the gate themselves)')
        return 0
    trap_fix = series_has_trap_fix(pathlib.Path(options.series))
    problems = judge(profile, args, trap_fix)
    if problems:
        for problem in problems:
            print('FAIL: ' + problem)
        return 1
    print(f'ok kprintf: {profile} carries {MARKER} and the series carries {TRAP_FIX} ({len(args)} arguments)')
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
