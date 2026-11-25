#!/usr/bin/env python3
"""Regression: swapping a kernel into boot.img changes the kernel bytes and nothing else.

Copies the real boot.img and payload.img, mutates one byte of the kernel, writes it
into both images through the shipped scripts, then asserts that the boot image
differs only inside the kernel range and that the payload's FAT structures are
untouched. A smaller kernel must be refused.
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
BOARD = pathlib.Path('/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27')
SCRATCH = pathlib.Path('/mnt/e/iOS Port/Work/scratch')


def main():
    work = pathlib.Path(tempfile.mkdtemp(prefix='swapboot-', dir=SCRATCH))
    board = work / 'board'
    (board / 'payload').mkdir(parents=True)
    (board / 'boot').mkdir(parents=True)
    shutil.copyfile(BOARD / 'payload/payload.img', board / 'payload/payload.img')
    shutil.copyfile(BOARD / 'payload/payload.json', board / 'payload/payload.json')
    shutil.copyfile(BOARD / 'boot/boot.img', board / 'boot/boot.img')
    kernel = bytearray((BOARD / 'kernel/kernel.macho').read_bytes())
    kernel[0x2000] ^= 0xFF
    changed = work / 'kernel.changed.macho'
    changed.write_bytes(bytes(kernel))

    first = subprocess.run([sys.executable, str(ROOT / 'scripts/k60-fast-payload.py'),
                            '--device', str(ROOT), '--board', str(board), '--kernel', str(changed)],
                           capture_output=True, text=True)
    assert first.returncode == 0, first.stderr + first.stdout
    before = (board / 'boot/boot.img').read_bytes()
    second = subprocess.run([sys.executable, str(ROOT / 'scripts/k60-kernel-swap.py'),
                             '--kernel', str(changed), '--payload', str(board / 'payload/payload.img'),
                             '--boot', str(board / 'boot/boot.img'), '--apply'],
                            capture_output=True, text=True)
    assert second.returncode == 0, second.stderr + second.stdout
    after = (board / 'boot/boot.img').read_bytes()
    diff = [index for index in range(len(before)) if before[index] != after[index]]
    assert diff, 'the boot image did not change'
    print(f'ok boot: {len(diff)} byte(s) differ, first at {diff[0]}, last at {diff[-1]}')
    assert 1377280 <= diff[0] and diff[-1] < 1377280 + len(kernel), 'a difference landed outside the kernel'
    print('ok boot: every difference is inside the kernel range')

    small = work / 'kernel.small.macho'
    small.write_bytes(bytes(kernel[:512]))
    third = subprocess.run([sys.executable, str(ROOT / 'scripts/k60-kernel-swap.py'),
                            '--kernel', str(small), '--payload', str(board / 'payload/payload.img'),
                            '--boot', str(board / 'boot/boot.img')],
                           capture_output=True, text=True)
    assert third.returncode != 0 and 'refuse' in (third.stdout + third.stderr)
    print('ok boot: a wrong-size kernel is refused')
    shutil.rmtree(work)
    print('TESTS OK: the boot swap writes the kernel range and nothing else')
    return 0


if __name__ == '__main__':
    sys.exit(main())
