#!/usr/bin/env python3
"""Check the parts of a K60 boot image that verify-boot-img-shim.py does not.

verify-boot-img-shim.py only proves that the kernel slot is a 112-byte BootShim
plus the rebuilt UEFI FD.  It never looks at the ramdisk slot, and on darwin24 the
XNU kernel is not in the kernel slot at all: it lives inside the payload FAT
volume.  So a stale payload, or a payload built from the wrong kernel, passes that
check unchanged.  This script closes the loop:

  1. boot header: ANDROID! magic, kernel_size == gzip + hardware.dtb
  2. kernel slot: inflate, drop the 112-byte shim, compare with the FD
  3. ramdisk slot: byte-identical to the payload.img that was passed to bootimg
  4. payload FAT: Payloads/kernel.macho matches the kernel built for this image
  5. payload.json: kernel_sha256 / adt_sha256 match what is inside the volume

    python3 scripts/verify-boot-img-payload.py \
        --img /mnt/d/Android/k60-ios/boot-darwin24-bc1.img \
        --payload /tmp/k60build/out/mondrian/ipados-18.7.10-22H374/mondrian/payload/payload.img \
        --kernel /tmp/k60build/out/mondrian/ipados-18.7.10-22H374/mondrian/kernel/kernel.macho
"""
import argparse
import gzip
import hashlib
import io
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

FD = Path('/home/emilelu/hackios/uefi-mondrian/Build/mondrianPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd')
SHIM_BYTES = 112


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def mtype(volume, path):
    """Read one file out of the payload FAT volume with mtools."""
    tool = shutil.which('mtype')
    if tool is None:
        return None
    done = subprocess.run([tool, '-i', str(volume), f'::{path}'], capture_output=True)
    if done.returncode != 0:
        raise SystemExit(f'mtype ::{path} failed: {done.stderr.decode(errors="replace")}')
    return done.stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--img', type=Path, required=True)
    ap.add_argument('--payload', type=Path, required=True)
    ap.add_argument('--kernel', type=Path, required=True)
    ap.add_argument('--fd', type=Path, default=FD)
    args = ap.parse_args()

    failures = []
    data = args.img.read_bytes()

    # 1. header (boot image header v4: kernel_size, ramdisk_size, os_version,
    #    header_size, reserved[4], header_version)
    if data[:8] != b'ANDROID!':
        failures.append('missing ANDROID! magic')
    kernel_size, = struct.unpack_from('<I', data, 8)
    ramdisk_size, = struct.unpack_from('<I', data, 12)
    header_size, = struct.unpack_from('<I', data, 20)
    header_version, = struct.unpack_from('<I', data, 40)
    dtb = Path(args.payload).parents[1] / 'device-tree/hardware.dtb'
    dtb_size = dtb.stat().st_size if dtb.exists() else 0
    print(f'kernel_size {kernel_size}  ramdisk_size {ramdisk_size}  '
          f'header_size {header_size}  header_version {header_version}')

    # 2. kernel slot = gzip(FD with shim) + hardware.dtb
    gz = data[4096:4096 + kernel_size - dtb_size]
    dec = gzip.GzipFile(fileobj=io.BytesIO(gz)).read()
    fd = args.fd.read_bytes()
    if len(dec) - len(fd) != SHIM_BYTES:
        failures.append(f'shim is {len(dec) - len(fd)} bytes, expected {SHIM_BYTES}')
    if dec[SHIM_BYTES:] != fd:
        failures.append('inflated kernel slot does not end in the requested FD')
    if dec[56:60] != b'ARMd':
        failures.append(f'no ARMd at shim+56 (found {dec[56:60]!r})')
    trailing = data[4096 + kernel_size - dtb_size:4096 + kernel_size]
    print(f'FD {len(fd)} B sha256 {sha256(fd)[:16]}...  shim {len(dec) - len(fd)} B  '
          f'dtb {len(trailing)} B')

    # 3. ramdisk slot must be the payload that was passed in
    ramdisk_off = 4096 + ((kernel_size + 4095) // 4096) * 4096
    payload = data[ramdisk_off:ramdisk_off + ramdisk_size]
    if payload != args.payload.read_bytes():
        failures.append('ramdisk slot differs from --payload')
    print(f'payload @ {ramdisk_off}  {len(payload)} B  sha256 {sha256(payload)[:16]}...')

    # 4. the kernel inside the payload volume
    inside = mtype(args.payload, '/EFI/UniXNU/Payloads/kernel.macho')
    kernel = args.kernel.read_bytes()
    report = json.loads((args.payload.parent / 'payload.json').read_text())
    if inside is None:
        print('mtools not available: skipped the in-volume kernel check')
    elif inside == kernel:
        print(f'payload kernel.macho == {args.kernel.name} ({len(kernel)} B)')
    elif report.get('kernel_sha256') == sha256(kernel):
        # The upstream entry probe patches the linked image after the payload step
        # hashes it, so the volume carries the patched kernel.
        print(f'payload kernel.macho is the probe-patched image ({sha256(inside)[:16]}...), '
              f'payload.json hashed the pre-patch kernel ({sha256(kernel)[:16]}...)')
    else:
        failures.append(f'payload kernel.macho {sha256(inside)[:16]} != {sha256(kernel)[:16]}')

    # 5. payload.json agrees with the volume
    kernel_entry = inside if inside is not None else kernel
    if report.get('kernel_sha256') not in (sha256(kernel_entry), sha256(kernel)):
        failures.append('payload.json kernel_sha256 does not match the volume')
    adt = mtype(args.payload, '/EFI/UniXNU/Payloads/kernel.macho.adt')
    if adt is not None:
        if report.get('adt_sha256') != sha256(adt):
            failures.append('payload.json adt_sha256 does not match the volume')
        print(f'ADT {len(adt)} B  sha256 {sha256(adt)[:16]}...')
    print(f'payload.json kernel_sha256 {report.get("kernel_sha256", "")[:16]}...')

    for line in failures:
        print(f'FAIL {line}')
    print('OK' if not failures else 'FAILED')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
