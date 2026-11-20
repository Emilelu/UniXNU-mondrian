#!/usr/bin/env python3
"""Decode chained-fixup slots in Apple's kernelcache and name what they point at.

The pinned 24A446 kernelcache is stripped (LC_SYMTAB nsyms 0), so a missing
prelink target cannot be named by symbol lookup. But the *data* is intact: each
slot holds a chained-fixup entry whose rebase target is the object the kext meant,
and that object is an OSMetaClass-ish header with a class-name pointer.

Usage (chained-fixup decoder for the pinned kernelcache):
  python3 decode_chain.py <kernelcache> <address> [<address> ...]
"""

import struct
import sys

MH_MAGIC_64 = 0xFEEDFACF
SEGMENT_CMD = 0x19
FILESET_ENTRY_CMD = 0x80000035
CHAINED_FIXUPS_CMD = 0x80000034

FORMAT_ARM64E = 1
FORMAT_ARM64E_KERNEL = 7


def header(data, at=0):
    magic, cpu, sub, filetype, ncmds, sizeofcmds, flags = struct.unpack_from('<IiiIIII', data, at)
    if magic != MH_MAGIC_64:
        raise SystemExit(f'not a 64-bit Mach-O at {at:#x}')
    return {'at': at, 'filetype': filetype, 'ncmds': ncmds,
            'sizeofcmds': sizeofcmds, 'flags': flags}


def commands(data, head):
    position, end = head['at'] + 32, head['at'] + 32 + head['sizeofcmds']
    while position < end:
        command, size = struct.unpack_from('<II', data, position)
        yield position, command, size
        if size < 8:
            return
        position += size


def segments(data, head):
    ranges = []
    for position, command, size in commands(data, head):
        if command == SEGMENT_CMD and size >= 72:
            name = data[position + 8:position + 24].split(b'\0')[0].decode()
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<QQQQ', data, position + 24)
            if vmsize:
                ranges.append({'name': name, 'vmaddr': vmaddr, 'vmsize': vmsize,
                               'fileoff': fileoff, 'filesize': filesize})
    return ranges


def chained_fixups(data, head):
    for position, command, size in commands(data, head):
        if command == CHAINED_FIXUPS_CMD:
            # linkedit_data_command: cmd, cmdsize, dataoff, datasize -- the header
            # starts at dataoff, not at the load command.
            dataoff, _datasize = struct.unpack_from('<II', data, position + 8)
            return dataoff, struct.unpack_from('<IIIIIII', data, dataoff)
    return None, None


def segment_of(ranges, address):
    for item in ranges:
        if item['vmaddr'] <= address < item['vmaddr'] + item['vmsize']:
            return item
    return None


def decode(data, head, address, verbose=True):
    """Decode the fixup entry stored at `address`.

    Each slot carries its own entry, so there is no chain to walk: the entry at
    the slot is the answer. page_start only matters for chains that spill past a
    page, which these slots do not.
    """
    payload, info = chained_fixups(data, head)
    if payload is None:
        raise SystemExit('this image has no LC_DYLD_CHAINED_FIXUPS')
    all_segments = segments(data, head)
    seg = index = None
    for position_index, item in enumerate(all_segments):
        if item['vmaddr'] <= address < item['vmaddr'] + item['vmsize']:
            seg, index = item, position_index
            break
    if seg is None:
        raise SystemExit(f'{address:#x} is in no segment')
    _version, starts_offset, _imports_offset, _symbols_offset, _count, pointer_format, _symfmt = info
    starts = payload + starts_offset
    seg_count = struct.unpack_from('<I', data, starts)[0]
    seg_offsets = struct.unpack_from(f'<{seg_count}I', data, starts + 4)
    if index >= seg_count or not seg_offsets[index]:
        raise SystemExit('that segment has no fixup info')
    slot = seg['fileoff'] + (address - seg['vmaddr'])
    value = struct.unpack_from('<Q', data, slot)[0]
    auth, is_bind = (value >> 63) & 1, (value >> 62) & 1
    following = (value >> 51) & 0x7FF
    if auth:
        offset = value & 0xFFFFFFFF
        key = (value >> 49) & 0x3
        diversity = (value >> 32) & 0xFFFF
        return slot, value, ('auth-rebase', offset, key, diversity, following,
                             pointer_format)
    if is_bind:
        return slot, value, ('bind', value & 0xFFFFFF, following, pointer_format)
    return slot, value, ('rebase', value & ((1 << 43) - 1), (value >> 43) & 0xFF,
                         following, pointer_format)


def string_at(data, ranges, address, limit=128):
    seg = segment_of(ranges, address)
    if seg is None:
        return None
    offset = seg['fileoff'] + (address - seg['vmaddr'])
    end = data.find(b'\0', offset, offset + limit)
    if end < 0:
        return None
    raw = data[offset:end]
    if len(raw) < 3 or not all(32 <= byte < 127 for byte in raw):
        return None
    return raw.decode()


def main(argv):
    if len(argv) < 3:
        raise SystemExit(__doc__)
    data = open(argv[1], 'rb').read()
    root = header(data)
    children = []
    for position, command, size in commands(data, root):
        if command == FILESET_ENTRY_CMD:
            _vmaddr, fileoff, entry_id = struct.unpack_from('<QQI', data, position + 8)
            start = position + entry_id
            end = data.index(0, start)
            children.append((data[start:end].decode(), fileoff))
    root_segments = segments(data, root)
    print('root fixups:', chained_fixups(data, root)[1])
    kernel = [item for item in children if item[0] == 'com.apple.kernel']
    print('children:', len(children), 'com.apple.kernel at',
          f'{kernel[0][1]:#x}' if kernel else 'absent')
    for text in argv[2:]:
        address = int(text, 0)
        position, value, decoded = decode(data, root, address)
        print(f'\n{address:#x}  slot file {position:#x}  entry {value:#018x}  {decoded}')
        if decoded[0] in ('rebase', 'auth-rebase'):
            target, high8 = decoded[1], decoded[2]
            ranges = segments(data, root)
            base = root_segments[0]['vmaddr']
            candidates = []
            if decoded[0] == 'auth-rebase':
                candidates.append((base + target, 'base+offset'))
            else:
                candidates.extend([(target, 'offset'), (base + target, 'base+offset'),
                                   (target | (high8 << 56), 'offset|high8')])
            for candidate, label in candidates:
                seg = segment_of(ranges, candidate)
                if seg:
                    print(f'   target {candidate:#x} ({label}) in {seg["name"]}')
                    name = string_at(data, ranges, candidate)
                    if name:
                        print(f'   target string: "{name}"')
                    for delta in (8, 16, 24, 32, 40, 48):
                        pointer = struct.unpack_from(
                            '<Q', data, seg['fileoff'] + (candidate - seg['vmaddr']) + delta)[0]
                        hit = string_at(data, ranges, pointer)
                        if hit:
                            print(f'   [target+{delta:#x}] -> "{hit}"')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
