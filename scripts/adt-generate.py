#!/usr/bin/env python3
"""route-a-18: dump the ADT the payload generates, importing the package properly."""
from pathlib import Path
import struct
import sys

CORE = Path('/tmp/k60build')
sys.path.insert(0, str(CORE / 'scripts'))

from unixnu import devicetree as dt            # noqa: E402
from unixnu.cli import parser as cli_parser    # noqa: E402
from unixnu.config import Context              # noqa: E402

OUT = CORE / 'out/mondrian/ipados-18.7.10-22H374/mondrian'
DTB = OUT / 'device-tree/hardware.dtb'

args = cli_parser().parse_args(['status', '-D', '/home/emilelu/hackios/UniXNU-mondrian'])
ctx = Context(args)
print('device:', ctx.device)
print('dtb:', DTB, DTB.stat().st_size)

blob = dt.generate(DTB, ctx.board, unique_chip_id='4B36305400000001')
print('generated ADT:', len(blob), 'bytes')


def walk(data):
    magic = struct.unpack_from('>I', data, 0)[0]
    if magic != 0xd00dfeed:
        raise SystemExit(f'not an FDT: 0x{magic:08x}')
    total = struct.unpack_from('>I', data, 4)[0]
    pos = struct.unpack_from('>I', data, 8)[0]
    path, nodes = [], []
    while pos < total:
        tok = struct.unpack_from('>I', data, pos)[0]
        pos += 4
        if tok == 1:
            end = data.index(b'\0', pos)
            name = data[pos:end].decode('utf-8', 'replace')
            pos = (end + 1 + 3) & ~3
            path.append(name)
            nodes.append('/' + '/'.join(x for x in path if x))
        elif tok == 2:
            if path:
                path.pop()
        elif tok == 3:
            ln, _ = struct.unpack_from('>II', data, pos)
            pos += 8 + ((ln + 3) & ~3)
        elif tok == 4:
            continue
        elif tok == 9:
            break
        else:
            break
    return nodes


nodes = walk(blob)
print('nodes:', len(nodes))
for n in nodes:
    print(' ', n)
print()
print('what pong ArmDTPlatform needs:')
for w in ('/chosen', '/arm-io', '/cpus', '/defaults', '/options'):
    print(f'  {w}: {"PRESENT" if w in nodes else "MISSING"}')
Path('/tmp/k60build/out/route-a18/adt-generated.bin').write_bytes(blob)
print()
print('saved -> /tmp/k60build/out/route-a18/adt-generated.bin')
