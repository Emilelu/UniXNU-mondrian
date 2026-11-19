#!/usr/bin/env python3
"""Judge the surface-creation probe (flight card g).

Three layers, the same order every card uses: validity first (P-236), then whether the path the
card claims to measure was actually reached, then the criteria. Exit 0 = PASS, 1 = FAIL,
3 = INVALID (nothing was measured), 2 = the log could not be read.
"""
import argparse
import io
import os
import re
import sys

FRAMES = re.compile(r'MiniIOMobileFramebuffer:\s*(\d+)\s*frames in\s*(\d+)\s*ms')
CLIENT = re.compile(r'Pong Metal: c(\d+)/0\s+d(\d+)')
SCANOUT = re.compile(r'scanout frames=(\d+) at')
SHAPE = re.compile(r'scanout copy ([a-z ]+?) source=(\d+) scanout=(\d+) rows=(\d+)')
SURFACE = re.compile(r'MiniIOSurface: surface made sid=(\d+) (\d+)x(\d+) bpr=(\d+) planes=(\d+)'
                     r' alloc=(\d+) asked=(\d+)')
PITCH = re.compile(r'MiniIOSurface: plane pitch asked=(\d+) reported=(\d+)')
IMPORTS = re.compile(r'imports=(\d+)')
PANEL = re.compile(r'(?:after the UI frame|panel after UI)[^\n]*?te\s*(\d+)/s')
PANEL_HZ = re.compile(r'panel after UI:[^\n]*?(\d+)\s*Hz')


def read(path):
    try:
        return io.open(path, encoding='utf-8', errors='replace').read()
    except OSError as error:
        sys.stderr.write('cannot read %s: %s\n' % (path, error))
        raise SystemExit(2)


def judge(text):
    lines = []
    frames = [int(m.group(1)) for m in FRAMES.finditer(text)]
    commits = [int(m.group(1)) for m in CLIENT.finditer(text)]
    scans = [int(m.group(1)) for m in SCANOUT.finditer(text)]
    surfaces = [tuple(int(g) for g in m.groups()) for m in SURFACE.finditer(text)]
    pitches = [tuple(int(g) for g in m.groups()) for m in PITCH.finditer(text)]
    shapes = [(m.group(1).strip(), int(m.group(2)), int(m.group(3))) for m in SHAPE.finditer(text)]
    panel = [int(m.group(1)) for m in PANEL.finditer(text)]
    panel += [int(m.group(1)) for m in PANEL_HZ.finditer(text)]

    lines.append('有效性: compositor=%d frames · client_commits=%d · scanout_lines=%d'
                 % (max(frames or [0]), max(commits or [0]), len(scans)))
    if not frames or max(frames) == 0 or not commits or max(commits) == 0:
        lines.append('verdict: INVALID (nothing was measured)')
        return 3, lines

    lines.append('surface made: %d line(s)' % len(surfaces))
    for sid, w, h, bpr, planes, alloc, asked in surfaces[:12]:
        mark = '  <-- 5888' if bpr == 5888 else ''
        lines.append('  sid=%d %dx%d bpr=%d planes=%d alloc=%d asked=%d%s'
                     % (sid, w, h, bpr, planes, alloc, asked, mark))
    lines.append('plane pitch mismatches: %d' % len(pitches))
    lines.append('shapes: %s' % (', '.join('%s (source %d scanout %d)' % s for s in shapes) or 'none'))

    bpr_values = set(s[3] for s in surfaces)
    has_5888 = 5888 in bpr_values
    # A scanout source stride wider than the scanout stride is the untile's reason; the probe
    # only answers "where does that stride come from", never "can it be removed".
    source_wide = any(src > dst for _, src, dst in shapes)

    ok = {}
    ok['S1'] = not re.search(r'panic\(|K60KEXC|DeviceLost|crashed: backboardd', text)
    ok['S2'] = len(surfaces) >= 3
    ok['S3'] = has_5888 or (surfaces and not has_5888)
    ok['S4'] = all(asked == bpr for _, _, _, bpr, _, _, asked in surfaces) or bool(pitches)
    ok['S5'] = bool(shapes)
    ok['S6'] = bool(panel) and max(panel) >= 110
    imports_ok = True
    for m in re.finditer(r'scanout frames=(\d+).*?imports=(\d+)', text):
        if m.group(1) != m.group(2):
            imports_ok = False
    ok['S7'] = imports_ok and bool(re.search(r'imports=', text))

    for key in sorted(ok):
        lines.append('%s %s' % (key, 'PASS' if ok[key] else 'FAIL'))

    failures = []
    if not ok['S1']:
        failures.append('F1 panic or device loss')
    if len(surfaces) == 0:
        failures.append('F2 no surface line: the probe did not run')
    if surfaces and not has_5888:
        failures.append('F3 every surface reports bpr in %s, none 5888: the canvas is built '
                        'somewhere else, stop editing pitch' % sorted(bpr_values))
    if source_wide and not has_5888:
        failures.append('F3 the scanout still offers a wider source stride than its own, and no '
                        'surface here explains it')

    code = 0 if all(ok.values()) else 1
    if code:
        lines.append('failure rules hit: %s' % (', '.join(failures) or 'none'))
        lines.append('verdict: FAIL (%s)' % ', '.join(k for k in sorted(ok) if not ok[k]))
    else:
        lines.append('verdict: PASS')
    return code, lines


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('evidence', help='an evidence directory or a console.log')
    args = parser.parse_args(argv)
    path = args.evidence
    if os.path.isdir(path):
        path = os.path.join(path, 'console.log')
    code, lines = judge(read(path))
    out = '\n'.join(lines)
    sys.stdout.buffer.write((out + '\n').encode('utf-8'))
    return code


if __name__ == '__main__':
    sys.exit(main())
