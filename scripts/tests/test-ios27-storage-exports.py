#!/usr/bin/env python3
"""Tests for check-ios27-storage-exports.py.

The fixtures are synthetic Mach-O files: a fileset whose entry carries an
export trie, one whose entry only keeps a symbol table, and one with neither.
The point is to keep the reader honest about where a symbol can appear,
because the real kernelcache answers "nowhere" and that answer decides A or B.
"""

import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / 'scripts' / 'check-ios27-storage-exports.py'

CASES = []


def case(name, ok, detail=None):
    CASES.append((name, ok, detail))


def uleb(value):
    out = b''
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out += bytes([byte | 0x80])
        else:
            return out + bytes([byte])


def build_trie(items):
    """Serialize {name: address} as an export trie, nesting shared prefixes."""
    root = {}
    for name, address in items.items():
        node = root
        for char in name:
            node = node.setdefault(char, {})
        node[''] = address

    def layout(node):
        entries = []
        for key, child in sorted(node.items()):
            if key == '':
                continue
            entries.append((key, child))
        return entries

    nodes = []
    def assign(node):
        index = len(nodes)
        nodes.append([node, None])
        children = []
        for key, child in layout(node):
            children.append((key, assign(child)))
        nodes[index][1] = children
        return index
    assign(root)

    offsets = [0] * len(nodes)
    for _ in range(5):
        blobs = []
        for node, children in nodes:
            blob = b''
            if '' in node:
                body = bytes([0]) + uleb(node[''])
                blob += uleb(len(body)) + body
            else:
                blob += uleb(0)
            blob += bytes([len(children)])
            for key, child in children:
                blob += key.encode() + b'\0' + uleb(offsets[child])
            blobs.append(blob)
        cursor = 0
        fresh = []
        for blob in blobs:
            fresh.append(cursor)
            cursor += len(blob)
        if fresh == offsets:
            break
        offsets = fresh
    return b''.join(blobs)


def macho(symbols=None, defined=None, exports=None, filetype=2):
    """Build one plain Mach-O image with a __TEXT segment, optional symtab and trie."""
    trie = build_trie(exports) if exports else b''
    strtab = b'\0'
    names = {}
    for symbol in (defined or {}):
        names[symbol] = len(strtab)
        strtab += symbol.encode() + b'\0'
    has_symtab = bool(names)
    base = 32 + 72 + (24 if has_symtab else 0) + (16 if trie else 0)
    symoff = base
    stroff = symoff + 16 * len(names)
    trieoff = stroff + len(strtab)
    total = trieoff + len(trie)
    cmds = [struct.pack('<II16sQQQQiiII', 0x19, 72, b'__TEXT'.ljust(16, b'\0'),
                        0, total, 0, total, 7, 5, 1, 0)]
    if has_symtab:
        cmds.append(struct.pack('<IIIIII', 0x2, 24, symoff, len(names), stroff, len(strtab)))
    if trie:
        cmds.append(struct.pack('<IIII', 0x80000033, 16, trieoff, len(trie)))
    cmds_size = 32 + 72 + (24 if has_symtab else 0) + (16 if trie else 0)
    header = struct.pack('<IiiIIIII', 0xFEEDFACF, 0x0100000C, 2, filetype, len(cmds), cmds_size, 0, 0)
    body = header + b''.join(cmds)
    body = body.ljust(base, b'\0')
    for symbol, value in (defined or {}).items():
        body += struct.pack('<IBBHQ', names[symbol], 0x0F, 1, 0, value)
    body += strtab + trie
    return body


def fileset(inner, name):
    """Wrap an inner image as the only entry of a fileset, name after the command."""
    label = name.encode() + b'\0'
    inner_off = 32 + 32 + len(label)
    inner_off += (-inner_off) % 8
    cmd = struct.pack('<IIQQII', 0x80000035, 32, 0, inner_off, 32, 0)
    header = struct.pack('<IiiIIIII', 0xFEEDFACF, 0x0100000C, 2, 12, 1, 32, 0, 0)
    body = header + cmd + label
    body = body.ljust(inner_off, b'\0')
    return body + inner


def run(args, tmp):
    return subprocess.run([sys.executable, str(TOOL)] + args, capture_output=True, text=True)


def main():
    tmp = Path(tempfile.mkdtemp())
    # 1. a fileset entry that exports the symbol
    inner = macho(exports={'__ZTV20IOBlockStorageDevice': 0x1234})
    path = tmp / 'exported.bin'
    path.write_bytes(fileset(inner, 'com.apple.iokit.IOStorageFamily'))
    done = run(['--kernelcache', str(path), '--symbol', '__ZTV20IOBlockStorageDevice'], tmp)
    case('an entry that exports the symbol answers exported', done.returncode == 0 and 'ios27-storage-exports: exported' in done.stdout, done.stdout)
    case('the export address is printed', '0x1234' in done.stdout)

    # 2. an entry that only keeps a symbol table
    inner = macho(defined={'__ZTV20IOBlockStorageDevice': 0x9999})
    path = tmp / 'symtab.bin'
    path.write_bytes(fileset(inner, 'com.apple.iokit.IOStorageFamily'))
    done = run(['--kernelcache', str(path), '--symbol', '__ZTV20IOBlockStorageDevice'], tmp)
    case('a symbol table without a trie answers symtab-only', 'ios27-storage-exports: symtab-only' in done.stdout, done.stdout)
    case('the symbol table value is printed', '0x9999' in done.stdout)

    # 3. an entry with neither
    inner = macho()
    path = tmp / 'absent.bin'
    path.write_bytes(fileset(inner, 'com.apple.iokit.IOStorageFamily'))
    done = run(['--kernelcache', str(path)], tmp)
    case('an empty entry answers not-exported', 'ios27-storage-exports: not-exported' in done.stdout, done.stdout)
    case('the answer names the fileset entry route', 'fileset entry (B)' in done.stdout)

    # 4. a plain executable with a symbol table
    path = tmp / 'plain.bin'
    path.write_bytes(macho(defined={'__ZTV20IOBlockStorageDevice': 0xaaaa}))
    done = run(['--kernelcache', str(path)], tmp)
    case('a plain image is read without a fileset', 'fileset entr' in done.stdout and '0 fileset entries' in done.stdout, done.stdout)

    # 5. the raw string is reported with its offset
    path = tmp / 'raw.bin'
    path.write_bytes(fileset(macho(), 'com.apple.iokit.IOStorageFamily') + b'__ZTV20IOBlockStorageDevice\0')
    done = run(['--kernelcache', str(path)], tmp)
    case('a bare string is reported, not counted as a symbol', 'as a plain string at' in done.stdout, done.stdout)

    # 6. --require-exported turns the finding into a failure
    path = tmp / 'absent2.bin'
    path.write_bytes(fileset(macho(), 'com.apple.iokit.IOStorageFamily'))
    done = run(['--kernelcache', str(path), '--require-exported'], tmp)
    case('--require-exported fails when nothing is exported', done.returncode == 1, str(done.returncode))
    path = tmp / 'exported2.bin'
    path.write_bytes(fileset(macho(exports={'__ZTV20IOBlockStorageDevice': 0x10}), 'com.apple.iokit.IOStorageFamily'))
    done = run(['--kernelcache', str(path), '--symbol', '__ZTV20IOBlockStorageDevice', '--require-exported'], tmp)
    case('--require-exported passes when it is exported', done.returncode == 0, done.stdout)

    # 7. a named entry that is not there
    path = tmp / 'wrongentry.bin'
    path.write_bytes(fileset(macho(exports={'__ZTV20IOBlockStorageDevice': 0x10}), 'com.apple.other'))
    done = run(['--kernelcache', str(path), '--entry', 'com.apple.iokit.IOStorageFamily'], tmp)
    case('a missing entry fails loudly', done.returncode == 1 and 'FAIL no fileset entry named' in done.stdout, done.stdout)

    # 8. a missing file
    done = run(['--kernelcache', str(tmp / 'nope.bin')], tmp)
    case('a missing kernelcache fails', done.returncode == 1 and 'FAIL no kernelcache at' in done.stdout, done.stdout)

    # 9. the report records the answer
    path = tmp / 'report.bin'
    path.write_bytes(fileset(macho(), 'com.apple.iokit.IOStorageFamily'))
    out = tmp / 'report.json'
    done = run(['--kernelcache', str(path), '--out', str(out)], tmp)
    try:
        report = json.loads(out.read_text())
    except (OSError, ValueError):
        report = {}
    case('the report carries the verdict', report.get('verdict') == 'not-exported', json.dumps(report)[:200])
    case('the report lists every missing symbol', len(report.get('missing', [])) == 11, len(report.get('missing', [])))
    case('the report never claims hardware', report.get('hardware_verified') is False)
    case('the report names the entry it read', report.get('entry') == 'com.apple.iokit.IOStorageFamily')

    # 10. a nested trie is walked to its leaves
    inner = macho(exports={'__ZTV20IOBlockStorageDevice': 0x55, '__ZTV20IOBlockStorageDeviceToo': 0x66})
    path = tmp / 'nested.bin'
    path.write_bytes(fileset(inner, 'com.apple.iokit.IOStorageFamily'))
    done = run(['--kernelcache', str(path), '--symbol', '__ZTV20IOBlockStorageDeviceToo'], tmp)
    case('a nested trie entry is found', '0x66' in done.stdout and 'exported' in done.stdout, done.stdout)

    failed = [name for name, ok, _ in CASES if not ok]
    for name, ok, detail in CASES:
        if not ok:
            print(f'FAIL {name}')
            if detail:
                print(f'     {detail[:400]}')
    if failed:
        print(f'TESTS FAILED {len(failed)} of {len(CASES)} case(s)')
        return 1
    print(f'TESTS OK {len(CASES)} case(s)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
