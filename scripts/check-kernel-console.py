#!/usr/bin/env python3
"""Assert the built kernel can actually write to a console.

Why this exists (P-300): every gate we had asked whether the *image* would be
accepted -- argument budget, header, loader contract, prelink closure. None
asked whether the *kernel* has anything to say. The 16.6.1 line carried
patches 0232/0243/0300 that install a ramoops console; the 27 line never got
them, and two flights produced 0 bytes that were then read as "the kernel died
before the console came up". The instrument was missing, not the kernel.

The unit here is a defined symbol in the kernel image, because that is the one
thing a build can prove without a device:

    _pong_ramoops_console_write   the 16-series mirror writes here
    _k60_usblog_console_up        the EP0 console raises this
    _pong_ramoops_console_init    the mirror is installed from arm_init

A kernel with none of them can be booted, but its silence carries no
information, so `--flight` (used by the flight preflight) refuses it.

Usage:
    python3 scripts/check-kernel-console.py --kernel <kernel.macho>
    python3 scripts/check-kernel-console.py --kernel <kernel.macho> --flight
"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NM = os.environ.get('K60_NM', 'llvm-nm-18')

# Any one of these is enough to prove the kernel can emit a byte somewhere we
# can read.  They are alternatives, not requirements.
SINKS = (
    '_pong_ramoops_console_write',
    '_pong_ramoops_console_init',
    '_k60_usblog_console_up',
    '_k60_console_export_sysctl',
)


def symbols(kernel: str) -> set | None:
    """Defined symbols in the image, or None when nm cannot read it."""
    try:
        out = subprocess.run([NM, '--defined-only', kernel],
                             capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f'note: {NM} could not be run: {exc}', file=sys.stderr)
        return None
    if out.returncode != 0:
        note = (out.stderr or '').strip().splitlines()
        print(f'note: {NM} could not read {kernel}'
              f'{": " + note[0] if note else ""}', file=sys.stderr)
        return None
    found = set()
    for line in out.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[-2] not in ('U', 'u'):
            found.add(parts[-1])
    return found


def judge(have: set, require: str | None = None) -> tuple[int, str]:
    """Decide from a symbol set.  Split out so the test needs no kernel."""
    if require:
        if require in have:
            return 0, f'ok console: the kernel defines {require}'
        return 2, (f'FAIL: the kernel does not define {require}; a flight with '
                   f'this image would be silent for lack of an instrument, '
                   f'not for lack of a kernel (P-300)')
    present = [name for name in SINKS if name in have]
    if present:
        return 0, 'ok console: the kernel defines ' + ', '.join(present)
    return 2, ('FAIL: the kernel defines none of ' + ', '.join(SINKS) + '. '
               'Booting it can only produce silence, and silence cannot '
               'distinguish a dead kernel from a working one (P-300).')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--kernel', required=True)
    ap.add_argument('--require', default=None,
                    help='a specific sink symbol that must be defined')
    ap.add_argument('--flight', action='store_true',
                    help='refuse an image that could not be heard')
    args = ap.parse_args()

    if not os.path.isfile(args.kernel):
        print(f'FAIL: no kernel at {args.kernel}')
        return 2
    have = symbols(args.kernel)
    if have is None:
        return 2
    status, line = judge(have, args.require)
    print(line)
    if status == 0:
        return 0
    if args.flight:
        print('   修法：把 0546-k60-ramoops-console-27.patch 打进 series，并让 '
              'build-ios27-linux.sh 给 arm_init.o / serial_console.o 传 '
              '-DXNU_PONG_RAMOOPS_CONSOLE=1')
        return 2
    return status


if __name__ == '__main__':
    raise SystemExit(main())
