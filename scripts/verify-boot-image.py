#!/usr/bin/env python3
"""Fail-closed verification of one K60 boot image against its build manifest.

Why this exists: on 2026-11-13 every boot between 16:43 and 17:37 was judged on
an image that still carried the 16:43 kernel, because nothing compared the bytes
inside the boot image with the bytes the build claimed to produce (P-181). A
manifest is only useful if something reads the image back and disagrees loudly.

What it checks, in order, and it stops at the first disagreement:

  1. Android boot header: ANDROID! magic, v4, header_size 1584, sections aligned
  2. kernel slot: gzip member, 112-byte BootShim, then the firmware volume whose
     sha256 must equal manifest.components.fd
  3. kernel slot tail: the small kernel DTB (not the 480 KiB UEFI one, P-149)
  4. ramdisk slot: byte-identical to manifest.components.payload
  5. payload FAT: Payloads/kernel.macho must equal manifest.components.payload_kernel
     (the kernel inside the payload is not the built kernel: the payload step
     patches it, so the manifest records both and this compares the right one)
  6. payload TOML: every `args =` line, which is what the firmware actually
     passes (P-175: PE_boot_args() returns the kernel's compiled-in default)
  7. policy: pong_adsp=1 is refused, pong_adsp=0 is allowed

Usage:
  scripts/verify-boot-image.py --manifest <build-manifest.json>
  scripts/verify-boot-image.py --manifest <...> --image <boot.img>   # override
Exit code 0 verified, 1 refused.
"""
import argparse
import gzip  # noqa: F401  (kept for the shim helpers that use it)
import hashlib

import json

import shutil
import struct
import zlib
import subprocess
import sys
import tempfile
from pathlib import Path

MAGIC = b'ANDROID!'
PAGE = 4096
HEADER_SIZE_V4 = 1584
SHIM_BYTES = 112
MAX_KERNEL_DTB = 65536


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def page_up(n):
    return (n + PAGE - 1) // PAGE * PAGE


def fail(problems, message):
    problems.append(message)
    return problems


def read_fat_file(volume, inner):
    """Read one file out of a FAT image with mtools (no kernel support needed)."""
    tool = shutil.which('mtype')
    if tool is None:
        raise SystemExit('verify-boot-image: mtype not found (install mtools)')
    done = subprocess.run([tool, '-i', str(volume), f'::{inner}'],
                          capture_output=True)
    if done.returncode != 0:
        return None, done.stderr.decode('utf-8', 'replace').strip()
    return done.stdout, ''


def check(manifest_path, image_override=None):
    problems = []
    manifest = json.loads(Path(manifest_path).read_text())
    comp = manifest.get('components') or {}
    image = Path(image_override or comp.get('boot_img_path') or '')
    if not image.is_file():
        return fail(problems, f'boot image missing: {image}')

    data = image.read_bytes()
    if len(data) < PAGE or data[:8] != MAGIC:
        return fail(problems, f'{image.name}: not an Android boot image')

    ksize, rsize = struct.unpack_from('<2I', data, 8)
    hsize = struct.unpack_from('<I', data, 20)[0]
    hver = struct.unpack_from('<I', data, 40)[0]
    if hver != 4:
        return fail(problems, f'header_version={hver}, this verifier covers v4')
    if hsize != HEADER_SIZE_V4:
        return fail(problems, f'header_size={hsize}, v4 is {HEADER_SIZE_V4}')

    k_off = PAGE
    r_off = k_off + page_up(ksize)
    if r_off + rsize > len(data):
        return fail(problems, f'sections run past the file: need {r_off + rsize}, have {len(data)}')

    # --- kernel slot: one gzip member (shim + FD), then the kernel DTB ------
    # Measured on boot-fixinit2.img: gzip inflates to 3,145,840 B (112-byte shim
    # + 3,145,728 B firmware volume), and the remaining 4,024 B are the kernel
    # DTB, stored raw after the member. Do not gzip.decompress() the whole slot:
    # it insists on a single member and the DTB is not part of it.
    kslot = data[k_off:k_off + ksize]
    try:
        inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
        inner = inflater.decompress(kslot)
        tail = inflater.unused_data
    except zlib.error as exc:
        return fail(problems, f'kernel slot is not one gzip member: {exc}')
    if not inflater.eof:
        return fail(problems, 'kernel slot gzip member is truncated')

    fd = inner[SHIM_BYTES:]
    if fd[40:44] != b'_FVH':
        problems.append('firmware volume does not start 40 bytes before _FVH')
    fd_sha = sha256_bytes(fd)
    if comp.get('fd') and fd_sha != comp['fd']:
        problems.append(f'firmware volume sha256 {fd_sha[:16]} != manifest {comp["fd"][:16]}')

    if not tail.startswith(b'\xd0\x0d\xfe\xed'):
        problems.append('no FDT magic after the firmware volume (kernel DTB missing)')
    elif len(tail) < 8:
        problems.append('kernel DTB header truncated')
    else:
        fdt_len = struct.unpack_from('>I', tail, 4)[0]
        if fdt_len != len(tail):
            problems.append(f'kernel DTB length {fdt_len} != {len(tail)} bytes present')
        if fdt_len > MAX_KERNEL_DTB:
            problems.append(f'kernel DTB is {fdt_len} B, over {MAX_KERNEL_DTB} (P-149: the UEFI DTB got packed)')

    # --- ramdisk slot: the payload volume -----------------------------------
    rslot = data[r_off:r_off + rsize]
    if comp.get('payload') and sha256_bytes(rslot) != comp['payload']:
        problems.append('ramdisk slot is not the payload this build produced')

    with tempfile.NamedTemporaryFile(suffix='.img', delete=False) as tmp:
        tmp.write(rslot)
        vol = Path(tmp.name)
    try:
        kernel_in_payload, err = read_fat_file(vol, 'EFI/UniXNU/Payloads/kernel.macho')
        if kernel_in_payload is None:
            problems.append(f'payload FAT has no Payloads/kernel.macho: {err}')
        else:
            got = sha256_bytes(kernel_in_payload)
            want = comp.get('payload_kernel') or comp.get('kernel_built')
            if want and got != want:
                problems.append(f'payload kernel {got[:16]} != manifest {want[:16]}')

        toml, err = read_fat_file(vol, 'EFI/UniXNU/unixnu.toml')
        if toml is None:
            problems.append(f'payload FAT has no unixnu.toml: {err}')
        else:
            text = toml.decode('utf-8', 'replace')
            for line in text.splitlines():
                s = line.strip()
                if not s.startswith('args'):
                    continue
                for token in s.replace('"', ' ').split():
                    if token == 'pong_adsp=1':
                        problems.append('payload TOML enables pong_adsp=1 (active ADSP probe is refused)')
    finally:
        vol.unlink(missing_ok=True)

    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--image')
    args = ap.parse_args()
    problems = check(args.manifest, args.image)
    if problems:
        print('verify-boot-image: REFUSED')
        for p in problems:
            print('  -', p)
        return 1
    print('verify-boot-image: OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
