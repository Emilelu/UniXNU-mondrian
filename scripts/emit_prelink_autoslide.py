#!/usr/bin/env python3
"""Auto-slide wrapper around the pinned XnuPrelink emitter.

The 20G81 prelink components are packed up to __PRELINK_DATA's end
(0xfffffff007ba0000), which overlaps the K60 kernel's own segments: the native
__DATA is larger than the 20G81 one, so slide 0 collides.  plan() only rejects
component extents that overlap a native segment, so the slide that clears every
component is bounded by the lowest native segment:

    slide <= min(native segment va) - max(component extent end)

That bound is computed from the two Mach-O headers (cheap) and then verified by
plan() itself; a few extra steps guard against a component extent that reaches
past the outer prelink segments.  The submodule is left untouched: the preflight
copies the original emitter to emit_prelink_orig.py and installs this file as
emit_prelink.py.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import emit_prelink_orig as orig  # noqa: E402
import native_prelink as np  # noqa: E402

STEP = 0x4000           # plan() requires a 4K-preserving slide
FALLBACK = 0x40000      # extra clearance when a component extent is not packed
ATTEMPTS = 16
PRELINK_SEGMENTS = ('__PRELINK_TEXT', '__PLK_TEXT_EXEC', '__PLK_DATA_CONST', '__PRELINK_DATA')


def component_end(original):
    """Upper bound of the component extents: the end of the outer prelink segments."""
    return max(s['va'] + s['size'] for s in original['segments']
               if s['name'] in PRELINK_SEGMENTS and s['size'])


def analytic_slide(native, original, requested):
    floor = min(s['va'] for s in native['segments'] if s['size'])
    need = floor - component_end(original)
    return (min(requested, need) // STEP) * STEP


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
    try:
        orig.plan(native, original, args.root, slide)
    except ValueError as exc:
        if 'collides' not in str(exc):
            raise
        slide = analytic_slide(np.macho(native), np.macho(original), slide)
        print(f'auto-slide: requested {args.slide:#x} collides ({exc}); '
              f'trying {slide:#x}', file=sys.stderr)
        for _ in range(ATTEMPTS):
            try:
                orig.plan(native, original, args.root, slide)
                break
            except ValueError as retry:
                if 'collides' not in str(retry):
                    raise
                print(f'auto-slide: {slide:#x} still collides ({retry})', file=sys.stderr)
                slide -= FALLBACK
        else:
            raise SystemExit(f'no slide clears the collision; last tried {slide + FALLBACK:#x}')

    image, report = orig.emit(native, original, args.root, slide, initializers)
    if args.output.exists():
        raise SystemExit('Refuse to overwrite an existing candidate')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(image)
    args.output.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    lowest = min(extent['va'] for extent in report['extents'])
    print(f'auto-slide: {slide:#x} (requested {args.slide:#x}); {len(image)} bytes; '
          f'lowest component extent {lowest:#x}')


if __name__ == '__main__':
    main()
