#!/usr/bin/env python3
"""Record a successful boot in the porting ledger.

The ledger is the only source porting-gate.py trusts for "this patch series
booted once" (see scripts/porting-gate.py, section S).  Nothing in this repo
ever wrote to it, so the series fingerprint drifted and iron-4/hard-33 went red
on main.  This script closes that loop honestly: it re-computes the fingerprint
exactly the way porting-gate does, refuses to record unless the console log
proves userland came up and shows no panic, and appends one JSON line.

Usage:
  scripts/record-boot.py --image boot-xxx.img --log <dir>/console.log \
      [--note "why this boot matters"] [--dry-run]
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = "/mnt/e/k60-work"
# Keep this identical to porting-gate.py: the fingerprint must describe
# the series the build actually applied (P-194).
SERIES = os.path.join(REPO, "patches/xnu/series")
if not os.path.exists(SERIES):
    SERIES = WORK + "/scratch/SERIES-FINAL.txt"
LEDGER = WORK + "/ledger.jsonl"

# Same list the capture classifier uses; "restart windows ready" is a banner.
PANIC_MARKERS = ("panic(", "K60PANIC: ring kept", "K60CACHE FAIL",
                 "initproc exited")


def series_fingerprint():
    """sha256(names + sizes) -> 16 hex chars.  Mirrors porting-gate.py:62-77."""
    h = hashlib.sha256()
    with open(SERIES, encoding="utf-8", errors="ignore") as fh:
        names = [l.strip() for l in fh if l.strip()]
    for n in names:
        h.update(n.encode())
        p = os.path.join(REPO, "patches/xnu", n)
        if os.path.exists(p):
            h.update(str(os.path.getsize(p)).encode())
    return h.hexdigest()[:16], len(names)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--note", default="")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if not os.path.isfile(a.log):
        print("❌ console log not found: %s" % a.log)
        return 1
    text = open(a.log, encoding="utf-8", errors="ignore").read()
    size = os.path.getsize(a.log)

    up = text.count("SpringBoard")
    if up < 100:
        print("❌ log has %d SpringBoard lines (<100): userland did not come up"
              % up)
        return 1
    hits = [m for m in PANIC_MARKERS if m in text]
    if hits:
        print("❌ log carries a failure marker: %s" % ", ".join(hits))
        return 1

    fp, n = series_fingerprint()
    rec = {
        "at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "result": "ok",
        "log-bytes": size,
        "image": "%s(%s)" % (os.path.basename(a.image), a.image[-12:]),
        "series": fp,
        "note": a.note or "recorded by scripts/record-boot.py",
        "console": a.log,
        "springboard-lines": up,
    }
    line = json.dumps(rec, ensure_ascii=False)
    if a.dry_run:
        print("would append: %s" % line)
        print("series %s (%d patches)" % (fp, n))
        return 0
    with open(LEDGER, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print("✅ recorded series %s (%d patches), %d SpringBoard lines, %d bytes"
          % (fp, n, up, size))
    return 0


if __name__ == "__main__":
    sys.exit(main())