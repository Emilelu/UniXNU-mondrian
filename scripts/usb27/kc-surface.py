#!/usr/bin/env python3
"""Offline USB criterion for an iOS kernel collection. No build, no device.

Three questions this answers, each with a reproducible command:

  kexts   which kexts the prelink actually carries (__PRELINK_INFO inventory)
  surface which symbols the collection defines (llvm-nm), per required prefix
  object  which of an object file's undefined symbols the collection cannot answer
  roots   which USB kexts a profile/board asks the prelink to carry

Every check prints PASS/FAIL. Exit status is 0 only when every requested check
passed, 1 when one failed, 2 on a usage or parse error.

Usage:
  kc-surface.py kexts  KERNEL [--require-kext ID]...
  kc-surface.py surface KERNEL [--require-prefix P]... [--require-symbol S]...
  kc-surface.py object KERNEL OBJECT [--providers TSV]
  kc-surface.py roots  PROFILE_TOML [BOARD_TOML] [--require-kext ID]...

llvm-nm defaults to llvm-nm-18 (the toolchain the 27 tree is built with).
"""
import argparse
import hashlib
import plistlib
import struct
import subprocess
import sys

MACHO64 = 0xFEEDFACF
LC_SEGMENT_64 = 0x19
MH_FILESET = 0x0C
MH_EXECUTE = 0x02


class Refusal(Exception):
    pass


def read(path):
    with open(path, 'rb') as handle:
        return handle.read()


def header(data):
    if len(data) < 32:
        raise Refusal('shorter than a mach-o 64 header')
    magic = struct.unpack_from('<I', data, 0)[0]
    if magic != MACHO64:
        raise Refusal(f'not a little-endian mach-o 64 file (magic {magic:#x})')
    cputype, cpusub, filetype, ncmds, sizeofcmds, flags, _res = struct.unpack_from('<IiiIIII', data, 4)
    return {'cputype': cputype, 'filetype': filetype, 'ncmds': ncmds, 'sizeofcmds': sizeofcmds}


def segments(data, head):
    out = []
    at = 32
    for _ in range(head['ncmds']):
        if at + 8 > len(data):
            raise Refusal('load command runs past the end of the file')
        cmd, cmdsize = struct.unpack_from('<II', data, at)
        if cmdsize < 8:
            raise Refusal(f'load command at {at:#x} has cmdsize {cmdsize}')
        if cmd == LC_SEGMENT_64:
            name = data[at + 8:at + 24].rstrip(b'\0').decode('utf-8', 'replace')
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<QQQQ', data, at + 24)
            out.append({'name': name, 'vmaddr': vmaddr, 'vmsize': vmsize, 'fileoff': fileoff, 'filesize': filesize})
        at += cmdsize
    return out


def prelink_info(data, segs):
    seg = next((s for s in segs if s['name'] == '__PRELINK_INFO'), None)
    if seg is None or not seg['filesize']:
        return None
    blob = data[seg['fileoff']:seg['fileoff'] + seg['filesize']]
    candidates = []
    end = blob.find(b'</plist>')
    if end >= 0:
        candidates.append(blob[:end + len(b'</plist>')])
    candidates.append(blob)
    for candidate in candidates:
        try:
            return plistlib.loads(candidate)
        except Exception:
            continue
    return None


def kext_inventory(meta):
    """(id, load address, __TEXT size) for every executable the prelink carries."""
    if meta is None:
        return []
    out = []
    for entry in meta.get('_PrelinkInfoDictionary', []):
        load = entry.get('_PrelinkExecutableLoadAddr')
        if load is None:
            continue
        load &= 0xFFFFFFFFFFFFFFFF
        size = entry.get('_PrelinkExecutableSize') or 0
        # The com.apple.kpi.* pseudo-entries carry the sentinel load address
        # 0x7fff_ffff_ffff_ffff and no bytes; they are not executables.
        if not size:
            continue
        out.append((entry.get('CFBundleIdentifier', '<unnamed>'), load, size))
    return sorted(out)


def nm_symbols(path, nm):
    """(defined, undefined) symbol names, from llvm-nm posix output."""
    result = subprocess.run([nm, '--format=posix', '--no-sort', path],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise Refusal(f'{nm} failed on {path}: {result.stderr.strip() or result.returncode}')
    defined, undefined = set(), set()
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        name, kind = fields[0], fields[1]
        # Mach-O nlist kinds: U undefined, C common, and the case-carrying
        # section kinds for definitions (t/T, d/D, s/S, b/B, a/A, w/W, i/I, z/Z).
        (undefined if kind in ('U', 'u') else defined).add(name)
    return defined, undefined


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def describe(path):
    data = read(path)
    head = header(data)
    return data, head, segments(data, head)


def cmd_kexts(args):
    data, head, segs = describe(args.kernel)
    meta = prelink_info(data, segs)
    inventory = kext_inventory(meta)
    print(f'kernel {args.kernel}')
    print(f'  sha256   {sha256_of(args.kernel)}')
    print(f'  filetype {head["filetype"]:#x} '
          f'({"MACH_FILESET" if head["filetype"] == MH_FILESET else "MACH_EXECUTE" if head["filetype"] == MH_EXECUTE else "other"})')
    print(f'  kexts    {len(inventory)}')
    if meta is None:
        print('  note     no machine-readable __PRELINK_INFO (legacy format, or not a fileset)')
    for identifier, load, size in inventory:
        print(f'    {identifier} @ {load:#x} ({size:#x} bytes)')
    failures = []
    for wanted in args.require_kext:
        present = any(identifier == wanted for identifier, _, _ in inventory)
        print(f'  {"PASS" if present else "FAIL"} kext {wanted}')
        if not present:
            failures.append(wanted)
    return failures


def cmd_surface(args):
    data, head, segs = describe(args.kernel)
    with_syms = [s['name'] for s in segs if s['filesize']]
    defined, undefined = nm_symbols(args.kernel, args.nm)
    print(f'kernel {args.kernel}')
    print(f'  sha256    {sha256_of(args.kernel)}')
    print(f'  symbols   {len(defined)} defined, {len(undefined)} undefined')
    print(f'  segments  {", ".join(with_syms)}')
    failures = []
    for prefix in args.require_prefix:
        hits = sorted(s for s in defined if prefix in s)
        print(f'  {"PASS" if hits else "FAIL"} prefix {prefix!r}: {len(hits)} defined')
        for name in hits[:10]:
            print(f'    {name}')
        if not hits:
            failures.append(prefix)
    for symbol in args.require_symbol:
        present = symbol in defined
        print(f'  {"PASS" if present else "FAIL"} symbol {symbol}')
        if not present:
            failures.append(symbol)
    return failures


def load_providers(path):
    table = {}
    if not path:
        return table
    for line in read(path).decode('utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        fields = line.split('\t')
        if len(fields) >= 2:
            table[fields[0]] = fields[1]
    return table


def cmd_object(args):
    data, head, segs = describe(args.kernel)
    defined, _ = nm_symbols(args.kernel, args.nm)
    _, needed = nm_symbols(args.object, args.nm)
    providers = load_providers(args.providers)
    missing = sorted(needed - defined)
    print(f'kernel  {args.kernel} ({len(defined)} defined symbols)')
    print(f'object  {args.object} ({len(needed)} undefined symbols)')
    print(f'  sha256 {sha256_of(args.object)}')
    print(f'  resolvable {len(needed) - len(missing)}, missing {len(missing)}')
    for name in missing:
        provider = providers.get(name, 'unknown provider')
        print(f'  FAIL {name}  <- {provider}')
    return missing


def prelink_roots(path):
    """The [kernel.prelink] roots a toml declares, or None when it has no such table."""
    import tomllib
    try:
        data = tomllib.loads(read(path).decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as error:
        raise Refusal(f'{path}: not readable toml ({error})')
    prelink = data.get('kernel', {}).get('prelink')
    if not isinstance(prelink, dict):
        return None
    return prelink.get('roots', [])


def cmd_roots(args):
    kept, excluded = [], []
    print('roots')
    for path in args.toml:
        roots = prelink_roots(path)
        if roots is None:
            print(f'  {path}: no [kernel.prelink] table (profile defaults apply)')
            continue
        print(f'  {path}: {len(roots)} roots')
        for entry in roots:
            name = str(entry).lstrip('!')
            if str(entry).startswith('!'):
                excluded.append(name)
            elif name not in kept:
                kept.append(name)
    if excluded:
        print(f'  exclusions {", ".join(excluded)}')
    usb = sorted({k for k in kept if 'USB' in k or 'SCSI' in k})
    print(f'  effective roots {len(kept) - len(excluded)}, usb/scsi roots {len(usb)}')
    for identifier in usb:
        print(f'    {identifier}')
    failures = []
    for wanted in args.require_kext:
        present = wanted in kept and wanted not in excluded
        print(f'  {"PASS" if present else "FAIL"} kext {wanted}')
        if not present:
            failures.append(wanted)
    return failures


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)

    kexts = sub.add_parser('kexts', help='prelinked kext inventory')
    kexts.add_argument('kernel')
    kexts.add_argument('--require-kext', action='append', default=[])
    kexts.set_defaults(run=cmd_kexts)

    surface = sub.add_parser('surface', help='symbol surface of the collection')
    surface.add_argument('kernel')
    surface.add_argument('--nm', default='llvm-nm-18')
    surface.add_argument('--require-prefix', action='append', default=[])
    surface.add_argument('--require-symbol', action='append', default=[])
    surface.set_defaults(run=cmd_surface)

    obj = sub.add_parser('object', help="an object file's undefined symbols against the collection")
    obj.add_argument('kernel')
    obj.add_argument('object')
    obj.add_argument('--nm', default='llvm-nm-18')
    obj.add_argument('--providers')
    obj.set_defaults(run=cmd_object)

    roots = sub.add_parser('roots', help='USB kext roots a profile/board declares for the prelink')
    roots.add_argument('toml', nargs='+', help='profile.toml first, then any board.toml')
    roots.add_argument('--require-kext', action='append', default=[])
    roots.set_defaults(run=cmd_roots)

    args = parser.parse_args(argv)
    try:
        failures = args.run(args)
    except Refusal as error:
        print(f'ERROR {error}', file=sys.stderr)
        return 2
    print('RESULT ' + ('PASS' if not failures else f'FAIL ({len(failures)})'))
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
