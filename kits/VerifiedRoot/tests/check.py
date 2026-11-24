#!/usr/bin/env python3
"""Exercise actual C parsing, real RSA verification and block integrity."""
import argparse
import ctypes
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--openssl-prefix', type=Path, required=True)
args = parser.parse_args()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
keys = out / 'keys'
keys.mkdir(mode=0o700, exist_ok=True)
os.chmod(keys, 0o700)
for name in ('owner', 'other'):
    private, public = keys / (name + '.pem'), keys / (name + '-public.pem')
    if not private.exists():
        fd = os.open(private, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:3072',
                        '-out', private], check=True, capture_output=True)
    os.chmod(private, 0o600)
    subprocess.run(['openssl', 'pkey', '-in', private, '-pubout', '-out', public], check=True, capture_output=True)
spec = importlib.util.spec_from_file_location('manifest', ROOT / 'tools/manifest.py')
manifest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manifest)
data = bytes((i * 23 + i // 4096) & 255 for i in range(4096 * 3 + 512))
record = manifest.make(io.BytesIO(data), len(data), keys / 'owner.pem', keys / 'owner-public.pem',
                       uuid.UUID('01e286f1-f4dd-4b2f-99d9-4973337fc788'), 7, out / 'signed')
library = out / 'verified-root.dylib'
subprocess.run(['xcrun', 'clang', '-std=c11', '-Wall', '-Wextra', '-Werror', '-dynamiclib',
                '-I', ROOT / 'include', '-I', args.openssl_prefix / 'include', ROOT / 'src/verified_root.c',
                ROOT / 'tests/openssl_provider.c', '-L', args.openssl_prefix / 'lib', '-lcrypto', '-o', library], check=True)
sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
subprocess.run(['xcrun', 'clang', '-target', 'arm64-apple-ios17.0', '-isysroot', sdk,
                '-std=c11', '-ffreestanding', '-Wall', '-Wextra', '-Werror', '-I', ROOT / 'include',
                '-c', ROOT / 'src/verified_root.c', '-o', out / 'verified-root-arm64.o'], check=True)


class View(ctypes.Structure):
    _fields_ = [('hashes', ctypes.c_void_p), ('image_bytes', ctypes.c_uint64), ('block_count', ctypes.c_uint64),
                ('generation', ctypes.c_uint64), ('volume_uuid', ctypes.c_uint8 * 16), ('image_sha256', ctypes.c_uint8 * 32)]


native = ctypes.CDLL(str(library))
native.vr_host_open.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_uint64, ctypes.POINTER(View)]
native.vr_host_open.restype = ctypes.c_int
native.vr_host_block.argtypes = [ctypes.POINTER(View), ctypes.c_uint64, ctypes.c_void_p, ctypes.c_size_t]
native.vr_host_block.restype = ctypes.c_int
envelope = (out / 'signed/manifest.bin').read_bytes()
key = (out / 'signed/trusted-key.bin').read_bytes()
other_key = manifest.public_anchor(keys / 'other-public.pem')
assert len(key) == 395
buffers = []
checks = []


def opened(blob, anchor=key, generation=7, expected=0):
    encoded, trusted, view = ctypes.create_string_buffer(blob), ctypes.create_string_buffer(anchor), View()
    result = native.vr_host_open(encoded, len(blob), trusted, generation, ctypes.byref(view))
    assert result == expected, (result, expected)
    if result:
        assert not view.hashes and view.image_bytes == 0
    buffers.extend((encoded, trusted))
    return view


view = opened(envelope)
assert view.image_bytes == len(data) and view.block_count == 4 and view.generation == 7
assert bytes(view.volume_uuid) == uuid.UUID(record['volume_uuid']).bytes
checks.append('real RSA3072-SHA256 verification and signed metadata')
for index in range(4):
    block = data[index * 4096:(index + 1) * 4096]
    assert native.vr_host_block(ctypes.byref(view), index, block, len(block)) == 0
checks.append('all original blocks including the exact final 512-byte tail')
for index in range(4):
    block = bytearray(data[index * 4096:(index + 1) * 4096])
    block[0] ^= 1
    assert native.vr_host_block(ctypes.byref(view), index, bytes(block), len(block)) == 5
checks.append('one-byte mutation refused in every actual block')
assert native.vr_host_block(ctypes.byref(view), 1, data[:4096], 4096) == 5
assert native.vr_host_block(ctypes.byref(view), 4, data[:4096], 4096) == 5
assert native.vr_host_block(ctypes.byref(view), 0, data[:512], 512) == 5
checks.append('block substitution, outside index and partial-block reads refused')
for offset, expected in ((40, 3), (160, 3), (544, 4)):
    changed = bytearray(envelope)
    changed[offset] ^= 1
    opened(bytes(changed), expected=expected)
checks.append('signed UUID/header, RSA signature and hash-table mutation refused')
opened(envelope, anchor=other_key, expected=2)
opened(envelope, generation=8, expected=1)
opened(envelope, generation=0, expected=1)
opened(envelope[:-1], expected=1)
opened(envelope + b'\0', expected=1)
checks.append('wrong trusted anchor, rollback generation, truncation and trailing bytes refused')
changed = bytearray(envelope)
changed[120:152] = __import__('hashlib').sha256(other_key).digest()
opened(bytes(changed), anchor=other_key, expected=3)
checks.append('matching attacker-selected key identifier cannot replace the actual RSA signature')
report = dict(real_c_parser=True, real_openssl_signature_verification=True, native_arm64_ios17_cross_compile=True,
              checks=checks, qemu_tested=False, boot_root_authenticated=False, hardware_tested=False)
(out / 'checks.json').write_text(json.dumps(report, indent=2) + '\n')
print('PASS:', len(checks), 'groups using real RSA signatures and actual C block verification; host only')
