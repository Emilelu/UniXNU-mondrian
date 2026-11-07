#!/usr/bin/env python3
"""Skip AppleARMCPU::_validateConfiguration() in a prelinked K60 kernel.

The K60 kernel prelinks Apple's kernelcache, so com.apple.driver.AppleARMPlatform
(and with it the AppleARMCPU class) is part of the image even though the board is a
Qualcomm SM8475.  its _validateConfiguration() only accepts an Apple Silicon device
tree and panics with "CPU configuration in device tree is invalid" before the
UniXNU ArmCpu/ArmDTPlatform drivers get a chance.  The CPU nubs are driven by
ArmCpu (IOProbeScore 2000) anyway, so making the validator return true removes the
Apple-only gate without changing which driver owns the CPUs.

Usage:
  patch_armcpu_validate.py kernel.macho --check     # verify original bytes
  patch_armcpu_validate.py kernel.macho --apply     # patch in place
"""
import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'kits/NativePrelink'))
import native_prelink as np

KEXT = 'com.apple.driver.AppleARMPlatform'
RVA = 0x2460                      # __TEXT_EXEC offset of _validateConfiguration
EXPECT = bytes.fromhex('ff8304d1fc6f0ca9')   # sub sp, sp, #0x120 ; stp x28, x27, [sp, #192]
PATCH = bytes.fromhex('20008052c0035fd6')    # mov w0, #1 ; ret


def locate(data):
    parent = np.macho(data)
    info = next(s for s in parent['segments'] if s['name'] == '__PRELINK_INFO')
    at = np.backed_offset(parent['segments'], info['va'], info['filesize'], len(data))
    entries = {e['CFBundleIdentifier']: e
               for e in np.unserialize_xml(data[at:at + info['filesize']])['_PrelinkInfoDictionary']}
    entry = entries.get(KEXT)
    if entry is None:
        raise SystemExit(f'{KEXT} is not in this kernel')
    load = entry['_PrelinkExecutableLoadAddr']
    header = np.backed_offset(parent['segments'], load, 32, len(data))
    kext = np.macho(data, header)
    text = next(s for s in kext['segments'] if s['name'] == '__TEXT_EXEC')
    return header + text['fileoff'] + RVA, load


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true')
    group.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    data = bytearray(args.kernel.read_bytes())
    offset, load = locate(data)
    found = bytes(data[offset:offset + 8])
    print(f'kext load {load:#x}  file offset {offset:#x}  bytes {found.hex()}')
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
