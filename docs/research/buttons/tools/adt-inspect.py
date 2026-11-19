#!/usr/bin/env python3
"""adt-inspect.py - dump an Apple flat ADT (kernel.macho.adt) as a node tree.

The payload ADT is NOT a devicetree blob and has NO file header. The whole
file is a bare node stream whose first node is "device-tree":

    node = u32 num_props, u32 num_children, props[num_props], children[num_children]
    prop = char name[32], u32 length, data padded up to a multiple of 4 bytes

The node name is the value of its first property, "name".
This mirrors scripts/unixnu/devicetree.py:13-21 (node()) in UniXNU.

Usage:
    python3 adt-inspect.py FILE.adt                  # full tree
    python3 adt-inspect.py FILE.adt --grep pong      # only matching paths
    python3 adt-inspect.py FILE.adt --path /device-tree/arm-io/pong-buttons
"""
import struct
import sys


def parse(data):
    def read_node(off):
        nprops, nchildren = struct.unpack_from('<II', data, off)
        off += 8
        props = []
        for _ in range(nprops):
            name = data[off:off + 32].split(b'\0')[0].decode('latin-1')
            length = struct.unpack_from('<I', data, off + 32)[0]
            off += 36
            value = data[off:off + length]
            off += (length + 3) & ~3
            props.append((name, value))
        children = []
        for _ in range(nchildren):
            child, off = read_node(off)
            children.append(child)
        return (props, children), off

    node, end = read_node(0)
    return node, end


def show(value):
    trimmed = value.rstrip(b'\0')
    if trimmed and all(32 <= byte < 127 for byte in trimmed):
        return trimmed.decode('latin-1')
    if len(value) in (1, 2, 4, 8):
        return '0x%x' % int.from_bytes(value, 'little')
    return value.hex()


def walk(node, path, out):
    props, children = node
    name = dict(props).get('name', b'?').split(b'\0')[0].decode('latin-1')
    here = path + '/' + name
    out.append((here, props))
    for child in children:
        walk(child, here, out)


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    data = open(sys.argv[1], 'rb').read()
    root, end = parse(data)
    out = []
    walk(root, '', out)

    def wanted(path):
        if '--path' in sys.argv:
            return path == sys.argv[sys.argv.index('--path') + 1]
        if '--grep' in sys.argv:
            needle = sys.argv[sys.argv.index('--grep') + 1].lower()
            return needle in path.lower()
        return True

    print('file=%s bytes=%d nodes=%d consumed=%d' % (sys.argv[1], len(data), len(out), end))
    if end != len(data):
        print('WARNING: parser consumed %d of %d bytes' % (end, len(data)))
    for here, props in out:
        if not wanted(here):
            continue
        print(here)
        for key, value in props:
            if key == 'name':
                continue
            print('    %-24s %s' % (key, show(value)))


if __name__ == '__main__':
    main()
