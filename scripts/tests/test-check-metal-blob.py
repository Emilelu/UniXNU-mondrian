#!/usr/bin/env python3
"""Verify check-metal-blob.py catches each broken shape.

The first device boot failed as K60METAL deploy files=5/6 error=22 because
k60_metal_blob_len omitted the alignment padding between bodies; no gate then
could see the mismatch (P-196). Each case mutates a correct container and
asserts the checker rejects it.

The fixture mirrors what scripts/gen-k60-metal-blob.py really emits: the table
and the names as .byte lines, then one .incbin per body. The checker counts
.incbin lines against the entry count, so a fixture that inlined the bodies
would test a shape the build never produces. Everything is built from the
constants below, so the test never reads a scratch path the repository does not
own (iron rule 1).
"""
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

CHECKER = Path(__file__).resolve().parents[1] / 'check-metal-blob.py'
ALIGN = 8
NAMES = [
    'addons/PongAdrenoMetal.bundle/Info.plist',
    'addons/PongAdrenoMetal.bundle/PongAdrenoMetal',
    'addons/PongAdrenoMetal.bundle/PongMetalBridge.dylib',
    'addons/PongAdrenoMetal.bundle/libvulkan_freedreno.dylib',
    'PongAdrenoMetal.clients',
    'PongAdrenoMetal.publish',
]
# Sizes mirror the real plugin; every body starts on an ALIGN boundary.
SIZES = [695, 94896, 33146048, 18036688, 122, 2]


def align(value: int) -> int:
    return (value + ALIGN - 1) & ~(ALIGN - 1)


def layout(pad_length: bool = True):
    """Return (header bytes, offsets, declared length).

    pad_length=True is the fixed generator: the declared length is the cursor
    after the last body. pad_length=False is the bug P-196 describes: bodies
    are still aligned, but the length only sums the raw sizes.
    """
    names = b''.join(n.encode() for n in NAMES)
    count = len(NAMES)
    base = align(8 + count * 10 + len(names))
    offsets, cursor = [], base
    for size in SIZES:
        cursor = align(cursor)
        offsets.append(cursor)
        cursor += size
    declared = cursor if pad_length else base + sum(SIZES)
    table = b''.join(struct.pack('<HII', len(n), s, o)
                     for n, s, o in zip(NAMES, SIZES, offsets))
    head = struct.pack('<4sI', b'K60M', count) + table + names
    head += bytes(base - len(head))
    return head, offsets, declared


def assembly(head: bytes, declared: int, incbins: int = len(NAMES)) -> str:
    lines = ['.data', '.globl _k60_metal_blob', '.p2align 3', '_k60_metal_blob:']
    for start in range(0, len(head), 16):
        chunk = head[start:start + 16]
        lines.append('    .byte ' + ','.join('0x%02x' % b for b in chunk))
    for idx in range(incbins):
        lines.append('    .incbin "body%d.bin"' % idx)
    lines += ['.globl _k60_metal_blob_len', '.p2align 3', '_k60_metal_blob_len:',
              '    .quad %d' % declared]
    lines += ['.globl _k60_metal_blob_modes', '.p2align 3', '_k60_metal_blob_modes:',
              '    .short ' + ','.join('0%o' % (0o644 if i not in (1, 2, 3) else 0o755)
                                        for i in range(incbins))]
    return '\n'.join(lines) + '\n'


def entry_at(head: bytes, idx: int) -> int:
    return 8 + idx * 10


def run(target: Path):
    proc = subprocess.run([sys.executable, str(CHECKER), str(target)],
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def main() -> None:
    results = []

    with tempfile.TemporaryDirectory() as td:
        t = Path(td)

        head, offsets, declared = layout()
        p = t / 'good.s'
        p.write_text(assembly(head, declared))
        rc, out = run(p)
        results.append(('a healthy container passes', rc == 0, out))

        buggy_head, buggy_offsets, buggy_declared = layout(pad_length=False)
        p = t / 'unpadded.s'
        p.write_text(assembly(buggy_head, buggy_declared))
        rc, out = run(p)
        results.append(('an unpadded length is rejected (the measured bug)',
                        rc == 1 and 'P-196' in out, out))

        results.append(('the unpadded length is %d and the padded one %d'
                        % (buggy_declared, declared),
                        buggy_declared < declared
                        and buggy_offsets[:4] == offsets[:4], ''))

        p = t / 'overlap.s'
        blob = bytearray(head)
        struct.pack_into('<HII', blob, entry_at(blob, 5), len(NAMES[5]), 2, offsets[4])
        p.write_text(assembly(bytes(blob), declared))
        rc, out = run(p)
        results.append(('an overlapping body is rejected', rc == 1 and 'overlap' in out, out))

        p = t / 'past.s'
        blob = bytearray(head)
        struct.pack_into('<HII', blob, entry_at(blob, 5), len(NAMES[5]), 2, declared + 16)
        p.write_text(assembly(bytes(blob), declared))
        rc, out = run(p)
        results.append(('a body past the end is rejected', rc == 1 and 'runs past' in out, out))

        p = t / 'magic.s'
        blob = bytearray(head)
        blob[0:4] = b'K59M'
        p.write_text(assembly(bytes(blob), declared))
        rc, out = run(p)
        results.append(('a wrong magic is rejected', rc == 1 and 'K60M' in out, out))

        p = t / 'count.s'
        p.write_text(assembly(head, declared, incbins=len(NAMES) - 1))
        rc, out = run(p)
        results.append(('an entry count that disagrees with the assembly is rejected',
                        rc == 1 and 'incbin' in out, out))

        p = t / 'empty.s'
        blob = bytearray(head)
        struct.pack_into('<HII', blob, entry_at(blob, 0), 0, SIZES[0], offsets[0])
        p.write_text(assembly(bytes(blob), declared))
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
