#!/usr/bin/env python3
"""Pin the Turnip render mode so it changes on purpose, not by drift.

The guide's default is gmem,nocb; Pong shipped sysmem,nocb because the A7xx
BV/BR scheduling was unwritten. The per-class probe measured an 18.4 MB blit at
12.4 ms (about 1.5 GB/s) on sysmem, which is the largest single term of the
frame, so the next single-variable flight switches the render mode and nothing
else. concurrent binning stays off, and overwrite must remain 1 so an inherited
environment cannot silently undo the choice.
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PLUGIN = os.path.join(REPO, 'drivers', 'PongMetal', 'PongMetalPlugin.mm')

failures = []
checks = 0


def check(name, ok, detail=''):
    global checks
    checks += 1
    if ok:
        print('ok   %s' % name)
    else:
        print('FAIL %s%s' % (name, (' -- ' + detail) if detail else ''))
        failures.append(name)


def main():
    with open(PLUGIN, encoding='utf-8', errors='replace') as handle:
        text = handle.read()

    matches = re.findall(r'setenv\("TU_DEBUG",\s*"([^"]*)",\s*([01])\)', text)
    check('the plugin sets TU_DEBUG exactly once', len(matches) == 1,
          'found %d' % len(matches))
    if not matches:
        return

    value, overwrite = matches[0]
    options = [part.strip() for part in value.split(',') if part.strip()]

    check('the render mode is gmem, the guide default', 'gmem' in options, value)
    check('sysmem is not also requested', 'sysmem' not in options, value)
    check('concurrent binning stays off', 'nocb' in options, value)
    check('the variable is overwritten, not inherited', overwrite == '1', overwrite)
    check('no unknown mode is requested',
          set(options) <= {'gmem', 'sysmem', 'nocb', 'cb'}, value)
    check('the comment names the measured reason',
          'gmem,nocb' in text and 'per-class' in text)


main()
print('TESTS OK %d checks' % checks if not failures else 'TESTS FAILED %d' % len(failures))
sys.exit(1 if failures else 0)
