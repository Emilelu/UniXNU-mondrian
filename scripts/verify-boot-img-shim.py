#!/usr/bin/env python3
"""route-a-23: confirm the 112-byte prefix is the boot shim and the rest is the
rebuilt FD, then flash."""
from pathlib import Path
import hashlib
import gzip
import io
import struct

IMG = Path('/mnt/d/Android/k60-ios/boot-darwin24-abi24.img')
FD = Path('/home/emilelu/hackios/uefi-mondrian/Build/mondrianPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd')
DTB = Path('/tmp/k60build/out/mondrian/ipados-18.7.10-22H374/mondrian/device-tree/hardware.dtb')

data = IMG.read_bytes()
ksize = struct.unpack_from('<I', data, 8)[0]
gz = data[4096:4096 + ksize - DTB.stat().st_size]
dec = gzip.GzipFile(fileobj=io.BytesIO(gz)).read()
fd = FD.read_bytes()
shim = len(dec) - len(fd)

print('inflated:', len(dec), ' FD:', len(fd), ' prefix:', shim)
print('prefix hex  :', dec[:32].hex())
print('prefix ascii:', dec[:32].decode('latin-1'))
print('ARMd at     :', dec.find(b'ARMd'))
print()
print('FD after prefix identical:', 'PASS' if dec[shim:] == fd else 'FAIL')
print('FD sha256 in image       :', hashlib.sha256(dec[shim:]).hexdigest())
print('FD sha256 on disk        :', hashlib.sha256(fd).hexdigest())
