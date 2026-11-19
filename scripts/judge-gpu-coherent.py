#!/usr/bin/env python3
"""Judge flight card b: did the IO coherence probe run, and did the skip it enables remove the
imported-frame maintenance from every submission?

Three layers, in this order (P-236): validity first, then path identity, then the thresholds. A run
that never presented a frame says nothing about coherence, so it must be judged invalid rather than
failed -- that mistake cost a flight on 2026-11-18.

Usage: judge-gpu-coherent.py <evidence-dir> [--card docs/research/gpu/FLIGHT-CARD-20261119b.md]
"""
import argparse
import pathlib
import re
import statistics
import sys

# Thresholds from the card. The before-values are the measured medians of gpu-consolidated-20261119
# (usblog-20261119-025400) and usblog-20261118-233946, not targets invented here.
PUBLISH_BEFORE_US = 6635
SUBMIT_BEFORE_US = 8420
PUBLISH_TARGET_US = 2000
SUBMIT_TARGET_US = 4500


def read_log(directory):
    path = pathlib.Path(directory) / "console.log"
    if not path.exists():
        return None, f"no console.log under {directory}"
    return path.read_bytes().decode("utf-8", "replace"), None


def frames_presented(text):
    best = 0
    for n in re.findall(r"MiniIOMobileFramebuffer:\s*(\d+)\s*frames in", text):
        best = max(best, int(n))
    return best


def client_commits(text):
    best = 0
    for n in re.findall(r"Pong Metal: c(\d+)/0\s+d(\d+)", text):
        best = max(best, int(n[0]))
    return best


def scanout_lines(text):
    return len(re.findall(r"scanout frames=", text))


def coherence_line(text):
    return re.findall(r"PONG ADRENO: IO coherence (on|off) \(pong_gpu_coherent=(\d+), probe ([^)]*)\)", text)


def vm_samples(text):
    """Each sample: (us, coherent, skipped). `us=` is this call's own duration."""
    out = []
    for m in re.finditer(r"PONG VM: publish sample .*?us=(\d+) .*?coherent=(\d+) skipped=(\d+)", text):
        out.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
    return out


def judge(directory, card):
    text, error = read_log(directory)
    if error:
        print(f"error: {error}")
        return 2

    print(f"log    : {directory}")
    print(f"bytes  : {len(text.encode('utf-8', 'replace'))}")

    # --- layer 1: validity (P-236) -----------------------------------------------------------
    frames = frames_presented(text)
    commits = client_commits(text)
    scanouts = scanout_lines(text)
    print(f"frames : compositor={frames} client_commits={commits} scanout_lines={scanouts}")
    invalid = []
    if frames <= 0:
        invalid.append(f"the compositor reported no frame (MiniIOMobileFramebuffer: N frames, N>0)")
    if commits <= 0:
        invalid.append("the client never committed (Pong Metal: c<n>/0 d<n>, n>0)")
    if scanouts <= 0:
        invalid.append("no `scanout frames=` line")
    if invalid:
        print("\nverdict: INVALID (not a criterion failure -- nothing was measured)")
        for reason in invalid:
            print(f"  - {reason}")
        return 3

    # --- layer 2: path identity --------------------------------------------------------------
    coh = coherence_line(text)
    print(f"\ncoherence lines: {len(coh)}")
    for state, arg, row in coh:
        print(f"  IO coherence {state} (pong_gpu_coherent={arg}, probe {row})")

    samples = vm_samples(text)
    print(f"publish samples: {len(samples)}")
    if samples:
        coherent_values = sorted({s[1] for s in samples})
        print(f"  coherent field: {coherent_values}")
        us = [s[0] for s in samples if s[0] > 0]
        if us:
            print(f"  publish us: median={statistics.median(us):.0f} min={min(us)} max={max(us)}")
        skipped = [s[2] for s in samples]
        print(f"  skipped: first={skipped[0]} last={skipped[-1]} "
              f"monotonic={'yes' if all(b >= a for a, b in zip(skipped, skipped[1:])) else 'no'}")

    stage = []
    for m in re.finditer(r"last frame: wait=(\d+) us copy=(\d+) us done=(\d+) us; "
                         r"imports=(\d+) import=(\d+) us encode=(\d+) us submit=(\d+) us "
                         r"gpu=(\d+) us sum=(\d+) us", text):
        stage.append(dict(wait=int(m.group(1)), copy=int(m.group(2)), imports=int(m.group(3)),
                          import_us=int(m.group(5)), encode=int(m.group(6)),
                          submit=int(m.group(7)), gpu=int(m.group(8)), total=int(m.group(9))))
    framed = [s for s in stage if s["imports"] >= 20]
    submit_median = statistics.median([s["submit"] for s in framed]) if framed else None
    print(f"stage samples: {len(stage)} ({len(framed)} with >=20 imports)")
    if framed:
        print(f"  frame-stage medians: import={statistics.median([s['import_us'] for s in framed]):.0f} "
              f"encode={statistics.median([s['encode'] for s in framed]):.0f} "
              f"submit={submit_median:.0f} gpu={statistics.median([s['gpu'] for s in framed]):.0f} "
              f"sum={statistics.median([s['total'] for s in framed]):.0f}")

    # --- layer 3: criteria -------------------------------------------------------------------
    checks = []
    def add(name, passed, detail):
        checks.append((name, passed, detail))

    bad = [m for m in ("panic(", "K60KEXC", "crashed: backboardd") if m in text]
    add("S1 no panic / no exception / no backboardd crash", not bad,
        f"found {bad}" if bad else "none")

    states = {c[0] for c in coh}
    add("S2 exactly one coherence verdict line", len(coh) == 1, f"{len(coh)} line(s)")

    if "on" in states:
        coherent_all = samples and all(s[1] == 1 for s in samples)
        monotonic = samples and all(b[2] >= a[2] for a, b in zip(samples, samples[1:]))
        grew = samples and samples[-1][2] > samples[0][2]
        add("S3 coherent=1 and skipped grows", bool(coherent_all and monotonic and grew),
            f"coherent_all={bool(coherent_all)} monotonic={bool(monotonic)} "
            f"skipped {samples[0][2] if samples else '-'}->{samples[-1][2] if samples else '-'}")
    else:
        add("S3 coherent=1 and skipped grows", False, "coherence is off, so S3 cannot hold")

    pub_us = [s[0] for s in samples if s[0] > 0]
    pub_median = statistics.median(pub_us) if pub_us else None
    add(f"S4 publish median < {PUBLISH_TARGET_US} us (was {PUBLISH_BEFORE_US})",
        pub_median is not None and pub_median < PUBLISH_TARGET_US,
        f"median={pub_median:.0f}" if pub_median is not None else "no samples")

    add(f"S5 submit median < {SUBMIT_TARGET_US} us (was {SUBMIT_BEFORE_US})",
        submit_median is not None and submit_median < SUBMIT_TARGET_US,
        f"median={submit_median:.0f}" if submit_median is not None else "no samples")

    adds = re.findall(r"actual GPU scanout copy completed", text)
    imports_ok = all(s["imports"] >= 20 for s in framed) if framed else False
    add("S6 still presents, imports==frames", scanouts >= 2 and imports_ok,
        f"scanout lines={scanouts} import growth={imports_ok}")

    poison = [m for m in ("GPU copy not retired", "poisoned") if m in text]
    add("S7 no poisoning", not poison, f"found {poison}" if poison else "none")

    print("\ncriteria")
    for name, passed, detail in checks:
        print(f"  {'PASS' if passed else 'FAIL'}  {name}  ({detail})")

    # --- failure rules ----------------------------------------------------------------------
    rules = []
    if bad:
        rules.append("F1 panic/exception/backboardd crash => set the default back to 0 immediately")
    if "off" in states:
        rules.append("F2 the probe honestly said no => do NOT force pong_gpu_coherent=1; read the probe row")
    if "on" in states and samples and samples[-1][2] == samples[0][2]:
        rules.append("F3 coherent=1 but skipped never grew => the skip predicate is not reached")
    if pub_median is not None and pub_median >= PUBLISH_BEFORE_US:
        rules.append("F4 publish did not fall => the 6.6 ms was not imported-frame maintenance")
    print("\nfailure rules hit")
    for rule in rules:
        print(f"  - {rule}")
    if not rules:
        print("  none")

    failed = [name for name, passed, _ in checks if not passed]
    verdict = "PASS" if not failed else f"FAIL ({','.join(n.split()[0] for n in failed)})"
    print(f"\nverdict: {verdict}")
    if framed and len(framed) >= 2:
        first, last = framed[0]["imports"], framed[-1]["imports"]
        elapsed_s = None
        m = re.search(r"scanout frames=(\d+) at (\d+)\.(\d+) s", text)
        if m and last > first:
            elapsed_s = (last - first)
            print(f"frames between samples: {elapsed_s} over the logged window")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    parser.add_argument("--card", default="docs/research/gpu/FLIGHT-CARD-20261119b.md")
    args = parser.parse_args()
    return judge(args.directory, args.card)


if __name__ == "__main__":
    sys.exit(main())
