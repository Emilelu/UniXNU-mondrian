#!/system/bin/sh
# Read the K60 ramoops console region the darwin24 kernel wrote while it owned
# the machine. Physical base 0xA7000000, 4 MiB reserved:
#   0x00..0x0B  header {u32 sig=0x43474244 'BDGC', u32 start, u32 size}
#   0x0C..      ring buffer, PONG_RAMOOPS_CONSOLE_BYTES (2 MiB) capacity
# Run as root (KernelSU): sh ramoops-read.sh
set -u

BASE=0xA7000000
SIZE=4194304   # 4 MiB reserved window

echo "=== [1] pstore, if the K60 Android DT declares this carveout ==="
ls -la /sys/fs/pstore/ 2>/dev/null || echo "(no /sys/fs/pstore)"

echo
echo "=== [2] dump the raw carveout ==="
OUT=/data/local/tmp/ramoops-$(date +%H%M%S).bin
if [ -e /dev/mem ]; then
  # /dev/mem may refuse; report rather than retry with another path
  dd if=/dev/mem of="$OUT" bs=4096 skip=$((BASE / 4096)) count=$((SIZE / 4096)) 2>&1 | tail -2
else
  echo "(no /dev/mem)"
fi

if [ -s "$OUT" ]; then
  echo
  echo "=== [3] header and payload ==="
  echo "dumped: $OUT  $(wc -c < "$OUT") bytes"
  echo "--- first 64 bytes ---"
  od -A x -t x1z -v -N 64 "$OUT"
  echo "--- printable text (first 8 KiB) ---"
  dd if="$OUT" bs=1024 count=8 2>/dev/null | strings | head -80
else
  echo "(nothing dumped)"
fi
