#!/usr/bin/env python3
"""Self-test for scripts/verify-boot-image.py and scripts/build-strict.sh guards.

No device, no build: it fabricates a boot image that satisfies a manifest, then
mutates one field at a time and requires the verifier to refuse. A verifier that
cannot fail is worse than none, because it turns "verified" into a feeling.
"""
import gzip
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # this file lives in scripts/tests/
VERIFY = ROOT / 'scripts' / 'verify-boot-image.py'
PAGE = 4096
SHIM = b'\x00' * 112
FDT_MAGIC = b'\xd0\x0d\xfe\xed'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build_fdt(length=4024):
    body = bytearray(length)
    body[0:4] = FDT_MAGIC
    struct.pack_into('>I', body, 4, length)
    return bytes(body)


def build_image(fd, dtb, payload):
    member = gzip.compress(SHIM + fd, 6)
    kslot = member + dtb
    rslot = payload
    ksize, rsize = len(kslot), len(rslot)
    header = bytearray(4096)
    header[0:8] = b'ANDROID!'
    struct.pack_into('<2I', header, 8, ksize, rsize)
    struct.pack_into('<I', header, 20, 1584)
    struct.pack_into('<I', header, 40, 4)
    out = bytes(header) + kslot
    out += b'\x00' * ((PAGE - len(out) % PAGE) % PAGE)
    out += rslot
    return out


def run(manifest, image):
    done = subprocess.run([sys.executable, str(VERIFY), '--manifest', str(manifest),
                           '--image', str(image)], capture_output=True, text=True)
    return done.returncode, done.stdout + done.stderr


def main():
    tmp = Path(tempfile.mkdtemp(prefix='verify-selftest-'))
    fd = bytearray(3 * 1024 * 1024)
    fd[40:44] = b'_FVH'
    fd = bytes(fd)
    dtb = build_fdt()
    # A payload FAT is not fabricated here: the ramdisk check only needs bytes,
    # and the FAT/Toml checks are exercised on real images by build-strict runs.
    payload = b'\x00' * PAGE
    image = build_image(fd, dtb, payload)
    img = tmp / 'boot.img'
    img.write_bytes(image)

    manifest = {
        'components': {
            'fd': sha(fd),
            'payload': sha(payload),
            'payload_kernel': sha(b'kernel-inside-payload'),
            'boot_img_path': str(img),
        }
    }
    mf = tmp / 'build-manifest.json'
    mf.write_text(json.dumps(manifest))

    cases = []

    rc, out = run(mf, img)
    # The fabricated ramdisk is not a FAT volume, so the payload checks fail by
    # design; what matters is that the firmware volume itself is accepted.
    cases.append(('a matching firmware volume is accepted', None, 'firmware volume sha256' not in out, out))

    manifest_bad = json.loads(json.dumps(manifest))
    manifest_bad['components']['fd'] = 'f' * 64
    mf_bad = tmp / 'manifest-bad-fd.json'
    mf_bad.write_text(json.dumps(manifest_bad))
    rc, out = run(mf_bad, img)
    cases.append(('a different firmware volume is refused', False, 'firmware volume sha256' in out, out))

    big_dtb = build_fdt(480 * 1024)
    big = tmp / 'boot-bigdtb.img'
    big.write_bytes(build_image(fd, big_dtb, payload))
    rc, out = run(mf, big)
    cases.append(('the 480 KiB UEFI DTB is refused (P-149)', False, 'P-149' in out, out))

    no_dtb = tmp / 'boot-nodtb.img'
    no_dtb.write_bytes(build_image(fd, b'', payload))
    rc, out = run(mf, no_dtb)
    cases.append(('a missing kernel DTB is refused', False, 'FDT magic' in out, out))

    trunc = tmp / 'boot-trunc.img'
    trunc.write_bytes(image[:PAGE + 64])
    rc, out = run(mf, trunc)
    cases.append(('a truncated kernel slot is refused', False, 'truncated' in out or 'past the file' in out, out))

    failures = 0
    for name, want_ok, extra, out in cases:
        ok = True if want_ok is None else ((rc == 0) if want_ok else (rc != 0))
        if ok and not extra:
            ok = False
        print(('ok   ' if ok else 'FAIL ') + name)
        if not ok:
            failures += 1
            print(out)

    # build-strict.sh guards: a missing --fd must be refused before any build.
    strict = ROOT / 'scripts' / 'build-strict.sh'
    done = subprocess.run(['bash', str(strict), 'selftest'], capture_output=True, text=True)
    ok = done.returncode != 0 and '--fd is required' in (done.stdout + done.stderr)
    print(('ok   ' if ok else 'FAIL ') + 'build-strict refuses a build with no --fd')
    if not ok:
        failures += 1
        print(done.stdout + done.stderr)

    done = subprocess.run(['bash', str(strict), 'selftest', '--fd', '/nonexistent.fd'],
                          capture_output=True, text=True)
    ok = done.returncode != 0 and 'does not exist' in (done.stdout + done.stderr)
    print(('ok   ' if ok else 'FAIL ') + 'build-strict refuses a missing --fd file')
    if not ok:
        failures += 1
        print(done.stdout + done.stderr)

    import os
    env = dict(os.environ, UNIXNU_SKIP_GATES='1')
    done = subprocess.run(['bash', str(strict), 'selftest', '--fd', str(tmp / 'x.fd')],
                          capture_output=True, text=True, env=env)
    ok = done.returncode != 0 and 'UNIXNU_SKIP_GATES' in (done.stdout + done.stderr)
    print(('ok   ' if ok else 'FAIL ') + 'build-strict refuses an inherited skip-gates run')
    if not ok:
        failures += 1
        print(done.stdout + done.stderr)

    print(f'{len(cases) + 3} cases, {failures} failure(s)')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
