#!/usr/bin/env python3
"""Build and run the verified-root policy host fixture with real RSA signatures."""
import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def run(command, **kwargs):
    subprocess.run([str(item) for item in command], check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, help='keep the fixture in this directory')
    args = parser.parse_args()
    work = args.work or Path(tempfile.mkdtemp(prefix='k60-root-policy-'))
    work.mkdir(parents=True, exist_ok=True)
    keys = work / 'keys'
    keys.mkdir(mode=0o700, exist_ok=True)
    for name in ('owner', 'other'):
        private, public = keys / (name + '.pem'), keys / (name + '-public.pem')
        run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:3072', '-out', private])
        run(['openssl', 'pkey', '-in', private, '-pubout', '-out', public])
    spec = importlib.util.spec_from_file_location('manifest', HERE / 'support/manifest.py')
    manifest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(manifest)
    data = bytes((i * 23 + i // 4096) & 255 for i in range(4096 * 3 + 512))
    (work / 'image.bin').write_bytes(data)
    signed = work / 'signed'
    record = manifest.make(__import__('io').BytesIO(data), len(data), keys / 'owner.pem', keys / 'owner-public.pem',
                           uuid.UUID('01e286f1-f4dd-4b2f-99d9-4973337fc788'), 7, signed)
    assert record['block_count'] == 4
    header = (signed / 'header.bin').read_bytes()
    signature = (signed / 'signature.bin').read_bytes()
    assert len(header) == 160 and len(signature) == 384
    (work / 'manifest.bin').write_bytes((signed / 'manifest.bin').read_bytes())
    (work / 'manifest.header.bin').write_bytes(header + signature)
    (work / 'trusted-key.bin').write_bytes((signed / 'trusted-key.bin').read_bytes())
    (work / 'table.bin').write_bytes((signed / 'hashes.bin').read_bytes())
    (work / 'other-key.bin').write_bytes(manifest.public_anchor(keys / 'other-public.pem'))
    cc = os.environ.get('CC', 'cc')
    cxx = os.environ.get('CXX', 'c++')
    build = work / 'build'
    build.mkdir(exist_ok=True)
    run([cc, '-std=c11', '-Wall', '-Wextra', '-Werror', '-I', ROOT, '-c', ROOT / 'verified_root.c', '-o', build / 'verified_root.o'])
    run([cc, '-std=c11', '-Wall', '-Wextra', '-Werror', '-I', ROOT, '-c', HERE / 'support/openssl_provider.c', '-o', build / 'openssl_provider.o'])
    run([cxx, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I', ROOT, '-I', HERE,
         '-c', HERE / 'RootPolicyTable.cpp', '-o', build / 'RootPolicyTable.o'])
    run([cxx, '-o', build / 'RootPolicyTable', build / 'RootPolicyTable.o', build / 'verified_root.o',
         build / 'openssl_provider.o', '-lcrypto'])
    run([build / 'RootPolicyTable', work])
    run([cxx, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I', ROOT, '-I', HERE,
         '-c', HERE / 'RootWindowVerifier.cpp', '-o', build / 'RootWindowVerifier.o'])
    run([cxx, '-o', build / 'RootWindowVerifier', build / 'RootWindowVerifier.o', build / 'verified_root.o',
         build / 'openssl_provider.o', '-lcrypto'])
    run([build / 'RootWindowVerifier', work])
    run([cxx, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I', ROOT, '-I', HERE,
         '-c', HERE / 'RootWindowReadVerified.cpp', '-o', build / 'RootWindowReadVerified.o'])
    run([cxx, '-o', build / 'RootWindowReadVerified', build / 'RootWindowReadVerified.o', build / 'verified_root.o',
         build / 'openssl_provider.o', '-lcrypto'])
    run([build / 'RootWindowReadVerified', work])


if __name__ == '__main__':
    main()