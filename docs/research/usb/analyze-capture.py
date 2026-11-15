#!/usr/bin/env python3
"""Evaluate the RESEARCH.md section 18 criteria against one capture evidence directory.

Usage: analyze-capture.py <evidence-dir>

Reads console.log + capture.json + boot.json and prints a PASS/FAIL/SKIP table for the
on-device criteria of RESEARCH.md section 18.3 (criteria 1-6, 5b, 5c). Read-only; never modifies evidence.

Three details that each cost a debugging round and are therefore encoded here:
  * the capture tools are PowerShell and write JSON with a UTF-8 BOM, so every JSON
    read must use encoding="utf-8-sig" (a plain json.load raises
    "Unexpected UTF-8 BOM (decode using utf-8-sig)");
  * one heartbeat tick prints TWO "K60 USBHB" lines (a DSTS line and a GDSC/QSCRATCH
    line), so the tick count is the number of "... USBHB: DSTS ..." lines;
  * a capture that recorded zero bytes cannot say anything about the image's
    descriptors, so criteria 3 and 4 report SKIP instead of FAIL;
  * patch 0410 renamed the configuration line from "composite cfg" to "cfg" and
    appended "echo <on> on <out>/<in>", so criterion 4 must accept both spellings
    or every 0410 image reads as a missing descriptor line;
  * patch 0411 sends "K60BEACON: ..." lines on EP3 without the ramoops ring
    and without passing the console gate, so criterion 5c reports them as the
    witness that the gate opened; an image without beacons says SKIP.
"""
import datetime
import json
import os
import re
import sys


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}
    except Exception as exc:                                  # noqa: BLE001
        return {"_error": "%s: %s" % (type(exc).__name__, exc)}


def parse_ts(value):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except ValueError:
        return None


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    evd = argv[1]
    log = os.path.join(evd, "console.log")
    if not os.path.isfile(log):
        print("FAIL  no console.log in %s" % evd)
        return 2
    with open(log, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    cap = load_json(os.path.join(evd, "capture.json"))
    boot = load_json(os.path.join(evd, "boot.json"))

    usblog = len(re.findall(r"^K60 USBLOG", text, re.M))
    ticks = len(re.findall(r"^K60 USBHB: DSTS", text, re.M))
    rows = []

    def row(name, v, detail):
        rows.append((name, v, detail))

    def verdict(ok):
        return "PASS" if ok else "FAIL"

    has_dev = "setup 80 06 0100 len 64" in text
    has_cfg98 = "setup 80 06 0200 len 98" in text
    silent = cap.get("bytes") == 0 or not text

    # 1 console alive
    row("1 console alive", verdict(usblog >= 250 and has_dev),
        "K60 USBLOG=%d GET_DESC(device)=%s GET_DESC(config 98B)=%s"
        % (usblog, has_dev, has_cfg98))

    # 2 heartbeat: one tick every 2 s of capture time
    start = parse_ts(cap.get("startedAt"))
    end = parse_ts(cap.get("lastDataAt")) or parse_ts(cap.get("finishedAt"))
    dur = (end - start).total_seconds() if start and end else 0.0
    expect = dur / 2.0
    hb_ok = ticks > 0 and (expect <= 0 or abs(ticks - expect) <= max(3.0, expect * 0.10))
    row("2 heartbeat", verdict(hb_ok),
        "ticks=%d expected~%.0f (capture %.0f s, 2 lines per tick)"
        % (ticks, expect, dur))

    skip_reason = None
    if silent:
        skip_reason = "capture recorded 0 bytes: the image never spoke, descriptors unknown"
    elif not has_cfg98:
        skip_reason = "image predates 0406 (host never asked for the 98-byte configuration)"

    # 3 physical endpoint budget (0407 diagnostic)
    m = re.search(r"GHWPARAMS1 0x([0-9a-fA-F]{8}) GHWPARAMS3 0x([0-9a-fA-F]{8}) "
                  r"GTXFIFOSIZ 0x([0-9a-fA-F]{8}) 0x([0-9a-fA-F]{8}) "
                  r"0x([0-9a-fA-F]{8}) 0x([0-9a-fA-F]{8})", text)
    if m:
        p3 = int(m.group(2), 16)
        neps = (p3 >> 12) & 0x3F
        ineps = (p3 >> 18) & 0x1F
        row("3 endpoint budget", verdict(neps >= 8 and ineps >= 4),
            "GHWPARAMS3=0x%08x NUM_EPS=%d NUM_IN_EPS=%d GTXFIFOSIZ=%s"
            % (p3, neps, ineps, " ".join(m.group(i) for i in (3, 4, 5, 6))))
    elif skip_reason:
        row("3 endpoint budget", "SKIP", skip_reason)
    else:
        row("3 endpoint budget", "FAIL",
            "98-byte configuration was requested but no GHWPARAMS1 line appeared: 0407 is missing from the image")

    # 4 EP6/EP7 configuration result (0407 diagnostic)
    m = re.search(r"(?:composite )?cfg (\d+) bytes ep6 (-?\d+) ep7 (-?\d+) "
                  r"DALEPENA 0x([0-9a-fA-F]{8})(?: echo (-?\d+) on (\d+)/(\d+))?", text)
    if m:
        ep6, ep7 = int(m.group(2)), int(m.group(3))
        dalep = int(m.group(4), 16)
        echo = ""
        if m.group(5) is not None:
            echo = "; echo=%s on ep%s/ep%s" % (m.group(5), m.group(6), m.group(7))
        row("4 EP6/EP7 configured", verdict(ep6 == 0 and ep7 == 0),
            "cfg=%sB ep6=%d ep7=%d DALEPENA=0x%08x%s (expect ep6/ep7=0, DALEPENA=0x000000ef)"
            % (m.group(1), ep6, ep7, dalep, echo))
    elif skip_reason:
        row("4 EP6/EP7 configured", "SKIP", skip_reason)
    else:
        row("4 EP6/EP7 configured", "FAIL",
            "composite cfg line not found although the 98-byte configuration was requested")

    # 5 teardown tolerated: ENDTRANSFER status lines are allowed, a dead console is not
    ends = re.findall(r"K60 USBLOG: ep(\d+) cmd 0x8 status (\d+)", text)
    if ends:
        idx = text.rfind("cmd 0x8 status")
        hb_after = "K60 USBHB" in text[idx:]
    else:
        hb_after = ticks > 0
    row("5 teardown tolerated", verdict(hb_after and usblog >= 250),
        "ENDTRANSFER status lines=%d %s; heartbeat after them=%s"
        % (len(ends), ends[:3], hb_after))

    # 5b vendor loopback echo (0410): only a mode 1/2 image that armed the
    # vendor pair can produce these lines; a console-only image must say SKIP.
    echoes = re.findall(r"K60 USBLOG: echo (\d+) bytes on ep(\d+) \(total (\d+)\)", text)
    if echoes:
        row("5b vendor echo", verdict(True),
            "%d echo line(s), first=%s bytes on ep%s (total %s)"
            % (len(echoes), echoes[0][0], echoes[0][1], echoes[0][2]))
    elif m and m.group(5) is not None and m.group(5) != "0":
        if (m.group(6), m.group(7)) == ("2", "3"):
            row("5b vendor echo", "SKIP",
                "mode 2 image: the echo rides the CDC pair ep2/ep3, not the vendor pair")
        else:
            row("5b vendor echo", "SKIP",
                "image armed the vendor pair (echo=1 on ep%s/ep%s) but the host never wrote to it"
                % (m.group(6), m.group(7)))
    else:
        row("5b vendor echo", "SKIP",
            "image did not arm the vendor pair (no k60_usbvend boot argument)")

    # 5c mode-1 beacons (0411): an out-of-band witness on EP3 that reads no
    # ramoops ring and passes no console gate, so it answers whether the
    # gate ever opened even when the console itself stays silent.
    beacons = re.findall(r"K60BEACON: (\S.*)$", text, re.M)
    if beacons:
        have_cfg = any(b.startswith("cfg mode1") for b in beacons)
        have_dtr = any(b.startswith("dtr ") for b in beacons)
        have_gate = any(b.startswith("gate open") for b in beacons)
        row("5c mode1 beacons", verdict(have_cfg and have_dtr and have_gate),
            "%d line(s): cfg=%s dtr=%s gate=%s -> %s"
            % (len(beacons), have_cfg, have_dtr, have_gate, " | ".join(beacons[-4:])))
    elif silent:
        row("5c mode1 beacons", "SKIP",
            "0 bytes recorded: no 0411 beacon reached the host (mode 2 gates them by design)")
    else:
        row("5c mode1 beacons", "SKIP",
            "no K60BEACON lines: image carries no 0411, or the host never read EP3")

    # 6 capture complete
    state = cap.get("state")
    complete = cap.get("complete")
    panic = cap.get("panicMarker")
    row("6 capture complete",
        verdict(state == "captured-budget-complete" and complete is True and not panic),
        "state=%s complete=%s panicMarker=%s bytes=%s"
        % (state, complete, panic, cap.get("bytes")))

    print("evidence: %s" % evd)
    print("image   : %s  bootAccepted=%s returnedToFastboot=%s"
          % (str(boot.get("imageSha256"))[:16] or "?", boot.get("bootAccepted"),
             boot.get("returnedToFastboot")))
    print()
    width = max(len(r[0]) for r in rows)
    for name, v, detail in rows:
        print("%-*s  %-4s  %s" % (width, name, v, detail))
    bad = [r for r in rows if r[1] == "FAIL"]
    skip = [r for r in rows if r[1] == "SKIP"]
    print()
    print("result: %s (%d pass, %d fail, %d skip of %d)"
          % ("ALL PASS" if not bad else "FAIL",
             len(rows) - len(bad) - len(skip), len(bad), len(skip), len(rows)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
