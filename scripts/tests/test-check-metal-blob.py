#!/usr/bin/env python3
"""Verify check-metal-blob.py catches each broken shape.

The first device boot failed as K60METAL deploy files=5/6 error=22 because
k60_metal_blob_len omitted the alignment padding between bodies; no gate then
could see the mismatch (P-196). Each case mutates a correct container and
asserts the checker rejects it.
"""
import struct
import subprocess
import tempfile
from pathlib import Path

CHECKER = Path('/mnt/e/hackios/k60-gates/scripts/check-metal-blob.py')
GOOD = Path('/tmp/k60metal-probe.s')
ALIGN = 8


def rewrite(source: Path, target: Path, blob_len=None, entry=None, magic=None) -> None:
    head, incbins, length = [], 0, None
    lines = source.read_text().splitlines()
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith('.byte '):
            head.extend(int(x, 16) for x in s[len('.byte '):].split(','))
        if s == '_k60_metal_blob_len:':
            length = i
            break
    assert length is not None
    data = list(head)
    if magic is not None:
        data[0:4] = magic
    if entry is not None:
        idx, (name_len, size, offset) = entry
        data[8 + idx * 10:8 + idx * 10 + 10] = struct.pack('<HII', name_len, size, offset)
    out = []
    emitted = False
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith('.byte ') and not emitted:
            out.append('    .byte ' + ','.join('0x%02x' % b for b in data))
            emitted = True
        elif i == length + 1 and blob_len is not None:
            out.append('    .quad %d' % blob_len)
        else:
            out.append(line)
    target.write_text('\n'.join(out) + '\n')


def run(target: Path):
    proc = subprocess.run(['python3', str(CHECKER), str(target)],
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def main() -> None:
    results = []

    with tempfile.TemporaryDirectory() as td:
        t = Path(td)

        rc, out = run(GOOD)
        results.append(('a healthy container passes', rc == 0, out))

        p = t / 'short.s'
        rewrite(GOOD, p, blob_len=51278763)
        rc, out = run(p)
        results.append(('an unpadded length is rejected (the measured bug)',
                        rc == 1 and 'P-196' in out, out))

        p = t / 'overlap.s'
        rewrite(GOOD, p, entry=(5, (24, 2, 51278640)))
        rc, out = run(p)
        results.append(('an overlapping body is rejected', rc == 1 and 'overlap' in out, out))

        p = t / 'past.s'
        rewrite(GOOD, p, entry=(5, (24, 2, 51278790)))
        rc, out = run(p)
        results.append(('a body past the end is rejected',
                        rc == 1 and 'runs past' in out, out))

        p = t / 'magic.s'
        rewrite(GOOD, p, magic=b'K59M')
        rc, out = run(p)
        results.append(('a wrong magic is rejected', rc == 1 and 'K60M' in out, out))

        p = t / 'empty.s'
        rewrite(GOOD, p, entry=(0, (0, 695, 312)))
        rc, out = run(p)
        results.append(('an empty name is rejected', rc == 1 and 'empty name' in out, out))

    failed = [name for name, ok, _ in results if not ok]
    for name, ok, out in results:
        print(('PASS' if ok else 'FAIL'), name)
        if not ok:
            print(out)
    print(f'TESTS OK {len(results)} cases ({len(failed)} failure(s))')
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
