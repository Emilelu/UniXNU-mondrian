#!/usr/bin/env python3
"""Judge a flight that was flown to find out whether every frame gets a fresh mapping address.

Three layers, in this order (the order is the lesson of P-236):

  1. validity   - did anything actually render? A zero-frame run measures nothing,
                  and a DeviceLost run is not "slow", it is dead (P-244).
  2. path       - is this the image that carries the probe at all? `addr=0x` has to appear
                  in the stage line, otherwise "no evidence" would read as "addresses match".
  3. hypothesis - join the kernel's `PONG SCANOUT: frame=N ... addr=0x..` with the presenter's
                  `Pong Metal: scanout frames=N ... import=<us>` by frame number and answer
                  H1 (distinct address per frame) or H2 (addresses repeat).

Exit codes: 0 = the flight answered the question, 1 = it did not, 3 = invalid, 2 = unreadable.
"""

import os
import re
import sys

# Two shapes of the same line, on purpose. The probe-agnostic one answers "did a frame get
# offered at all", which decides validity; the full one answers "did this image carry the
# address", which is a path question. Using the full shape for both made an image without the
# probe look like an invalid flight, i.e. a device flake instead of a wrong artifact (P-236).
STAGE_ANY = re.compile(r"PONG SCANOUT: frame=(\d+)")
STAGE = re.compile(
    r"PONG SCANOUT: frame=(\d+) prepare=(\d+) us offer_and_copy=(\d+) us total=(\d+) us"
    r" addr=0x([0-9a-fA-F]+) bytes=(\d+)")
CLIENT = re.compile(
    r"Pong Metal: scanout frames=(\d+) at [\d.]+ s; last frame: wait=(\d+) us copy=(\d+) us"
    r" done=(\d+) us; imports=(\d+) import=(\d+) us encode=(\d+) us submit=(\d+) us"
    r" gpu=(\d+) us sum=(\d+) us")
COMPOSITOR = re.compile(r"MiniIOMobileFramebuffer:\s*(\d+)\s*frames in\s*(\d+)\s*ms")
COMMITS = re.compile(r"Pong Metal: c(\d+)/0 d(\d+)")
PANEL = re.compile(r"(?:after the UI frame|panel after UI)[^\n]*?te\s*(\d+)/s")
DEVICE_LOST = "DeviceLost"

EXPENSIVE_US = 5000
CHEAP_US = 1000


def validity(text):
    """Return (ok, lines). A run that measured nothing cannot answer a question."""
    frames = [int(m.group(1)) for m in COMPOSITOR.finditer(text)]
    commits = [int(m.group(1)) for m in COMMITS.finditer(text)]
    stage = STAGE_ANY.findall(text)
    lost = text.count(DEVICE_LOST)
    problems = []
    if not frames:
        problems.append("no MiniIOMobileFramebuffer frame line")
    elif max(frames) <= 0:
        problems.append("the compositor reported 0 frames")
    if not commits or max(commits) <= 0:
        problems.append("no command buffer was ever committed")
    if not stage:
        problems.append("no PONG SCANOUT stage line")
    if lost:
        problems.append(f"{lost} DeviceLost lines - the GPU died, this is not a slow run (P-244)")
    return (not problems), problems


def path(text):
    """Return (ok, lines). The probe has to be in the image and it has to have run."""
    stage = STAGE.findall(text)
    problems = []
    if not stage:
        problems.append("no stage line carries addr=/bytes= - the probe is absent or never ran (F2)")
    client = CLIENT.findall(text)
    if not client:
        problems.append("no presenter line carries imports=/import= - nothing to join on")
    return (not problems) and bool(stage), problems


def report(text):
    """Return (exit_code, report_text)."""
    ok, problems = validity(text)
    if not ok:
        head = "INVALID (nothing was measured)\n" + "".join(f"  - {p}\n" for p in problems)
        return 3, head

    ok, problems = path(text)
    if not ok:
        head = "FAIL (the probe did not reach the image)\n" + "".join(f"  - {p}\n" for p in problems)
        return 1, head

    stage = {int(m[0]): {"prepare": int(m[1]), "total": int(m[3]),
                         "addr": m[4].lower(), "bytes": int(m[5])}
             for m in STAGE.findall(text)}
    client = {int(m[0]): {"copy": int(m[2]), "imports": int(m[4]), "import": int(m[5]),
                          "encode": int(m[6]), "sum": int(m[9])}
              for m in CLIENT.findall(text)}

    joined = sorted(set(stage) & set(client))
    out = []
    out.append(f"stage lines: {len(stage)}, presenter lines: {len(client)}, joined: {len(joined)}")
    frames = client and max(client) or 0
    if joined:
        out.append("")
        out.append("  frame   addr               bytes       import  encode   copy    sum")
        for n in joined:
            s, c = stage[n], client[n]
            out.append(f"  {n:5d}   0x{s['addr']:<16} {s['bytes']:<11} {c['import']:6d} {c['encode']:6d}"
                       f" {c['copy']:6d} {c['sum']:6d}")

    # The question: does every frame get its own address?
    seen = {}
    for n, s in sorted(stage.items()):
        seen.setdefault(s["addr"], []).append(n)
    repeated = {a: ns for a, ns in seen.items() if len(ns) > 1}
    out.append("")
    out.append(f"addresses: {len(seen)} distinct over {len(stage)} frames")
    if repeated:
        out.append("repeated addresses:")
        for a, ns in sorted(repeated.items(), key=lambda kv: kv[1][0]):
            costs = [client[n]["import"] for n in ns if n in client]
            shown = ", ".join(f"{n}:{client[n]['import']}us" for n in ns if n in client)
            expensive = [c for c in costs if c >= EXPENSIVE_US]
            cheap = [c for c in costs if c < CHEAP_US]
            out.append(f"  0x{a}: frames {ns} ({shown})"
                       f" -> {len(expensive)} expensive, {len(cheap)} cheap")

    # S7 is a property of the presenter line itself: the frame it names and the import count it
    # reports have to be the same number. Only checking the joined lines would hide a line whose
    # kernel half is missing from the log.
    monotone = sorted(n for n, c in client.items() if c["imports"] != n)
    if monotone:
        out.append(f"imports != frame number on frames {monotone} (S7 fails)")

    panel = [int(m) for m in PANEL.findall(text)]
    out.append(f"panel: {panel and max(panel)} Hz")

    # Verdict.
    code = 0
    if len(seen) == len(stage):
        out.append("")
        out.append("H1: every frame got its own address - a kept mapping is the fix (token/evict),")
        out.append("    and the win is bounded by the expensive imports above minus the cheap ones.")
    else:
        # H2 needs the repeats themselves to stay expensive. The first touch of an address is
        # allowed to cost 15 ms - that is what a page walk is - so only the later occurrences
        # decide whether keeping the mapping would help.
        mixed = any(all(client[n]["import"] >= EXPENSIVE_US for n in ns[1:] if n in client)
                    and any(n in client for n in ns[1:])
                    for ns in repeated.values())
        if mixed:
            out.append("")
            out.append("H2: an address repeated and the import stayed expensive - the address is not")
            out.append("    the variable; do NOT start the token work, look at HostMemory in the bridge.")
        else:
            out.append("")
            out.append("H1': addresses repeat but the repeats are cheap - keeping the mapping still")
            out.append("     removes the first-touch cost; report the distribution before choosing.")
            code = 1
    if monotone or not joined:
        code = 1
    return code, "".join(l + "\n" for l in out)


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    path_arg = argv[1]
    if os.path.isdir(path_arg):
        path_arg = os.path.join(path_arg, "console.log")
    try:
        with open(path_arg, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        print(f"cannot read {path_arg}: {exc}")
        return 2
    code, text_out = report(text)
    sys.stdout.write(text_out)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
