#!/usr/bin/env python3
"""Make AppleARMPlatform's AppleARMCPU::_validateConfiguration() return true.

The K60 kernel prelinks Apple's kernelcache, so AppleARMPlatform's AppleARMCPU
class ships inside it and _validateConfiguration() only accepts an Apple Silicon
device tree: it panics with "CPU configuration in device tree is invalid"
(@AppleARMCPU.cpp:111) before our ArmCpu can take the /cpus nubs. Patching the
function to return true makes it accept this board; the replacement return is
selected from the function's PAC prologue, since 16.6.1 and 24A446 use different
return-authentication conventions.

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
* The return instruction depends on the *function's own* ABI, and the two kernels
  disagree. On 27 the kext entry is `bti c ; pacibsp ; sub sp, sp, #0x120`, the
  prologue sits 8 bytes into the function, and the function's own epilogue ends in
  `add sp, sp, #0x120 ; retab`; `pacibsp` signed LR against SP at entry, so only
  `retab` authenticates it against the same modifier. The replacement there is
  `mov w0, #1 ; retab`. Skipping `sub sp` and never reaching `add sp` leaves SP at
  the entry value, so the `retab` modifier equals the `pacibsp` modifier and the
  return contract is the one the compiler emitted (P-278). A plain `ret` would
  jump through a signed LR without authenticating it and fail under key B.
  On 16.6.1 the function has no `pacibsp` and nothing is signed: its epilogue is a
  plain `ret` and the whole image contains zero `retab` instructions, so writing
  `retab` there would authenticate an unsigned LR against an uninitialised key and
  is just as wrong in the other direction. The site therefore decides: the eight
  bytes immediately before the prologue are `bti c ; pacibsp` in a PAC function
  and the previous function's plain `ret` otherwise. Measured on both kernels:
  16 preceding 8 = `f44fc2a8 c0035fd6`, 27 preceding 8 = `5f2403d5 7f2303d5`.
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
PATCH_RET = bytes.fromhex('20008052c0035fd6')    # mov w0, #1 ; ret
PATCH_RETAB = bytes.fromhex('20008052ff0f5fd6')  # mov w0, #1 ; retab
PACIBSP = bytes.fromhex('7f2303d5')          # pacibsp
BTI_C_PACIBSP = bytes.fromhex('5f2403d57f2303d5') # bti c ; pacibsp
# Select the return from the function's own entry sequence, not just the image
# subtype. The measured 16.6.1 function has no PAC prologue and uses plain ret;
# 24A446 has bti c; pacibsp and returns with retab. Skipping the stack frame
# keeps SP at entry in both cases. On the PAC form, retab therefore authenticates
# LR with the same SP modifier pacibsp used (P-278).
# The eight bytes that follow the prologue on both kernels. The replacement
# alone is too common to anchor on, so already-patched sites must also have this
# tail. This permits a second payload pass without accepting arbitrary patches.
TAIL = bytes.fromhex('fa670da9f85f0ea9')     # stp x26, x25, [sp, #208] ; stp x24, x23, [sp, #224]
ARM64_SUBTYPES = (0x0, 0x1, 0x2, 0x80000002, 0xc0000002)
ARM64_PAC_SUBTYPES = (0x80000002, 0xc0000002)


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
    return {'kind': kind, 'subtype': subtype, 'segments': segments}


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


def replacement_for(code, site, subtype):
    """Return the instruction sequence this function's own entry ABI requires.

    A `bti c ; pacibsp` entry means LR was signed, so the return has to
    authenticate it: `retab`. Anything else on a plain ARM64 image is an
    unsigned frame and a plain `ret` is correct. When the image says arm64e but
    the function has no PAC prologue, neither answer is proven: fail closed
    rather than write eight bytes into a signed function on a guess.
    """
    if site >= len(BTI_C_PACIBSP) and code[site - len(BTI_C_PACIBSP):site] == BTI_C_PACIBSP:
        return PATCH_RETAB
    if subtype in ARM64_PAC_SUBTYPES:
        raise SystemExit(
            f'cannot prove the return contract for {KEXT}: the image is arm64e (subtype {subtype:#x}) '
            f'but the code before the patch site is {code[max(0, site - 8):site].hex()}, not '
            f'bti c ; pacibsp ({BTI_C_PACIBSP.hex()}). Refusing to guess between ret and retab.')
    return PATCH_RET


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
    tried, seen = [], []
    for start in (text['fileoff'], header + text['fileoff']):
        if start in tried or start + text['filesize'] > len(data):
            continue
        tried.append(start)
        code = bytes(data[start:start + text['filesize']])
        # The payload step runs more than once per build when a later archive is
        # rebuilt, so an already-patched kernel must be recognised rather than
        # reported as "the prologue is missing". Both forms are anchored on the
        # shared tail. The stop is len(code) - 15, not - 16: a 16-byte window
        # starting at len(code) - 16 still fits, and the earlier bound skipped
        # exactly that last aligned site.
        sites = range(0, len(code) - 15, 4)
        original = [i for i in sites if code[i:i + 8] == EXPECT and code[i + 8:i + 16] == TAIL]
        patched = [i for i in sites if code[i:i + 8] in (PATCH_RET, PATCH_RETAB)
                   and code[i + 8:i + 16] == TAIL]
        # Only the *real* origin holds one site. The other candidate is a wrong
        # guess at where this kext's text begins, so it is normal for it to slice
        # some other part of the image and find a prologue there: 16.6.1 has a
        # second `sub sp, #0x120 ; stp x28, x27` frame at 0x4a09000 that is not
        # this function. Requiring global uniqueness would refuse a healthy
        # kernel, so the first origin that yields exactly one site wins and the
        # others are only reported when no origin does.
        if len(original) == 1 and not patched:
            site = original[0]
            replacement = replacement_for(code, site, kext['subtype'])
            return start + site, load, site, start, replacement
        if len(patched) == 1 and not original:
            site = patched[0]
            actual = code[site:site + 8]
            expected = replacement_for(code, site, kext['subtype'])
            if actual != expected:
                abi = 'pacibsp/retab' if expected == PATCH_RETAB else 'plain ret'
                raise SystemExit(f'{KEXT} site at {start + site:#x} is patched for the wrong return ABI: '
                                 f'found {actual.hex()}, expected {expected.hex()} ({abi}); rebuild the payload kernel')
            return start + site, load, site, start, expected
        if original or patched:
            seen.append(f'{start:#x}(original={len(original)}, patched={len(patched)})')
    raise SystemExit(
        f'{KEXT} __TEXT_EXEC holds no unique site: original {EXPECT.hex()} + tail {TAIL.hex()} '
        f'or a patched form + tail {TAIL.hex()}. '
        f'Windows tried: {[hex(s) for s in tried] or "none in range"}; '
        f'non-unique windows: {", ".join(seen) or "no window held it at all"}.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true')
    group.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    data = bytearray(args.kernel.read_bytes())
    offset, load, rva, at, replacement = locate(data)
    found = bytes(data[offset:offset + 8])
    abi_name = 'retab (pacibsp)' if replacement == PATCH_RETAB else 'ret (plain arm64)'
    print(f'kext load {load:#x}  __TEXT_EXEC file {at:#x}  rva {rva:#x}  '
          f'file offset {offset:#x}  bytes {found.hex()}  return ABI {abi_name}')
    if found in (PATCH_RET, PATCH_RETAB):
        # locate() already refused a patched form that does not match the
        # function's own entry sequence, so reaching here means the bytes are
        # the ones this build would write; patching again would be a no-op.
        print('already patched')
        return 0
    if found != EXPECT:
        raise SystemExit(f'unexpected bytes at the patch site: {found.hex()}')
    if args.apply:
        data[offset:offset + 8] = replacement
        args.kernel.write_bytes(data)
        instruction = 'retab' if replacement == PATCH_RETAB else 'ret'
        print(f'patched: mov w0, #1 ; {instruction}')
    else:
        print('original bytes match; --apply would write ' + replacement.hex())
    return 0


if __name__ == '__main__':
    sys.exit(main())
