#!/usr/bin/env python3
"""Sign a complete original image's ordered block hashes with an owner key."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import uuid


def public_anchor(public_key):
    text = subprocess.check_output(['openssl', 'rsa', '-pubin', '-in', str(public_key), '-text', '-noout'], text=True)
    if not re.search(r'(?:Exponent|exponent): 65537\b', text):
        raise ValueError('Require exponent 65537')
    line = subprocess.check_output(['openssl', 'rsa', '-pubin', '-in', str(public_key), '-modulus', '-noout'], text=True)
    modulus = bytes.fromhex(line.strip().split('=', 1)[1])
    if len(modulus) != 384 or not modulus[0] & 128 or not modulus[-1] & 1:
        raise ValueError('Require an actual 3072-bit RSA public key')
    return b'VROOTKEY' + modulus + b'\x01\x00\x01'


def make(stream, image_bytes, key, public_key, volume_uuid, generation, output):
    if image_bytes <= 0 or generation <= 0:
        raise ValueError('Require a nonempty image and a positive generation')
    output.mkdir(parents=True, exist_ok=True)
    anchor = public_anchor(public_key)
    table = output / 'hashes.bin'
    image_hash, table_hash = hashlib.sha256(), hashlib.sha256()
    count = 0
    with table.open('wb') as hashes:
        remaining = image_bytes
        while remaining:
            data = stream.read(min(4096, remaining))
            if len(data) != min(4096, remaining):
                raise ValueError('Short image stream')
            digest = hashlib.sha256(data).digest()
            image_hash.update(data)
            table_hash.update(digest)
            hashes.write(digest)
            remaining -= len(data)
            count += 1
        if stream.read(1):
            raise ValueError('Image stream exceeds its actual declared size')
    header = struct.pack('<8s4I2Q16s32s32s32sQ', b'VROOT01\0', 1, 160, 4096, 0,
                         image_bytes, count, uuid.UUID(str(volume_uuid)).bytes,
                         image_hash.digest(), table_hash.digest(), hashlib.sha256(anchor).digest(), generation)
    (output / 'header.bin').write_bytes(header)
    (output / 'trusted-key.bin').write_bytes(anchor)
    signature = output / 'signature.bin'
    subprocess.run(['openssl', 'dgst', '-sha256', '-sign', str(key), '-out', str(signature), str(output / 'header.bin')], check=True)
    if len(signature.read_bytes()) != 384:
        raise ValueError('Unexpected RSA signature size')
    subprocess.run(['openssl', 'dgst', '-sha256', '-verify', str(public_key), '-signature', str(signature),
                    str(output / 'header.bin')], check=True, capture_output=True)
    with (output / 'manifest.bin').open('wb') as envelope:
        envelope.write(header)
        envelope.write(signature.read_bytes())
        with table.open('rb') as hashes:
            for data in iter(lambda: hashes.read(1024 * 1024), b''):
                envelope.write(data)
    record = dict(version=1, block_bytes=4096, image_bytes=image_bytes, block_count=count,
                  volume_uuid=str(volume_uuid).upper(), generation=generation,
                  image_sha256=image_hash.hexdigest(), hash_table_sha256=table_hash.hexdigest(),
                  trusted_key_sha256=hashlib.sha256(anchor).hexdigest(),
                  signature_algorithm='RSA3072-PKCS1v1.5-SHA256', signature_verified_by_openssl=True,
                  image_modified=False, hardware_tested=False, boot_root_authenticated=False)
    (output / 'manifest.json').write_text(json.dumps(record, indent=2) + '\n')
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--private-key', type=Path, required=True)
    parser.add_argument('--public-key', type=Path, required=True)
    parser.add_argument('--volume-uuid', type=uuid.UUID, required=True)
    parser.add_argument('--generation', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.image.is_file():
        parser.error('CLI image input must be an existing regular file')
    with args.image.open('rb') as stream:
        result = make(stream, args.image.stat().st_size, args.private_key, args.public_key,
                      args.volume_uuid, args.generation, args.output)
    print(json.dumps(result, indent=2))
