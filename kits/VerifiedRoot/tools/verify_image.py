#!/usr/bin/env python3
"""Verify real signatures and every image block with the compiled C provider."""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--library', type=Path, required=True)
parser.add_argument('--manifest', type=Path, required=True)
parser.add_argument('--trusted-key', type=Path, required=True)
parser.add_argument('--image', type=Path, required=True)
parser.add_argument('--volume-uuid', type=uuid.UUID, required=True)
parser.add_argument('--minimum-generation', type=int, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()


class View(ctypes.Structure):
    _fields_ = [('hashes', ctypes.c_void_p), ('image_bytes', ctypes.c_uint64), ('block_count', ctypes.c_uint64),
                ('generation', ctypes.c_uint64), ('volume_uuid', ctypes.c_uint8 * 16), ('image_sha256', ctypes.c_uint8 * 32)]


native = ctypes.CDLL(str(args.library.resolve()))
native.vr_host_open.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_uint64, ctypes.POINTER(View)]
native.vr_host_block.argtypes = [ctypes.POINTER(View), ctypes.c_uint64, ctypes.c_void_p, ctypes.c_size_t]
encoded = ctypes.create_string_buffer(args.manifest.read_bytes())
anchor_bytes = args.trusted_key.read_bytes()
if len(anchor_bytes) != 395:
    raise SystemExit('Require the explicit complete trusted public anchor')
anchor = ctypes.create_string_buffer(anchor_bytes)
view = View()
status = native.vr_host_open(encoded, len(encoded) - 1, anchor, args.minimum_generation, ctypes.byref(view))
if status or bytes(view.volume_uuid) != args.volume_uuid.bytes:
    raise SystemExit('Real manifest authentication or authorized volume identity failed')
if not args.image.is_file() or args.image.stat().st_size != view.image_bytes:
    raise SystemExit('Require the actual exact-size original regular image')
digest = hashlib.sha256()
with args.image.open('rb') as stream:
    for index in range(view.block_count):
        block = stream.read(min(4096, view.image_bytes - index * 4096))
        if native.vr_host_block(ctypes.byref(view), index, block, len(block)) != 0:
            raise SystemExit('Actual image block authentication failed at index ' + str(index))
        digest.update(block)
    if stream.read(1):
        raise SystemExit('The image grew beyond the signed bounds')
if digest.digest() != bytes(view.image_sha256):
    raise SystemExit('Complete image digest differs from the genuinely signed metadata')
report = dict(image_bytes=view.image_bytes, blocks_verified=view.block_count,
              image_sha256=digest.hexdigest(), volume_uuid=str(args.volume_uuid).upper(),
              generation=view.generation, trusted_key_sha256=hashlib.sha256(anchor_bytes).hexdigest(),
              real_c_signature_and_block_verification=True, original_image_modified=False,
              host_only=True, boot_root_authenticated=False, qemu_tested=False, hardware_tested=False)
args.output.write_text(json.dumps(report, indent=2) + '\n')
print('PASS: real RSA signature and all', view.block_count, 'original blocks verified by C; host only')
