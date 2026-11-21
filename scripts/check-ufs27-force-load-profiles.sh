#!/usr/bin/env bash
# Run the storage force-load blocks against each profile's switches, offline.
#
# The question is not "does the file contain the line" but "would this profile
# link build/native-ufs/libNativeUfs.a": 16.6.1 sets CONFIG_XNU_NATIVE_UFS=y and
# must keep linking it, 27 sets it to n and must not. So the blocks are lifted
# out of the builders verbatim and executed with stub variables — no compiler, no
# make, no kernel, and nothing is written outside a scratch tree.
#
# `XNU_NATIVE_UFS_BUNDLE` is the guard the Lead's removal diff adds
# (docs/research/storage/UFS27-FORCE-LOAD-REMOVAL.patch). Until that diff lands
# the guard case is reported as SKIP, not as a pass: a criterion that cannot run
# yet must not look green.
#
# Usage:
#   scripts/check-ufs27-force-load-profiles.sh [--source <tree>]
#
# --source grades another copy of the two builders and the two defconfigs, which
# is how the guard case is demonstrated before the diff lands: apply
# docs/research/storage/UFS27-FORCE-LOAD-REMOVAL.patch to a scratch copy and the
# guard rows stop being SKIP.
#
# Exit code 0 when every applicable expectation holds.
set -u

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SOURCE=$ROOT
while [ $# -gt 0 ]; do
    case "$1" in
        --source) SOURCE=$(cd "$2" && pwd); shift 2 ;;
        -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
        *) echo "check-ufs27-force-load-profiles: unknown argument $1" >&2; exit 2 ;;
    esac
done
WORK=${TMPDIR:-/tmp}/ufs27-force-load
STUB=$WORK/root
problems=0

say() { echo "check-ufs27-force-load-profiles: $*"; }

switch_of() { # defconfig -> value of CONFIG_XNU_NATIVE_UFS
    sed -n 's/^CONFIG_XNU_NATIVE_UFS=//p' "$1" | head -1 | tr -d '"[:space:]'
}

# The two UFS switch blocks in the builders both match the same `if` header, so a
# block is only the one that appends the archive: the switch-set block at
# build-xnu-generic.sh:228 sets PERSONALITY_CFLAGS and must not be lifted.
extract_block() { # builder index outfile
    python3 - "$1" "$2" "$3" <<'PY'
import sys
from pathlib import Path

path, index, out = Path(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])
lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
blocks, cursor = [], 0
while cursor < len(lines):
    if lines[cursor].lstrip().startswith('if [ "${XNU_NATIVE_UFS:-0}" = 1 ]'):
        end = cursor
        while end < len(lines) and lines[end].rstrip("\r\n") != "  fi":
            end += 1
        body = "".join(lines[cursor : end + 1])
        if "-force_load,$UFS_ARCHIVE" in body:
            blocks.append(body)
        cursor = end + 1
    else:
        cursor += 1
if index >= len(blocks):
    sys.exit(f"{path.name}: only {len(blocks)} force-load block(s), wanted index {index}")
out.write_text(blocks[index], encoding="utf-8", newline="")
print(f"{path.name}: block {index} of {len(blocks)}, {len(blocks[index].splitlines())} lines")
PY
}

run_block() { # block-file env...
    local file=$1
    shift
    env "$@" ROOT="$STUB" KERNEL_EXTRA_ARCHIVES= KERNEL_ARCHIVE_DEPENDENCIES= \
        PLATFORM_ARCHIVES= PLATFORM_DEPENDENCIES= \
        bash -c "set -euo pipefail
                 $(cat "$file")
                 printf '%s|%s\n' \"\$KERNEL_EXTRA_ARCHIVES\" \"\$PLATFORM_ARCHIVES\""
}

expect() { # label wanted(linked|unlinked) block-file env...
    local label=$1 want=$2 file=$3
    shift 3
    local out linked
    if ! out=$(run_block "$file" "$@" 2>&1); then
        say "FAIL: $label: the block itself failed: $out"
        problems=$((problems + 1))
        return
    fi
    case "$out" in
        *libNativeUfs.a*) linked=linked ;;
        *) linked=unlinked ;;
    esac
    if [ "$linked" = "$want" ]; then
        say "ok   $label: $linked"
    else
        say "FAIL: $label: wanted $want, got $linked; archives were '$out'"
        problems=$((problems + 1))
    fi
}

rm -rf "$WORK"
mkdir -p "$WORK" "$STUB/build/native-ufs"
: > "$STUB/build/native-ufs/libNativeUfs.a"

GENERIC=$SOURCE/scripts/build-xnu-generic.sh
BASELINE=$SOURCE/scripts/build-xnu-4k-baseline.sh
for builder in "$GENERIC" "$BASELINE"; do
    [ -f "$builder" ] || { say "FATAL: no $(basename "$builder")"; exit 2; }
done

# A missing block must stop the run: "no block" would otherwise grade as
# "unlinked" and pass the very expectation it should fail.
for pair in "$GENERIC:0:generic" "$BASELINE:0:baseline-kernel" "$BASELINE:1:baseline-platform"; do
    builder=${pair%%:*}; rest=${pair#*:}; index=${rest%%:*}; name=${rest#*:}
    extract_block "$builder" "$index" "$WORK/$name.block" || {
        say "FATAL: cannot lift a force-load block out of $(basename "$builder")"
        exit 2
    }
done

six_switch=$(switch_of "$SOURCE/configs/mondrian_defconfig")
twenty7_switch=$(switch_of "$SOURCE/configs/mondrian_ios27_defconfig")
six_env=XNU_NATIVE_UFS=0
[ "$six_switch" = y ] && six_env=XNU_NATIVE_UFS=1
twenty7_env=XNU_NATIVE_UFS=0
[ "$twenty7_switch" = y ] && twenty7_env=XNU_NATIVE_UFS=1
say "source $SOURCE"
say "16.6.1 CONFIG_XNU_NATIVE_UFS=$six_switch  27 CONFIG_XNU_NATIVE_UFS=$twenty7_switch"

# The 16.6.1 profile has no bundle: the guard, once it exists, stays open.
expect "16.6.1 kernel archives keep it" linked   "$WORK/baseline-kernel.block"   "$six_env" XNU_NATIVE_UFS_BUNDLE=0
expect "16.6.1 platform archives keep it" linked "$WORK/baseline-platform.block" "$six_env" XNU_NATIVE_UFS_BUNDLE=0
expect "27 does not link it"             unlinked "$WORK/generic.block"          "$twenty7_env"

# Once the Lead's diff lands, the guard has to be able to close the block.
if grep -q 'XNU_NATIVE_UFS_BUNDLE' "$WORK/generic.block"; then
    expect "guard closes the block" unlinked "$WORK/generic.block" XNU_NATIVE_UFS=1 XNU_NATIVE_UFS_BUNDLE=1
    expect "guard open still links" linked   "$WORK/generic.block" XNU_NATIVE_UFS=1 XNU_NATIVE_UFS_BUNDLE=0
else
    say "SKIP guard case: XNU_NATIVE_UFS_BUNDLE is not in the block yet (the removal diff is with the Lead)"
fi

if [ "$problems" -eq 0 ]; then
    say "force-load profiles: OK"
    exit 0
fi
say "force-load profiles: $problems problem(s)"
exit 1
