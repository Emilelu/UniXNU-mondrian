#!/usr/bin/env python3
"""Compare the scan records the driver served with the list wifid handed to Settings.

Usage: diff-scan-list.py <console.log> [--ssid Emilelu_5G]
  * uses the LAST list logged with client='Preferences' (that is the one Settings shows);
  * mission18 and later logs carry a BSSID per record, so records match the list exactly;
  * mission16 and earlier only sampled three records per band, so those rows are SAMPLED.
"""
import re, sys
from pathlib import Path

BSS = re.compile(r"wifi-net: bss (\d+)/(\d+) (\d+) MHz (-?\d+) dBm age (\d+) bssid ([0-9a-f:]{17}) ie (\d+) cap ([0-9a-f]{4})(?: cc (\w\w|--))? ?(.*)$")
BAND = re.compile(r"wifi-net: scan band (\d+) MHz (-?\d+) dBm (.*)$")
NET = re.compile(r"<WiFiScanObserverNetwork : 0x[0-9a-f]+ SSID='(.*?)' BSSID='([0-9a-f:]{17})' RSSI=(-?\d+)>")

def rows_of(lines):
    rows = []
    for ln in lines:
        m = BSS.search(ln)
        if m:
            rows.append(dict(mhz=int(m.group(3)), rssi=int(m.group(4)), age=int(m.group(5)), bssid=m.group(6),
                             ie=int(m.group(7)), cap=m.group(8), cc=m.group(9) or "", ssid=m.group(10).strip()))
            continue
        m = BAND.search(ln)
        if m:
            rows.append(dict(mhz=int(m.group(1)), rssi=int(m.group(2)), age=-1, bssid="", ie=-1, cap="----",
                             cc="", ssid=m.group(3).strip()))
    seen, uniq = set(), []
    for r in reversed(rows):
        key = (r["bssid"], r["ssid"], r["mhz"], r["rssi"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    return list(reversed(uniq))

def lists(lines):
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        if "_handleScanResults" in ln and "results='{(" in ln:
            m = re.search(r"client='([^']*)'", ln)
            cur = []
            for e in NET.finditer(ln):
                cur.append(dict(ssid=e.group(1), bssid=e.group(2), rssi=int(e.group(3))))
            i += 1
            while i < len(lines) and "_handleScanResults" not in lines[i]:
                for e in NET.finditer(lines[i]):
                    cur.append(dict(ssid=e.group(1), bssid=e.group(2), rssi=int(e.group(3))))
                i += 1
            out.append(dict(client=m.group(1) if m else "?", entries=cur))
            continue
        i += 1
    return out

def band(mhz):
    return "6" if mhz >= 5925 else ("5" if mhz >= 4900 else "2.4")

def main():
    args = [a for a in sys.argv[1:]]
    want = "Emilelu_5G"
    if "--ssid" in args:
        k = args.index("--ssid")
        want = args[k + 1]
        del args[k:k + 2]
    if len(args) != 1:
        print("usage: diff-scan-list.py <console.log> [--ssid NAME]")
        return 2
    path = Path(args[0])
    lines = path.read_text(errors="replace").splitlines()
    rows, ls = rows_of(lines), lists(lines)
    print("console %s: %d distinct records, %d observer lists" % (path.name, len(rows), len(ls)))
    if not rows:
        print("NO-RECORDS: this log has neither per-record dumps nor per-band samples")
        return 1
    pref = [l for l in ls if l["client"] == "Preferences"]
    chosen = (pref or ls or [None])[-1]
    if not chosen:
        print("NO-LIST: nobody opened Settings, so the daemon's own list is unobserved")
        return 0
    pr = chosen["entries"]
    if chosen["client"] != "Preferences":
        print("NO-PANE-LIST: no Preferences list; the nearest is client=%s (%d entries)" % (chosen["client"], len(pr)))
    else:
        print("pane list: client=Preferences, %d entries" % len(pr))
    print("the pane list mentions %r %d time(s); it holds %d entries with an SSID"
          % (want, sum(1 for p in pr if p["ssid"] == want), sum(1 for p in pr if p["ssid"])))
    by_bssid = {p["bssid"]: p for p in pr}
    kept = dropped = sampled = 0
    for r in rows:
        if not r["bssid"]:
            sampled += 1
            print("SAMPLED %-3s %5d MHz %4d dBm  %s" % (band(r["mhz"]), r["mhz"], r["rssi"], r["ssid"] or "<hidden>"))
            continue
        hit = by_bssid.get(r["bssid"])
        if hit:
            kept += 1
            print("KEPT    %-3s %5d MHz %4d dBm ie %3d cap %s  %s -> pane %r %d dBm"
                  % (band(r["mhz"]), r["mhz"], r["rssi"], r["ie"], r["cap"], r["ssid"] or "<hidden>",
                     hit["ssid"], hit["rssi"]))
        else:
            dropped += 1
            print("DROPPED %-3s %5d MHz %4d dBm ie %3d cap %s  %s"
                  % (band(r["mhz"]), r["mhz"], r["rssi"], r["ie"], r["cap"], r["ssid"] or "<hidden>"))
    print("summary: %d kept, %d dropped, %d sampled of %d records" % (kept, dropped, sampled, len(rows)))
    for r in rows:
        if want in (r["ssid"] or ""):
            verdict = "SAMPLED" if not r["bssid"] else ("KEPT" if r["bssid"] in by_bssid else "DROPPED")
            print("target %r at %d MHz %d dBm: %s" % (want, r["mhz"], r["rssi"], verdict))
    return 0

if __name__ == "__main__":
    sys.exit(main())