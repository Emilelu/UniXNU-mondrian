#!/usr/bin/env bash
set -uo pipefail
python3 - "${1:-/mnt/d/Android/k60-ios/boot-tc.img}" <<'PY'
import hashlib, struct, sys, zlib
from pathlib import Path

BOOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/mnt/d/Android/k60-ios/boot-tc.img")
FD   = Path("/home/emilelu/hackios/uefi-mondrian/Build/mondrianPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd")
DTB  = Path("/tmp/k60build/out/mondrian/ipados-16.6.1-20G81/mondrian/device-tree/hardware.dtb")
PAY  = Path("/tmp/k60build/out/mondrian/ipados-16.6.1-20G81/mondrian/payload/payload.img")

d = BOOT.read_bytes()
ok = True
def chk(cond, msg):
    global ok
    print(("  OK   " if cond else "  FAIL ") + msg)
    ok = ok and cond

print("== header ==")
chk(d[:8] == b"ANDROID!", "magic ANDROID!")
ks, ka, rs, ra, ss, sa, tags, page, ver, osv = struct.unpack_from("<10I", d, 8)
print(f"  kernel_size={ks} kernel_addr={ka:#x} ramdisk_size_field={rs} second={ss} hdr_ver={ver}")
chk(ver == 4, "header_version == 4")
chk(ss == 0, "no second stage")

print("== kernel area ==")
kblob = d[4096:4096 + ks]
dec = zlib.decompressobj(16 + zlib.MAX_WBITS)
inflated = dec.decompress(kblob)
chk(dec.eof, "gzip member terminates inside the kernel area")
tree = dec.unused_data
fd = FD.read_bytes()
chk(inflated.endswith(fd), "inflated stream ends with the exact UEFI FD bytes")
shim = inflated[:len(inflated) - len(fd)]
print(f"  shim {len(shim)} bytes, ARM64 header at 56: {shim[56:60]!r}")
chk(shim[56:60] == b"ARM\x64", "shim keeps the ARM64 image header")
dtb = DTB.read_bytes()
chk(tree == dtb, f"appended device tree equals hardware.dtb ({len(dtb)} bytes)")
print("  dtb sha256", hashlib.sha256(tree).hexdigest()[:32])

print("== ramdisk ==")
pay = PAY.read_bytes()
start = 4096 + ((ks + 4095) // 4096) * 4096
chk(d[start:start + len(pay)] == pay, f"ramdisk at {start} equals payload.img ({len(pay)} bytes)")
end = start + ((len(pay) + 4095) // 4096) * 4096
chk(len(d) >= end and set(d[end:]) in ({0}, set()), "file length matches kernel+ramdisk pages (trailing zero padding allowed)")
print("  payload sha256", hashlib.sha256(pay).hexdigest()[:32])
print("== RESULT ==", "PASS" if ok else "FAIL")
PY
