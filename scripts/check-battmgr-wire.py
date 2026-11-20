#!/usr/bin/env python3
"""Check the battery/charger wire property table against its three sources.

Wire prop_id on the PMIC GLINK channel is the *index* into the field's map
array, not the enum value, and Xiaomi's map inserts entries the mainline enum
does not have (CAPACITY is 0x2e where mainline has 41). Three independent
materials therefore have to agree, and this gate is where they meet:

  1. drivers/PongPower/K60Battmgr.c  the fields[] table, in protocol order
     (the order itself is fixed by the K60Bm* enum in K60Battmgr.h)
  2. docs/research/charger/04-PROP-MAP.md  the .ko decompilation table, which
     is what actually established the values
  3. qti_battery_charger_main_m81.ko  the vendor module's .rodata maps

Source 3 lives outside the repository, so it is optional: pass --ko (or set
K60_VENDOR_KO) and the gate reads the maps out of the ELF; without it the gate
says so and still proves sources 1 and 2 agree.

Why it matters for iOS 27: the wire indices are cross-version constants (same
ADSP, same battmgr protocol), while the IOKit property numbers are not. A table
that drifts silently would look like a firmware regression.

Exit 0 all agree, 1 a disagreement, 2 the manifest or a source cannot be read.
"""
import argparse
import pathlib
import struct
import sys

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - python < 3.11
    tomllib = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "research" / "charger" / "WIRE-PROPS.toml"
DRIVER = "drivers/PongPower/K60Battmgr.c"
HEADER = "drivers/PongPower/K60Battmgr.h"
MAP_SYMBOLS = {"OP_BATTERY": "battery_prop_map", "OP_USB": "usb_prop_map",
               "OP_WIRELESS": "wls_prop_map"}


def read(path):
    return pathlib.Path(path).read_text(encoding="utf-8", errors="replace")


def driver_table(root):
    """Return [(name, opcode, index)] in the order the enum fixes."""
    header = read(root / HEADER)
    start = header.index("K60BmStatus,")
    end = header.index("K60BmFields")
    names = [part.strip().rstrip(",") for part in header[start:end].replace("\n", " ").split(",")]
    names = [n for n in names if n.startswith("K60Bm") and n != "K60BmFields"]
    source = read(root / DRIVER)
    body = source[source.index("fields[K60BmFields] = {") :]
    body = body[: body.index("};")]
    pairs = []
    for chunk in body.split("{")[1:]:
        head = chunk.split("}")[0].strip()
        if not head:
            continue
        opcode, index = [part.strip() for part in head.split(",")]
        pairs.append((opcode, int(index)))
    return names, pairs


def doc_value(root, where):
    path, _, line = where.rpartition(":")
    text = read(root / path).splitlines()
    number = int(line)
    if not 1 <= number <= len(text):
        raise SystemExit("check-battmgr-wire: %s is outside %s" % (where, path))
    row = text[number - 1]
    for token in row.replace("|", " ").split():
        if token.lower().startswith("0x"):
            return row, token
    return row, None


def elven(path):
    """Minimal ELF64 reader: {symbol: bytes} for the three map arrays."""
    blob = pathlib.Path(path).read_bytes()
    if blob[:4] != b"\x7fELF" or blob[4] != 2:
        raise SystemExit("check-battmgr-wire: %s is not an ELF64 file" % path)
    shoff = struct.unpack_from("<Q", blob, 0x28)[0]
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", blob, 0x3A)
    sections = []
    for i in range(shnum):
        base = shoff + i * shentsize
        name, kind = struct.unpack_from("<II", blob, base)
        offset, size = struct.unpack_from("<QQ", blob, base + 0x18)
        link = struct.unpack_from("<I", blob, base + 0x28)[0]
        sections.append({"name": name, "kind": kind, "offset": offset,
                         "size": size, "link": link})
    names_blob = blob[sections[shstrndx]["offset"] : sections[shstrndx]["offset"] + sections[shstrndx]["size"]]
    for section in sections:
        raw = names_blob[section["name"] :]
        section["name"] = raw[: raw.index(b"\0")].decode("ascii", "replace")
    symtab = next(s for s in sections if s["kind"] == 2)
    strtab = sections[symtab["link"]]
    strings = blob[strtab["offset"] : strtab["offset"] + strtab["size"]]
    rodata = next(s for s in sections if s["name"] == ".rodata")
    maps = {}
    for i in range(symtab["size"] // 24):
        base = symtab["offset"] + i * 24
        name, _, _, shndx = struct.unpack_from("<IBBH", blob, base)
        value, size = struct.unpack_from("<QQ", blob, base + 8)
        label = strings[name : strings.index(b"\0", name)].decode("ascii", "replace")
        if label not in MAP_SYMBOLS.values() or shndx == 0 or size % 4:
            continue
        start = rodata["offset"] + value
        maps[label] = list(struct.unpack_from("<%dI" % (size // 4), blob, start))
    missing = sorted(set(MAP_SYMBOLS.values()) - set(maps))
    if missing:
        raise SystemExit("check-battmgr-wire: %s carries no %s" % (path, ", ".join(missing)))
    return maps


def verify(root, manifest_path, ko=None):
    if tomllib is None:
        raise SystemExit("check-battmgr-wire: python 3.11+ (tomllib) is required")
    try:
        manifest = tomllib.loads(read(manifest_path))
    except OSError as error:
        raise SystemExit("check-battmgr-wire: cannot read the manifest: %s" % error)
    fields = manifest.get("field") or []
    problems, notes = [], []
    names, pairs = driver_table(root)
    if len(names) != len(pairs):
        raise SystemExit("check-battmgr-wire: %d enum names but %d pair(s) in fields[]"
                         % (len(names), len(pairs)))
    table = [(n[5:], op, idx) for n, (op, idx) in zip(names, pairs)]
    if len(fields) != len(table):
        problems.append("manifest lists %d field(s), the driver sends %d" % (len(fields), len(table)))
    for want, (name, opcode, index) in zip(fields, table):
        label = want.get("name", "?")
        if label != name:
            problems.append("row %s is at the driver position of %s" % (label, name))
        if want.get("opcode") != opcode:
            problems.append("%s: manifest opcode %s, driver sends %s" % (label, want.get("opcode"), opcode))
        if want.get("index") != index:
            problems.append("%s: manifest index %s, driver sends %d" % (label, want.get("index"), index))
    known = set(MAP_SYMBOLS)
    for want in fields:
        label = want.get("name", "?")
        if want.get("opcode") not in known:
            problems.append("%s: unknown opcode %r" % (label, want.get("opcode")))
        try:
            row, token = doc_value(root, want.get("documented_at", ""))
        except SystemExit as error:
            problems.append("%s: %s" % (label, error))
            continue
        value = want.get("map_value")
        if token is None:
            problems.append("%s: %s carries no 0x value" % (label, want.get("documented_at")))
        elif value is not None and int(token, 16) != int(value, 16):
            problems.append("%s: manifest says map %s, %s says %s"
                            % (label, value, want.get("documented_at"), token))
    maps = None
    if ko:
        maps = elven(ko)
        for want in fields:
            label, opcode, index = want.get("name"), want.get("opcode"), want.get("index")
            table_for = maps[MAP_SYMBOLS[opcode]]
            if not isinstance(index, int) or index >= len(table_for):
                problems.append("%s: index %r is outside %s (%d entries)"
                                % (label, index, MAP_SYMBOLS[opcode], len(table_for)))
                continue
            live = table_for[index]
            if int(want.get("map_value", "0x0"), 16) != live:
                problems.append("%s: manifest says map %s, the module has 0x%02x"
                                % (label, want.get("map_value"), live))
        notes.append("read the maps out of %s" % pathlib.Path(ko).name)
    else:
        notes.append("no vendor module given (--ko / K60_VENDOR_KO); "
                     "the driver table and the decompilation table still have to agree")
    return fields, problems, notes


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--manifest", default=str(MANIFEST))
    parser.add_argument("--ko", default=None, help="vendor qti_battery_charger_main_m81.ko")
    args = parser.parse_args(argv)
    import os
    ko = args.ko or os.environ.get("K60_VENDOR_KO") or None
    try:
        fields, problems, notes = verify(pathlib.Path(args.root), args.manifest, ko)
    except SystemExit as error:
        print(error)
        return 2
    for note in notes:
        print("note: %s" % note)
    for problem in problems:
        print("FAIL %s" % problem)
    if problems:
        print("battmgr-wire: FAIL (%d problem(s))" % len(problems))
        return 1
    print("battmgr-wire: OK (%d field(s) agree with the driver, the decompilation table%s)"
          % (len(fields), " and the vendor module" if ko else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
