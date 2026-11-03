#!/usr/bin/env python3
"""route-a-18: unwrap the 22H374 kernelcache IM4P (robust DER walk)."""
from pathlib import Path
import subprocess

SRC = Path('/tmp/k60build/out/ipsw/22H374/kernelcache.release.ipad7c')
OUT = Path('/tmp/k60build/out/ipsw/22H374/kernelcache.decompressed')
data = SRC.read_bytes()
print('source:', SRC.stat().st_size)

i = data.find(b'IM4P')
pos = i + 4

def der_item(buf, p):
    tag = buf[p]
    ln = buf[p+1]
    if ln & 0x80:
        n = ln & 0x7f
        ln = int.from_bytes(buf[p+2:p+2+n], 'big')
        hdr = 2 + n
    else:
        hdr = 2
    return tag, buf[p+hdr:p+hdr+ln], p + hdr + ln

tag, val, pos = der_item(data, pos)
print('type:', tag, val)
tag, ver, pos = der_item(data, pos)
print('version:', tag, ver)
tag, payload, pos = der_item(data, pos)
print('payload tag:', hex(tag), 'length:', len(payload), 'head:', payload[:8].hex())

magic = payload[:8]
print('magic:', magic)
if magic[:4] == b'bvx2':
    print('=> lzss; decompress with lzss')
    tmp = OUT.with_suffix('.lzss')
    tmp.write_bytes(payload)
    OUT.write_bytes(tmp.read_bytes())
elif magic[:4] == b'bvx$' or magic[:2] == b'bv':
    print('=> lzfse')
    tmp = OUT.with_suffix('.lzfse')
    tmp.write_bytes(payload)
    r = subprocess.run(['/opt/unixnu-linux/bin/lzfse', '-decode', '-i', str(tmp), '-o', str(OUT)],
                       capture_output=True, text=True)
    print('lzfse rc:', r.returncode, (r.stderr or '')[:200])
    if OUT.exists():
        print('decompressed size:', OUT.stat().st_size)
else:
    tmp = OUT.with_suffix('.raw')
    tmp.write_bytes(payload)
    print('unknown compression; raw payload at', tmp, len(payload))

if OUT.exists() and OUT.stat().st_size > 1024:
    head = OUT.read_bytes()[:32]
    print('decompressed head:', head.hex())
    import struct
    if head[:4] in (b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf'):
        magic, cpu, sub, ft, ncmds = struct.unpack_from('<IiiII', head, 0)
        print(f'Mach-O magic 0x{magic:08x} cputype {cpu} filetype {ft} ncmds {ncmds}')
