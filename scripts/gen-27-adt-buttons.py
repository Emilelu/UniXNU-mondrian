#!/usr/bin/env python3
"""Generate the iOS 27 ADT offline and check the input nodes inside the bytes.

This closes the gap between "board.toml carries the node" and "the ADT the
payload gets carries the node": the hardware DTS is compiled by dtc, the ADT is
built by the framework's own generator (scripts/unixnu/devicetree.py:generate),
and the resulting node table is decoded and compared property by property.

No build, no payload, no device. Paths are all arguments; nothing is hardcoded
to /opt and the work directory defaults to a temporary directory.

Exit code 0 when every expected property is present with the expected value,
1 otherwise (each mismatch is printed), 2 on a usage or tool error.
"""
import argparse
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

# The four official /buttons fields (docs/zh/guide/mobilegestalt.md:26-27, :42-44)
# and the six properties the K60 key driver asserts by exact name
# (bsd/dev/pong_buttons.c:45-50).
BUTTONS_STRING = {
    'compatible': b'buttons\0',
    'device_type': b'buttons\0',
}
BUTTONS_OTHER = {
    'button-names': b'hold\0voldown\0volup\0',
    'home-button-type': struct.pack('<I', 2),
}
PONG_BUTTONS = {
    'core-base': struct.pack('<Q', 0xc400000),
    'cnfg-base': struct.pack('<Q', 0xc42d000),
    'observer-base': struct.pack('<Q', 0xc440000),
    'ee': struct.pack('<I', 0),
    'pon-ppid': struct.pack('<I', 0x013),
    'volume-up-ppid': struct.pack('<I', 0x18d),
}
PONG_TOUCH = {
    'compatible': b'xiaomi,m11a-spi\0',
    'spi-base': struct.pack('<Q', 0x990000),
    'tlmm-base': struct.pack('<Q', 0xf000000),
    'gcc-base': struct.pack('<Q', 0x100000),
    'gpio-offset': struct.pack('<I', 0x100000),
    'avdd-gpio': struct.pack('<I', 71),
    'max-x': struct.pack('<I', 14400),
    'max-y': struct.pack('<I', 32000),
}

PONG_TOUCH['pins'] = bytes.fromhex('100000001100000012000000130000001500000014000000')
PONG_TOUCH['bitbang-pins'] = bytes.fromhex('10000000110000001200000013000000')
PONG_TOUCH_PINS = '100000001100000012000000130000001500000014000000'
PONG_TOUCH_BITBANG = '10000000110000001200000013000000'


def decode(blob):
    """Decode the Apple ADT node table into {path: {property: raw value}}.

    The layout matches scripts/test-devicetree-handoff.py:45-56 and the encoder
    in scripts/unixnu/devicetree.py:13-22 (u32 property count, u32 child count,
    32-byte NUL-padded name plus u32 length per property, 4-byte padding).
    """
    entries = {}

    def consume(offset, parent):
        count, children = struct.unpack_from('<II', blob, offset)
        offset += 8
        properties = {}
        for _ in range(count):
            key, size = struct.unpack_from('<32sI', blob, offset)
            offset += 36
            properties[key.split(b'\0', 1)[0].decode()] = blob[offset:offset + size]
            offset += (size + 3) & ~3
        path = parent + '/' + properties.pop('name').rstrip(b'\0').decode()
        entries[path] = properties
        for _ in range(children):
            offset = consume(offset, path)
        return offset

    if consume(0, '') != len(blob):
        raise ValueError('trailing ADT bytes')
    return entries


def decode_text(raw, expected=None):
    """Render a property value the way dtc would print it.

    The expected value decides the rendering, so a small integer never prints
    as the ASCII characters that share its bytes.
    """
    if expected is not None:
        segments = expected.split(b'\0')
        if segments and segments[-1] == b'':
            segments = segments[:-1]
        text = bool(segments) and all(seg and all(32 <= byte < 127 for byte in seg) for seg in segments)
        if text:
            return raw.split(b'\0')[0].decode() + ''.join('", "' + part.decode() for part in segments[1:])
        if len(expected) in (4, 8) and len(raw) == len(expected):
            return '0x%x' % int.from_bytes(raw, 'little')
        if expected and len(expected) % 4 == 0:
            cells = [int.from_bytes(raw[i:i + 4], 'little') for i in range(0, len(raw), 4)]
            return '<' + ' '.join('0x%x' % cell for cell in cells) + '>'
    if raw.endswith(b'\0') and all(32 <= byte < 127 or byte == 0 for byte in raw):
        return raw.rstrip(b'\0').decode().replace('\0', '", "')
    if len(raw) in (4, 8):
        return '0x%x' % int.from_bytes(raw, 'little')
    if raw and len(raw) % 4 == 0:
        cells = [int.from_bytes(raw[i:i + 4], 'little') for i in range(0, len(raw), 4)]
        return '<' + ' '.join('0x%x' % cell for cell in cells) + '>'
    return raw.hex()


def compare(name, entries, path, expected, problems, table):
    props = entries.get(path)
    if props is None:
        problems.append(f'{path}: node missing from the ADT')
        table.append((path, '-', 'node', 'missing', 'FAIL'))
        return
    extra = sorted(set(props) - set(expected))
    for key, want in expected.items():
        if key not in props:
            problems.append(f'{path}:{key}: missing')
            table.append((path, key, decode_text(want, want), 'absent', 'FAIL'))
            continue
        got = props[key]
        ok = got == want
        table.append((path, key, decode_text(want, want), decode_text(got, want), 'ok' if ok else 'FAIL'))
        if not ok:
            problems.append(f'{path}:{key}: expected {want.hex()}, got {got.hex()}')
    for key in extra:
        table.append((path, key, '-', decode_text(props[key]), 'extra'))
    print(f'{name}: {len(props)} propert(y|ies) at {path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board', type=Path, required=True, help='device board.toml')
    parser.add_argument('--dts', type=Path, required=True, help='hardware DTS compiled into the FDT')
    parser.add_argument('--os-profile', type=Path, required=True, help='OS profile.toml merged over the board')
    parser.add_argument('--framework', type=Path, required=True, help='UniXNU checkout (scripts/ on sys.path)')
    parser.add_argument('--include-dir', type=Path, action='append', default=[],
                        help='extra dtc include directory (may repeat)')
    parser.add_argument('--work', type=Path, help='keep dtb/adt here instead of a temporary directory')
    parser.add_argument('--dtc', default=shutil.which('dtc') or 'dtc')
    parser.add_argument('--unique-chip-id', default='1',
                        help='synthetic identity for the offline run; it only feeds /chosen, never the input nodes')
    parser.add_argument('--json', action='store_true', help='print the table as JSON')
    args = parser.parse_args()

    sys.path.insert(0, str(args.framework / 'scripts'))
    from unixnu.devicetree import generate
    from unixnu.profiles import merge

    board = tomllib.loads(args.board.read_text(encoding='utf-8'))
    profile = tomllib.loads(args.os_profile.read_text(encoding='utf-8'))
    config = merge(profile, board)

    keep = args.work is not None
    work = args.work or Path(tempfile.mkdtemp(prefix='adt27-'))
    if keep:
        work.mkdir(parents=True, exist_ok=True)
    dtb, adt = work / 'hardware.dtb', work / 'kernel.macho.adt'
    command = [args.dtc, '-I', 'dts', '-O', 'dtb', '-o', str(dtb)]
    for directory in args.include_dir:
        command += ['-i', str(directory)]
    command.append(str(args.dts))
    done = subprocess.run(command, capture_output=True, text=True)
    if done.returncode:
        print(done.stderr.strip() or done.stdout.strip(), file=sys.stderr)
        return 2
    decompiled = work / 'hardware.decompiled.dts'
    back = subprocess.run([args.dtc, '-I', 'dtb', '-O', 'dts', '-o', str(decompiled), str(dtb)],
                          capture_output=True, text=True)
    if back.returncode:
        print(back.stderr.strip() or back.stdout.strip(), file=sys.stderr)
        return 2
    adt.write_bytes(generate(dtb, config, unique_chip_id=args.unique_chip_id))
    entries = decode(adt.read_bytes())

    problems, table = [], []
    compare('/buttons', entries, '/device-tree/buttons', BUTTONS_STRING | BUTTONS_OTHER, problems, table)
    compare('/arm-io/pong-buttons', entries, '/device-tree/arm-io/pong-buttons', PONG_BUTTONS, problems, table)
    compare('/arm-io/pong-touch', entries, '/device-tree/arm-io/pong-touch', PONG_TOUCH, problems, table)
    # A /buttons with menu would mean a home-button device and disabled gestures
    # (docs/zh/guide/mobilegestalt.md:42-44); it must not appear.
    names = entries.get('/device-tree/buttons', {}).get('button-names', b'')
    if b'menu' in names:
        problems.append('/device-tree/buttons:button-names: menu must not be present')

    if args.json:
        print(json.dumps({'dtb': str(dtb), 'adt': str(adt), 'adt_bytes': adt.stat().st_size,
                          'dtb_bytes': dtb.stat().st_size, 'nodes': len(entries), 'table': table,
                          'problems': problems}, ensure_ascii=False, indent=2))
    else:
        print(f'\nhardware.dtb {dtb.stat().st_size:,} B → kernel.macho.adt {adt.stat().st_size:,} B, '
              f'{len(entries)} ADT node(s), work {work}')
        print(f'dtc round trip: hardware.dtb → {decompiled.name} '
              f'{decompiled.stat().st_size:,} B, {len(decompiled.read_text().splitlines())} lines')
        print(f'{"node":<18} {"property":<18} {"expected":<22} {"in the ADT":<22} verdict')
        for path, key, want, got, verdict in table:
            print(f'{path:<18} {key:<18} {want[:22]:<22} {got[:22]:<22} {verdict}')
    if problems:
        print('\nverdict: FAIL (exit 1) — ' + '; '.join(problems))
        return 1
    print(f'\nverdict: PASS (exit 0)\nPASS: /buttons ({len(BUTTONS_STRING) + len(BUTTONS_OTHER)} fields), '
          f'/arm-io/pong-buttons ({len(PONG_BUTTONS)} properties), '
          f'/arm-io/pong-touch ({len(PONG_TOUCH)} properties) are present in the generated ADT bytes')
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
