#!/usr/bin/env python3
"""Decide whether a built kernel carries a crypto provider.

The build has two bootstrap modes (scripts/build-xnu-generic.sh:184-201):

  source    prng_random.c compiles in source_corecrypto14_bootstrap(), which
            starts the original corecrypto from the primary collection or
            falls back to corecrypto_kext_start().
  prelinked prng_random.o is rebuilt with -UXNU_SOURCE_CORECRYPTO14, so the
            kernel keeps no starter of its own and relies on the boot kernel
            collection carrying com.apple.kec.corecrypto.

The Data gate chain (scripts/check-bluetooth-data-gate-chain.py) asks for
prelinked. This checker answers the question that has to come first: does the
artifact that would be booted actually hold that provider? It reads the Mach-O
header, counts LC_FILESET_ENTRY records (0x80000035, the entry identifier is an
offset from the start of the load command) and looks for the corecrypto entry,
and it looks for the source provider's markers. Host-only, no device.
"""
import argparse
import json
import struct
import sys
from pathlib import Path

LC_FILESET_ENTRY = 0x80000035
MH_FILESET = 12
CORECRYPTO_IDENTIFIER = 'com.apple.kec.corecrypto'
SOURCE_MARKERS = (b'source_corecrypto14', b'corecrypto_kext_start')


def read_layers(paths):
    values, origin = {}, {}
    for path in paths:
        path = Path(path)
        if not path.is_file():
            raise SystemExit(f'FAIL layer {path} not found')
        for number, raw in enumerate(path.read_text().splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            name, _, value = line.partition('=')
            name, value = name.strip(), value.strip()
            if not name.startswith('CONFIG_'):
                continue
            if value.startswith('"') and value.endswith('"') and len(value) >= 2:
                value = value[1:-1]
            elif value == 'y':
                value = '1'
            elif value == 'n':
                value = '0'
            values[name[len('CONFIG_'):]] = value
            origin[name[len('CONFIG_'):]] = f'{path.name}:{number}'
    return values, origin


def read_macho(path):
    data = Path(path).read_bytes()
    if len(data) < 32:
        raise SystemExit(f'FAIL {path} is shorter than a Mach-O header')
    magic, _, _, filetype, ncmds, _, _, _ = struct.unpack('<8I', data[:32])
    if magic != 0xfeedfacf:
        raise SystemExit(f'FAIL {path} is not a 64-bit Mach-O (magic {magic:#x})')
    entries = []
    offset = 32
    for _ in range(ncmds):
        if offset + 8 > len(data):
            raise SystemExit(f'FAIL {path} ends inside its load commands')
        command, size = struct.unpack('<2I', data[offset:offset + 8])
        if size < 8 or offset + size > len(data):
            raise SystemExit(f'FAIL {path} has a load command of size {size}')
        if command == LC_FILESET_ENTRY:
            # fileset_entry_command: cmd, cmdsize, vmaddr, fileoff, entry_id, reserved.
            # entry_id is an offset from the start of this command to the name.
            identifier = struct.unpack('<I', data[offset + 24:offset + 28])[0]
            start = offset + identifier
            end = data.index(b'\0', start)
            entries.append(data[start:end].decode('utf-8', 'replace'))
        offset += size
    return data, filetype, entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', required=True, type=Path, help='built kernel.macho or boot kernel collection')
    parser.add_argument('--defconfig', type=Path, help='the device defconfig (the last layer)')
    parser.add_argument('--layer', action='append', default=[], type=Path,
                        help='a profile config layer that precedes the device defconfig')
    parser.add_argument('--mode', help='override CONFIG_XNU_CRYPTO_BOOTSTRAP')
    parser.add_argument('--out', type=Path, help='write report.json here')
    args = parser.parse_args()

    layers = list(args.layer) + ([args.defconfig] if args.defconfig else [])
    values, origin = read_layers(layers) if layers else ({}, {})
    mode = args.mode or values.get('XNU_CRYPTO_BOOTSTRAP', 'source')
    data, filetype, entries = read_macho(args.kernel)
    corecrypto = [name for name in entries if CORECRYPTO_IDENTIFIER in name]
    markers = {marker.decode(): data.count(marker) for marker in SOURCE_MARKERS}

    print(f'kernel: {args.kernel}')
    print(f'filetype: {filetype} ({"MH_FILESET" if filetype == MH_FILESET else "not a fileset"})')
    print(f'fileset entries: {len(entries)}')
    for name in entries[:8]:
        print(f'  {name}')
    print(f'corecrypto entries: {len(corecrypto)}')
    for name in corecrypto:
        print(f'  {name}')
    print('source markers: ' + ', '.join(f'{name}={count}' for name, count in markers.items()))
    if 'XNU_CRYPTO_BOOTSTRAP' in origin:
        print(f'XNU_CRYPTO_BOOTSTRAP={values["XNU_CRYPTO_BOOTSTRAP"]} ({origin["XNU_CRYPTO_BOOTSTRAP"]})')
    print(f'mode: {mode}')

    failures = []
    if mode == 'source':
        missing = [name for name, count in markers.items() if count == 0]
        if missing:
            failures.append('source mode was selected but the kernel does not carry '
                            + ', '.join(missing))
    elif mode == 'prelinked':
        if not corecrypto:
            failures.append(f'prelinked mode leaves no crypto provider: {len(entries)} fileset '
                            f'entr(y/ies) and none named {CORECRYPTO_IDENTIFIER}; the source '
                            'provider is compiled out by -UXNU_SOURCE_CORECRYPTO14, so nothing '
                            'starts corecrypto in this artifact')
        elif filetype != MH_FILESET:
            failures.append(f'prelinked mode needs a boot kernel collection, but this artifact '
                            f'is filetype {filetype}')
    else:
        failures.append(f'unknown XNU_CRYPTO_BOOTSTRAP={mode} (source or prelinked)')

    for failure in failures:
        print(f'FAIL {failure}')
    verdict = 'FAILED' if failures else 'OK'
    print(f'bluetooth-crypto-provider: {verdict}')

    report = {
        'kernel': str(args.kernel),
        'filetype': filetype,
        'fileset_entries': entries,
        'corecrypto_entries': corecrypto,
        'source_markers': markers,
        'mode': mode,
        'mode_origin': origin.get('XNU_CRYPTO_BOOTSTRAP'),
        'failures': failures,
        'hardware_verified': False,
    }
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
