#!/usr/bin/env python3
"""Check the F1 artifacts after a build, with no board attached.

`unixnu build kernel`, `build payload` and `bootimg` each verify what they
produce, but nothing checks the set afterwards: that the payload still carries
the kernel the kernel step linked, that the ADT still pins /chosen/random-seed
(a random seed turns one boot in three into a pmap_map_bd death), that the
identity the profile promises is the one in the tree, and that boot.img holds
the firmware volume and the payload byte for byte. Each of those fails silently
in a rebuild, so they are asserted here.

    python3 scripts/check-ios27-artifacts.py ~/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27

The board directory defaults to $UNIXNU_OUT/mondrian/<profile>/<config> when the
variable is set. Exits nonzero and prints `error: ...` on the first broken
invariant.
"""
import argparse
import hashlib
import os
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

MH_MAGIC_64 = 0xFEEDFACF
CPU_TYPE_ARM64 = 0x0100000C
CPU_SUBTYPE_ARM64E = 2
MH_EXECUTE = 2
MH_NOUNDEFS, MH_PIE = 0x1, 0x200000
LC_BUILD_VERSION = 0x32
PLATFORM_IOS = 2
FD_BYTES = 0x300000
FAT_KERNEL = '::/EFI/UniXNU/Payloads/kernel.macho'
FAT_ADT = '::/EFI/UniXNU/Payloads/kernel.macho.adt'


class Failure(Exception):
    pass


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def macho(path):
    """Header and LC_BUILD_VERSION of the thin arm64e executable."""
    data = path.read_bytes()
    magic, cputype, cpusubtype, filetype, ncmds, sizeofcmds, flags, _ = struct.unpack_from('<8I', data, 0)
    if magic != MH_MAGIC_64:
        raise Failure(f'{path.name}: magic {magic:#x}, not MH_MAGIC_64')
    if cputype != CPU_TYPE_ARM64:
        raise Failure(f'{path.name}: cputype {cputype:#x}, not arm64')
    if cpusubtype & 0x00FFFFFF != CPU_SUBTYPE_ARM64E:
        raise Failure(f'{path.name}: cpusubtype {cpusubtype & 0xFFFFFF}, not arm64e')
    if filetype != MH_EXECUTE:
        raise Failure(f'{path.name}: filetype {filetype}, not MH_EXECUTE')
    for name, bit in (('NOUNDEFS', MH_NOUNDEFS), ('PIE', MH_PIE)):
        if not flags & bit:
            raise Failure(f'{path.name}: MH_{name} is not set')
    pos, build = 32, None
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', data, pos)
        if cmd == LC_BUILD_VERSION:
            platform, minos, sdk = struct.unpack_from('<3I', data, pos + 8)
            build = (platform, minos, sdk)
        pos += size
    if build is None:
        raise Failure(f'{path.name}: no LC_BUILD_VERSION')
    platform, minos, sdk = build
    if platform != PLATFORM_IOS:
        raise Failure(f'{path.name}: platform {platform}, not iOS')
    for label, value in (('minos', minos), ('sdk', sdk)):
        if value >> 16 != 27:
            raise Failure(f'{path.name}: {label} {value >> 16}.{value & 0xFFFF}, not 27.x')
    return len(data), flags


def fat_extract(image, member, directory):
    target = directory / Path(member).name
    result = subprocess.run(['mcopy', '-o', '-n', '-i', str(image), member, str(target)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise Failure(f'{image.name}: cannot read {member}: {result.stderr.strip()}')
    return target.read_bytes()


def parse_node(data, pos):
    nprops, nchildren = struct.unpack_from('<II', data, pos)
    pos += 8
    props = {}
    for _ in range(nprops):
        key = data[pos:pos + 32].split(b'\0')[0].decode()
        size, = struct.unpack_from('<I', data, pos + 32)
        props[key] = data[pos + 36:pos + 36 + size]
        pos += 36 + size + (-size % 4)
    children = []
    for _ in range(nchildren):
        child, pos = parse_node(data, pos)
        children.append(child)
    return (props['name'].rstrip(b'\0').decode(), props, children), pos


def chosen_properties(adt):
    def walk(node):
        name, props, children = node
        if name == 'chosen':
            return props
        for child in children:
            found = walk(child)
            if found is not None:
                return found
        return None
    node, end = parse_node(adt, 0)
    if end != len(adt):
        raise Failure(f'ADT: parsed {end} of {len(adt)} bytes')
    chosen = walk(node)
    if chosen is None:
        raise Failure('ADT: no /chosen node')
    return chosen


def check(board, chip_id, unique_chip_id):
    kernel = board / 'kernel/kernel.macho'
    payload = board / 'payload/payload.img'
    boot = board / 'boot/boot.img'
    for path in (kernel, payload, boot):
        if not path.is_file():
            raise Failure(f'missing {path}: build kernel, payload and bootimg first')

    size, flags = macho(kernel)
    print(f'ok kernel.macho: arm64e MH_EXECUTE, flags {flags:#x}, {size} bytes, sha256 {sha256(kernel)[:12]}')

    with tempfile.TemporaryDirectory(prefix='ios27-artifacts-') as name:
        directory = Path(name)
        packed_kernel = fat_extract(payload, FAT_KERNEL, directory)
        if packed_kernel != kernel.read_bytes():
            raise Failure('payload kernel.macho differs from kernel/kernel.macho')
        adt = fat_extract(payload, FAT_ADT, directory)
        print(f'ok payload.img: {payload.stat().st_size} bytes, kernel.macho identical, ADT {len(adt)} bytes')

    chosen = chosen_properties(adt)
    seed = chosen.get('random-seed')
    if seed is None:
        raise Failure('ADT: /chosen has no random-seed, the kernel will use a fresh physmap slide')
    if len(seed) != 256:
        raise Failure(f'ADT: random-seed is {len(seed)} bytes, xnu-12377 reads four 64-byte seeds')
    if len(set(seed)) != 1:
        raise Failure('ADT: random-seed is not a pinned value, the slide moves between builds')
    print(f'ok ADT random-seed: {len(seed)} bytes of {seed[0]:#04x}')

    identity = chosen.get('chip-id')
    if identity is None or int.from_bytes(identity, 'little') != chip_id:
        actual = 'absent' if identity is None else f'{int.from_bytes(identity, "little"):04x}'
        raise Failure(f'ADT: chip-id {actual}, expected {chip_id:04x}')
    seed_id = chosen.get('unique-chip-id')
    if seed_id is None or int.from_bytes(seed_id, 'little') != unique_chip_id:
        actual = 'absent' if seed_id is None else f'{int.from_bytes(seed_id, "little"):016x}'
        raise Failure(f'ADT: unique-chip-id {actual}, expected {unique_chip_id:016x}')
    print(f'ok ADT identity: chip-id {chip_id:04x}, unique-chip-id {unique_chip_id:016x}')

    image = boot.read_bytes()
    magic, kernel_size, ramdisk_size, _, header_size = struct.unpack_from('<8s4I', image, 0)
    if magic != b'ANDROID!':
        raise Failure(f'boot.img: magic {magic!r}, not ANDROID!')
    if struct.unpack_from('<I', image, 40)[0] != 4:
        raise Failure('boot.img: header is not v4')
    page = 4096
    start = page * ((header_size + page - 1) // page)
    stream = zlib.decompressobj(31)
    blob = stream.decompress(image[start:start + kernel_size])
    tree = stream.unused_data
    if len(blob) < FD_BYTES:
        raise Failure(f'boot.img: kernel payload is {len(blob)} bytes, shorter than the firmware volume')
    firmware = blob[-FD_BYTES:]
    if firmware[40:44] != b'_FVH':
        raise Failure('boot.img: the firmware volume has no _FVH signature at offset 40')
    if tree[:4] != b'\xd0\x0d\xfe\xed' or struct.unpack_from('>I', tree, 4)[0] != len(tree):
        raise Failure('boot.img: the appended device tree is missing or truncated')
    ramdisk_at = start + ((kernel_size + page - 1) // page) * page
    ramdisk = image[ramdisk_at:ramdisk_at + ramdisk_size]
    if ramdisk != payload.read_bytes():
        raise Failure('boot.img: the ramdisk is not the current payload.img')
    print(f'ok boot.img: {len(image)} bytes, hdr v4 {header_size}, shim {len(blob) - FD_BYTES} B, '
          f'FD {FD_BYTES} B sha256 {hashlib.sha256(firmware).hexdigest()[:12]}, DTB {len(tree)} B, '
          f'ramdisk = payload')
    print(f'artifacts: {boot.stat().st_size} byte boot.img sha256 {sha256(boot)}')


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('board', nargs='?', help='board output directory (default: $UNIXNU_OUT/mondrian/...)')
    parser.add_argument('--chip-id', default='8140', help='expected /chosen/chip-id (T8140)')
    parser.add_argument('--unique-chip-id', default='4d4f4e445249414e', help='expected /chosen/unique-chip-id')
    args = parser.parse_args()
    board = Path(args.board) if args.board else Path(
        os.environ.get('UNIXNU_OUT', '')) / 'mondrian/ios-27.0.1-24A446/mondrian_ios27'
    if not board.is_dir():
        parser.error(f'no board directory at {board}; pass it or set UNIXNU_OUT')
    try:
        check(board, int(args.chip_id, 16), int(args.unique_chip_id, 16))
    except Failure as error:
        print(f'error: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
