#!/usr/bin/env python3
"""Offline USB criterion for an iOS kernel collection. No build, no device.

Three questions this answers, each with a reproducible command:

  kexts   which kexts the prelink actually carries (__PRELINK_INFO inventory)
  surface which symbols the collection defines (llvm-nm), per required prefix
  object  which of an object file's undefined symbols the collection cannot answer
  roots   which USB kexts a profile/board asks the prelink to carry
  adt     whether the USB controller is declared in the ADT at all: the device
          tree nodes in a hardware.dtb against the board's [adt.arm-io.*] blocks

Every check prints PASS/FAIL. Exit status is 0 only when every requested check
passed, 1 when one failed, 2 on a usage or parse error.

Usage:
  kc-surface.py kexts  KERNEL [--require-kext ID]...
  kc-surface.py surface KERNEL [--require-prefix P]... [--require-symbol S]...
  kc-surface.py object KERNEL OBJECT [--providers TSV]
  kc-surface.py roots  PROFILE_TOML [BOARD_TOML] [--require-kext ID]...
  kc-surface.py adt    HARDWARE_DTB BOARD_TOML [--expect-base 0xa600000]

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


FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_NOP, FDT_END = 1, 2, 3, 4, 9
USB_WORDS = ('usb', 'dwc3', 'eusb2', 'ssphy')


def fdt_nodes(data):
    """[(path, {prop: bytes})] from a flattened device tree, file order."""
    if len(data) < 40:
        raise Refusal('shorter than an fdt header')
    magic, _total, off_struct, off_strings, _off_rsv, _ver, _last, _cpu, size_strings, _size_struct = \
        struct.unpack_from('>10I', data, 0)
    if magic != FDT_MAGIC:
        raise Refusal(f'not a flattened device tree (magic {magic:#x})')
    strings = data[off_strings:off_strings + size_strings]
    nodes, stack, at = [], [], off_struct
    current = None
    while True:
        if at + 4 > len(data):
            raise Refusal('structure block runs past the end of the file')
        token = struct.unpack_from('>I', data, at)[0]
        at += 4
        if token == FDT_BEGIN_NODE:
            end = data.index(b'\0', at)
            name = data[at:end].decode('utf-8', 'replace')
            at += (end - at + 1 + 3) & ~3
            path = '/' + '/'.join([part for part in stack if part] + ([name] if name else []))
            stack.append(name)
            nodes.append({'path': path, 'props': {}})
            current = nodes[-1]
        elif token == FDT_END_NODE:
            if len(stack) > 1:
                stack.pop()
        elif token == FDT_PROP:
            length, nameoff = struct.unpack_from('>II', data, at)
            at += 8
            name = strings[nameoff:strings.index(b'\0', nameoff)].decode('utf-8', 'replace')
            value = data[at:at + length]
            at += (length + 3) & ~3
            if current is not None:
                current['props'][name] = value
        elif token == FDT_NOP:
            continue
        elif token == FDT_END:
            break
        else:
            raise Refusal(f'unknown fdt token {token:#x} at {at - 4:#x}')
    return nodes


def fdt_reg_bases(props):
    """Base addresses from a reg property, assuming 2+2 or 1+1 cells."""
    raw = props.get('reg')
    if not raw:
        return []
    bases = []
    if len(raw) % 16 == 0:
        for offset in range(0, len(raw), 16):
            high, low = struct.unpack_from('>II', raw, offset)
            bases.append((high << 32) | low)
    elif len(raw) % 8 == 0:
        for offset in range(0, len(raw), 8):
            bases.append(struct.unpack_from('>I', raw, offset)[0])
    return bases


def fdt_strings(props, key):
    raw = props.get(key)
    if not raw:
        return []
    return [part.decode('utf-8', 'replace') for part in raw.split(b'\0') if part]


def adt_arm_io(path):
    """{node name: {prop: value}} from a board.toml [adt.arm-io.*] table."""
    import tomllib
    try:
        data = tomllib.loads(read(path).decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as error:
        raise Refusal(f'{path}: not readable toml ({error})')
    arm = data.get('adt', {}).get('arm-io')
    if arm is None:
        return {}
    out = {}
    for name, kinds in arm.items():
        props = {}
        if isinstance(kinds, dict):
            for kind, values in kinds.items():
                if isinstance(values, dict):
                    props.update(values)
        out[name] = props
    return out


def hex_values(props):
    """Every number in an arm-io node, from "0x…" strings and ints."""
    found = []
    for name, value in props.items():
        candidates = value if isinstance(value, list) else [value]
        for item in candidates:
            if isinstance(item, int) and not isinstance(item, bool):
                found.append(item)
            elif isinstance(item, str) and item.lower().startswith('0x'):
                try:
                    found.append(int(item, 16))
                except ValueError:
                    continue
    return found


def is_usb_name(text):
    low = text.lower()
    return any(word in low for word in USB_WORDS)


def cmd_adt(args):
    """Is the USB controller declared in the ADT the kernel actually receives?

    The ADT is not the hardware device tree: UniXNU/scripts/unixnu/devicetree.py
    generate() builds a new /device-tree and exports a hardware node into
    /device-tree/arm-io only when the node carries unixnu,adt-name
    (devicetree.py:388-397). Board [adt.arm-io.*] tables become arm-io children
    too, and a name that appears in both is a hard error there
    ("Configured arm-io child duplicates an exported hardware node").
    So a usb node in hardware.dtb counts only with unixnu,adt-name, and a board
    block counts by itself.
    """
    data = read(args.dtb)
    nodes = fdt_nodes(data)
    board = adt_arm_io(args.board)

    usb_nodes, exported, configured = [], [], []
    for node in nodes:
        compat = ' '.join(fdt_strings(node['props'], 'compatible'))
        if not (is_usb_name(node['path']) or is_usb_name(compat)):
            continue
        bases = fdt_reg_bases(node['props'])
        names = fdt_strings(node['props'], 'unixnu,adt-name')
        usb_nodes.append((node['path'], compat or '(no compatible)', bases, names))
        if names:
            exported.append((names[0], node['path'], bases))
    configured = [(name, hex_values(props)) for name, props in board.items() if is_usb_name(name)]

    print(f'dtb   {args.dtb} ({len(data)} bytes, {len(nodes)} nodes)')
    print(f'  usb nodes {len(usb_nodes)}')
    for path, compat, bases, names in usb_nodes:
        shown = ', '.join(f'{base:#x}' for base in bases) or '(no reg)'
        exported_as = f'  unixnu,adt-name {names[0]}' if names else '  NOT exported (no unixnu,adt-name)'
        print(f'    {path}  compatible {compat}  reg {shown}{exported_as}')
    print(f'board {args.board}')
    print(f'  adt.arm-io nodes {len(board)}: {", ".join(sorted(board)) or "(none)"}')
    print(f'  usb arm-io nodes {len(configured)}')
    for name, values in configured:
        shown = ', '.join(f'{value:#x}' for value in sorted(set(values))) or '(no numeric property)'
        print(f'    [adt.arm-io.{name}] numbers {shown}')

    failures = []
    if not usb_nodes:
        # Not a failure by itself: a board [adt.arm-io] block declares the child
        # without any device tree node (devicetree.py:393-396).
        print('  info  the hardware device tree has no usb node; only a board '
              '[adt.arm-io] block can declare one')
    if not exported and not configured:
        failures.append('no usb node carries unixnu,adt-name and no [adt.arm-io] block '
                        'declares one, so the ADT has no usb child')
    for name, path, bases in exported:
        if not bases:
            failures.append(f'{path} exports {name} without a reg window')
        print(f'  node  {path} exports arm-io/{name} '
              f'({", ".join(f"{base:#x}" for base in bases) or "no reg"})')
    for name, _path, bases in exported:
        clash = [other for other, _values in configured if other == name]
        if clash:
            failures.append(f'{name} is declared twice (unixnu,adt-name and [adt.arm-io.{name}]); '
                            'devicetree.py generate() raises on that')
    declared = [base for _name, _path, bases in exported for base in bases]
    declared += [value for _name, values in configured for value in values]
    if args.expect_base is not None:
        present = args.expect_base in declared
        print(f'  node  expected base {args.expect_base:#x} '
              f'{"declared" if present else "absent"} in the ADT inputs')
        if not present:
            failures.append(f'expected base {args.expect_base:#x} is not declared by either input')
    for failure in failures:
        print(f'  REASON {failure}')
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

    adt = sub.add_parser('adt', help='is the USB controller declared in the ADT at all')
    adt.add_argument('dtb', help='hardware.dtb from the payload')
    adt.add_argument('board', help='board.toml carrying [adt.arm-io.*]')
    adt.add_argument('--expect-base', type=lambda text: int(text, 0), default=None,
                     help='require this reg base in a usb device tree node')
    adt.set_defaults(run=cmd_adt)

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
