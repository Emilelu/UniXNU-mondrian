#!/system/bin/sh
# Replay repaired resource-fork blocks onto the unixnu OS window.
# Host precomputed: rf2-seeks.txt lines are "src_skip_4k dst_seek_512 count_4k".
set -e
DEV="$1"; D=/data/local/tmp; BS=4096
[ -n "$DEV" ] || { echo "usage: sh rf2-apply.sh <dev>"; exit 1; }
[ -f $D/rf2-payload.bin ] || { echo "missing payload"; exit 1; }
[ -f $D/rf2-seeks.txt ] || { echo "missing seeks"; exit 1; }
N=0
while read src dst cnt; do
  dd if=$D/rf2-payload.bin bs=$BS skip=$src count=$cnt 2>/dev/null > $D/rf2.tmp
  dd if=$D/rf2.tmp of=$DEV bs=512 seek=$dst count=$(( cnt * 8 )) conv=notrunc 2>/dev/null
  rm -f $D/rf2.tmp
  N=$(( N + 1 ))
  [ $(( N % 50 )) -eq 0 ] && echo "segments $N done"
done < $D/rf2-seeks.txt
sync
echo "ALL SEGMENTS WRITTEN ($N)"
