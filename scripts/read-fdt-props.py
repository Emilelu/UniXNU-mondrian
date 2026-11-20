#!/usr/bin/env python3
"""Read properties out of a flattened device tree (FDT/DTB) dump.

Why this exists: several hardware contracts are settled by a value that only
lives in the board's own device tree, not in any source file in this
repository - the five thermal trip points and the ADSP carveout are the ones
that cost a hand-rolled parser each. A second source that nobody can re-read is
not a source, so the walker lives here with a fixture suite
(scripts/tests/test-read-fdt-props.py) and every contract row can cite
'read-fdt-props.py <dump> --node <path> --prop <name>'.

The dump is the flattened blob Android/UEFI leaves behind, version 17: a
10-word big-endian header, a memory reservation map, a structure block of
tokens, and a string table. Node names are NUL terminated and padded to a
4-byte boundary measured from the start of the structure block; property
values are padded the same way. Getting that padding wrong is why the first
attempt at the thermal trips found zero zones.

Read-only by construction: it opens one file for reading and never writes.
"""

import argparse
import json
import struct
import sys

MAGIC = 0xD00DFEED
BEGIN_NODE, END_NODE, PROP, NOP, END = 1, 2, 3, 4, 9

NUL = chr(0).encode()


class DtbError(Exception):
    pass


def _align4(value, base):
    return value + ((4 - ((value - base) % 4)) % 4)


def read_tree(path):
    """Return (paths_in_document_order, {path: {prop: bytes}})."""
    with open(path, "rb") as handle:
        data = handle.read()
    if len(data) < 40:
        raise DtbError("%s is %d bytes, too short for an FDT header" % (path, len(data)))
    (magic, _total, off_struct, off_strings, _off_rsv, version, _last_comp,
     _boot_cpu, size_strings, size_struct) = struct.unpack_from(">10I", data, 0)
    if magic != MAGIC:
        raise DtbError("%s is not a flattened device tree (magic 0x%08x, expected 0x%08x)"
                       % (path, magic, MAGIC))
    if version < 16:
        raise DtbError("%s is FDT version %d; a flat tree without a string table is not supported"
                       % (path, version))
    strings = data[off_strings:off_strings + size_strings]
    end_struct = off_struct + size_struct
    pos = off_struct
    stack = []
    order = []
    nodes = {}
    while pos < end_struct:
        token = struct.unpack_from(">I", data, pos)[0]
        pos += 4
        if token == BEGIN_NODE:
            stop = data.index(NUL, pos)
            name = data[pos:stop].decode("utf-8", "replace")
            pos = _align4(stop + 1, off_struct)
            if stack:
                full = stack[-1].rstrip("/") + "/" + name
            else:
                full = "/" if name in ("", "/") else "/" + name
            stack.append(full)
            nodes[full] = {}
            order.append(full)
        elif token == END_NODE:
            if not stack:
                raise DtbError("END_NODE with no open node at offset 0x%x" % pos)
            stack.pop()
        elif token == PROP:
            if not stack:
                raise DtbError("PROP outside any node at offset 0x%x" % pos)
            length, nameoff = struct.unpack_from(">II", data, pos)
            pos += 8
            stop = strings.index(NUL, nameoff)
            name = strings[nameoff:stop].decode("utf-8", "replace")
            nodes[stack[-1]][name] = data[pos:pos + length]
            pos = _align4(pos + length, off_struct)
        elif token in (NOP,):
            continue
        elif token == END:
            break
        else:
            raise DtbError("unknown FDT token 0x%x at offset 0x%x" % (token, pos))
    if stack:
        raise DtbError("the structure block ended with %d node(s) still open" % len(stack))
    return order, nodes


def render(value):
    """A property value as text: cells when it divides by four, else a string or hex."""
    if value and len(value) % 4 == 0 and not (value[-1:] == NUL and all(32 <= b < 127 for b in value[:-1])):
        cells = struct.unpack(">%dI" % (len(value) // 4), value)
        return " ".join("0x%08x" % cell for cell in cells)
    if value[-1:] == NUL and all(32 <= b < 127 for b in value[:-1]):
        return value[:-1].decode("ascii")
    return value.hex()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dump", help="the flattened device tree to read")
    parser.add_argument("--list", action="store_true", help="print every node path")
    parser.add_argument("--node", help="print every property of this node")
    parser.add_argument("--prop", help="with --node: print only this property")
    parser.add_argument("--hex", action="store_true",
                        help="with --node/--prop: print the raw bytes, lowercase hex")
    parser.add_argument("--json", action="store_true", help="print the whole tree as JSON")
    parser.add_argument("--contains", help="with --list: only paths containing this substring")
    args = parser.parse_args(argv)
    if not (args.list or args.node or args.json):
        parser.error("nothing to do: pass --list, --node or --json")

    try:
        order, nodes = read_tree(args.dump)
    except (DtbError, OSError) as error:
        print("read-fdt-props: %s" % error)
        return 3

    if args.json:
        print(json.dumps({path: {name: value.hex() for name, value in props.items()}
                          for path, props in nodes.items()}, indent=2, sort_keys=True))
        return 0

    if args.list:
        for path in order:
            if args.contains and args.contains not in path:
                continue
            print(path)
        return 0

    props = nodes.get(args.node)
    if props is None:
        print("read-fdt-props: no node %s in %s (see --list)" % (args.node, args.dump))
        return 2
    names = [args.prop] if args.prop else list(props)
    if args.prop and args.prop not in props:
        print("read-fdt-props: node %s has no property %s (it has: %s)"
              % (args.node, args.prop, ", ".join(props) or "nothing"))
        return 2
    for name in names:
        value = props[name]
        print(value.hex() if args.hex else "%s = %s" % (name, render(value)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
