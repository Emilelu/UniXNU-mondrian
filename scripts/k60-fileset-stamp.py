#!/usr/bin/env python3
"""Make the prelinked collection satisfy the loader's member rule.

`MH_FILESET` collections carry one header per child, and `DarwinBoot`'s member
rule compares three fields of the `com.apple.kernel` child against the outer
header: filetype must be `MH_EXECUTE`, cpusubtype must equal the collection's
bit for bit, and `MH_DYLIB_IN_CACHE` must be set. Apple's own 24A446 collection
satisfies all three (305/305 children equal the outer `0xc0000002`). Ours sets
the flag and leaves the child at `0x80000002`, because the local clang writes
`CPU_SUBTYPE_ARM64E_WITH_PTRAUTH_VERSION(0, false)` and ld64 adopts the object's
value (measured 2026-11-20: `llvm/lib/MC/MachObjectWriter.cpp` promotes
arm64e to versioned-but-user; Apple's ld with `-static -e _start` writes the
kernel form). So the last eight bits of the ABI label have to be corrected after
linking, and that is all this tool does -- it never touches code, sizes or the
other 31 children.

It refuses rather than guesses:

  * the file must be `MH_FILESET`, little-endian 64-bit arm64e;
  * exactly one entry may be named `com.apple.kernel`;
  * that child must be `MH_EXECUTE` with `MH_DYLIB_IN_CACHE` already set, because
    the stamp is only allowed to fix the label, not to invent the rest of the
    rule;
  * if the child already equals the collection the tool says so and exits 0, so
    a second build step cannot fail on its own output (P-278's lesson).

    python3 scripts/k60-fileset-stamp.py kernel.macho            # report
    python3 scripts/k60-fileset-stamp.py kernel.macho --apply    # rewrite 4 bytes
"""
import argparse
import mmap
import struct
import sys

MH_MAGIC_64 = 0xFEEDFACF
CPU_TYPE_ARM64 = 0x0100000C
MH_EXECUTE, MH_FILESET = 2, 12
MH_DYLIB_IN_CACHE = 0x80000000
LC_FILESET_ENTRY = 0x80000035
KERNEL_ENTRY = b'com.apple.kernel'


class Failure(Exception):
    pass


def header(data, at):
    """Parse one 64-bit Mach-O header, with the bounds checks the loader relies on."""
    if at + 32 > len(data):
        raise Failure('header at 0x%x runs past the end of the file' % at)
    magic, cpu, subtype, filetype, ncmds, sizeofcmds, flags = struct.unpack_from('<7I', data, at)
    if magic != MH_MAGIC_64:
        raise Failure('header at 0x%x is not a 64-bit little-endian Mach-O' % at)
    if cpu != CPU_TYPE_ARM64:
        raise Failure('header at 0x%x is not arm64' % at)
    if at + 32 + sizeofcmds > len(data):
        raise Failure('load commands at 0x%x run past the end of the file' % at)
    return {'at': at, 'subtype': subtype, 'filetype': filetype, 'ncmds': ncmds,
            'sizeofcmds': sizeofcmds, 'flags': flags}


def entries(data, outer):
    """(name, child header offset) for every LC_FILESET_ENTRY in the collection."""
    found = []
    at = outer['at'] + 32
    for _ in range(outer['ncmds']):
        cmd, size = struct.unpack_from('<II', data, at)
        if size < 8 or at + size > len(data):
            raise Failure('load command at 0x%x has an impossible size %d' % (at, size))
        if cmd == LC_FILESET_ENTRY:
            if size < 32:
                raise Failure('fileset entry at 0x%x is shorter than 32 bytes' % at)
            _vmaddr, fileoff, entry_id = struct.unpack_from('<QQI', data, at + 8)
            name_at = at + entry_id
            zero = data.find(b'\0', name_at, min(name_at + 256, len(data)))
            if zero < 0:
                raise Failure('entry name at 0x%x is not terminated' % name_at)
            found.append((bytes(data[name_at:zero]), fileoff))
        at += size
    return found


def child_offsets(data, outer):
    """The `com.apple.kernel` child, requiring it to appear exactly once."""
    matches = [fileoff for name, fileoff in entries(data, outer) if name == KERNEL_ENTRY]
    if not matches:
        raise Failure('no com.apple.kernel entry in the collection')
    if len(matches) > 1:
        raise Failure('com.apple.kernel appears %d times; the loader takes one' % len(matches))
    return matches[0]


def stamp(data, apply=False):
    """Return (offset, old, new, applied) after checking the loader's whole member rule."""
    outer = header(data, 0)
    if outer['filetype'] != MH_FILESET:
        raise Failure('filetype is %d, not MH_FILESET: nothing to stamp' % outer['filetype'])
    at = child_offsets(data, outer)
    inner = header(data, at)
    if inner['filetype'] != MH_EXECUTE:
        raise Failure('com.apple.kernel child is filetype %d, not MH_EXECUTE'
                      % inner['filetype'])
    if not inner['flags'] & MH_DYLIB_IN_CACHE:
        raise Failure('com.apple.kernel child lacks MH_DYLIB_IN_CACHE: the emitter, not '
                      'this tool, has to set that flag')
    if inner['subtype'] == outer['subtype']:
        return at + 8, inner['subtype'], outer['subtype'], False
    if apply:
        struct.pack_into('<I', data, at + 8, outer['subtype'])
    return at + 8, inner['subtype'], outer['subtype'], apply


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('kernel', help='prelinked MH_FILESET kernel')
    parser.add_argument('--apply', action='store_true', help='write the four bytes')
    args = parser.parse_args(argv)

    path = args.kernel
    with open(path, 'r+b' if args.apply else 'rb') as handle:
        with mmap.mmap(handle.fileno(), 0,
                       access=mmap.ACCESS_WRITE if args.apply else mmap.ACCESS_READ) as data:
            try:
                offset, old, new, applied = stamp(data, apply=args.apply)
            except Failure as error:
                print('FAIL: %s' % error)
                return 1
            finally:
                if args.apply:
                    data.flush()

    label = '%s -> %s' % (format(old, '#010x'), format(new, '#010x'))
    if old == new:
        print('ok fileset: com.apple.kernel already carries the collection cpusubtype %s'
              % format(new, '#010x'))
        return 0
    if applied:
        print('stamped: com.apple.kernel cpusubtype %s at file offset 0x%x' % (label, offset))
        return 0
    print('note fileset: com.apple.kernel cpusubtype %s at file offset 0x%x (use --apply)'
          % (label, offset))
    return 0


if __name__ == '__main__':
    sys.exit(main())
