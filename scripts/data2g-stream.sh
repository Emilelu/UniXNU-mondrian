#!/system/bin/sh
# Stream the 2 GiB Data image into the (already resized) Data window.
# mksh arithmetic is 32-bit signed, so all seeks are computed on the HOST
# and baked into /tmp/data2g-seeks.txt as "src_skip_4k dst_seek_4k count_4k".
# usage: sh data2g-stream.sh /dev/block/by-name/unixnu
set -e
DEV="$1"; D=/tmp; BS=4096
[ -f $D/data-2g-gpt.img ] && [ -f $D/data2g-seeks.txt ] || { echo "missing inputs"; exit 1; }
while read src dst cnt; do
  dd if=$D/data-2g-gpt.img bs=$BS skip=$src count=$cnt 2>/dev/null > $D/chunk.tmp
  dd if=$D/chunk.tmp of=$DEV bs=$BS seek=$dst count=$cnt conv=notrunc 2>/dev/null
  rm -f $D/chunk.tmp
  echo "seg src=$src dst=$dst cnt=$cnt done"
done < $D/data2g-seeks.txt
sync
echo "ALL SEGMENTS WRITTEN"
