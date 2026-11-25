#!/usr/bin/env python3
"""Refresh payload.img after a kernel-only rebuild, without repacking the FAT.

The slow path (`unixnu build payload`) rebuilds the ADT, lays out a 192 MiB FAT
image and copies the kernel in: ~184 s, almost all of it I/O. When only the
kernel changed and the transformed kernel has the same size, the FAT cluster
chain cannot change, so the payload can be refreshed by writing bytes in place
and updating the three hashes in payload.json. Everything else is left alone.

The transform is not optional: `check-ios27-artifacts.py` replays
`patch-armcpu-validate` and `k60-fileset-stamp` and refuses a payload whose
recorded hashes do not match, so this script runs both before writing.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys


def load_swap(root):
    spec = importlib.util.spec_from_file_location('swap', root / 'scripts/k60-kernel-swap.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', required=True, help='device repository checkout')
    parser.add_argument('--board', required=True, help='assembled board directory')
    parser.add_argument('--kernel', required=True, help='raw kernel.macho from the kernel stage')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    root = pathlib.Path(args.device)
    board = pathlib.Path(args.board)
    payload_img = board / 'payload/payload.img'
    manifest_path = board / 'payload/payload.json'
    for required in (payload_img, manifest_path, pathlib.Path(args.kernel)):
        if not required.is_file():
            raise SystemExit(f'refuse: {required} is missing')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    for key in ('kernel_sha256', 'payload_kernel_sha256', 'payload_sha256'):
        if key not in manifest:
            raise SystemExit(f'refuse: payload.json has no {key}')

    work = board / 'payload/kernel.fast.macho'
    shutil.copyfile(args.kernel, work)
    for script, extra in (
        ('scripts/patch-armcpu-validate.py', ['--apply']),
        ('scripts/k60-fileset-stamp.py', ['--apply']),
    ):
        run = subprocess.run([sys.executable, str(root / script), str(work)] + extra,
                             capture_output=True, text=True)
        if run.returncode != 0:
            raise SystemExit(f'refuse: {script} failed: {run.stderr.strip()[:300]}')

    transformed = work.read_bytes()
    swap = load_swap(root)
    image = bytearray(payload_img.read_bytes())
    fat = swap.Fat(image)
    offset, size = fat.find('EFI/UniXNU/Payloads/kernel.macho')
    if offset is None:
        raise SystemExit('refuse: payload has no kernel')
    if size != len(transformed):
        raise SystemExit(f'refuse: payload kernel is {size} bytes, rebuilt kernel is {len(transformed)}')
    if hashlib.sha256(transformed).hexdigest() == manifest['payload_kernel_sha256']:
        # The packed bytes are right, but the record of *which linker output*
        # produced them may be stale (r290l: it still carried the patched hash
        # from the r290k run). Repair the record even when the image is reused.
        linker = sha256(pathlib.Path(args.kernel))
        if manifest.get('kernel_sha256') != linker:
            if args.dry_run:
                print(f'note: dry run; payload.json kernel_sha256 would become {linker}')
            else:
                manifest['kernel_sha256'] = linker
                manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
                print('ok payload.json: kernel_sha256 updated to the linker output')
        else:
            print('ok payload: the rebuilt kernel is byte-identical to the packed one; nothing to do')
        return 0
    fat.write_in_place(offset, transformed)
    new_payload_sha = hashlib.sha256(bytes(image)).hexdigest()
    print(f'ok payload: kernel at offset {offset}, {len(transformed)} bytes')
    print(f'   kernel_sha256          {sha256(pathlib.Path(args.kernel))}')
    print(f'   payload_kernel_sha256  {hashlib.sha256(transformed).hexdigest()}')
    print(f'   payload_sha256         {new_payload_sha}')
    if args.dry_run:
        print('note: dry run; payload.img and payload.json untouched')
        return 0
    payload_img.write_bytes(image)
    manifest['kernel_sha256'] = sha256(pathlib.Path(args.kernel))
    manifest['payload_kernel_sha256'] = hashlib.sha256(transformed).hexdigest()
    manifest['payload_sha256'] = new_payload_sha
    manifest['payload_bytes'] = len(image)
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print('ok payload.json: hashes updated')
    return 0


if __name__ == '__main__':
    sys.exit(main())
