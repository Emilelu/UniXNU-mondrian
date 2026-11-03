#!/usr/bin/env python3
"""route-a-18: build the darwin24 prelink roots list.

__PRELINK_INFO holds an XML fragment (<dict>... without the <?xml header), so
wrap it before parsing. Then check which of our 20G81 roots survive in 22H374
and emit the new roots list for the profile.
"""
from pathlib import Path
import re
import struct

KC = Path('/tmp/k60build/out/ipsw/22H374/kernelcache.decompressed')
data = KC.read_bytes()
if data[:4] == b'\xca\xfe\xba\xbe':
    count = struct.unpack('>I', data[4:8])[0]
    for i in range(count):
        cpu, sub, off, size, align = struct.unpack('>5I', data[8+20*i:28+20*i])
        if cpu == 0x0100000c:
            data = data[off:off+size]

ncmds = struct.unpack_from('<I', data, 16)[0]
p, segs = 32, {}
for _ in range(ncmds):
    cmd, cmdsize = struct.unpack_from('<II', data, p)
    if cmd == 0x19:
        name = data[p+8:p+24].split(b'\0')[0].decode()
        _, _, fileoff, filesize = struct.unpack_from('<QQQQ', data, p+24)
        segs[name] = (fileoff, filesize)
    p += cmdsize

off, size = segs['__PRELINK_INFO']
blob = data[off:off+size]
end = blob.find(b'</plist>')
frag = blob[:end] if end > 0 else blob
text = frag.decode('utf-8', 'replace')

# CFBundleIdentifier pairs, in document order, deduplicated.
pairs = re.findall(r'<key>CFBundleIdentifier</key>\s*<string>([^<]+)</string>', text)
ordered = list(dict.fromkeys(pairs))
print('kexts in __PRELINK_INFO:', len(ordered))

OURS = """com.apple.AppleFSCompression.AppleFSCompressionTypeZlib com.apple.driver.AppleARMPlatform
com.apple.driver.AppleARMWatchdogTimer com.apple.driver.AppleAudioClockLibs
com.apple.driver.AppleEffaceableStorage com.apple.driver.AppleIISController
com.apple.driver.AppleM2ScalerCSCDriver com.apple.driver.AppleMobileFileIntegrity
com.apple.driver.ApplePMGR com.apple.driver.IODARTFamily com.apple.filesystems.apfs
com.apple.iokit.CoreAnalyticsFamily com.apple.iokit.IOAVFamily com.apple.iokit.IOAudio2Family
com.apple.iokit.IOCECFamily com.apple.iokit.IOCryptoAcceleratorFamily com.apple.iokit.IOGPUFamily
com.apple.iokit.IOHDCPFamily com.apple.iokit.IOMobileGraphicsFamily com.apple.iokit.IOReportFamily
com.apple.iokit.IOSlowAdaptiveClockingFamily com.apple.iokit.IOStorageFamily com.apple.iokit.IOSurface
com.apple.kec.pthread com.apple.kec.Libm com.apple.kec.corecrypto com.apple.kext.AppleMatch
com.apple.kext.CoreTrust com.apple.security.AppleImage4 com.apple.security.sandbox
com.apple.iokit.IOHIDFamily com.apple.iokit.IOHIDEventDriver""".split()

present = set(ordered)
keep = [r for r in OURS if r in present]
lost = [r for r in OURS if r not in present]
print(f'our roots still present: {len(keep)}/{len(OURS)}')
for r in lost:
    print('  LOST:', r)

# Kexts we rely on that are NOT in our current list but exist in darwin24.
EXTRA_CANDIDATES = ['com.apple.driver.AppleS5L8920XPTCSH', 'com.apple.iokit.IOHIDFamily',
                    'com.apple.driver.AppleA7IOP', 'com.apple.driver.AppleARMPMU',
                    'com.apple.driver.AppleT8103PCIe', 'com.apple.driver.ApplePCIeController',
                    'com.apple.iokit.IOPCIFamily', 'com.apple.driver.AppleSART',
                    'com.apple.driver.AppleSMMU', 'com.apple.iokit.IOMMUFamily']
print()
print('other candidates present in 22H374:')
for c in EXTRA_CANDIDATES:
    if c in present:
        print('  yes:', c)

Path('/tmp/k60build/out/ipsw/22H374/kext-ids.txt').write_text('\n'.join(ordered) + '\n')
Path('/tmp/k60build/out/ipsw/22H374/roots-darwin24.txt').write_text(
    ' '.join(keep) + '\n')
print()
print('wrote kext-ids.txt', len(ordered), 'and roots-darwin24.txt', len(keep))
