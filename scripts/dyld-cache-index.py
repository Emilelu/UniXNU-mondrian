#!/usr/bin/env python3
"""Name the frames of a K60 crash stack without a device and without a .map.

A console.log carries two things this script needs:

  * the shared-cache slide, printed by our own service scan as
    "K60SR26 t=75 start=0x1946b0000 slide=0x146b0000";
  * the raw frames of the first-throw stack (one long line of hex words).

What it was missing is the image table: which dylib sits at which unslid
address. That table is inside the IPSW. The 20G81 SystemOS cryptex carries the
dyld shared cache as a set of "dyld_v1   arm64" members, and the first member
holds imagesText - 2620 records of uuid[16] | loadAddress | textSize |
pathOffset. Carving those 32-byte records is enough to turn every frame into
/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation+0x948c.

That is image-level, not symbol-level: a function name still needs the .map.
For the crash families we read (a selector mismatch, a nil URL) the image and
the offset are already the answer, and they cost no adb pull.

Usage:
    # once, from the local IPSW (about 90 s on the 2.5 GB cryptex image)
    python3 scripts/dyld-cache-index.py --dmg 096-56782-083.dmg \
        --out /mnt/e/iOS Port/Work/caches/20G81/dyld-index-20G81.json

    # per crash log
    python3 scripts/dyld-cache-index.py --index dyld-index-20G81.json \
        --log console.log [--json] [--frame-limit 24]

Exit codes: 0 every cache frame resolved, 1 some frames outside the index,
2 the index or the log is missing or unreadable.
"""

import argparse
import bisect
import json
import os
import re
import struct
import sys
import tempfile

MAGIC = b"dyld_v1"
HEADER_READ = 0x1000
RECORD = 32
BLOCK = 8 << 20
SLIDE = re.compile(r"K60SR\d+\s+t=\d+\s+start=0x([0-9a-fA-F]+)\s+slide=0x([0-9a-fA-F]+)")
HEX = re.compile(r"0x([0-9a-fA-F]{6,16})")


def u32(buf, off):
    return struct.unpack_from("<I", buf, off)[0]


def u64(buf, off):
    return struct.unpack_from("<Q", buf, off)[0]


def parse_member(fh, offset):
    """Return the imagesText records of one cache member, or None."""
    fh.seek(offset)
    head = fh.read(HEADER_READ)
    if len(head) < HEADER_READ or head[:7] != MAGIC:
        return None
    arch = head[0x10:0x20].split(b"\0")[0].decode("latin1", "replace")
    text_off, text_count = u64(head, 0x88), u64(head, 0x90)
    if not text_count or not text_off:
        return None
    need = text_off + text_count * RECORD
    if need > HEADER_READ:
        fh.seek(offset + text_off)
        table = fh.read(text_count * RECORD)
    else:
        table = head[text_off:need]
    if len(table) < text_count * RECORD:
        return None
    records = []
    for index in range(text_count):
        base = index * RECORD
        load, size, path_off = struct.unpack_from("<QII", table, base + 16)
        records.append({"load": load, "size": size, "pathOffset": path_off,
                        "uuid": table[base:base + 16].hex()})
    return {"offset": offset, "arch": arch, "records": records}


def find_index(fh, min_records=100):
    """Scan the image for the cache member that carries the image table."""
    fh.seek(0, os.SEEK_END)
    end = fh.tell()
    pos = 0
    while pos < end:
        fh.seek(pos)
        block = fh.read(BLOCK + len(MAGIC))
        if not block:
            break
        start = 0
        while True:
            hit = block.find(MAGIC, start)
            if hit < 0:
                break
            start = hit + 1
            absolute = pos + hit
            if absolute % 4096:
                continue
            member = parse_member(fh, absolute)
            if member and len(member["records"]) >= min_records:
                return member
        pos += BLOCK
    return None


def read_paths(fh, member):
    """Fill in every record's path string from the member it lives in."""
    records = member["records"]
    base = member["offset"]
    top = max(item["pathOffset"] for item in records)
    fh.seek(base)
    body = fh.read(min(top + 512, 1 << 26))
    for item in records:
        off = item.pop("pathOffset")
        if off >= len(body):
            item["path"] = "<outside member>"
            continue
        stop = body.find(b"\0", off)
        item["path"] = body[off:stop if stop >= 0 else off].decode("latin1", "replace")
    records.sort(key=lambda item: item["load"])
    return records


def build_index(dmg_path):
    with open(dmg_path, "rb") as fh:
        member = find_index(fh)
        if not member:
            raise SystemExit("dyld-cache-index: no cache member with an image table in %s" % dmg_path)
        records = read_paths(fh, member)
    return {"source": os.path.basename(dmg_path), "memberOffset": member["offset"],
            "arch": member["arch"], "count": len(records),
            "images": [{"load": item["load"], "size": item["size"],
                        "path": item["path"], "uuid": item["uuid"]} for item in records]}


def load_index(path):
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    images = data["images"]
    return data, images, [item["load"] for item in images]


def lookup(images, loads, address):
    index = bisect.bisect_right(loads, address) - 1
    if index < 0:
        return None
    image = images[index]
    if address >= image["load"] + image["size"]:
        return None
    return "%s+0x%x" % (image["path"], address - image["load"])


def read_slide(text):
    """Return the slide printed by the service scan, plus every slide seen."""
    seen = {}
    for match in SLIDE.finditer(text):
        slide = int(match.group(2), 16)
        seen[slide] = seen.get(slide, 0) + 1
    if not seen:
        return None, []
    slide = max(seen, key=seen.get)
    return slide, sorted(seen)


def read_stack(text, limit, after=None):
    """Return the first long hex line, optionally only after a marker line.

    A log can carry several backtraces (a nil URL in one process, a selector
    mismatch in another), so the caller names the one it wants by the text that
    precedes it.
    """
    started = after is None
    for line in text.splitlines():
        if not started:
            if after in line:
                started = True
            continue
        tokens = HEX.findall(line)
        if len(tokens) >= 10:
            return [int(token, 16) for token in tokens[:limit]]
    return []


def run(index_path, log_path, want_json, limit, after=None):
    if not os.path.isfile(index_path):
        print("dyld-cache-index: index not found: %s" % index_path)
        return 2
    if not os.path.isfile(log_path):
        print("dyld-cache-index: log not found: %s" % log_path)
        return 2
    data, images, loads = load_index(index_path)
    with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    slide, all_slides = read_slide(text)
    if slide is None:
        print("dyld-cache-index: no K60SR slide line in %s" % log_path)
        return 2
    stack = read_stack(text, limit, after)
    if not stack:
        print("dyld-cache-index: no backtrace line%s in %s"
              % ("" if after is None else " after %r" % after, log_path))
        return 2
    frames = []
    for address in stack:
        name = lookup(images, loads, address - slide)
        frames.append({"address": "0x%x" % address, "unslid": "0x%x" % (address - slide),
                       "image": name})
    resolved = sum(1 for frame in frames if frame["image"])
    if want_json:
        print(json.dumps({"log": log_path, "index": index_path, "after": after,
                          "slide": "0x%x" % slide,
                          "slides_seen": ["0x%x" % item for item in all_slides],
                          "frames": frames, "resolved": resolved,
                          "total": len(frames)}, indent=2))
    else:
        print("dyld-cache-index: log %s, index %s (%d images, member 0x%x)"
              % (log_path, index_path, data["count"], data["memberOffset"]))
        print("dyld-cache-index: slide 0x%x%s"
              % (slide, "" if len(all_slides) == 1
                 else " (log prints %d different slides)" % len(all_slides)))
        for frame in frames:
            print("  %-12s %s" % (frame["address"], frame["image"] or "(outside the shared cache)"))
        print("dyld-cache-index: %d of %d frames resolved" % (resolved, len(frames)))
    return 0 if resolved == len(frames) else 1


def selftest():
    root = tempfile.mkdtemp(prefix="dyld-cache-index-")
    image = os.path.join(root, "member.bin")
    head = bytearray(HEADER_READ)
    head[:7] = MAGIC
    head[0x10:0x18] = b"  arm64\0"
    records = [(0x1800b0000, 0x39EA0, "/usr/lib/libobjc.A.dylib"),
               (0x1800ea000, 0xBCB000,
                "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")]
    table_off = 0x800
    struct.pack_into("<Q", head, 0x88, table_off)
    struct.pack_into("<Q", head, 0x90, len(records))
    path_off = HEADER_READ  # the fixture keeps the path strings after the header
    cursor = 0
    path_cursor = 0
    for load, size, path in records:
        struct.pack_into("<QII", head, table_off + cursor + 16, load, size,
                         path_off + path_cursor)
        cursor += RECORD
        path_cursor += len(path) + 1
    paths = b"".join(path.encode() + b"\0" for _, _, path in records)
    with open(image, "wb") as handle:
        handle.write(bytes(head) + paths)
    with open(image, "rb") as handle:
        member = find_index(handle, min_records=1)
        if not member:
            print("dyld-cache-index: selftest FAILED: no member found")
            return 1
        parsed = read_paths(handle, member)
    index_path = os.path.join(root, "index.json")
    with open(index_path, "w", encoding="utf-8") as handle:
        json.dump({"source": "selftest", "memberOffset": 0, "arch": "  arm64",
                   "count": len(parsed),
                   "images": [{"load": item["load"], "size": item["size"],
                               "path": item["path"], "uuid": item["uuid"]} for item in parsed]},
                  handle)
    log_path = os.path.join(root, "console.log")
    with open(log_path, "w", encoding="utf-8") as handle:
        handle.write("K60SR26 t=75 start=0x1946b0000 slide=0x146b0000\n"
                     "first-throw (0x194775050 0x19b42148c 0x10111f930 0x180000000)\n"
                     "fixture (0x195375050 0x19b5b248c 0x10111f930)\n")
    data, images, loads = load_index(index_path)
    slide, seen = read_slide(open(log_path, encoding="utf-8").read())
    checks = [
        ("member found", bool(member)),
        ("record count", len(parsed) == 2),
        ("paths read", parsed[0]["path"] == "/usr/lib/libobjc.A.dylib"),
        ("sorted by load", [item["load"] for item in parsed] == [0x1800b0000, 0x1800ea000]),
        ("slide parsed", slide == 0x146B0000),
        ("single slide", seen == [0x146B0000]),
        ("libobjc frame",
         lookup(images, loads, 0x1800b0000 + 0x15050) == "/usr/lib/libobjc.A.dylib+0x15050"),
        ("corefoundation frame",
         lookup(images, loads, 0x1800ea000 + 0x948c) ==
         "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation+0x948c"),
        ("private frame", lookup(images, loads, 0x10111f930 - slide) is None),
        ("below first image", lookup(images, loads, 0x100000000) is None),
        ("outside last image", lookup(images, loads, 0x1800ea000 + 0xBCB000) is None),
    ]
    failed = [name for name, ok in checks if not ok]
    if failed:
        print("dyld-cache-index: selftest FAILED: %s" % ", ".join(failed))
        return 1
    print("dyld-cache-index: selftest ok (%d checks)" % len(checks))
    return 0


def main(argv):
    parser = argparse.ArgumentParser(description="Name crash frames from a dyld shared cache image table.")
    parser.add_argument("--dmg", help="SystemOS cryptex image that carries the cache")
    parser.add_argument("--out", help="where to write the index JSON")
    parser.add_argument("--index", help="index JSON built earlier")
    parser.add_argument("--log", help="console.log whose stack should be named")
    parser.add_argument("--frame-limit", type=int, default=32, help="frames to name (default 32)")
    parser.add_argument("--after", help="only read the backtrace that follows this text")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--selftest", action="store_true", help="run the built-in fixture")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.dmg:
        if not args.out:
            print("dyld-cache-index: --dmg needs --out")
            return 2
        index = build_index(args.dmg)
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(index, handle, indent=1)
        print("dyld-cache-index: wrote %s (%d images, member 0x%x)"
              % (args.out, index["count"], index["memberOffset"]))
        return 0
    if args.index and args.log:
        return run(args.index, args.log, args.json, args.frame_limit, args.after)
    print("dyld-cache-index: give --dmg/--out to build an index, or --index/--log to name frames")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
