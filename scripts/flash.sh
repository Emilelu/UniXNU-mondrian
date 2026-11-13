#!/bin/bash
# flash.sh — the only sanctioned boot entry point.
#
# 铁则 8（2026-11-12）：没有串口日志的 boot 是盲实验。抓取必须在 fastboot boot
# 之前武装好，并且只能有一个进程拥有 COM 口。
#
# 2026-11-12 修：以前这里先起 capture-k60-usblog.ps1，再由 boot-and-capture.ps1
# 另起一个 reader，两者各写一个时间戳目录，还互相抢 COM5 —— 结果主判据看的是一个
# 0 字节文件，于是把"正在正常启动"误判成"内核早死了"。现在只有一个 supervisor
# （boot-and-capture.ps1）和一个 collector（capture-k60-usblog.ps1），证据目录
# 由 supervisor 指定，collector 先写 capture.ready 才允许 boot。
set -u
IMG="${1:?用法: flash.sh <img> [秒数]}"
SECS="${2:-220}"
ADB=/mnt/d/Android/platform-tools/adb.exe
FB=/mnt/d/Android/platform-tools/fastboot.exe
SERIAL="${K60_SERIAL:-6033dbec}"
REPO=$(cd "$(dirname "$0")/.." && pwd)
WORK=$(mktemp -d /tmp/k60flash.XXXXXX) || exit 1
trap 'rm -rf "$WORK"' EXIT
PG_ARGS="--quick"
if [ "${K60_FORCE_NEW:-0}" = "1" ]; then PG_ARGS="--quick --force-new-series"; fi

echo "=== 0) 门禁 ==="
if ! python3 "$REPO/scripts/porting-gate.py" $PG_ARGS > "$WORK/gate-porting.log" 2>&1; then
  echo "❌ 文档/porting 门禁未通过，拒绝启动："
  grep -E 'FAIL' "$WORK/gate-porting.log" | head -10
  exit 1
fi
if ! python3 "$REPO/scripts/eight-step-gate.py" --flash > "$WORK/gate-eight.log" 2>&1; then
  echo "❌ 八步流程未通过，拒绝启动："
  cat "$WORK/gate-eight.log"
  exit 1
fi
if ! python3 "$REPO/scripts/check-boot-procedure.py" > "$WORK/gate-boot.log" 2>&1; then
  echo "❌ 启动流程门禁未通过，拒绝启动："
  grep -E '❌' "$WORK/gate-boot.log" | head -10
  exit 1
fi
if ! python3 "$REPO/scripts/research-gate.py" > "$WORK/gate-research.log" 2>&1; then
  echo "❌ 研究完整性门禁未通过，拒绝启动："
  cat "$WORK/gate-research.log"
  exit 1
fi
echo "  ✅ porting / 八步（flash）/ 启动流程 / 研究"

state() {
  if "$FB" devices 2>/dev/null | tr -d '\r' | grep -qE "^${SERIAL}[[:space:]]+fastboot"; then
    echo fastboot
  elif "$ADB" devices 2>/dev/null | tr -d '\r' | grep -qE "^${SERIAL}[[:space:]]+(device|recovery|sideload)"; then
    echo adb
  else
    echo none
  fi
}
waitfor() {
  local want="$1" seconds="$2" waited=0
  while [ "$waited" -lt "$seconds" ]; do
    if [ "$(state)" = "$want" ]; then echo "  ✅ $want（${waited}s）"; return 0; fi
    sleep 2
    waited=$((waited + 2))
  done
  echo "  ❌ 等不到 $want（${seconds}s）"
  return 1
}

echo
echo "=== 1) 设备状态 ==="
S=$(state)
echo "  当前: $S"
case "$S" in
  fastboot) ;;
  adb)  "$ADB" -s "$SERIAL" reboot bootloader >/dev/null 2>&1; waitfor fastboot 150 || exit 1 ;;
  none) echo "  ❌ 设备不可见（既不在 fastboot 也不在 adb）—— 需要长按电源+音量下"; exit 2 ;;
esac

echo
echo "=== 2) 启动（单一 supervisor 先武装抓取）==="
WIN_IMG=$(echo "$IMG" | sed 's|^/mnt/\([a-z]\)/|\U\1:\\|; s|/|\\|g')
STAMP=$(date +%Y%m%d-%H%M%S)
WIN_OUT="E:\\k60-work\\evidence\\usblog-${STAMP}"
WIN_BOOT=$(echo "$REPO/scripts/boot-and-capture.ps1" | sed 's|^/mnt/\([a-z]\)/|\U\1:\\|; s|/|\\|g')
echo "  img: $WIN_IMG"
echo "  证据目录: $WIN_OUT"
powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "$WIN_BOOT" \
  -Image "$WIN_IMG" -Seconds "$SECS" -WaitFastboot 150 -OutDir "$WIN_OUT" -Serial "$SERIAL"
RC=$?
echo
echo "=== 3) 判读 ==="
echo "  supervisor rc=$RC  证据目录: $WIN_OUT"
case "$RC" in
  0) echo "  ✅ 抓取完整、未因 panic/复位中断" ;;
  1) echo "  ❌ 启动或抓取监督失败" ;;
  2) echo "  ❌ 控制台没拿到任何字节：端口未出现 / 打开失败 / 零字节——看 capture.json 的 state" ;;
  3) echo "  ❌ 已有另一个抓取进程占用串口，boot 没有被发出" ;;
  4) echo "  ⚠️  抓到了但被截断或断线：看 capture.json 的 stopReason" ;;
  5) echo "  ⚠️  设备已自己回到 fastboot（可能是 panic 复位），看 console.log 尾部" ;;
  *) echo "  ❓ 未预期的退出码 $RC" ;;
esac
