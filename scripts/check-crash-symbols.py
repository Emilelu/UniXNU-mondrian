#!/usr/bin/env python3
"""Symbolicate the crash frames of a K60 console log against a dyld shared cache map.

The board has no serial console; the screen log is the evidence. Crash stacks in
console.log are raw addresses (0x19b42148c ...), so a frame can only be named
once the matching 20G81 dyld_shared_cache_arm64e.map is available. This checker
takes the log and the map and prints one line per frame. It stays dormant while
the cache is missing: exit 2 means "no evidence yet", not "no crash".

Usage:
    python3 scripts/check-crash-symbols.py --log console.log \
        --map dyld_shared_cache_arm64e.map [--cache dyld_shared_cache_arm64e] [--json]

Exit codes: 0 every cache-range frame resolved, 1 some cache-range frames
unresolved, 2 the map or log is missing or unreadable.
"""

import argparse
import bisect
import json
import os
import re
import sys
import tempfile

HEX = re.compile(r"0x([0-9a-fA-F]{8,16})")
MAP_LINE = re.compile(r"^\s*(?:0x)?([0-9a-fA-F]{6,16})\s*[:\s]\s*(\S.*)$")
MAP_OFFSET = re.compile(r"^\+0x[0-9a-fA-F]+:\s*")
CACHE_GAP = 0x80000  # a shared-cache symbol never spans more than half a megabyte


def parse_map(path):
    """Return sorted (address, name) pairs from a dyld shared cache .map file."""
    symbols = {}
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = MAP_LINE.match(line)
            if not match:
                continue
            name = MAP_OFFSET.sub("", match.group(2)).strip()
            if not name or name.startswith("-") or name.startswith("0x"):
                continue
            address = int(match.group(1), 16)
            symbols.setdefault(address, name)
    return sorted(symbols.items())


def collect_addresses(text):
    """Return the distinct frame addresses in the order they appear."""
    addresses = []
    seen = set()
    for line in text.splitlines():
        tokens = HEX.findall(line)
        if len(tokens) < 3:  # a stack line or the pc/lr/sp line, not a stray mention
            continue
        for token in tokens:
            value = int(token, 16)
            if value not in seen:
                seen.add(value)
                addresses.append(value)
    return addresses


def resolve(symbols, keys, address):
    """Name one address, or None when it lives outside the shared cache."""
    if address < symbols[0][0]:
        return None
    index = bisect.bisect_right(keys, address) - 1
    base, name = symbols[index]
    if address - base > CACHE_GAP:
        return None
    return "%s+0x%x" % (name, address - base)


def run(log_path, map_path, cache_path=None, want_json=False):
    if not os.path.isfile(map_path):
        print("check-crash-symbols: map not found: %s" % map_path)
        return 2
    if not os.path.isfile(log_path):
        print("check-crash-symbols: log not found: %s" % log_path)
        return 2
    symbols = parse_map(map_path)
    if not symbols:
        print("check-crash-symbols: no symbols parsed from %s" % map_path)
        return 2
    keys = [item[0] for item in symbols]
    with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    addresses = collect_addresses(text)
    frames = []
    resolved = 0
    unresolved = 0
    private = 0
    for address in addresses:
        name = resolve(symbols, keys, address)
        if name is None:
            if address < symbols[0][0]:
                private += 1
                frames.append({"address": "0x%x" % address, "symbol": None,
                               "note": "private segment or kernel, not in the shared cache"})
            else:
                unresolved += 1
                frames.append({"address": "0x%x" % address, "symbol": None,
                               "note": "gap in the map"})
        else:
            resolved += 1
            frames.append({"address": "0x%x" % address, "symbol": name})
    if want_json:
        print(json.dumps({"log": log_path, "map": map_path,
                          "symbols": len(symbols), "frames": frames,
                          "resolved": resolved, "unresolved": unresolved,
                          "private": private}, indent=2))
    else:
        cache = (" cache %s" % cache_path) if cache_path else ""
        print("check-crash-symbols: log %s, map %s (%d symbols)%s"
              % (log_path, map_path, len(symbols), cache))
        for frame in frames:
            if frame["symbol"]:
                print("  %-12s %s" % (frame["address"], frame["symbol"]))
            else:
                print("  %-12s (%s)" % (frame["address"], frame["note"]))
        print("check-crash-symbols: %d resolved, %d unresolved, %d private"
              % (resolved, unresolved, private))
    return 0 if unresolved == 0 else 1


def selftest():
    root = tempfile.mkdtemp(prefix="check-crash-symbols-")
    map_path = os.path.join(root, "cache.map")
    log_path = os.path.join(root, "console.log")
    with open(map_path, "w", encoding="utf-8") as handle:
        handle.write("0x180000000: __dyld_start\n"
                     "0x180001000 +0x0: exit\n"
                     "0x180010000: main\n")
    with open(log_path, "w", encoding="utf-8") as handle:
        handle.write("2026-11-03 04:32:41 backboardd[55:376] (0x180001234 0x180010010 0x180000001)\n"
                     "KXPC pc=0x180000008 lr=0x170000000 sp=0x16ecfd350\n")
    symbols = parse_map(map_path)
    keys = [item[0] for item in symbols]
    checks = [
        ("parse three symbols", len(symbols) == 3),
        ("offset prefix stripped", symbols[1][1] == "exit"),
        ("exit offset", resolve(symbols, keys, 0x180001234) == "exit+0x234"),
        ("main offset", resolve(symbols, keys, 0x180010010) == "main+0x10"),
        ("lowest symbol", resolve(symbols, keys, 0x180000001) == "__dyld_start+0x1"),
        ("pc frame", resolve(symbols, keys, 0x180000008) == "__dyld_start+0x8"),
        ("private frame", resolve(symbols, keys, 0x170000000) is None),
        ("frame count", len(collect_addresses(open(log_path, encoding="utf-8").read())) == 6),
    ]
    failed = [name for name, ok in checks if not ok]
    if failed:
        print("check-crash-symbols: selftest FAILED: %s" % ", ".join(failed))
        return 1
    print("check-crash-symbols: selftest ok (%d checks)" % len(checks))
    return 0


def main(argv):
    parser = argparse.ArgumentParser(description="Symbolicate crash frames from a K60 console log.")
    parser.add_argument("--log", help="console.log to read")
    parser.add_argument("--map", dest="map_path", help="dyld_shared_cache_arm64e.map")
    parser.add_argument("--cache", help="dyld_shared_cache_arm64e (optional, for the report)")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--selftest", action="store_true", help="run the built-in fixture")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.log or not args.map_path:
        print("check-crash-symbols: --log and --map are required (or --selftest)")
        return 2
    return run(args.log, args.map_path, args.cache, args.json)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
