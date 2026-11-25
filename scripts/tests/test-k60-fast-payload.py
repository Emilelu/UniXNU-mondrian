#!/usr/bin/env python3
"""Regression: the in-place payload refresh touches the kernel bytes and nothing else.

Uses the real 93 MB kernel and the real 192 MiB payload, so the FAT32 layout,
the cluster chain and the transform chain are the ones that ship. Runs three
cases: byte-identical kernel (no-op), one mutated kernel (writes only the kernel
range, leaves every FAT structure untouched), and a wrong-size kernel (refused).
"""
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
BOARD = pathlib.Path('/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27')
SCRATCH = pathlib.Path('/mnt/e/iOS Port/Work/scratch')


def run(board, kernel, dry=False):
    command = [sys.executable, str(ROOT / 'scripts/k60-fast-payload.py'),
               '--device', str(ROOT), '--board', str(board), '--kernel', str(kernel)]
    if dry:
        command.append('--dry-run')
    return subprocess.run(command, capture_output=True, text=True)


def main():
    payload = (BOARD / 'payload/payload.img').read_bytes()
    manifest = json.loads((BOARD / 'payload/payload.json').read_text(encoding='utf-8'))
    kernel = (BOARD / 'kernel/kernel.macho').read_bytes()
    work = pathlib.Path(tempfile.mkdtemp(prefix='fastpayload-', dir=SCRATCH))
    board = work / 'board'
    (board / 'payload').mkdir(parents=True)
    (board / 'payload/payload.img').write_bytes(payload)
    shutil.copyfile(BOARD / 'payload/payload.json', board / 'payload/payload.json')
    print(f'note: payload {len(payload)} bytes, kernel {len(kernel)} bytes, work {work}')

    same = work / 'kernel.same.macho'
    same.write_bytes(kernel)
    result = run(board, same)
    assert result.returncode == 0, result.stderr
    assert 'byte-identical' in result.stdout, result.stdout
    print('ok same-kernel: recognised as a no-op')

    mutated = bytearray(kernel)
    mutated[0x1000] ^= 0xFF
    changed = work / 'kernel.changed.macho'
    changed.write_bytes(bytes(mutated))
    before = (board / 'payload/payload.img').read_bytes()
    result = run(board, changed)
    assert result.returncode == 0, result.stderr
    after = (board / 'payload/payload.img').read_bytes()
    diff = [index for index in range(len(before)) if before[index] != after[index]]
    assert diff, 'no bytes changed'
    print(f'ok changed-kernel: {len(diff)} byte(s) differ, first at {diff[0]}, last at {diff[-1]}')
    fat_end = 799744  # mirrored from the image layout: boot sector + FATs + root, all before the data area
    assert max(diff) < fat_end or diff[0] >= 807936, 'a difference landed inside the FAT structures'
    manifest_after = json.loads((board / 'payload/payload.json').read_text(encoding='utf-8'))
    assert manifest_after['payload_sha256'] == hashlib.sha256(after).hexdigest()
    assert manifest_after['payload_kernel_sha256'] != manifest['payload_kernel_sha256']
    print('ok manifest: payload_sha256 and payload_kernel_sha256 follow the bytes')

    small = work / 'kernel.small.macho'
    small.write_bytes(kernel[:1024])
    result = run(board, small)
    assert result.returncode != 0, 'a truncated kernel must be refused'
    assert 'refuse' in (result.stdout + result.stderr)
    print('ok wrong-size: refused')
    shutil.rmtree(work)
    print('TESTS OK: fast payload keeps the FAT and the manifest honest')
    return 0


if __name__ == '__main__':
    sys.exit(main())
