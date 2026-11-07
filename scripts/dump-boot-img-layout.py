#!/usr/bin/env python3
"""route-a-23: dump the real boot image layout and prove the rebuilt FD is inside.

Previous attempt assumed the kernel area was gzip at offset 4096; its first bytes
are the FDT magic, so the layout is different. Locate the pieces by their magic:
  gzip  1f 8b      -> the UEFI FD blob
  FDT   d00dfeed   -> the appended device tree
  'ARMd'           -> the ARM64 image header inside the shim
"""
from pathlib import Path
import hashlib
import gzip
import io
import struct

IMG = Path('/mnt/d/Android/k60-ios/boot-darwin24-abi24.img')
FD = Path('/home/emilelu/hackios/uefi-mondrian/Build/mondrianPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd')
DTB = Path('/tmp/k60build/out/mondrian/ipados-18.7.10-22H374/mondrian/device-tree/hardware.dtb')
PAY = Path('/tmp/k60build/out/mondrian/ipados-18.7.10-22H374/mondrian/payload/payload.img')

data = IMG.read_bytes()
print('image:', IMG.name, len(data), 'bytes')
print('sha256:', hashlib.sha256(data).hexdigest())

ksize, kaddr = struct.unpack_from('<II', data, 8)
page = struct.unpack_from('<I', data, 36)[0] or 4096
print(f'header: kernel_size={ksize} kernel_addr=0x{kaddr:x} page={page}')

print()
print('first 48 bytes at offset 4096:', data[4096:4144].hex())
print('first 16 bytes at offset 0   :', data[:16].hex())

print()
print('--- magic search across the whole image ---')
for name, magic in (('gzip', b'\x1f\x8b\x08'), ('FDT', b'\xd0\x0d\xfe\xed'),
                    ('ARMd', b'ARMd'), ('ANDROID!', b'ANDROID!')):
    pos = data.find(magic)
    print(f'  {name:10s} first at {pos}')

# gzip stream: decode and compare with the rebuilt FD
gz_at = data.find(b'\x1f\x8b\x08')
if gz_at >= 0:
    try:
        dec = gzip.GzipFile(fileobj=io.BytesIO(data[gz_at:])).read()
        print()
        print(f'  gzip at {gz_at} decodes to {len(dec)} bytes')
        fd = FD.read_bytes()
        print(f'  rebuilt FD is      {len(fd)} bytes')
        print(f'  IDENTICAL: {"YES" if dec == fd else "NO"}')
        if dec != fd:
            # find how many leading bytes agree
            n = 0
            for a, b in zip(dec, fd):
                if a != b:
                    break
                n += 1
            print(f'  common prefix: {n} bytes')
    except Exception as exc:
        print('  gzip decode failed:', exc)

# DTB comparison
fdt_at = data.find(b'\xd0\x0d\xfe\xed')
if fdt_at >= 0:
    total = struct.unpack_from('>I', data, fdt_at + 4)[0]
    seg = data[fdt_at:fdt_at + total]
    dtb = DTB.read_bytes()
    print()
    print(f'  FDT at {fdt_at}, totalsize {total}')
    print(f'  equals hardware.dtb: {"YES" if seg == dtb else "NO"}')

# payload
pay_off = len(data) - len(PAY.read_bytes())
seg = data[pay_off:]
print()
print(f'  payload at {pay_off}: {"YES" if hashlib.sha256(seg).hexdigest() == hashlib.sha256(PAY.read_bytes()).hexdigest() else "NO"}')
