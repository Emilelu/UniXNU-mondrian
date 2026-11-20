#!/usr/bin/env python3
"""Fixture suite for scripts/read-fdt-props.py.

The tool exists because a contract second source has to be re-readable, so its
own parser needs the same treatment: a synthetic tree built here exercises the
padding rules that cost the first hand-rolled walker half a day, and the real
device dump (when this host has it) is read back to the five thermal trip
values the contract table cites.
"""

import json
import os
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "read-fdt-props.py"
REAL_CANDIDATES = [Path("E:/k60-work/reports/live-6033dbec-fdt.dtb"),
                   Path("/mnt/e/k60-work/reports/live-6033dbec-fdt.dtb")]
REAL = next((path for path in REAL_CANDIDATES if path.exists()), REAL_CANDIDATES[0])

BEGIN_NODE, END_NODE, PROP, END = 1, 2, 3, 9
NUL = chr(0).encode()
FAILURES = []
CHECKS = 0


def check(condition, message):
    global CHECKS
    CHECKS += 1
    if not condition:
        FAILURES.append(message)
        print("FAIL: %s" % message)


def pad(blob, base):
    return blob + bytes((4 - ((len(blob) - base) % 4)) % 4)


def build_tree(build):
    """Write a small FDT under build/ and return its path."""
    strings = bytearray()
    offsets = {}

    def name_offset(name):
        if name not in offsets:
            offsets[name] = len(strings)
            strings.extend(name.encode() + NUL)
        return offsets[name]

    body = bytearray()

    def begin(name):
        body.extend(struct.pack(">I", BEGIN_NODE))
        padded = name.encode() + NUL
        body.extend(padded + bytes((4 - (len(padded) % 4)) % 4))

    def prop(name, value):
        body.extend(struct.pack(">III", PROP, len(value), name_offset(name)))
        body.extend(value + bytes((4 - (len(value) % 4)) % 4))

    def end():
        body.extend(struct.pack(">I", END_NODE))

    begin("")
    prop("compatible", b"k60-test" + NUL + NUL)
    begin("soc")
    begin("thermal-zones")
    begin("ddr")
    begin("trips")
    begin("ddr0-config")
    prop("temperature", struct.pack(">I", 90000))
    prop("hysteresis", struct.pack(">I", 5000))
    prop("type", b"passive" + NUL)
    prop("flag", b"ab" + NUL)
    end()
    end()
    end()
    end()
    end()
    end()
    body.extend(struct.pack(">I", END))

    off_rsv = 40
    rsv = struct.pack(">QQ", 0, 0)
    off_struct = off_rsv + len(rsv)
    off_strings = off_struct + len(body)
    total = off_strings + len(strings)
    header = struct.pack(">10I", 0xD00DFEED, total, off_struct, off_strings, off_rsv,
                         17, 16, 0, len(strings), len(body))
    path = build / "test.dtb"
    path.write_bytes(header + rsv + bytes(body) + bytes(strings))
    return path



def build_root_only(build):
    """A structurally valid tree whose walker finds nothing but the root."""
    strings = b"" + NUL
    body = bytearray()
    body.extend(struct.pack(">I", BEGIN_NODE))
    body.extend(NUL + b"\0\0\0")
    body.extend(struct.pack(">I", END_NODE))
    body.extend(struct.pack(">I", 4) * 20)
    body.extend(struct.pack(">I", END))
    off_rsv = 40
    rsv = struct.pack(">QQ", 0, 0)
    off_struct = off_rsv + len(rsv)
    off_strings = off_struct + len(body)
    total = off_strings + len(strings)
    header = struct.pack(">10I", 0xD00DFEED, total, off_struct, off_strings, off_rsv,
                         17, 16, 0, len(strings), len(body))
    path = build / "root-only.dtb"
    path.write_bytes(header + rsv + bytes(body) + strings)
    return path


def run(*args):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run([sys.executable, str(TOOL)] + [str(arg) for arg in args],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", env=env)
    return completed.returncode, completed.stdout, completed.stderr


def main():
    build = ROOT / "build" / ("read-fdt-tests-%d" % os.getpid())
    build.mkdir(parents=True, exist_ok=True)
    dtb = build_tree(build)

    code, out, _ = run(dtb, "--list")
    check(code == 0, "--list exits 0")
    lines = out.splitlines()
    check(lines[0] == "/", "the root node prints first, got %r" % (lines[:1],))
    check("/soc/thermal-zones/ddr/trips/ddr0-config" in lines,
          "the nested node path is built from padded names")

    code, out, _ = run(dtb, "--list", "--contains", "trips")
    check(code == 0 and len(out.splitlines()) == 2, "--contains filters the listing")

    code, out, _ = run(dtb, "--node", "/soc/thermal-zones/ddr/trips/ddr0-config")
    check(code == 0, "--node exits 0")
    check("temperature = 0x00015f90" in out, "a 32-bit cell prints as hex, got %r" % out)
    check("type = passive" in out, "a NUL terminated string prints as text")
    check("flag = ab" in out, "a short NUL terminated string prints as text")
    check("hysteresis = 0x00001388" in out, "the property after a 3-byte value is still found")

    code, out, _ = run(dtb, "--node", "/soc/thermal-zones/ddr/trips/ddr0-config",
                       "--prop", "temperature", "--hex")
    check(code == 0 and out.strip() == "00015f90", "--hex prints the raw bytes, got %r" % out)

    code, out, _ = run(dtb, "--node", "/soc/nope")
    check(code == 2, "a missing node exits 2")
    check("no node /soc/nope" in out, "a missing node says so")
    check("the dump has 6 node(s)" in out, "a missing node says how many the walker did see")
    code, out, err = run(dtb, "--list", "--contains", "no-such-node")
    check(code == 0 and not out.strip(), "a filter that matches nothing prints nothing")
    check("0 of 6 node(s) contain" in err,
          "a zero match is counted out loud, got %r" % err)

    code, out, err = run(dtb, "--list")
    check("6 node(s)" in err, "a plain listing says how many it printed, got %r" % err)

    lonely = build_root_only(build)
    code, out, _ = run(lonely, "--list")
    check(code == 3 and "the parser, not the dump, is wrong" in out,
          "a walker that finds only the root refuses its own result, got %d %r" % (code, out))

    code, out, _ = run(dtb, "--node", "/soc", "--prop", "nope")
    check(code == 2 and "has no property nope" in out, "a missing property exits 2 and lists what exists")

    junk = build / "junk.dtb"
    junk.write_bytes(b"not a device tree at all, but long enough to hold a header......")
    code, out, _ = run(junk, "--list")
    check(code == 3 and "not a flattened device tree" in out, "a non-FDT file exits 3, got %d %r" % (code, out))

    code, out, _ = run(dtb)
    check(code == 2, "asking for nothing is a usage error")

    code, out, _ = run(dtb, "--json")
    check(code == 0, "--json exits 0")
    try:
        tree = json.loads(out)
    except ValueError as error:
        tree = None
        check(False, "--json prints JSON (%s)" % error)
    if tree is not None:
        leaf = tree.get("/soc/thermal-zones/ddr/trips/ddr0-config", {})
        check(leaf.get("temperature") == "00015f90", "the JSON view keeps the raw hex")

    if REAL.exists():
        code, out, _ = run(REAL, "--node", "/soc/thermal-zones/ddr/trips/ddr0-config",
                           "--prop", "temperature", "--hex")
        check(code == 0 and out.strip() == "00015f90", "the real dump's ddr0 trip reads 90000")
        expected = {
            ("gpuss-0", "tj_cfg"): "00017318",
            ("cpu-1-0", "cpu4-emerg0-cfg"): "0001adb0",
            ("aoss-0", "reset-mon-cfg"): "0001c138",
            ("pa", "thermal-engine-config0"): "0001e848",
        }
        for (zone, trip), hex_value in expected.items():
            code, out, _ = run(REAL, "--node", "/soc/thermal-zones/%s/trips/%s" % (zone, trip),
                               "--prop", "temperature", "--hex")
            check(code == 0 and out.strip() == hex_value,
                  "the real dump's %s/%s reads %s, got %r" % (zone, trip, hex_value, out))
    else:
        print("note: %s is not on this host; the real dump half is skipped" % REAL)

    total = CHECKS
    print("TESTS OK %d checks (%d failure(s))" % (total, len(FAILURES)))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
