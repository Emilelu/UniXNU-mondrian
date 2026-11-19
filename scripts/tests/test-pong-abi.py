#!/usr/bin/env python3
"""Offline verification for the framework ABI shapes in drivers/PongWifi/PongWifiAbi.h.

Compiles the header with its host self-test, runs it, then checks the constants and the anchors in
drivers/PongWifi/PongWifiNet.cpp that serve the 24A446 scan record, scan request and association
event. Exit code 0 means every check passed; the summary format matches test-pong-sae.py.
"""
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "drivers/PongWifi"
HEADER = SRC / "PongWifiAbi.h"
NET = SRC / "PongWifiNet.cpp"
SELFTEST = pathlib.Path(__file__).resolve().parent / "pong-abi-selftest.c"

checks = 0
failures = []


def check(ok, what):
    global checks
    checks += 1
    if ok:
        print("  PASS " + what)
    else:
        failures.append(what)
        print("  FAIL " + what)


def sheng_number(text, name):
    m = re.search(r"#define\s+%s\s+\(?(0x[0-9a-fA-F]+|\d+)" % name, text)
    return int(m.group(1), 0) if m else None


def check_reference():
    """The 24A446 shapes were derived from the sheng port; compare them while that checkout exists."""
    import os
    repo = pathlib.Path(os.environ.get("K60_SHENG_REPO") or (ROOT.parent / "UniXNU-sheng"))
    if not (repo / ".git").exists():
        print("  SKIP the sheng 27 reference is not checked out")
        return
    def show(path):
        r = subprocess.run(["git", "-C", str(repo), "show", "origin/main:" + path], capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else ""
    result = show("package/WifiScanResult.h")
    scan = show("package/WifiScan.h")
    net = show("package/WifiNet.cpp")
    if not result or not scan:
        print("  SKIP origin/main does not carry the 27 wifi headers")
        return
    header = HEADER.read_text(encoding="utf-8")
    for ours, theirs, name in (
        ("PONG_SCAN_RECORD_24A446", "SHENG_WIFI_SCAN_RESULT_BYTES", "the record size"),
        ("PONG_SCAN_ELEMENTS_OFFSET", "SHENG_WIFI_SCAN_ELEMENTS", "the element offset"),
        ("PONG_SCAN_ELEMENTS_BYTES", "SHENG_WIFI_SCAN_ELEMENTS_BYTES", "the element bytes"),
        ("PONG_SCAN_TIMESTAMP_OFFSET", "SHENG_WIFI_SCAN_TIMESTAMP", "the timestamp offset"),
        ("PONG_WIFI_CAPS_BYTES", "SHENG_WIFI_CAPS_BYTES", "the capability answer size"),
    ):
        mine = sheng_number(header, ours)
        ref = sheng_number(result if "SCAN" in theirs else scan, theirs)
        check(mine is not None and mine == ref, "%s still matches the sheng port (%s)" % (name, theirs))
    for anchor, what in (
        ("0x8 the number of SSID entries", "the reference still puts the names at 0xc"),
        ("0x200 the scan type", "the reference still puts the scan type at 0x200"),
        ("0x210/0x214 the channels", "the reference still puts the channels at 0x210"),
    ):
        check(anchor in scan, what)
    if net:
        check("0x290" in net and "540" in net and "0x214" in net and "0x218" in net,
              "the reference still uses the 0x290 request and the 540-byte completion event")


def main():
    for path in (HEADER, NET, SELFTEST):
        if not path.is_file():
            print("FAIL: missing %s" % path)
            return 1
    text = HEADER.read_text(encoding="utf-8")
    net = NET.read_text(encoding="utf-8")

    check("#define PONG_SCAN_RECORD_24A446 0x8e8u" in text, "the 24A446 scan record is 0x8e8 bytes")
    check("#define PONG_SCAN_ELEMENTS_BYTES 2048u" in text, "the element area is 2048 bytes")
    check("#define PONG_SCAN_TIMESTAMP_OFFSET 0x8d0u" in text, "the timestamp sits at 0x8d0")
    check("#define PONG_ASSOC_REQUEST_24A446 0x290u" in text, "the 24A446 association request is 0x290 bytes")
    check("struct pong_assoc_event27" in text and "uint32_t reason, result, has_result;" in text,
          "the association event carries attempts, reason, result and validity")
    check("#define PONG_WIFI_CAP_NAMED_SCAN 22u" in text and "#define PONG_WIFI_CAP_SCAN_DONE_EVENT 46u" in text,
          "the two scan capability bits are named")
    check("static inline uint32_t pong_scan_elements_room(uint32_t request_bytes)" in text,
          "the element room follows the request")
    check("#define PONG_SCAN_TYPE_CACHED 3u" in text, "scan type 3 means the results already held")
    check("pong_scan_multiple_parse" in text and "pong_scan_frequencies" in text,
          "the named scan and its channels are parsed")

    check("static_assert(sizeof(scan_result)==PONG_SCAN_RECORD_24A446" in net and
          "__builtin_offsetof(scan_result,timestamp_ns)==PONG_SCAN_TIMESTAMP_OFFSET" in net,
          "the served record asserts the 24A446 size and timestamp offset")
    check("pong_scan_elements_room(request_bytes ? request_bytes : PONG_SCAN_RECORD_24A446)" in net,
          "the driver asks how much room the request leaves")
    check("sizeof(pong_assoc_event27)" in net, "the completion event is posted at its 24A446 size")
    check("nw_wifi_scan_frequencies" in net, "the driver asks the station for the named channels")

    with tempfile.TemporaryDirectory() as td:
        exe = pathlib.Path(td) / "pong-abi-selftest"
        cc = subprocess.run(
            ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1", "-I", str(SRC), str(SELFTEST), "-o", str(exe)],
            capture_output=True, text=True)
        check(cc.returncode == 0, "the header and its self-test compile clean" + ("" if cc.returncode == 0 else ": " + cc.stderr.strip()[:300]))
        if cc.returncode == 0:
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            m = re.search(r"(\d+) checks passed, (\d+) failed", run.stdout)
            check(run.returncode == 0, "the self-test exits zero")
            check(m is not None, "the self-test reports its counts")
            if m:
                check(int(m.group(1)) >= 20, "the self-test runs at least twenty checks")
                check(int(m.group(2)) == 0, "the self-test reports no failure")
            print("    " + run.stdout.strip().replace("\n", "\n    "))

    check_reference()

    print("%d checks, %d failure(s)" % (checks, len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
