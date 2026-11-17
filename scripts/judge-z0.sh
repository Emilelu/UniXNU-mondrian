#!/usr/bin/env bash
# judge-z0.sh <usblog-dir> [--expect-arg pong_wifi=0]
#
# Why: a control flight is only readable if the image really carried the
# argument we think it carried.  cellular-l3-20261114d recorded
# kernel_args_requested = [''] -- the build forgot the argument, the driver took
# its default and returned, and flying that image proves nothing.  [''] and
# ['pong_wifi=0'] are the same on the kernel command line but not in the
# evidence chain: the first is a forgotten flag, the second is a deliberate
# control.  So this wrapper proves the image's identity and its argument before
# it lets the judge speak.
#
# Order -- prove identity, then judge, then show evidence:
#   1. console.log size
#   2. boot.json image + sha256
#   3. argument self-check: the manifest field, then the bytes in boot.img
#      (the bytes are authoritative: trial builds keep only four manifest keys)
#   4. bare judge call -> verdict word + [exit N] + the real rc
#   5. marker counts, with the two opposite meanings kept apart
#   6. tail of the console
#
# Exit codes: the judge's own 0 alive / 1 driver-dead / 2 silent / 3 unknown.
# 4 means NOT A VERDICT -- the argument self-check failed, the directory is
# unusable, or a helper (check-arg.py / judge-wifi-boot.py) cannot be found.
# Never read 4 as "silent".
#
# Paths: check-arg.py and judge-wifi-boot.py sit next to this script in
# scripts/.  If the pair lives elsewhere (scratch copy), point K60_REFMINE_REPO
# at the repo root.  A missing helper is a loud refusal (exit 4), never a verdict.
set -u

d="${1:-}"
shift || true
expect="pong_wifi=0"
while [ $# -gt 0 ]; do
  case "$1" in
    --expect-arg) expect="${2:-}"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 4 ;;
  esac
done
if [ -z "$d" ]; then
  echo "usage: judge-z0.sh <usblog-dir> [--expect-arg pong_wifi=0]" >&2
  exit 4
fi
[ -d "$d" ] || { echo "no such directory: $d" >&2; exit 4; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK="$HERE/check-arg.py"
find_judge() {
  if [ -n "${K60_REFMINE_REPO:-}" ] && [ -f "$K60_REFMINE_REPO/scripts/judge-wifi-boot.py" ]; then
    echo "$K60_REFMINE_REPO/scripts/judge-wifi-boot.py"; return 0
  fi
  if [ -f "$HERE/judge-wifi-boot.py" ]; then
    echo "$HERE/judge-wifi-boot.py"; return 0
  fi
  return 1
}
JUDGE="$(find_judge)" || JUDGE=""
if [ ! -f "$CHECK" ] || [ ! -f "$JUDGE" ]; then
  echo "== REFUSING TO JUDGE: helper not found (dead path, never read as silent)"
  echo "   CHECK=$CHECK"
  echo "   JUDGE=$JUDGE"
  exit 4
fi
log="$d/console.log"

echo "== 1. capture $d"
if [ -f "$log" ]; then
  echo "   console.log $(stat -c %s "$log") bytes"
else
  echo "   console.log MISSING"
fi

echo "== 2. image"
python3 - "$d" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1]) / "boot.json"
try:
    b = json.loads(p.read_text(encoding="utf-8-sig"))
except Exception as e:
    print("   boot.json unreadable: %s" % e)
    raise SystemExit(0)
print("   %s" % b.get("image"))
print("   sha256=%s" % b.get("imageSha256"))
PY

echo "== 3. argument self-check (expected $expect)"
python3 "$CHECK" "$d" "$expect"
argrc=$?
if [ "$argrc" -ne 0 ]; then
  echo
  echo "== REFUSING TO JUDGE: 镜像参数缺失，判读无效"
  echo "   the image did not carry the argument this flight is supposed to"
  echo "   isolate, so whatever the console says cannot be attributed to that"
  echo "   variable.  Rebuild with the argument passed explicitly."
  exit 4
fi

echo "== 4. judge (bare call, no pipeline)"
python3 "$JUDGE" "$d"
rc=$?
echo "   RC=$rc"

echo "== 5. markers"
if [ -f "$log" ]; then
  count() { grep -c -- "$1" "$log" 2>/dev/null || true; }
  sb=$(count SpringBoard); xpc=$(count "K60XPC compat=")
  pw=$(count "PongWifi:"); hb=$(count "held back by k60_wifi_stage")
  mhi=$(count "Pong MHI"); nc=$(count "console never came up")
  echo "   SpringBoard=$sb  K60XPC=$xpc"
  echo "   PongWifi:=$pw  held back by k60_wifi_stage=$hb"
  echo "   Pong MHI=$mhi  console never came up=$nc"
  echo "   -- reading"
  if [ "$pw" -gt 0 ] && [ "$hb" -eq 0 ]; then
    echo "      PongWifi:>0, held back==0 -> the driver executed"
  elif [ "$pw" -eq 0 ] && [ "$hb" -eq 0 ]; then
    echo "      PongWifi:==0, held back==0 -> the driver printed nothing:"
    echo "      the strong form of silent, not a held stage"
  else
    echo "      held back>0 -> stopped by the stage gate, not a hang"
  fi
else
  echo "   no console.log: nothing to count"
fi

echo "== 6. tail"
if [ -f "$log" ]; then tail -n 12 "$log"; else echo "   (empty)"; fi

exit $rc
