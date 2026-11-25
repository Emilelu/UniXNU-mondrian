#!/usr/bin/env python3
"""Verify scripts/judge-wallpaper-log.py against the shapes it will meet on the phone.

The judge exists so a real boot log cannot be read out of order under time
pressure.  These cases therefore assert the verdict, not just the exit code:

  dead    -- a pre-0618 image (no K60WALL line, both old SKIPs present)
  half    -- K60WALL landed but the init guard still skipped the stock view
             (the shape Lead expects most: fix engaged, chain still broken)
  half    -- K60WALL rejected the catalogue (buffer/size failure branch)
  half    -- the 2026-11-15 resid regression: size=772 resid=7420 rejected, i.e. the
             image still tests resid != 0 on a buffer whose resid is free space
  half    -- views mounted but the UI library skipped the 7410 submission
  success -- K60WALL + no SKIP + 7410 submitted
  success -- same, but step 5 is N-A because no k60_wallpaper_reset=1 was passed
  dead    -- a log that never reaches userland at all (early death)

Two optional cases run the judge over real capture logs when they are present
on this host (they are not in the repository); they are skipped silently
otherwise so the suite stays portable.  The Lead's two pre-0618 captures
(usblog-20261115-003207, usblog-20261114-235957) are named there too, and one
case proves a capture directory is resolved to its console.log.

Run: python3 scripts/tests/test-judge-wallpaper-log.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# The judge prints Chinese diagnoses; under a GBK console the child raises
# UnicodeEncodeError and leaves stdout empty, which reads as a wrong verdict.
ENV = dict(os.environ, PYTHONIOENCODING='utf-8')
RUN = dict(capture_output=True, text=True, encoding='utf-8', errors='replace', env=ENV)

ROOT = Path(__file__).resolve().parents[2]
JUDGE = ROOT / 'scripts' / 'judge-wallpaper-log.py'

CASES = 0
FAILURES = 0

EARLY_DEATH = """K60 DISPLAY: first frame presented (swap 1, 1440x3200 canvas on 1440x3200 panel)
Pong init: HackiOS userland adapter / iOS 16.6.1 20G81 / static arm64
Pong init: Data mount /dev/disk2s1 result=0 errno=0
KX! 18 1 launchd exit=0 sig=11
pid 1 exited -- exit reason namespace 2 subcode 0xb
"""

PRE_0618 = """Pong init: HackiOS userland adapter / iOS 16.6.1 20G81 / static arm64
Pong init: boot view /private/var/pong/boot-jobs -> /pong/LaunchDaemons result=-1 errno=1
Pong init: boot view /private/var/pong/empty-hal -> /System/Library/Audio/Plug-Ins/HAL result=-1 errno=1
Pong init: optional boot view SKIP /private/var/pong/stock-wallpaper (source/target unavailable)
Pong init: wallpaper aliases SKIP (stock view unavailable)
Pong UI: 20G81 compatibility library entered SpringBoard
"""

SEED_OK_GUARD_STILL = """K60DATA mkdir ok=14/14
K60WALL catalogue bytes=772 resid=0 error=0
Pong init: HackiOS userland adapter / iOS 16.6.1 20G81 / static arm64
Pong init: boot view /private/var/pong/boot-jobs -> /pong/LaunchDaemons result=-1 errno=1
Pong init: optional boot view SKIP /private/var/pong/stock-wallpaper (source/target unavailable)
Pong init: wallpaper aliases SKIP (stock view unavailable)
Pong UI: wallpaper existing-content=1 restore-stock=1 (1=present -1=unavailable)
"""

SEED_REJECTED = """K60WALL catalogue size=8192 resid=4096 rejected
Pong init: optional boot view SKIP /private/var/pong/stock-wallpaper (source/target unavailable)
Pong init: wallpaper aliases SKIP (stock view unavailable)
"""

RESID_REGRESSION = """K60WALL catalogue size=772 resid=7420 rejected
Pong init: optional boot view SKIP /private/var/pong/stock-wallpaper (source/target unavailable)
Pong init: wallpaper aliases SKIP (stock view unavailable)
Pong UI: wallpaper existing-content=1 restore-stock=1 (1=present -1=unavailable)
Pong UI: submitting genuine wallpaper 7410 native lock+home path=/Library/Wallpaper/Stills/iPad/7410.WWDC_2022-1024w-1366h@2x~ipad.wallpaper
"""
VIEWS_FAIL_PIXELS_DECIDE = """K60WALL catalogue bytes=772 resid=0 error=0
Pong init: HackiOS userland adapter / iOS 16.6.1 20G81 / static arm64
Pong init: boot view /private/var/pong/boot-jobs -> /pong/LaunchDaemons result=-1 errno=1
Pong init: optional boot view SKIP /private/var/pong/stock-wallpaper (source/target unavailable)
Pong init: wallpaper aliases SKIP (stock view unavailable)
Pong UI: wallpaper existing-content=1 restore-stock=1 (1=present -1=unavailable)
Pong UI: genuine wallpaper asset 7410.WWDC_2022.thumbnail-1024w-1366h@2x~ipad.heic present=1
Pong UI: submitting genuine wallpaper 7410 native lock+home path=/Library/Wallpaper/Stills/iPad/7410.WWDC_2022-1024w-1366h@2x~ipad.wallpaper
Pong UI: native wallpaper completion returned; visual pixels remain to be observed
"""

VIEWS_OK_UI_SKIP = """K60WALL catalogue bytes=772 resid=0 error=0
Pong init: boot view /Library/Wallpaper -> /private/var/pong/stock-wallpaper result=0 errno=0
Pong init: boot view /private/var/pong/Wallpaper -> /Library/Wallpaper result=0 errno=0
Pong UI: wallpaper existing-content=1 restore-stock=1 (1=present -1=unavailable)
Pong UI: genuine wallpaper asset 7410.WWDC_2022.thumbnail-1024w-1366h@2x~ipad.heic present=1
Pong UI: genuine wallpaper bootstrap SKIP (native 20G81 WallpaperKit ABI unavailable)
"""

FULL_SUCCESS = """K60WALL catalogue bytes=772 resid=0 error=0
Pong init: boot view /Library/Wallpaper -> /private/var/pong/stock-wallpaper result=0 errno=0
Pong init: boot view /private/var/pong/Wallpaper -> /Library/Wallpaper result=0 errno=0
Pong UI: wallpaper existing-content=1 restore-stock=1 (1=present -1=unavailable)
Pong UI: genuine wallpaper asset 7410.WWDC_2022.thumbnail-1024w-1366h@2x~ipad.heic present=1
Pong UI: submitting genuine wallpaper 7410 native lock+home path=/Library/Wallpaper/Stills/iPad/7410.WWDC_2022-1024w-1366h@2x~ipad.wallpaper
Pong UI: native wallpaper completion returned; visual pixels remain to be observed
"""

SUCCESS_NO_RESET = """K60WALL catalogue bytes=772 resid=0 error=0
Pong init: boot view /Library/Wallpaper -> /private/var/pong/stock-wallpaper result=0 errno=0
Pong init: boot view /private/var/pong/Wallpaper -> /Library/Wallpaper result=0 errno=0
Pong UI: wallpaper existing-content=1 restore-stock=0 (1=present -1=unavailable)
"""


def check(condition, label, detail=''):
    global CASES, FAILURES
    CASES += 1
    if condition:
        print(f'ok   {label}')
    else:
        FAILURES += 1
        print(f'FAIL {label}' + (f': {detail}' if detail else ''))


def run(text):
    with tempfile.NamedTemporaryFile('w', suffix='.log', delete=False, encoding='utf-8') as handle:
        handle.write(text)
        path = handle.name
    proc = subprocess.run([sys.executable, str(JUDGE), path, '--quiet'], **RUN)
    Path(path).unlink(missing_ok=True)
    verdict = ''
    for line in proc.stdout.splitlines():
        if line.startswith('verdict:'):
            verdict = line.split(':', 1)[1].strip()
    return proc.returncode, verdict, proc.stdout + proc.stderr


def expect(text, want, label):
    code, verdict, output = run(text)
    check(verdict == want, label, f'verdict={verdict!r} want={want!r} rc={code} output={output[:200]}')
    return verdict


def main():
    expect(EARLY_DEATH, 'dead', 'early death before userland is dead')
    expect(PRE_0618, 'dead', 'a pre-0618 image with both SKIPs is dead')
    expect(SEED_OK_GUARD_STILL, 'half', 'seed landed but the init guard still skipped the view')
    expect(SEED_REJECTED, 'half', 'a rejected catalogue is half, never success')
    expect(RESID_REGRESSION, 'half', 'the resid regression is half, never success')
    expect(VIEWS_OK_UI_SKIP, 'half', 'views mounted but the UI library skipped 7410')
    expect(FULL_SUCCESS, 'success', 'seed + views + 7410 submission is success')
    expect(SUCCESS_NO_RESET, 'success', 'no reset flag keeps the user wallpaper: step 5 is N-A')

    # Step 6 is never machine-decidable: it must always be EYES, never PASS.
    # --quiet hides the step rows, so read this one in full.
    with tempfile.NamedTemporaryFile('w', suffix='.log', delete=False, encoding='utf-8') as handle:
        handle.write(FULL_SUCCESS)
        eyes_path = handle.name
    eyes = subprocess.run([sys.executable, str(JUDGE), eyes_path], **RUN)
    Path(eyes_path).unlink(missing_ok=True)
    check('EYES 6 screen pixels' in eyes.stdout and 'PASS 6' not in eyes.stdout,
          'step 6 stays EYES on a full success', eyes.stdout[:200])

    # The one half shape a screenshot can close: the seed landed, the only failures
    # are the two overlay views, and the wallpaper was still submitted from the OS
    # window. The judge must say so instead of sending the reader to F2.
    with tempfile.NamedTemporaryFile('w', suffix='.log', delete=False, encoding='utf-8') as handle:
        handle.write(VIEWS_FAIL_PIXELS_DECIDE)
        closure_path = handle.name
    closed = subprocess.run([sys.executable, str(JUDGE), closure_path], **RUN)
    Path(closure_path).unlink(missing_ok=True)
    check('verdict: half' in closed.stdout and 'closure:' in closed.stdout
          and 'close the case' in closed.stdout,
          'views failing after a submitted wallpaper prints the closure note',
          closed.stdout[-300:])

    # The same failures without a submission are ordinary work, not a closure.
    code, verdict, output = run(SEED_OK_GUARD_STILL)
    check(verdict == 'half' and 'closure:' not in output,
          'no closure note when the wallpaper was never submitted', output[-200:])

    # The regression the 2026-11-15 boot exposed: resid is the buffer's free space, so
    # a fixed image cannot reject a 772 B catalogue.  The judge must name that cause
    # instead of sending the reader to a generic §1 detour.
    with tempfile.NamedTemporaryFile('w', suffix='.log', delete=False, encoding='utf-8') as handle:
        handle.write(RESID_REGRESSION)
        resid_path = handle.name
    resid = subprocess.run([sys.executable, str(JUDGE), resid_path], **RUN)
    Path(resid_path).unlink(missing_ok=True)
    check('diagnosis: resid 判据回归' in resid.stdout and 'resid=7420' in resid.stdout,
          'a size=772 resid=7420 rejection is named as a resid regression',
          resid.stdout[-300:])

    # A log with no wallpaper text at all must not be reported as success.
    expect('nothing here\n', 'dead', 'an empty log is dead, not success')

    # A capture directory resolves to its console.log (the collector's layout).
    with tempfile.TemporaryDirectory() as tmp:
        capture = Path(tmp) / 'usblog-test'
        capture.mkdir()
        (capture / 'console.log').write_text(SEED_OK_GUARD_STILL, encoding='utf-8')
        proc = subprocess.run([sys.executable, str(JUDGE), str(capture), '--quiet'], **RUN)
        check('verdict: half' in proc.stdout,
              'a capture directory is judged by its console.log', proc.stdout[:200])
        (capture / 'console.log').unlink()
        # json.dumps, not %-formatting: a Windows path carries backslashes and
        # '{"log": "C:\\..."}' is not valid JSON, so the judge saw no log at all.
        (capture / 'capture.json').write_text(
            json.dumps({'log': str(capture / 'inner.log')}), encoding='utf-8')
        (capture / 'inner.log').write_text(SEED_OK_GUARD_STILL, encoding='utf-8')
        proc = subprocess.run([sys.executable, str(JUDGE), str(capture), '--quiet'], **RUN)
        check('verdict: half' in proc.stdout,
              'capture.json names the log when console.log is absent', proc.stdout[:200])

    # Real captures, when this host has them (they are not in the repo).
    for path in (Path('/mnt/e/iOS Port/Work/evidence/audio-probe-j/run1/console.log'),
                 Path('/mnt/e/iOS Port/Work/evidence/usblog-20261115-013520/console.log'),
                 Path('/mnt/e/iOS Port/Work/evidence/usblog-20261115-003207'),
                 Path('/mnt/e/iOS Port/Work/evidence/usblog-20261114-235957')):
        if not path.exists():
            continue
        proc = subprocess.run([sys.executable, str(JUDGE), str(path), '--quiet'], **RUN)
        check('verdict: dead' in proc.stdout,
              f'real pre-0618 capture stays dead ({path.parent.name if path.is_file() else path.name})',
              proc.stdout[:200])

    print(f'TESTS OK {CASES} cases ({FAILURES} failure(s))')
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
