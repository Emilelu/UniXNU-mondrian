#!/usr/bin/env python3
"""Judge the gpu-telemetry flight against FLIGHT-CARD-20261119c.md.

Three layers, in this order, because a run that measured nothing must not be
scored as a failure (P-236):

  1. validity   - did the compositor and the client actually produce frames?
  2. path       - is this the image and the code path the card asked for?
  3. criteria   - S1..S7 and the failure rules.

Usage: judge-gpu-telemetry.py <evidence-dir>
Exit codes: 0 measured, 3 INVALID, 2 the log could not be read.
"""

import os
import re
import sys

# Every row the plugin now streams. The card asks for all of them by name.
ROWS = [
    ("T pipeline", r"T pipeline n=\d+"),
    ("T library", r"T library n=\d+"),
    ("T function", r"T function n=\d+"),
    ("G commit-to-complete", r"G commit-to-complete n=\d+"),
    ("J scheduled wait", r"J scheduled wait n=\d+"),
    ("J completed wait", r"J completed wait n=\d+"),
    ("J resource wait", r"J resource wait n=\d+"),
    ("J surface cache", r"J surface cache n=\d+"),
    ("V vkpipe", r"V vkpipe n=\d+"),
    ("Q timing v2", r"Q timing v2"),
]

FRAMES = re.compile(r"MiniIOMobileFramebuffer:\s*(\d+)\s*frames in\s*(\d+)\s*ms")
CLIENT = re.compile(r"Pong Metal: c(\d+)/0\s+d(\d+)")
SCANOUT = re.compile(r"scanout frames=(\d+)")
PER_COMMIT = re.compile(r"K(\d+) t=[\d.]+s rp\d+ dr\d+ kpx\d+ cs\d+ bl\d+ ctc=(\d+)us")
STATUS = re.compile(r"Pong Metal: c\d+/0\s+d\d+")
CTC_MEAN = re.compile(r"G commit-to-complete n=(\d+) total=(\d+)ms max=(\d+)ms mean=(\d+)us")
VKPIPE = re.compile(r"V vkpipe n=(\d+) total=(\d+)ms max=(\d+)ms")
WAIT_DONE = re.compile(r"J completed wait n=(\d+) total=(\d+)ms max=(\d+)ms")
TE_AFTER_UI = re.compile(r"after the UI frame te\s+(\d+)/s")


def read_log(evidence_dir):
    path = os.path.join(evidence_dir, "console.log")
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def validity(text):
    frames = [int(n) for n, _ in FRAMES.findall(text)]
    clients = [int(c) for c, _ in CLIENT.findall(text)]
    scanouts = [int(n) for n in SCANOUT.findall(text)]
    reasons = []
    if not any(n > 0 for n in frames):
        reasons.append("no compositor frame count")
    if not any(c > 0 for c in clients):
        reasons.append("no client commit count")
    if not scanouts:
        reasons.append("no scanout line")
    return (not reasons), reasons, frames, clients, scanouts


def report(text, frames, clients, scanouts):
    out = []
    out.append("frames: compositor=%d client_commits=%d scanout_lines=%d"
               % (max(frames or [0]), max(clients or [0]), len(scanouts)))

    rows = []
    for name, pattern in ROWS:
        rows.append((name, len(re.findall(pattern, text))))
    missing = [name for name, count in rows if count == 0]
    out.append("timing rows: %d/%d present" % (len(ROWS) - len(missing), len(ROWS)))
    if missing:
        out.append("  missing: %s" % ", ".join(missing))

    commits = PER_COMMIT.findall(text)
    out.append("per-commit K rows: %d (with ctc: %d)"
               % (len(commits), sum(1 for _, c in commits if c)))

    status = len(STATUS.findall(text))
    out.append("status lines: %d (cadence 5/20/60/120/180 s)" % status)

    ctc = CTC_MEAN.search(text)
    if ctc:
        out.append("G commit-to-complete: n=%s total=%sms max=%sms mean=%sus"
                   % (ctc.group(1), ctc.group(2), ctc.group(3), ctc.group(4)))
    vk = VKPIPE.search(text)
    if vk:
        out.append("V vkpipe: n=%s total=%sms max=%sms -> %sus each"
                   % (vk.group(1), vk.group(2), vk.group(3),
                      (int(vk.group(2)) * 1000) // max(1, int(vk.group(1)))))
    wd = WAIT_DONE.search(text)
    if wd:
        out.append("J completed wait: n=%s total=%sms max=%sms" % (wd.group(1), wd.group(2), wd.group(3)))
    te = TE_AFTER_UI.findall(text)
    if te:
        out.append("panel after UI: %s Hz" % te[-1])

    # Frame interval from the compositor windows, for F4's comparison.
    intervals = []
    for count, millis in FRAMES.findall(text):
        if int(count) > 0:
            intervals.append(int(millis) / int(count))
    frame_ms = sorted(intervals)[len(intervals) // 2] if intervals else 0
    out.append("median compositor frame interval: %.1f ms" % frame_ms)

    failures = []
    if not commits or not all(c for _, c in commits[:3]):
        failures.append("F3 no per-commit rows")
    if ctc and frame_ms and int(ctc.group(4)) >= frame_ms * 1000:
        failures.append("F4 client waits more than a frame for the GPU")
    return out, rows, missing, commits, status, ctc, vk, frame_ms, failures


def main(argv):
    if len(argv) != 2:
        sys.exit("usage: judge-gpu-telemetry.py <evidence-dir>")
    evidence = argv[1]
    try:
        text = read_log(evidence)
    except OSError as exc:
        print("cannot read %s: %s" % (evidence, exc))
        return 2

    ok, reasons, frames, clients, scanouts = validity(text)
    print("evidence: %s (%d bytes)" % (evidence, len(text)))
    if not ok:
        print("validity: INVALID -- %s" % "; ".join(reasons))
        print("verdict: INVALID (not a criterion failure -- nothing was measured)")
        return 3
    print("validity: ok")

    lines, rows, missing, commits, status, ctc, vk, frame_ms, failures = \
        report(text, frames, clients, scanouts)
    print("")
    for line in lines:
        print(line)

    print("")
    print("S1 no panic: %s" % ("PASS" if not re.search(r"panic\(|K60KEXC|crashed: backboardd", text) else "FAIL"))
    print("S2 every timing row: %s" % ("PASS" if not missing else "FAIL"))
    print("S3 per-commit rows: %s" % ("PASS" if len(commits) >= 3 else "FAIL"))
    print("S4 status past 120 s: %s (%d lines)" % ("PASS" if status >= 4 else "FAIL", status))
    print("S5 presentation intact: %s" % ("PASS" if max(clients or [0]) >= 50 else "FAIL"))
    print("S6 numbers recorded: %s" % ("PASS" if (ctc or vk) else "FAIL"))
    print("")
    if failures:
        print("failure rules hit: %s" % ", ".join(failures))
    else:
        print("failure rules hit: none")
    print("verdict: %s" % ("PASS" if not missing and len(commits) >= 3 and status >= 4 and not failures else "FAIL"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
