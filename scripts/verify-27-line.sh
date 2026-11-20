#!/bin/bash
# Prove the three legs of the 27 line on a throwaway clone of the seeded tree:
#   1. carry the seed's uncommitted modifications,
#   2. apply 0626..0630 in series order,
#   3. append conffiles-port.txt at bsd/dev/unix_startup.c.
#
# Nothing is written to the tree that is passed in: the clone is made with
# --shared, so the objects are reused and only the working files are copied.
#
# usage: bash scripts/verify-27-line.sh --tree <xnu-work> [--patches <dir>] [--appender <py>] [--keep]
set -u

TREE=""
PATCHES="$(cd "$(dirname "$0")/.." && pwd)/patches/xnu-12377"
KEEP=0
APPENDER=""
while [ $# -gt 0 ]; do
	case "$1" in
		--tree) TREE="$2"; shift 2 ;;
		--patches) PATCHES="$2"; shift 2 ;;
		--appender) APPENDER="$2"; shift 2 ;;
		--keep) KEEP=1; shift ;;
		*) echo "usage: $0 --tree <xnu-work> [--patches <dir>] [--appender <py>] [--keep]" >&2; exit 2 ;;
	esac
done
[ -n "$TREE" ] || { echo "usage: $0 --tree <xnu-work>" >&2; exit 2; }
[ -d "$TREE/.git" ] || { echo "K60 TRIAL REFUSED no git repository at $TREE" >&2; exit 3; }
[ -f "$PATCHES/conffiles-port.txt" ] || { echo "K60 TRIAL REFUSED no conffiles-port.txt in $PATCHES" >&2; exit 3; }

WORK="${K60_WORK:-/mnt/e/k60-work}/scratch"
mkdir -p "$WORK"
TRIAL="$(mktemp -d "$WORK/xnu27-trial-XXXXXX")" || exit 4
cleanup() { if [ "$KEEP" = "1" ]; then echo "K60 TRIAL kept $TRIAL"; else rm -rf "$TRIAL"; fi; }
trap cleanup EXIT

git clone -q --shared "$TREE" "$TRIAL/xnu" || { echo "K60 TRIAL FAILED clone"; exit 4; }
T="$TRIAL/xnu"
git -C "$TREE" diff > "$TRIAL/seed.diff" 2>/dev/null
if [ -s "$TRIAL/seed.diff" ]; then
	git -C "$T" apply "$TRIAL/seed.diff" || { echo "K60 TRIAL FAILED the seed modifications do not carry"; exit 1; }
	echo "K60 TRIAL ok   seed modifications carried"
else
	echo "K60 TRIAL ok   the seed is committed clean"
fi

for name in 0626-k60-modem-image 0627-k60-modem-qrtr 0628-k60-ipa \
            0629-kern-exec-call-sites 0630-k60-smem; do
	if git -C "$T" apply "$PATCHES/$name.patch" 2>"$TRIAL/err"; then
		echo "K60 TRIAL ok   $name applies"
	else
		echo "K60 TRIAL FAILED $name: $(head -2 "$TRIAL/err" | tr '\n' ' ')"
		exit 1
	fi
done

if [ -n "$APPENDER" ]; then
	python3 "$APPENDER" --verify "$T" "$PATCHES/conffiles-port.txt" || {
		echo "K60 TRIAL FAILED the shared appender refused the clone"; exit 1; }
	echo "K60 TRIAL ok   the shared appender accepted the clone"
else
python3 - "$T" "$PATCHES/conffiles-port.txt" <<'PY'
import pathlib
import sys

tree = pathlib.Path(sys.argv[1])
entries = [line for line in pathlib.Path(sys.argv[2]).read_text().splitlines() if line.strip()]
tab = chr(9)
anchor = "bsd/dev/unix_startup.c" + tab * 3 + "standard"
conf = tree / "bsd" / "conf" / "files"
text = conf.read_text()
if anchor not in text:
    print("K60 TRIAL FAILED the conffiles anchor is missing from bsd/conf/files")
    sys.exit(1)
missing = [e.split(tab)[0] for e in entries if not (tree / e.split(tab)[0]).is_file()]
if missing:
    print("K60 TRIAL FAILED %d entries point at sources the patches do not install: %s"
          % (len(missing), " ".join(missing[:4])))
    sys.exit(1)
block = anchor
added = 0
for entry in entries:
    if entry in text:
        continue
    block = block + chr(10) + entry
    added += 1
conf.write_text(text.replace(anchor, block, 1))
listed = len([line for line in conf.read_text().splitlines()
              if line.startswith("bsd/dev/pong_") or line.startswith("bsd/dev/qcom_glink")])
print("K60 TRIAL ok   appended %d build entries, bsd/conf now lists %d" % (added, listed))
if added != len(entries):
    print("K60 TRIAL FAILED only %d of %d entries were appended" % (added, len(entries)))
    sys.exit(1)
PY
fi
status=$?
[ $status -eq 0 ] || exit $status
echo "K60 TRIAL PASS seed, five patches and the build entries on one clone"
