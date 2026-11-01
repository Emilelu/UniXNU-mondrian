#!/usr/bin/env bash
# Compare the boot image's ramdisk against the darwin24 payload explicitly.
set -uo pipefail
IMG=/mnt/d/Android/k60-ios/boot-darwin24.img
PAY=/tmp/k60build/out/mondrian/ipados-18.7.10-22H374/mondrian/payload/payload.img

echo "===== expected payload ====="
ls -la "$PAY"
sha256sum "$PAY"

echo
echo "===== image layout ====="
python3 - <<'PY'
import hashlib, struct
img = '/mnt/d/Android/k60-ios/boot-darwin24.img'
pay = '/tmp/k60build/out/mondrian/ipados-18.7.10-22H374/mondrian/payload/payload.img'
data = open(img, 'rb').read()
print('image size:', len(data))
print('magic:', data[:8])
ksize, kaddr, rsize, rsize2 = struct.unpack_from('<IIII', data, 8)
print(f'kernel_size={ksize} kernel_addr=0x{kaddr:x} ramdisk_size={rsize} hdr_ver={struct.unpack_from("<I", data, 40)[0]}')
page = 4096
rd_off = page + ((ksize + page - 1) // page) * page
print('ramdisk offset:', rd_off, 'header ramdisk_size field:', rsize)
expected = open(pay, 'rb').read()
seg = data[rd_off:rd_off + len(expected)]
print('in-image ramdisk sha256:', hashlib.sha256(seg).hexdigest())
print('payload.img sha256    :', hashlib.sha256(expected).hexdigest())
print('MATCH' if seg == expected else 'MISMATCH')
PY
