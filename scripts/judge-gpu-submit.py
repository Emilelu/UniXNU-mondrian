#!/usr/bin/env python3
"""Judge flight card e: is the 3.0 ms inside [MTLCommandBuffer commit] our kernel's or the translator's?

Three layers, in this order, because reading a threshold before checking that anything was
measured is how a flight with no data gets recorded as a win (P-236):

  1. validity   - did the device present anything at all?
  2. path       - is the probe in this image, and is the counter actually being credited?
  3. attribution- the one comparison the card was written for.

The window is the whole point: the sample line reads
native_adreno_method_stats[NativeAdrenoMethodSubmit] from inside the submit, so its own credit
has not landed yet. The printed pair is cumulative totals of the last COMPLETED submission, and
the per-submit mean is prevsub_total/prevsub_count - not a delta across one call (P-237).

Exit codes: 0 = PASS, 1 = FAIL, 2 = log unreadable, 3 = INVALID (nothing measured).
"""
import os
import re
import statistics
import sys

SUBMIT_BEFORE_US = 3015      # median submit in usblog-20261119-070345
KMD_SHARE_KERNEL = 0.60      # F3: at or above this the kernel owns it
KMD_SHARE_UPSTREAM = 0.20    # F4: below this the translator owns it

MIF = re.compile(r'MiniIOMobileFramebuffer:\s*(\d+)\s*frames in\s*(\d+)\s*ms')
DEVICE_LOST = re.compile(r'DeviceLost')
CLIENT = re.compile(r'Pong Metal: c(\d+)/0 d(\d+)')
SCANOUT = re.compile(r'scanout frames=(\d+) at ([\d.]+) s; last frame: wait=(\d+) us copy=(\d+) us done=(\d+) us;'
                     r' imports=(\d+) import=(\d+) us encode=(\d+) us submit=(\d+) us gpu=(\d+) us sum=(\d+) us')
SHAPE = re.compile(r'scanout copy ([a-z ]+) source=(\d+) scanout=(\d+) rows=(\d+)')
SUB = re.compile(r'PONG SUB: sample n=(\d+) buffers=(\d+) referenced=(\d+) publish=(\d+) us'
                 r' prevsub_count=(\d+) prevsub_total=(\d+) us')
PANEL = re.compile(r'after the UI frame te (\d+)/s')


def utf8():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')


def validity(text):
    frames = max((int(m.group(1)) for m in MIF.finditer(text)), default=0)
    commits = max((int(m.group(1)) for m in CLIENT.finditer(text)), default=0)
    scan = len(SCANOUT.findall(text))
    reasons = []
    # P-244: a lost Metal device keeps logging at ~1450 lines a second while nothing renders.
    # "very slow" and "already dead" look identical unless this is checked first.
    if DEVICE_LOST.search(text):
        reasons.append('the Metal device was declared lost during the flight (DeviceLost x%d);'
                       ' a dead device keeps logging without rendering' % len(DEVICE_LOST.findall(text)))
    if frames < 1:
        reasons.append('no compositor frame line with N>=1')
    if commits < 1:
        reasons.append('no Pong Metal: c<n>/0 line with n>=1')
    if scan < 1:
        reasons.append('no scanout frames= line')
    return frames, commits, scan, reasons


def report(path):
    try:
        with open(path, encoding='utf-8', errors='replace') as handle:
            text = handle.read()
    except OSError as error:
        print('❌ cannot read %s: %s' % (path, error))
        return 2

    print('evidence: %s (%d bytes, %d lines)'
          % (path, len(text.encode('utf-8', 'replace')), text.count('\n') + 1))
    frames, commits, scan, reasons = validity(text)
    print('validity: compositor=%d frames · client_commits=%d · scanout_lines=%d'
          % (frames, commits, scan))
    if reasons:
        print('verdict: INVALID (nothing was measured, so no criterion can be judged)')
        for reason in reasons:
            print('  - %s' % reason)
        return 3

    subs = SUB.findall(text)
    print('submit samples: %d' % len(subs))
    if not subs:
        print('verdict: FAIL (S2)')
        print('  F2: no PONG SUB line carries prevsub_count/prevsub_total - the probe did not')
        print('      reach the image or did not run. Do not read this as "the kernel is fast".')
        return 1

    counts = [int(s[4]) for s in subs]
    totals = [int(s[5]) for s in subs]
    monotonic = all(b >= a for a, b in zip(counts, counts[1:]))
    print('  prevsub_count first=%d last=%d monotonic=%s'
          % (counts[0], counts[-1], 'yes' if monotonic else 'no'))
    print('  prevsub_total first=%d us last=%d us' % (totals[0], totals[-1]))

    # group 2 is the timestamp in seconds, the only non-integer field in the line.
    rows = [(int(m.group(1)), float(m.group(2))) + tuple(int(m.group(i)) for i in range(3, 12))
            for m in SCANOUT.finditer(text)]
    steady = [r for r in rows if r[4] >= 20]
    submit_median = int(statistics.median([r[8] for r in steady])) if steady else None
    print('stage samples: %d (%d with >=20 imports)' % (len(rows), len(steady)))
    if submit_median is not None:
        print('  submit median=%d us (before: %d us)' % (submit_median, SUBMIT_BEFORE_US))

    shapes = SHAPE.findall(text)
    if shapes:
        name, source, scanout_stride, shape_rows = shapes[0]
        print('  copy shape: %s source=%s scanout=%s rows=%s'
              % (name, source, scanout_stride, shape_rows))
    panels = [int(p) for p in PANEL.findall(text)]
    if panels:
        print('  panel after UI: %d Hz' % panels[-1])

    per_submit = (totals[-1] / counts[-1]) if counts[-1] else 0.0
    share = (per_submit / submit_median) if submit_median else 0.0
    print('attribution:')
    print('  KMD submit mean = prevsub_total/prevsub_count = %.0f us' % per_submit)
    if submit_median:
        print('  share of the submit median = %.1f %%' % (share * 100))

    failed = []
    hit = []
    if not monotonic:
        failed.append('S3')
    if totals[-1] == 0 and counts[-1] > 0:
        # A rules that fires must also fail the flight: reporting it next to "PASS" is how a
        # counter nobody credits gets recorded as a kernel that is fast.
        failed.append('F5')
        hit.append('F5: prevsub_count grows but prevsub_total is still 0 - the counter is not'
                   ' credited by anything, so fix the counter before attributing anything')
    if shapes and shapes[0][0].strip() != 'texture untile':
        failed.append('S7')
    if panels and panels[-1] < 110:
        failed.append('S6')

    if submit_median is None:
        failed.append('S5')
    elif share >= KMD_SHARE_KERNEL:
        print('  F3 HIT: the 3.0 ms is inside our kernel (>= %.0f %%)' % (KMD_SHARE_KERNEL * 100))
    elif share < KMD_SHARE_UPSTREAM:
        print('  F4 HIT: the 3.0 ms is upstream of us (< %.0f %%)' % (KMD_SHARE_UPSTREAM * 100))
    else:
        print('  neither F3 nor F4: the time is split, refine the probe before acting')

    print('verdict: %s%s' % ('FAIL' if failed else 'PASS',
                             (' (%s)' % ','.join(failed)) if failed else ''))
    for line in hit:
        print('  ' + line)
    if not failed and not hit:
        print('  next: follow the branch reported above; the number to beat is the submit median')
    return 1 if failed else 0


def main():
    utf8()
    if len(sys.argv) != 2:
        print('usage: judge-gpu-submit.py <evidence dir or console.log>')
        return 2
    path = sys.argv[1]
    if os.path.isdir(path):
        path = os.path.join(path, 'console.log')
    return report(path)


if __name__ == '__main__':
    sys.exit(main())
