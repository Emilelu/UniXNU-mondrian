#!/usr/bin/env python3
"""Make AppleARMPlatform's AppleARMCPU::_validateConfiguration() return true.

The K60 kernel prelinks Apple's kernelcache, so AppleARMPlatform's AppleARMCPU
class ships inside it and _validateConfiguration() only accepts an Apple Silicon
device tree: it panics with "CPU configuration in device tree is invalid"
(@AppleARMCPU.cpp:111) before our ArmCpu can take the /cpus nubs. Patching the
function to `mov w0, #1 ; ret` makes it accept this board.

Why this is not a fixed offset any more
--------------------------------------
The 16 line located the function at a hardcoded __TEXT_EXEC offset 0x2460. The
24A446 kernel ships a different build of the same kext and that offset holds
unrelated code, so the site is found by its prologue instead:

    sub sp, sp, #0x120 ; stp x28, x27, [sp, #192]
    ff 83 04 d1  fc 6f 0c a9

Three layout facts differ between the two kernels and each one silently breaks a
naive port:

* __TEXT_EXEC fileoff. In the 16.6.1 MH_EXECUTE kernel a kext's segment offsets
  are relative to the kext header (fileoff 0x76d2c0, header 0x42d7d40). In the
  27 MH_FILESET kernel they are container-absolute (fileoff 0x15efdb0, header
  0x16b1b0). Both candidates are therefore tried and only the one that really
  holds the prologue is accepted.
* arm64e. The 27 kext entry is `bti c ; pacibsp ; sub sp, sp, #0x120`, so the
  prologue sits 8 bytes into the function. Rewriting those 8 bytes with
  `mov w0, #1 ; ret` leaves the two prefix instructions in place, which is
  harmless: nothing reads sp and nothing returns through the signed frame.
* __PRELINK_INFO. 16.6.1 uses a bare <dict> root, 27 wraps it in <plist>. The
  kit's native_prelink.unserialize_xml() only knows the first form ('Unsupported
  prelink XML element plist') and plistlib only knows the second
  (InvalidFileException), so this reads with ElementTree and accepts either root.

The prologue appears once inside the kext text on both kernels, but 180 times in
the whole 27 kernel, which is why the search is scoped to the kext's own
__TEXT_EXEC bytes and insists on exactly one hit. On the 27 kernel the hit is
verified to be the real validator by control flow, not just by shape: the
enclosing function (RVA 0x2df4, size 0x8cc) is the only one in the kext that
branches to the stub at __TEXT_EXEC+0x53600 which prints that panic string.
"""
import argparse
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

KITS = ('XnuPrelink', 'NativePrelink')


def _kit():
    root = Path(__file__).resolve().parents[1] / 'kits'
    tried = []
    for name in KITS:
        candidate = root / name
        tried.append(str(candidate))
        if (candidate / 'native_prelink.py').is_file():
            return candidate
    raise SystemExit('native_prelink.py is not in any known kit; tried: ' + ', '.join(tried))


sys.path.insert(0, str(_kit()))
import native_prelink as np

KEXT = 'com.apple.driver.AppleARMPlatform'
EXPECT = bytes.fromhex('ff8304d1fc6f0ca9')   # sub sp, sp, #0x120 ; stp x28, x27, [sp, #192]
PATCH = bytes.fromhex('20008052c0035fd6')    # mov w0, #1 ; ret
# The eight bytes that follow the prologue on both kernels. `mov w0, #1 ; ret`
# alone is far too common to anchor on (it is everywhere in kernel code), so the
# patched site is recognised by the patch followed by this same tail. Without it
# a second payload step on an already-patched kernel cannot tell "already done"
# from "the prologue is gone", and the build fails on its own output.
TAIL = bytes.fromhex('fa670da9f85f0ea9')     # stp x26, x25, [sp, #208] ; stp x24, x23, [sp, #224]
ARM64_SUBTYPES = (0x0, 0x1, 0x2, 0x80000002, 0xc0000002)


def macho(data, at=0):
    if at < 0 or at + 32 > len(data):
        raise ValueError('Mach-O header outside image')
    magic, cpu, subtype, kind, count, size = struct.unpack_from('<6I', data, at)
    if magic != 0xfeedfacf or cpu != 0x100000c or subtype not in ARM64_SUBTYPES:
        raise ValueError(f'not a 64-bit ARM Mach-O: {magic:#x}/{cpu:#x}/{subtype:#x}')
    end = at + 32 + size
    if end > len(data):
        raise ValueError('load commands outside image')
    offset = at + 32
    segments = []
    for _ in range(count):
        command, length = struct.unpack_from('<II', data, offset)
        if length < 8 or length % 8 or offset + length > end:
            raise ValueError('invalid load command extent')
        if command == 0x19:
            name, va, vsize, fileoff, filesize = struct.unpack_from('<16s4Q', data, offset + 8)
            if filesize > vsize:
                raise ValueError('segment filesize exceeds its size')
            segments.append({'name': name.rstrip(b'\0').decode(), 'va': va, 'size': vsize,
                             'fileoff': fileoff, 'filesize': filesize})
        offset += length
    if offset != end:
        raise ValueError('load command size mismatch')
    return {'kind': kind, 'segments': segments}


def _scalar(node):
    return node.text or '' if node.tag in ('integer', 'string') else None


def _dict(node):
    out = {}
    children = list(node)
    for i in range(0, len(children) - 1, 2):
        key, value = children[i], children[i + 1]
        if value.tag == 'dict':
            out[key.text] = _dict(value)
        elif value.tag == 'array':
            out[key.text] = [_dict(v) if v.tag == 'dict' else _scalar(v) for v in value]
        else:
            out[key.text] = _scalar(value)
    return out


def prelink_entries(data, parent):
    info = next((s for s in parent['segments'] if s['name'] == '__PRELINK_INFO'), None)
    if info is None or not info['filesize']:
        raise SystemExit('this kernel has no __PRELINK_INFO payload')
    at = np.backed_offset(parent['segments'], info['va'], info['filesize'], len(data))
    blob = bytes(data[at:at + info['filesize']]).split(b'\0', 1)[0]
    root = ET.fromstring(blob)
    if root.tag == 'plist':
        root = root[0]
    return {e['CFBundleIdentifier']: e for e in _dict(root)['_PrelinkInfoDictionary']}


def locate(data):
    parent = macho(data)
    entries = prelink_entries(data, parent)
    entry = entries.get(KEXT)
    if entry is None:
        raise SystemExit(f'{KEXT} is not in this kernel: {len(entries)} kexts, none by that name')
    raw = entry['_PrelinkExecutableLoadAddr']
    # plist integers are signed: the load address arrives as -68600532560 on 27 and
    # as the hex string '0xfffffff004429d40' on 16.6.1.
    load = (int(raw, 0) if isinstance(raw, str) else int(raw)) & 0xFFFFFFFFFFFFFFFF
    header = np.backed_offset(parent['segments'], load, 32, len(data))
    kext = macho(data, header)
    text = next((s for s in kext['segments'] if s['name'] == '__TEXT_EXEC'), None)
    if text is None or not text['filesize']:
        raise SystemExit(f'{KEXT} has no __TEXT_EXEC segment')
    tried = []
    for start in (text['fileoff'], header + text['fileoff']):
        if start in tried or start + text['filesize'] > len(data):
            continue
        tried.append(start)
        code = bytes(data[start:start + text['filesize']])
        # The payload step runs more than once per build when a later archive is
        # rebuilt, so an already-patched kernel must be recognised rather than
        # reported as "the prologue is missing". Both forms are anchored on the
        # shared tail; only an unambiguous site is accepted.
        original = [i for i in range(0, len(code) - 16, 4) if code[i:i + 8] == EXPECT and code[i + 8:i + 16] == TAIL]
        patched = [i for i in range(0, len(code) - 16, 4) if code[i:i + 8] == PATCH and code[i + 8:i + 16] == TAIL]
        if len(original) == 1 and not patched:
            return start + original[0], load, original[0], start
        if len(patched) == 1 and not original:
            return start + patched[0], load, patched[0], start
    raise SystemExit(f'{EXPECT.hex()} is not unique in {KEXT} __TEXT_EXEC; '
                     f'file offsets tried: {[hex(s) for s in tried]}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true')
    group.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    data = bytearray(args.kernel.read_bytes())
    offset, load, rva, at = locate(data)
    found = bytes(data[offset:offset + 8])
    print(f'kext load {load:#x}  __TEXT_EXEC file {at:#x}  rva {rva:#x}  '
          f'file offset {offset:#x}  bytes {found.hex()}')
    if found == PATCH:
        print('already patched')
        return 0
    if found != EXPECT:
        raise SystemExit(f'unexpected bytes at the patch site: {found.hex()}')
    if args.apply:
        data[offset:offset + 8] = PATCH
        args.kernel.write_bytes(data)
        print('patched: mov w0, #1 ; ret')
    else:
        print('original bytes match; --apply would write ' + PATCH.hex())
    return 0


if __name__ == '__main__':
    sys.exit(main())
