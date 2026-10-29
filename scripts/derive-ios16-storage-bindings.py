#!/usr/bin/env python3
"""Derive the original 20G81 IOBlockStorageDevice imports for the pong/k60 block driver.

The public IOStorageFamily reference object only annotates the ABI; it is never
linked or executed. The bindings are the absolute VAs of the original kernelcache
kext, which the prelink slides together with the native kernel.
"""
import argparse
import hashlib
import json
import os
import platform
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

DEVICE = Path(__file__).resolve().parents[1]
REFERENCE_COMMIT = '609cbbdf9fa8fd5eae973d9135c7d44b47e6502e'
REFERENCE_URL = f'https://codeload.github.com/apple-oss-distributions/IOStorageFamily/tar.gz/{REFERENCE_COMMIT}'
KERNEL_PIN = 'd260defcc2eaac258fd3a2234454dda46791dae45e97608c5416f9ba8fd366e9'
DEFAULT_IPSW_URL = ('https://updates.cdn-apple.com/2023SummerFCS/fullrestores/042-44385/'
                    '366890C4-D9B5-4938-B399-C19FB58DBEE0/iPad_Pro_HFR_16.6.1_20G81_Restore.ipsw')
# The K60 native kernel links at this address (ARM64_LINK_ADDR of the baseline make).
ARM64_LINK_ADDR = 0xfffffff007004000
# The auto-slide wrapper packs components up to the end of these segments and then
# slides them clear of the lowest native segment in 4 KiB steps.
PRELINK_SEGMENTS = ('__PRELINK_TEXT', '__PLK_TEXT_EXEC', '__PLK_DATA_CONST', '__PRELINK_DATA')
SLIDE_STEP = 0x4000
SLOTS = 190
PURE_VIRTUAL = 14
CLASS_SIZE = 0x90


def prelink_placement(image):
    """Return (base, slide, fixed) matching what the auto-slide wrapper will emit.

    The wrapper packs the components up to the end of the outer prelink segments
    and then slides them clear of the lowest native segment in 4 KiB steps, so the
    bindings must be expressed in that final address space, not in the original
    kernelcache's.
    """
    base = min(s['va'] for s in image['segments'] if s['name'].startswith('__PRELINK') and s['size'])
    component_end = max(s['va'] + s['size'] for s in image['segments']
                        if s['name'] in PRELINK_SEGMENTS and s['size'])
    need = ARM64_LINK_ADDR - component_end
    slide = (min(0, need) // SLIDE_STEP) * SLIDE_STEP
    return base, slide, base + slide


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sh(cmd, **kw):
    return subprocess.check_output(cmd, text=True, **kw).strip()


class RangeFile:
    """Read-only seekable view of a remote file using HTTP range requests."""

    def __init__(self, url, block=1 << 20):
        self.url = url
        self.block = block
        self.cache = {}
        request = urllib.request.Request(url, headers={'Range': 'bytes=0-0'})
        with urllib.request.urlopen(request) as response:
            if response.status != 206:
                raise SystemExit(f'{url} does not support range requests')
            self.size = int(response.headers['Content-Range'].split('/')[-1])

    def read_at(self, offset, length):
        if offset >= self.size:
            return b''
        end = min(offset + length, self.size) - 1
        request = urllib.request.Request(self.url, headers={'Range': f'bytes={offset}-{end}'})
        with urllib.request.urlopen(request) as response:
            return response.read()


def fetch_member(ipsw_url, tree):
    """Return (member_name, bytes) for the KernelCache member of the IPSW."""
    stream = RangeFile(ipsw_url)
    os.makedirs(tree, exist_ok=True)

    # zipfile needs a seekable file object; back it with the range reader.
    class Reader:
        def __init__(self, inner):
            self.inner, self.pos = inner, 0
            self.inner_size = inner.size

        def seek(self, offset, whence=0):
            if whence == 0:
                self.pos = offset
            elif whence == 1:
                self.pos += offset
            else:
                self.pos = self.inner_size + offset
            return self.pos

        def tell(self):
            return self.pos

        def read(self, length=-1):
            if length is None or length < 0:
                length = self.inner_size - self.pos
            data = self.inner.read_at(self.pos, length)
            self.pos += len(data)
            return data

        def seekable(self):
            return True

        def readable(self):
            return True

    archive = zipfile.ZipFile(Reader(stream))
    manifest = archive.read('BuildManifest.plist')
    identity = plistlib.loads(manifest)['BuildIdentities'][0]
    name = identity['Manifest']['KernelCache']['Info']['Path']
    return name, archive.read(name)


def im4p_payload(blob):
    """Strip the IM4P container and return the packed payload."""
    at = 0

    def der(data, at):
        tag, length = data[at], data[at + 1]
        body = at + 2
        if length & 0x80:
            count = length & 0x7f
            length = int.from_bytes(data[body:body + count], 'big')
            body += count
        return tag, body, body + length

    tag, at, end = der(blob, 0)
    if tag != 0x30 or end != len(blob):
        raise SystemExit('expected one complete IM4P sequence')
    fields = []
    while at < end:
        kind, body, finish = der(blob, at)
        fields.append((kind, blob[body:finish]))
        at = finish
    if len(fields) < 4 or fields[0][1] != b'IM4P' or fields[1][1] != b'krnl' or fields[3][0] != 0x04:
        raise SystemExit(f'unexpected IM4P fields: {[(hex(k), v[:8]) for k, v in fields[:5]]}')
    return fields[3][1]


def decompress(packed, out):
    if platform.system() == 'Darwin':
        cmd = ['/usr/bin/compression_tool', '-decode', '-a', 'lzfse', '-i', str(packed), '-o', str(out)]
    else:
        cmd = ['lzfse', '-decode', '-i', str(packed), '-o', str(out)]
    subprocess.run(cmd, check=True, capture_output=True)
    return out.read_bytes()


def slice_arm64(fat):
    if fat[:4] == bytes.fromhex('cafebabe'):
        count = struct.unpack_from('>I', fat, 4)[0]
        slices = [struct.unpack_from('>5I', fat, 8 + 20 * i) for i in range(count)]
        chosen = [s for s in slices if s[:2] == (0x100000c, 0)]
        if len(chosen) != 1:
            raise SystemExit('expected exactly one arm64 slice')
        _, _, offset, size, _ = chosen[0]
        return fat[offset:offset + size]
    return fat


def fetch_reference(dest):
    """Fetch the Darwin 22 IOStorageFamily source once."""
    if (dest / 'IOBlockStorageDevice.cpp').is_file():
        return dest
    archive = urllib.request.urlopen(REFERENCE_URL).read()
    scratch = Path(tempfile.mkdtemp())
    tar = scratch / 'reference.tar.gz'
    tar.write_bytes(archive)
    subprocess.run(['tar', 'xzf', str(tar), '-C', str(scratch)], check=True)
    root = next(p for p in scratch.iterdir() if p.is_dir())
    dest.mkdir(parents=True, exist_ok=True)
    for name in ('IOBlockStorageDevice.cpp', 'IOBlockStorageDevice.h'):
        shutil.copyfile(root / name, dest / name)
    for path in root.glob('*.h'):
        shutil.copyfile(path, dest / path.name)
    return dest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tree', required=True, type=Path, help='assembled target tree')
    parser.add_argument('--output', type=Path, default=DEVICE / 'mac-build/storage-abi/interface-audit.json')
    parser.add_argument('--kernel', type=Path, help='already-decompressed 20G81 kernel Mach-O')
    parser.add_argument('--ipsw-url', default=os.environ.get('UNIXNU_20G81_IPSW_URL', DEFAULT_IPSW_URL),
                        help='IPSW URL when --kernel is absent')
    parser.add_argument('--cache', type=Path, default=DEVICE / 'mac-build/storage-abi/cache')
    parser.add_argument('--expect-kernel-sha256', default=KERNEL_PIN)
    args = parser.parse_args()

    tree = args.tree.resolve()
    out = args.output.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    cache = args.cache.resolve()
    cache.mkdir(parents=True, exist_ok=True)

    # ---- 1. original kernelcache Mach-O -------------------------------------
    original_path = cache / 'kernelcache.decompressed'
    if args.kernel:
        original = Path(args.kernel).read_bytes()
    elif original_path.is_file() and digest(original_path.read_bytes()) == args.expect_kernel_sha256:
        original = original_path.read_bytes()
    else:
        if not args.ipsw_url:
            raise SystemExit('need --kernel or --ipsw-url')
        name, member = fetch_member(args.ipsw_url, cache)
        print(f'IPSW member: {name} ({len(member)} bytes)')
        packed = cache / 'kernelcache.lzfse'
        packed.write_bytes(im4p_payload(member))
        original = slice_arm64(decompress(packed, cache / 'kernelcache.fat'))
        packed.unlink(missing_ok=True)
    if digest(original) != args.expect_kernel_sha256:
        raise SystemExit(f'original kernelcache sha256 {digest(original)} != pin {args.expect_kernel_sha256}')
    original_path.write_bytes(original)
    print(f'original 20G81 kernel: {len(original)} bytes sha256 {digest(original)[:16]}')

    sys.path.insert(0, str(tree / 'kits' / 'XnuPrelink'))
    import native_prelink as np

    # ---- 2. public reference object ----------------------------------------
    reference = fetch_reference(cache / 'IOStorageFamily')
    headers = cache / 'include/IOKit/storage'
    headers.mkdir(parents=True, exist_ok=True)
    for path in reference.glob('*.h'):
        shutil.copyfile(path, headers / path.name)
    sdk = sh(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'])
    macsdk = Path(sh(['xcrun', '--sdk', 'macosx', '--show-sdk-path']))
    shutil.copyfile(macsdk / 'usr/include/TargetConditionals.h', cache / 'include/TargetConditionals.h')
    framework = tree / '.cache/fakeroot/System/Library/Frameworks/Kernel.framework/Versions/A'
    if not (framework / 'PrivateHeaders').is_dir():
        raise SystemExit(f'missing Kernel.framework headers: {framework}')
    obj = cache / 'reference.o'
    command = ['xcrun', '--sdk', 'iphoneos', 'clang++', '-target', 'arm64-apple-ios16.0',
               '-isysroot', sdk, '-mkernel', '-ffreestanding', '-fno-builtin', '-fno-exceptions',
               '-fno-rtti', '-std=gnu++17', '-fblocks', '-O2', '-g',
               '-DKERNEL=1', '-DKERNEL_PRIVATE=1', '-DXNU_KERNEL_PRIVATE=1',
               '-I', str(cache / 'include'), '-I', str(framework / 'PrivateHeaders'),
               '-I', str(framework / 'Headers'), '-Wno-deprecated-declarations',
               '-Wno-c99-designator', '-Wno-reorder-init-list', '-Wno-unnecessary-virtual-specifier',
               '-c', str(reference / 'IOBlockStorageDevice.cpp'), '-o', str(obj)]
    (cache / 'reference-command.json').write_text(json.dumps(command, indent=2) + '\n')
    result = subprocess.run(command, capture_output=True, text=True)
    (cache / 'reference.log').write_text(result.stdout + result.stderr)
    if result.returncode:
        raise SystemExit('reference compile failed:\n' + (result.stdout + result.stderr)[-3000:])

    # ---- 3. 190-slot dispatch order from the reference object ---------------
    blob = obj.read_bytes()
    image = np.macho(blob)
    dwarf = sh(['xcrun', 'dwarfdump', '--name=IOBlockStorageDevice', '--show-children', str(obj)])
    match = re.search(r'DW_AT_name\s+\("IOBlockStorageDevice"\)[\s\S]{0,200}?DW_AT_byte_size\s+\((0x[0-9a-f]+)\)', dwarf)
    if not match or int(match.group(1), 16) != CLASS_SIZE:
        raise SystemExit(f'public class size changed: {match.group(1) if match else None}')
    symcmd = next(at for command_id, at, size in image['commands'] if command_id == 2)
    sy, count, st, _ = struct.unpack_from('<4I', blob, symcmd + 8)
    symbols = []
    for index in range(count):
        ix, kind, _, _, value = struct.unpack_from('<IBBHQ', blob, sy + index * 16)
        symbols.append((blob[st + ix:blob.index(b'\0', st + ix)].decode(), value, kind))
    vtable = next(v for name, v, kind in symbols if name == '__ZTV20IOBlockStorageDevice')
    relocations = {}
    for segment in image['segments']:
        for section in segment['sections']:
            if section['va'] <= vtable < section['va'] + section['size']:
                ro, rc = struct.unpack_from('<II', blob, section['command_offset'] + 56)
                for index in range(rc):
                    at, word = struct.unpack_from('<II', blob, ro + index * 8)
                    if word >> 27 & 1 and word >> 28 == 0 and word >> 25 & 3 == 3:
                        relocations[section['va'] + at] = symbols[word & 0xffffff][0]
    methods = []
    while vtable + 16 + len(methods) * 8 in relocations:
        methods.append(relocations[vtable + 16 + len(methods) * 8])
    if len(methods) != SLOTS or methods.count('___cxa_pure_virtual') != PURE_VIRTUAL:
        raise SystemExit(f'unexpected dispatch shape: {len(methods)} slots, '
                         f'{methods.count("___cxa_pure_virtual")} pure virtual')

    # ---- 4. locate the original kext and its dispatch table ----------------
    kernel = np.macho(original)
    exports = np.exports(original, kernel)
    known = {name: va for va, names in exports.items() for name in names}
    info_section = next(s for g in kernel['segments'] for s in g['sections'] if s['name'] == '__info')
    info = np.unserialize_xml(original[info_section['fileoff']:info_section['fileoff'] + info_section['size']].rstrip(b'\0'))
    entry = next(e for e in info['_PrelinkInfoDictionary']
                 if e.get('CFBundleIdentifier') == 'com.apple.iokit.IOStorageFamily')
    kext_at = np.backed_offset(kernel['segments'], entry['_PrelinkExecutableLoadAddr'], 32, len(original))
    kext = np.macho(original, kext_at)
    const = next(s for s in kext['segments'] if s['name'] == '__DATA_CONST')
    text = next(s for s in kext['segments'] if s['name'] == '__TEXT_EXEC')

    def read(va, size):
        at = np.backed_offset(kernel['segments'], va, size, len(original))
        return original[at:at + size]

    data = read(const['va'], const['size'])
    matches = []
    for at in range(0, len(data) - (SLOTS + 2) * 8 + 1, 8):
        if data[at:at + 16] != bytes(16):
            continue
        pointers = struct.unpack_from('<' + 'Q' * SLOTS, data, at + 16)
        if all(pointers[i] == known[name] for i, name in enumerate(methods) if name in known):
            matches.append((const['va'] + at, pointers))
    if len(matches) != 1:
        raise SystemExit(f'20G81 storage dispatch is not unique: {len(matches)} candidates')
    table, pointers = matches[0]
    matched = sum(name in known for name in methods)
    print(f'dispatch table {table:#x}; {matched}/{SLOTS} slots are kernel exports')

    # metaclass getter: adrp/add/ret at slot 7
    words = struct.unpack('<3I', read(pointers[7], 12))
    adrp, add, ret = words
    if adrp & 0x9f00001f != 0x90000000 or add & 0xffc003ff != 0x91000000 or ret != 0xd65f03c0:
        raise SystemExit('unexpected metaclass getter layout')
    immediate = ((adrp >> 5 & 0x7ffff) << 2) | (adrp >> 29 & 3)
    if immediate & 1 << 20:
        immediate -= 1 << 21
    meta = (pointers[7] & ~4095) + immediate * 4096 + (add >> 10 & 4095)

    base = min(s['va'] for s in kernel['segments'] if s['name'].startswith('__PRELINK') and s['size'])

    # protected constructor: the unique __TEXT_EXEC stub that stores table + 16
    text_bytes = read(text['va'], text['size'])
    constructors = []
    for offset in range(0, text['size'] - 32, 4):
        words = struct.unpack_from('<8I', text_bytes, offset)
        if (words[:2] != (0xa9bf7bfd, 0x910003fd) or words[2] & 0xfc000000 != 0x94000000 or
                words[3] & 0x9f00001f != 0x90000008 or words[4] & 0xffc003ff != 0x91000108 or
                words[5:] != (0xf9000008, 0xa8c17bfd, 0xd65f03c0)):
            continue
        address = text['va'] + offset
        immediate = ((words[3] >> 5 & 0x7ffff) << 2) | (words[3] >> 29 & 3)
        if immediate & 1 << 20:
            immediate -= 1 << 21
        stored = ((address + 12) & ~4095) + immediate * 4096 + ((words[4] >> 10) & 4095)
        if stored == table + 16:
            constructors.append(address)
    if len(constructors) != 1:
        raise SystemExit(f'storage protected constructor is not unique: {len(constructors)}')
    constructor = constructors[0]

    # base destructor: the branch immediately before the slot-0 abstract trap
    destructor = pointers[0] - 4
    if struct.unpack('<I', read(destructor, 4))[0] & 0xfc000000 != 0x14000000:
        raise SystemExit('storage base destructor layout changed')

    fixed = prelink_placement(image)[2]
    slide = fixed - base
    bindings = {name: pointers[i] + slide for i, name in enumerate(methods)
                if name not in known and name != '___cxa_pure_virtual'}
    bindings.update({'__ZN20IOBlockStorageDevice10gMetaClassE': meta + slide,
                     '__ZTV20IOBlockStorageDevice': table + slide,
                     '__ZN20IOBlockStorageDeviceC2EPK11OSMetaClass': constructor + slide,
                     '__ZN20IOBlockStorageDeviceD2Ev': destructor + slide})

    report = dict(
        build='20G81', darwin='22.6.0', source=str(reference), method_slots=SLOTS,
        compiled_public_class_size=CLASS_SIZE, pure_virtual_slots=PURE_VIRTUAL,
        kernel_bindings=matched, fixed_prelink_base=hex(fixed), prelink_base=hex(base),
        vtable=hex(table), original_metaclass=hex(meta),
        original_protected_constructor=hex(constructor), original_base_destructor=hex(destructor),
        candidate_sha256=digest(original), live_native_4k=True,
        abstract_complete_destructors_trap=True,
        bindings={name: hex(value) for name, value in bindings.items()},
        methods=[dict(slot=i, reference_name=name, candidate_target=hex(pointers[i]))
                 for i, name in enumerate(methods)],
    )
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(f'wrote {out} with {len(bindings)} original storage imports')
    print(f'fixed_prelink_base {fixed:#x} (slide {slide:#x})')


if __name__ == '__main__':
    main()
