#!/system/bin/sh
# Install the 2 GiB Data window onto the unixnu partition.
# Inputs pushed to /tmp:
#   data-2g-gpt.img     the 2 GiB GPT-wrapped APFS container (Windows side)
#   shngroot-2g.bin     rebuilt manifest header (checksum updated)
#   shngroot-before.bin current manifest (integrity gate)
#   data-before-shrink  backup of the current 34 MiB window (gate: exists)
# usage: sh data2g-install.sh /dev/block/by-name/unixnu
set -e
DEV="$1"
[ -n "$DEV" ] || { echo "usage: sh data2g-install.sh <dev>"; exit 1; }
D=/tmp
BS=4096

for f in data-2g-gpt.img shngroot-2g.bin shngroot-before.bin; do
  [ -f $D/$f ] || { echo "missing $D/$f"; exit 1; }
done

# 0) gate: manifest unchanged since planning
dd if=$DEV bs=$BS count=1 2>/dev/null | cmp -s - $D/shngroot-before.bin \
  || { echo "SHNGROOT drifted since planning - abort"; exit 1; }

# 1) write the new manifest header FIRST (kernel not running; window offline)
dd if=$D/shngroot-2g.bin of=$DEV bs=$BS count=1 conv=notrunc 2>/dev/null
sync

# 2) stream the 2 GiB image in 256 MiB chunks (keeps recovery /tmp small)
SIZE=$(ls -l $D/data-2g-gpt.img | awk '{print $5}')
[ $((SIZE % BS)) -eq 0 ] || { echo "image not 4 KiB aligned"; exit 1; }
CH=$((256 * 1024 * 1024))
n=0
while [ $n -lt $SIZE ]; do
  cnt=$(( CH < SIZE - n ? CH : SIZE - n ))
  dd if=$D/data-2g-gpt.img of=$D/chunk.tmp bs=1 skip=$n count=$cnt 2>/dev/null
  seek=$(( (7780433920 + n) / BS ))
  dd if=$D/chunk.tmp of=$DEV bs=$BS seek=$seek count=$(( cnt / BS )) conv=notrunc 2>/dev/null
  n=$(( n + cnt ))
  echo "written $n / $SIZE"
  rm -f $D/chunk.tmp
done
sync

# 3) verify: manifest + first 4 KiB of the window + full-image sha256
dd if=$DEV bs=$BS count=1 2>/dev/null | cmp -s - $D/shngroot-2g.bin \
  || { echo "post-write manifest mismatch"; exit 1; }
dd if=$DEV bs=$BS skip=$((7780433920/BS)) count=1 2>/dev/null | dd bs=1 skip=512 count=8 2>/dev/null | grep -q "EFI PART" \
  || { echo "window does not start with GPT"; exit 1; }
got=$(dd if=$DEV bs=$BS skip=$((7780433920/BS)) count=$((2147483648/BS)) 2>/dev/null | sha256sum | cut -d' ' -f1)
want=$(sha256sum $D/data-2g-gpt.img | cut -d' ' -f1)
[ "$got" = "$want" ] || { echo "sha256 mismatch got=$got want=$want"; exit 1; }
echo "VERIFY OK: 2 GiB Data window installed, sha256 $want"
