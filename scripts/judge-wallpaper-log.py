#!/usr/bin/env python3
"""Judge a console.log against the wallpaper fix chain (docs/research/springboard/RESEARCH.md §0).

Six steps, in the §0 order, each PASS / FAIL / EYES with the deciding line number:

  1  K60WALL catalogue bytes=772 resid=0 error=0     (must appear, exact values)
  2  K60WALL catalogue open/read/create error=…      (must NOT appear)
     K60WALL catalogue size=… resid=… rejected       (must NOT appear)
  3  Pong init: optional boot view SKIP …stock-wallpaper   (must NOT appear)
  4  Pong init: wallpaper aliases SKIP (stock view unavailable)  (must NOT appear)
  5  Pong UI: wallpaper existing-content=… -> asset present=… -> submitting genuine wallpaper 7410
  6  screen pixels                                   (EYES: judge from a screenshot)

Step 5 has one legitimate non-failure: on a normal image (no k60_wallpaper_reset=1)
the UI library keeps the user's wallpaper, so the log shows
`wallpaper existing-content=1 restore-stock=0` and nothing after it.  That is
reported as N/A, not FAIL.

Verdict:
  success -- steps 1-4 hold and step 5 submitted (or N/A); pixels still need eyes
  half    -- the fix partly engaged (some steps pass, some fail); never skip ahead
  dead    -- no K60WALL line at all: the 0618 seed never ran in this image

One half shape needs a second line: when the seed landed (step 1 PASS) and the
only failures are steps 3 and 4 -- the bindfs overlay views -- the judge also
prints a `closure:` line.  The UI library submits wallpaper 7410 straight out
of the OS window (userland/ui_compat.c:690), never through the overlay, so a
dead view does not by itself mean a black wallpaper.  If the screenshot shows
the wallpaper, that half is the end of the case and F2 must not be built.

Pure reader: no writes, no device.  Run:

    python3 scripts/judge-wallpaper-log.py <console.log|capture-dir> [--quiet]

A capture directory is resolved the way the collector writes it: console.log in
the directory, else the "log" path inside capture.json.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

K60WALL_OK = re.compile(r'K60WALL catalogue bytes=(\d+) resid=(\d+) error=(\d+)')
K60WALL_BAD = re.compile(r'K60WALL catalogue (?:open|read|create) error=|'
                         r'K60WALL catalogue size=\d+ resid=\d+ rejected')
SKIP_VIEW = re.compile(r'Pong init: optional boot view SKIP /private/var/pong/stock-wallpaper')
SKIP_ALIAS = re.compile(r'Pong init: wallpaper aliases SKIP')
UI_EXISTING = re.compile(r'Pong UI: wallpaper existing-content=(-?\d+) restore-stock=(\d+)')
UI_ASSET = re.compile(r'Pong UI: genuine wallpaper asset (\S+) present=(\d+)')
UI_SUBMIT = re.compile(r'Pong UI: submitting genuine wallpaper 7410')
UI_SKIP = re.compile(r'Pong UI: genuine wallpaper bootstrap SKIP \(([^)]*)\)')


def hits(lines, rx):
    return [(n, line.strip()) for n, line in enumerate(lines, 1) if rx.search(line)]


def judge(lines):
    """Return [(step, state, detail, goto)] where state in PASS/FAIL/N-A/EYES."""
    out = []

    ok = [h for h in hits(lines, K60WALL_OK)
          if h[1].find('bytes=772 resid=0 error=0') >= 0]
    bad = hits(lines, K60WALL_BAD)
    any_k60 = bool(hits(lines, K60WALL_OK))

    if ok and not bad:
        out.append(('1 K60WALL catalogue', 'PASS', ok[0], 'RESEARCH.md §1'))
    elif bad:
        out.append(('1 K60WALL catalogue', 'FAIL', bad[0], 'RESEARCH.md §1'))
    elif any_k60:
        out.append(('1 K60WALL catalogue', 'FAIL', hits(lines, K60WALL_OK)[0], 'RESEARCH.md §1'))
    else:
        out.append(('1 K60WALL catalogue', 'FAIL', None, 'RESEARCH.md §1'))

    if bad:
        out.append(('2 K60WALL errors', 'FAIL', bad[0], 'RESEARCH.md §1'))
    elif any_k60:
        out.append(('2 K60WALL errors', 'PASS', None, 'RESEARCH.md §1'))
    else:
        out.append(('2 K60WALL errors', 'N-A', None, 'RESEARCH.md §1 (no K60WALL line at all)'))

    v = hits(lines, SKIP_VIEW)
    out.append(('3 optional boot view SKIP', 'FAIL' if v else 'PASS', v[0] if v else None, 'RESEARCH.md §2'))

    a = hits(lines, SKIP_ALIAS)
    out.append(('4 wallpaper aliases SKIP', 'FAIL' if a else 'PASS', a[0] if a else None, 'RESEARCH.md §2'))

    existing = hits(lines, UI_EXISTING)
    submit = hits(lines, UI_SUBMIT)
    skipped = hits(lines, UI_SKIP)
    assets = hits(lines, UI_ASSET)
    if submit:
        out.append(('5 Pong UI wallpaper chain', 'PASS', submit[0], 'RESEARCH.md §3'))
    elif skipped:
        out.append(('5 Pong UI wallpaper chain', 'FAIL', skipped[0], 'RESEARCH.md §3'))
    elif existing:
        m = existing[0][1]
        restore = int(re.search(r'restore-stock=(-?\d+)', m).group(1))
        content = int(re.search(r'existing-content=(-?\d+)', m).group(1))
        if content == 1 and restore == 0:
            out.append(('5 Pong UI wallpaper chain', 'N-A', existing[0],
                        'RESEARCH.md §3 (no k60_wallpaper_reset=1: user wallpaper kept)'))
        else:
            detail = assets[0] if assets else existing[0]
            out.append(('5 Pong UI wallpaper chain', 'FAIL', detail, 'RESEARCH.md §3'))
    else:
        out.append(('5 Pong UI wallpaper chain', 'FAIL', None, 'RESEARCH.md §3'))

    out.append(('6 screen pixels', 'EYES', None, 'RESEARCH.md §4 (screenshot only)'))
    return out


VIEW_STEPS = ('3 ', '4 ')


def closure(rows):
    """Return a closure note when the only failures are the two overlay views.

    Steps 3 and 4 describe the bindfs view /Library/Wallpaper <-> the Data-side
    stock-wallpaper directory.  The UI library reads the OS window directly, so
    these two failing while the seed and the submission both pass is a shape
    that a screenshot can close for good.
    """
    if rows[0][1] != 'PASS':
        return None
    failing = [step for step, state, _, _ in rows if state == 'FAIL']
    if not failing or not all(step.startswith(VIEW_STEPS) for step in failing):
        return None
    return ('steps 3-4 cover the bindfs overlay only; userland/ui_compat.c:690 submits 7410 from '
            'the OS window. If the screenshot shows the wallpaper, close the case -- do not build F2.')


def verdict(rows):
    """dead = the 0618 seed never ran; half = partly engaged; success = 1-4 hold."""
    states = [s for _, s, _, _ in rows]
    if states[0] == 'FAIL' and states[1] == 'N-A':
        return 'dead'
    if any(s == 'FAIL' for s in states):
        return 'half'
    return 'success'


def capture_log(directory):
    """Return the console.log a capture directory holds, or None."""
    direct = directory / 'console.log'
    if direct.is_file():
        return direct
    meta = directory / 'capture.json'
    if meta.is_file():
        try:
            import json
            recorded = json.loads(meta.read_text(encoding='utf-8-sig')).get('log')
        except (OSError, ValueError):
            recorded = None
        if recorded:
            candidate = Path(str(recorded))
            if candidate.is_file():
                return candidate
    return None


def main(argv):
    args = [a for a in argv[1:] if not a.startswith('--')]
    quiet = '--quiet' in argv
    if len(args) != 1:
        print(__doc__)
        return 2
    path = Path(args[0])
    if path.is_dir():
        path = capture_log(path) or path
    if not path.is_file():
        print(f'judge-wallpaper-log: not a file: {path}')
        return 2
    lines = path.read_text(encoding='utf-8', errors='ignore').splitlines()
    rows = judge(lines)
    final = verdict(rows)
    if not quiet:
        print(f'judge-wallpaper-log: {path} ({len(lines)} lines)')
        for step, state, detail, goto in rows:
            line = f'  {state:4} {step}'
            if detail:
                line += f'  [{detail[0]}] {detail[1][:110]}'
            if state == 'FAIL':
                line += f'  -> see {goto}'
            elif state == 'N-A':
                line += f'  ({goto})'
            print(line)
    print(f'verdict: {final}')
    note = closure(rows)
    if note:
        print(f'closure: {note}')
    return 0 if final in ('success', 'half') else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
