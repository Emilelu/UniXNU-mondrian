#!/usr/bin/env python3
"""Prelink 22H374 kexts onto the K60 darwin24 kernel (route A-18).

Why this exists: the darwin24 route has no `profiles/os/ipados-18.7.10-22H374`,
so `unixnu build kernel` never ran its prelink step and the kernel shipped with
`__PRELINK_TEXT / __PRELINK_INFO / __PRELINK_DATA` all empty (20.8 MB against
the 20G81 kernel's 7.4 MB / 461 KB / 1.4 MB).  pong's own darwin24 pipeline does
run it (`build-ipados18-prelinked-boot.py`); our route skipped it.

Slide is fixed at -0x112C000 on purpose.  `plan()` only rejects components that
collide with native segments, and the auto-slide wrapper derives -0x2dc000, which
does not collide but does not match the layout pong proved either.  The legal
window is [-0x112C000, -0xcdc000]: the component block spans 0x2bb0000 and has to
land inside the 48 MiB `__PRELINK_TEXT` placeholder, i.e. 0xfffffff004004000 ..
0xfffffff007004000.

The three platform drivers come in as dependencies of the five roots, so they are
passed as library-only: their code and pointer bindings stay (symbols resolve),
their IOKitPersonalities are dropped (AppleARMPE would otherwise fight the
ArmDTPlatform we force-load, and AppleARMWatchdogTimer would arm a watchdog we do
not own yet).

    python3 scripts/k60-prelink-darwin24.py
    python3 scripts/k60-prelink-darwin24.py --verify-only out/.../kernel.macho
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIT = Path.home() / 'hackios/UniXNU-pong/kits/NativePrelink'
TREE = Path('/tmp/k60build/out/route-a18/Pong-iPadOS18-native')
DEFAULT_KERNEL = TREE / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/mach.development.pong.unstripped.noctf'
DEFAULT_ORIGINAL = Path('/tmp/k60build/out/ipsw/22H374/kernelcache.decompressed')
DEFAULT_OUTPUT = Path('/tmp/k60build/out/mondrian/ipados-18.7.10-22H374/mondrian/kernel/kernel.macho')

SLIDE = -0x112C000
PRELINK_FLOOR = 0xFFFFFFF004004000        # __PRELINK_TEXT placeholder
PRELINK_CEIL = 0xFFFFFFF007004000         # __TEXT of the native kernel
WINDOW_LIMIT = 254 * 1024 * 1024          # DarwinBoot: End-Base <= WINDOW_SIZE - 2 MiB

ROOTS = [
    'com.apple.kec.corecrypto',
    'com.apple.kec.pthread',
    'com.apple.filesystems.apfs',
    'com.apple.kec.Compression',
    'com.apple.AppleFSCompression.AppleFSCompressionTypeZlib',
]
LIBRARY_ONLY = {
    'com.apple.driver.AppleARMPlatform',
    'com.apple.driver.AppleARMWatchdogTimer',
    'com.apple.driver.AppleEffaceableStorage',
}

sys.path.insert(0, str(KIT))


def load_kit():
    try:
        from emit_prelink import COALESCED, emit
        from native_prelink import arm64_image, macho
    except ImportError as exc:  # pragma: no cover - environment check
        raise SystemExit(f'prelink kit not importable from {KIT}: {exc}')
    return COALESCED, emit, arm64_image, macho


def segment_table(data):
    _, _, _, macho = load_kit()
    image = macho(data)
    return [(s['name'], s['va'], s['size'], s.get('filesize', s['size']))
            for s in image['segments']]


def entry_point(data):
    """LC_UNIXTHREAD PC, parsed the way DarwinBoot's ParseKernel does."""
    _, _, _, macho = load_kit()
    commands = macho(data)['commands']
    threads = [off for cmd, off, length in commands if cmd == 0x5 and length == 288]
    if len(threads) != 1:
        raise ValueError(f'expected exactly one LC_UNIXTHREAD, found {len(threads)}')
    import struct
    return struct.unpack_from('<Q', data, threads[0] + 272)[0]


def check(data, source, expect_entry=None):
    """What DarwinBoot's ParseKernel enforces, plus the prelink extent window."""
    failures = []
    entry = next((s for s in segment_table(data) if s[0] == '__PRELINK_TEXT'), None)
    if entry is None:
        failures.append(f'{source}: no __PRELINK_TEXT segment')
        va = size = filesize = 0
    else:
        _, va, size, filesize = entry
    if size == 0:
        failures.append(f'{source}: __PRELINK_TEXT is still empty')
    info = next((s for s in segment_table(data) if s[0] == '__PRELINK_INFO'), None)
    if info is None or info[2] == 0:
        failures.append(f'{source}: __PRELINK_INFO is empty (no kext summary)')

    segments = [s for s in segment_table(data) if s[2]]
    ordered = sorted(segments, key=lambda s: s[1])
    for (name_a, va_a, size_a, _), (name_b, va_b, _, _) in zip(ordered, ordered[1:]):
        if va_a + size_a > va_b:
            failures.append(f'{source}: {name_a} overlaps {name_b}')

    low = min(s[1] for s in segments)
    high = max(s[1] + s[2] for s in segments)
    if low < PRELINK_FLOOR:
        failures.append(f'{source}: lowest segment {low:#x} below the prelink floor')
    # Only the code/data blocks have to stay under the native __TEXT; __PRELINK_INFO
    # is legitimately placed above it (0xfffffff0084e4000 on Apple's own kernel).
    for name, seg_va, seg_size, _ in segments:
        if name.startswith('__PLK') or name in ('__PRELINK_TEXT', '__PRELINK_DATA'):
            if seg_va + seg_size > PRELINK_CEIL:
                failures.append(f'{source}: {name} ends above the native __TEXT')
    if high - low > WINDOW_LIMIT:
        failures.append(f'{source}: span {high - low:#x} exceeds the loader window')

    pc = entry_point(data)
    if expect_entry is not None and pc != expect_entry:
        failures.append(f'{source}: entry {pc:#x} != native entry {expect_entry:#x}')
    return failures, {'__PRELINK_TEXT': (hex(va), hex(size), filesize),
                      '__PRELINK_INFO_size': hex(info[2]) if info else '0x0',
                      'entry': hex(pc),
                      'lowest': hex(low), 'highest': hex(high), 'span': hex(high - low)}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--kernel', type=Path, default=DEFAULT_KERNEL)
    ap.add_argument('--original', type=Path, default=DEFAULT_ORIGINAL,
                    help='22H374 kernelcache.decompressed (cafebabe fat wrapper)')
    ap.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument('--slide', type=lambda s: int(s, 0), default=SLIDE)
    ap.add_argument('--verify-only', type=Path, metavar='MACHO',
                    help='only run the structural checks on an existing kernel.macho')
    args = ap.parse_args()

    if args.verify_only:
        failures, facts = check(args.verify_only.read_bytes(), args.verify_only.name)
        print(json.dumps(facts, indent=2))
        for line in failures:
            print(f'FAIL {line}')
        return 1 if failures else 0

    COALESCED, emit, arm64_image, macho = load_kit()
    for path in (args.kernel, args.original):
        if not path.exists():
            raise SystemExit(f'not found: {path}')
    if args.output.exists():
        raise SystemExit(f'refusing to overwrite {args.output}')

    native = args.kernel.read_bytes()
    original = arm64_image(args.original.read_bytes())
    image = macho(original)
    base = min(s['va'] for s in image['segments'] if s['name'] in COALESCED and s['size'])
    native_entry = entry_point(native)
    print(f'native  : {args.kernel.name} ({len(native)} B), entry {native_entry:#x}')
    print(f'original: {args.original.name} arm64 slice {len(original)} B')
    print(f'component base {base:#x}, slide {args.slide:#x} -> '
          f'{base + args.slide:#x} (floor {PRELINK_FLOOR:#x})')

    candidate, selection = emit(native, original, ROOTS, args.slide,
                                verify_images=True,
                                library_only_components=LIBRARY_ONLY)

    failures, facts = check(candidate, 'candidate', expect_entry=native_entry)
    print(json.dumps(facts, indent=2))
    print(f'components          : {len(selection["components"])}')
    print(f'library-only        : {", ".join(sorted(selection["library_only_components"])) or "-"}')
    print(f'components list     : {", ".join(sorted(selection["components"]))}')
    for line in failures:
        print(f'FAIL {line}')
    if failures:
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    report = args.output.with_suffix('.json')
    report.write_text(json.dumps({'slide': hex(args.slide),
                                  'roots': ROOTS,
                                  'library_only': sorted(LIBRARY_ONLY),
                                  'components': selection['components'],
                                  'library_only_components':
                                      selection['library_only_components'],
                                  'original': str(args.original),
                                  'native': str(args.kernel),
                                  'bytes': len(candidate)}, indent=2) + '\n')
    print(f'wrote {args.output} ({len(candidate)} B)')
    print(f'wrote {report}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
