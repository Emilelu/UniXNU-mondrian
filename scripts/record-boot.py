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


def image_manifest(image):
    """The build manifest that travelled with the image, or None.

    P-211: the ledger used to describe whatever series the *repo* carried at
    record time, so a boot of another line's image was written down as a boot of
    this repo's series.  build-strict.sh already writes
    ``build-manifest.json`` next to ``boot.img``; read that when it exists.
    """
    for candidate in (os.path.join(os.path.dirname(os.path.abspath(image)),
                                   "build-manifest.json"),
                      os.path.splitext(os.path.abspath(image))[0] + ".json"):
        if os.path.isfile(candidate):
            try:
                with open(candidate, encoding="utf-8") as fh:
                    return candidate, json.load(fh)
            except (OSError, ValueError):
                return candidate, None
    return None, None


def image_series(image):
    """(fingerprint, count, source, repo_fingerprint) for the image being recorded."""
    repo_fp, _ = series_fingerprint()
    path, data = image_manifest(image)
    if not data:
        return repo_fp, None, "repo-series", repo_fp
    series = data.get("series") or {}
    sha = str(series.get("sha256") or "")
    count = series.get("count")
    if len(sha) < 16:
        return repo_fp, count, "repo-series", repo_fp
    return sha[:16], count, "manifest:%s" % path, repo_fp


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

    fp, n, source, repo_fp = image_series(a.image)
    if n is None:
        n = series_fingerprint()[1]
    if source != "repo-series" and fp != repo_fp:
        print("⚠ the image was built from series %s, this repo carries %s;"
              % (fp, repo_fp))
        print("  recording the image's series so the ledger cannot claim the"
              " repo series booted (P-211)")
    rec = {
        "at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "result": "ok",
        "log-bytes": size,
        "image": "%s(%s)" % (os.path.basename(a.image), a.image[-12:]),
        "series": fp,
        "series-count": n,
        "series-source": source,
        "repo-series": repo_fp,
        "note": a.note or "recorded by scripts/record-boot.py",
        "console": a.log,
        "springboard-lines": up,
    }
    line = json.dumps(rec, ensure_ascii=False)
    if a.dry_run:
        print("would append: %s" % line)
        print("series %s (%d patches) from %s" % (fp, n, source))
        return 0
    with open(LEDGER, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print("✅ recorded series %s (%d patches) from %s, %d SpringBoard lines,"
          " %d bytes" % (fp, n, source, up, size))
    return 0


if __name__ == "__main__":
    sys.exit(main())