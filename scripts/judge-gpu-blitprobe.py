#!/usr/bin/env python3
"""Judge flight card d: did the same bytes cost more going into the framebuffer?

Three layers, in order, because a threshold read before the run is shown to be
real is how a wrong number gets written down as a finding:

  1. validity  - the run presented frames, committed work and offered scanouts
  2. identity  - the control line and the copy-shape line are present
  3. criteria  - S1..S7 of the card, then the F rules that pick the next step

Usage: judge-gpu-blitprobe.py <evidence dir or console.log>
Exit:  0 judged, 2 log unreadable, 3 invalid run (nothing may be concluded)
"""

import io
import os
import re
import sys

CONTROL = re.compile(
    r"scanout blit control bytes=(\d+) src-to-device=(\d+) us device-to-scanout=(\d+) us")
SHAPE = re.compile(r"scanout copy (\S+(?: \S+)*?) source=(\d+) scanout=(\d+) rows=(\d+)")
STAGE = re.compile(
    r"scanout frames=(\d+) at [\d.]+ s; last frame: wait=(\d+) us copy=(\d+) us done=(\d+) us; "
    r"imports=(\d+) import=(\d+) us encode=(\d+) us submit=(\d+) us gpu=(\d+) us sum=(\d+) us")
COMPOSITOR = re.compile(r"MiniIOMobileFramebuffer:.*?(\d+)\s*frames in\s*(\d+)\s*ms")
CLIENT = re.compile(r"Pong Metal: c(\d+)/0\s+d(\d+)")


def read_log(target):
    path = target
    if os.path.isdir(path):
        path = os.path.join(path, "console.log")
    if not os.path.exists(path):
        return None, path
    return io.open(path, encoding="utf-8", errors="replace").read(), path


def median(values):
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) // 2


def main(argv):
    if len(argv) != 2:
        print("usage: judge-gpu-blitprobe.py <evidence dir or console.log>")
        return 2
    text, path = read_log(argv[1])
    if text is None:
        print("cannot read %s" % path)
        return 2
    print("log: %s (%d bytes)" % (path, len(text.encode("utf-8", "replace"))))

    frames = [int(m.group(1)) for m in COMPOSITOR.finditer(text)]
    commits = [int(m.group(1)) for m in CLIENT.finditer(text)]
    stages = [tuple(int(g) for g in m.groups()) for m in STAGE.finditer(text)]
    control = CONTROL.search(text)
    shape = SHAPE.search(text)

    print("\n== 1. validity (P-236) ==")
    print("  compositor frames : %s" % (max(frames) if frames else 0))
    print("  client commits    : %s" % (max(commits) if commits else 0))
    print("  scanout lines     : %d" % len(stages))
    valid = bool(frames and max(frames) >= 1 and commits and max(commits) >= 1 and stages)
    if not valid:
        print("  verdict: INVALID - nothing was measured, so no F rule may fire")
        return 3
    print("  verdict: valid")

    print("\n== 2. identity ==")
    if shape:
        print("  copy shape: %s source=%s scanout=%s rows=%s" % shape.groups())
    else:
        print("  copy shape: MISSING")
    if control:
        size, to_device, to_scanout = (int(g) for g in control.groups())
        print("  control   : bytes=%d src-to-device=%d us device-to-scanout=%d us"
              % (size, to_device, to_scanout))
        print("  ratio     : %.2fx  (src-to-device slower when < 1)"
              % (to_scanout / to_device if to_device else 0.0))
        print("  throughput: src-to-device %.2f GB/s, device-to-scanout %.2f GB/s"
              % ((size / to_device / 1e3) if to_device else 0.0,
                 (size / to_scanout / 1e3) if to_scanout else 0.0))
    else:
        size = to_device = to_scanout = None
        print("  control   : MISSING")

    copies = [row[2] for row in stages]
    gpus = [row[8] for row in stages]
    imports_ok = all(row[4] == row[0] for row in stages)
    print("  copy median=%s us  gpu median=%s us  imports==frames on every row: %s"
          % (median(copies), median(gpus), imports_ok))

    print("\n== 3. criteria ==")
    results = []
    results.append(("S1 no panic", "panic(" not in text and "K60KEXC" not in text
                    and "crashed: backboardd" not in text))
    results.append(("S2 exactly one control line", len(CONTROL.findall(text)) == 1))
    results.append(("S3 both numbers non-zero",
                    bool(control) and to_device > 0 and to_scanout > 0))
    results.append(("S4 shape texture untile and imports==frames",
                    bool(shape) and shape.group(1).strip() == "texture untile" and imports_ok))
    results.append(("S5 three numbers recorded",
                    bool(control) and median(copies) is not None))
    panel = re.search(r"after the UI frame te ([\d.]+)/s", text)
    results.append(("S6 panel >= 110 Hz", bool(panel) and float(panel.group(1)) >= 110))
    results.append(("S7 still presenting", len(stages) >= 2))
    for name, ok in results:
        print("  %s %s" % ("ok  " if ok else "FAIL", name))

    print("\n== 4. what the numbers pick ==")
    hit = []
    if not results[0][1]:
        hit.append("F1 panic - roll the control back and confirm with pong_gpu_blit_probe=0")
    if not control and shape:
        hit.append("F2 the control never ran - check the bundle strings, not the price")
    if control and to_device >= 5000 and to_scanout >= 5000 and max(to_device, to_scanout) < 2 * min(to_device, to_scanout):
        hit.append("F3 both sides slow and alike - the cost is global (clock or bandwidth), "
                   "so read the GPU frequency next rather than changing the destination")
    if control and to_device and to_device <= 2000 and to_scanout >= 8000:
        hit.append("F4 the firmware framebuffer is the slow side - move to zizhan's panel-buffer "
                   "target, and zero-copy scanout becomes the only real fix")
    if control and to_device >= 8000:
        hit.append("F5 the copy implementation is the slow side - time a CPU memcpy of the same "
                   "bytes as the floor and look for a shape that can land as CP_MEMCPY")
    if not hit:
        hit.append("no failure rule fired")
    for line in hit:
        print("  - %s" % line)

    print("\nverdict: %s" % ("PASS" if all(ok for _, ok in results) else
                             "FAIL (%s)" % ",".join(n.split()[0] for n, ok in results if not ok)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
