#!/usr/bin/env python3
"""Assert the 27 image is allowed to print.

`pexpert/arm/pe_kprintf.c:26-27` starts with both gates true.  `debug_boot_arg`
clears `disable_serial_output` only; `disable_kprintf_output` is cleared by
`#if DEBUG` or, in a DEVELOPMENT build, by `-enable_kprintf_spam`.  The 27 kernel
is DEVELOPMENT (MACHINE_CONFIGS=BCM2837 KERNEL_CONFIGS=DEVELOPMENT), so without
that argument every kprintf is a no-op -- and "no output" then says nothing
about whether the kernel ran (P-308).

Usage:
    check-kprintf-enabled.py [--device .] [--image boot.img]
Exit 0 when the effective 27 kernel_args carry the argument.
"""
from __future__ import annotations

import argparse
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
    if MARKER not in args:
        problems.append(
            'kernel_args has no ' + MARKER + ': a DEVELOPMENT build keeps '
            'disable_kprintf_output = true (pe_kprintf.c:47-56), so every kprintf is a no-op '
            'and "the kernel printed nothing" is not evidence of anything (P-308)')
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
    print(f'ok kprintf: {profile} passes {MARKER} ({len(args)} arguments)')
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
