#!/usr/bin/env python3
"""Auto-slide wrapper around the pinned XnuPrelink emitter.

The 20G81 prelink components overlap the K60 kernel's __DATA at slide 0.
Search downward in 0x4000 steps until plan() accepts the slide, then emit.
The submodule is left untouched: the preflight copies the original emitter to
emit_prelink_orig.py and installs this file as emit_prelink.py.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import emit_prelink_orig as orig  # noqa: E402

STEP = 0x4000
LIMIT = -0x400000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', required=True, type=Path)
    parser.add_argument('--prelinked', required=True, type=Path)
    parser.add_argument('--root', required=True, action='append')
    parser.add_argument('--slide', required=True, type=lambda value: int(value, 0))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--early-security-init', action='append', default=[],
                        metavar='BUNDLE=ORIGINAL_VA')
    args = parser.parse_args()

    initializers = {}
    for request in args.early_security_init:
        identifier, separator, address = request.partition('=')
        if not separator or not identifier or identifier in initializers:
            parser.error('Use one BUNDLE=ORIGINAL_VA initializer per module')
        initializers[identifier] = int(address, 0)

    native = args.kernel.read_bytes()
    original = args.prelinked.read_bytes()
    slide = args.slide
    last = None
    while True:
        try:
            orig.plan(native, original, args.root, slide)
            break
        except ValueError as exc:
            if 'collides' not in str(exc):
                raise
            last = exc
            if slide <= LIMIT:
                raise SystemExit(
                    f'no slide in [{LIMIT:#x}, {args.slide:#x}] avoids collision: {last}')
            slide -= STEP

    image, report = orig.emit(native, original, args.root, slide, initializers)
    if args.output.exists():
        raise SystemExit('Refuse to overwrite an existing candidate')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(image)
    args.output.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'auto-slide: {slide:#x} (requested {args.slide:#x}); {len(image)} bytes')


if __name__ == '__main__':
    main()
