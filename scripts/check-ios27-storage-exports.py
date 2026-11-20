#!/usr/bin/env python3
"""Answer one question about a kernelcache: are the storage symbols exported?

The 27 kernel links the ufs driver into com.apple.kernel, but IOBlockStorageDevice
lives in the com.apple.iokit.IOStorageFamily fileset entry. Before choosing
between binding those imports (A) and shipping NativeUfs as its own entry (B),
someone has to read the artifact and say whether the symbols are exported at all.
This tool reads a kernelcache or a prelinked kernel and reports, per symbol,
which entry exports it (address included) or that no entry does.

Exit status is 0 for both answers: "not exported" is a finding, not an error.
--require-exported turns the finding into a failure, for the day the artifact
is supposed to carry them.
"""

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

STORAGE_SYMBOLS = [
    '__ZTV20IOBlockStorageDevice',
    '__ZN20IOBlockStorageDevice10gMetaClassE',
    '__ZN20IOBlockStorageDevice4initEP12OSDictionary',
    '__ZN20IOBlockStorageDeviceC2EPK11OSMetaClass',
    '__ZN20IOBlockStorageDeviceD2Ev',
    '__ZN20IOBlockStorageDevice11requestIdleEv',
    '__ZN20IOBlockStorageDevice13doSetPriorityEP26IOBlockStorageDeviceExtentjh',
    '__ZN20IOBlockStorageDevice20doGetProvisionStatusEyyPjP35IOBlockStorageProvisionDeviceExtenty',
    '__ZN20IOBlockStorageDevice7doUnmapEP26IOBlockStorageDeviceExtentjj',
    '__ZN20IOBlockStorageDevice13setPropertiesEP8OSObject',
    '__ZNK20IOBlockStorageDevice11getPropertyEPK8OSSymbol',
]

FAT_MAGIC = 0xCAFEBABE
FAT_MAGIC_64 = 0xCAFEBABF
MH_MAGIC_64 = 0xFEEDFACF
MH_FILESET = 12
LC_SYMTAB = 0x2
LC_DYLD_INFO_ONLY = 0x80000022
LC_DYLD_EXPORTS_TRIE = 0x80000033
LC_FILESET_ENTRY = 0x80000035


def read_uleb(data, offset):
    result = 0
    shift = 0
    while True:
        byte = data[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, offset
        shift += 7


def walk_trie(data):
    """Return {name: address} for one export trie."""
    exports = {}
    if not data:
        return exports
    stack = [('', 0)]
    seen = set()
    while stack:
        prefix, offset = stack.pop()
        if offset in seen or offset >= len(data):
            continue
        seen.add(offset)
        terminal, cursor = read_uleb(data, offset)
        name = prefix
        if terminal:
            flags, cursor2 = read_uleb(data, cursor)
            address, _ = read_uleb(data, cursor2)
            exports[name] = address
        cursor = cursor + terminal
        if cursor >= len(data):
            continue
        children = data[cursor]
        cursor += 1
        for _ in range(children):
            end = data.index(b'\0', cursor)
            edge = data[cursor:end].decode('utf-8', 'replace')
            child, cursor = read_uleb(data, end + 1)
            stack.append((name + edge, child))
    return exports


def parse_macho(buf, base, out):
    """Parse one Mach-O slice at buf[base:]; fill out with what it says."""
    magic, = struct.unpack_from('<I', buf, base)
    if magic != MH_MAGIC_64:
        raise ValueError(f'not a 64-bit Mach-O at {base:#x} (magic {magic:#x})')
    cputype, cpusub, filetype, ncmds, sizeofcmds = struct.unpack_from('<iiIII', buf, base + 4)
    out.setdefault('image', {})['filetype'] = filetype
    out['image']['ncmds'] = ncmds
    out['image']['cputype'] = cputype
    commands = []
    offset = base + 32
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from('<II', buf, offset)
        commands.append((cmd, offset, cmdsize))
        offset += cmdsize
    exports = {}
    symtab = {}
    tries = []
    fixed = False
    for cmd, off, size in commands:
        if cmd == LC_SYMTAB:
            symoff, nsyms, stroff, strsize = struct.unpack_from('<IIII', buf, off + 8)
            for index in range(nsyms):
                strx, ntype, nsect, ndesc, nvalue = struct.unpack_from('<IBBHQ', buf, base + symoff + index * 16)
                end = buf.index(b'\0', base + stroff + strx)
                name = buf[base + stroff + strx:end].decode('utf-8', 'replace')
                symtab[name] = (ntype, nvalue)
        elif cmd == LC_DYLD_INFO_ONLY:
            exports_off, exports_size = struct.unpack_from('<II', buf, off + 40)
            if exports_size:
                tries.append((exports_off, exports_size))
        elif cmd == LC_DYLD_EXPORTS_TRIE:
            dataoff, datasize = struct.unpack_from('<II', buf, off + 8)
            if datasize:
                tries.append((dataoff, datasize))
        elif cmd == 0x80000034:
            fixed = True
    for dataoff, datasize in tries:
        exports.update(walk_trie(buf[base + dataoff:base + dataoff + datasize]))
    out['image']['symtab_symbols'] = len(symtab)
    out['image']['symtab'] = symtab
    out['image']['export_tries'] = len(tries)
    out['image']['chained_fixups'] = fixed
    out['image']['exports'] = exports
    return commands, base


def parse_file(path):
    buf = path.read_bytes()
    magic, = struct.unpack_from('>I', buf, 0)
    base = 0
    if magic in (FAT_MAGIC, FAT_MAGIC_64):
        count, = struct.unpack_from('>I', buf, 4)
        wide = 32 if magic == FAT_MAGIC_64 else 20
        best = None
        for index in range(count):
            off = 8 + index * wide
            if wide == 32:
                cputype, cpusub, offset, size, align, _ = struct.unpack_from('>iiQQII', buf, off)
            else:
                cputype, cpusub, offset, size, align = struct.unpack_from('>iiIII', buf, off)
            if (cputype & 0x00FFFFFF) == 12:
                best = offset
                break
        if best is None:
            raise ValueError('the fat file carries no arm64 slice')
        base = best
    result = {}
    commands, base = parse_macho(buf, base, result)
    entries = []
    if result['image']['filetype'] == MH_FILESET:
        for cmd, off, size in commands:
            if cmd != LC_FILESET_ENTRY:
                continue
            vmaddr, fileoff, entry_id, reserved = struct.unpack_from('<QQII', buf, off + 8)
            start = off + entry_id
            end = buf.index(b'\0', start)
            name = buf[start:end].decode('utf-8', 'replace')
            info = {'name': name, 'fileoff': fileoff, 'vmaddr': vmaddr}
            try:
                parse_macho(buf, fileoff, info)
            except (ValueError, struct.error) as error:
                info['error'] = str(error)
            entries.append(info)
    result['entries'] = entries
    result['buffer'] = buf
    return result


def locate(entries, offset):
    hits = [e for e in entries if e['fileoff'] <= offset]
    return hits[-1]['name'] if hits else 'unknown'


def main():
    parser = argparse.ArgumentParser(description='Say whether a kernelcache exports the storage symbols.')
    parser.add_argument('--kernelcache', type=Path, required=True)
    parser.add_argument('--entry', default='com.apple.iokit.IOStorageFamily')
    parser.add_argument('--symbol', action='append', dest='symbols')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--require-exported', action='store_true')
    args = parser.parse_args()
    symbols = args.symbols or STORAGE_SYMBOLS
    if not args.kernelcache.is_file():
        print(f'FAIL no kernelcache at {args.kernelcache}')
        print('ios27-storage-exports: FAILED')
        return 1
    try:
        parsed = parse_file(args.kernelcache)
    except (ValueError, struct.error, IndexError) as error:
        print(f'FAIL cannot read {args.kernelcache}: {error}')
        print('ios27-storage-exports: FAILED')
        return 1
    buf = parsed['buffer']
    entries = parsed['entries']
    image = parsed['image']
    print(f'kernel: {args.kernelcache} ({len(buf):,} B, sha256 {hashlib.sha256(buf).hexdigest()})')
    print(f'image: filetype {image["filetype"]}'
          + (' (MH_FILESET)' if image['filetype'] == MH_FILESET else '')
          + f', {image["ncmds"]} load command(s), {len(entries)} fileset entr'
          + ('y' if len(entries) == 1 else 'ies'))
    plain = f'export trie(s) {image["export_tries"]}, {image["symtab_symbols"]} symbol name(s)'
    if not entries:
        print(f'image: {plain}')
    if entries:
        with_tries = [e for e in entries if e.get('image', {}).get('export_tries')]
        with_syms = [e for e in entries if e.get('image', {}).get('symtab_symbols')]
        print(f'entries: {len(with_tries)} of {len(entries)} carry an export trie, '
              f'{len(with_syms)} carry symbol names')
    target = next((e for e in entries if e['name'] == args.entry), None)
    if target is None and entries:
        print(f'FAIL no fileset entry named {args.entry}')
        print('ios27-storage-exports: FAILED')
        return 1
    if target is not None:
        timage = target.get('image', {})
        print(f'target: {args.entry} at file offset {target["fileoff"]:#x}'
              f', filetype {timage.get("filetype")}'
              f', {timage.get("symtab_symbols")} symbol name(s)'
              f', {timage.get("export_tries")} export trie(s)')
    exported = {}
    defined = {}
    found_in = {}
    raw_hits = {}
    for symbol in symbols:
        pool = target.get('image', {}) if target else image
        where = None
        address = None
        if symbol in pool.get('exports', {}):
            address = pool['exports'][symbol]
            where = args.entry if target else 'the kernel'
        else:
            for entry in entries:
                if symbol in entry.get('image', {}).get('exports', {}):
                    address = entry['image']['exports'][symbol]
                    where = entry['name']
                    break
        if where:
            exported[symbol] = address
            found_in[symbol] = where
            print(f'  exported  {symbol} -> {address:#x} ({where})')
            continue
        table = pool.get('symtab', {})
        if symbol in table and (table[symbol][0] & 0xE0) == 0:
            defined[symbol] = table[symbol][1]
            found_in[symbol] = 'symbol table'
            print(f'  defined   {symbol} -> {table[symbol][1]:#x} (symbol table, not exported)')
            continue
        offset = buf.find(symbol.encode() + b'\0')
        if offset >= 0:
            raw_hits[symbol] = offset
            print(f'  absent    {symbol} (as a plain string at {offset:#x}, in {locate(entries, offset)})')
        else:
            print(f'  absent    {symbol}')
    covered = len(exported) + len(defined)
    if len(exported) == len(symbols):
        verdict = 'exported'
    elif covered == len(symbols):
        verdict = 'symtab-only'
    elif covered:
        verdict = 'partial'
    else:
        verdict = 'not-exported'
    if verdict == 'exported':
        print('answer: every symbol is exported; binding them (A) is mechanical')
    elif verdict == 'symtab-only':
        print('answer: the image defines them in its symbol table but exports none; '
              'a linker can bind them only against a file that keeps that table')
    elif verdict == 'partial':
        missing = [s for s in symbols if s not in exported and s not in defined]
        print(f'answer: {len(missing)} of {len(symbols)} are neither exported nor defined here')
    else:
        print('answer: no entry exports or defines these symbols, so binding them (A)')
        print('        cannot be done from this artifact; the driver must be its own')
        print('        fileset entry (B)')
    if args.out:
        report = {
            'kernel': str(args.kernelcache),
            'size': len(buf),
            'sha256': hashlib.sha256(buf).hexdigest(),
            'filetype': image['filetype'],
            'entries': len(entries),
            'entry': args.entry,
            'target': None if target is None else {
                'fileoff': target['fileoff'],
                'filetype': target.get('image', {}).get('filetype'),
                'symtab_symbols': target.get('image', {}).get('symtab_symbols'),
                'export_tries': target.get('image', {}).get('export_tries'),
            },
            'symbols': symbols,
            'exported': exported,
            'defined_in_symtab': defined,
            'exported_by': found_in,
            'missing': [s for s in symbols if s not in exported and s not in defined],
            'raw_string_offsets': raw_hits,
            'verdict': verdict,
            'hardware_verified': False,
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + '\n')
        print(f'report: {args.out}')
    print(f'ios27-storage-exports: {verdict}')
    if args.require_exported and verdict != 'exported':
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
