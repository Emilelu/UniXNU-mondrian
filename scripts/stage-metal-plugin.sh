#!/usr/bin/env bash
# Stage the Metal plugin in the flat layout that gen-k60-metal-blob.py reads.
#
# The macOS build emits a real bundle directory plus the two seed files beside
# it:
#
#   <src>/PongAdrenoMetal.bundle/{Info.plist,PongAdrenoMetal,
#                                PongMetalBridge.dylib,libvulkan_freedreno.dylib}
#   <src>/PongAdrenoMetal.clients
#   <src>/PongAdrenoMetal.publish
#
# The blob generator wants one flat directory: the four bundle members, plus
# both seeds, all as siblings. Copying is cheap (51 MB) and keeps the generator
# free of layout assumptions.
set -eu

SRC=${1:?usage: stage-metal-plugin.sh <built-plugin-dir> <staging-dir>}
DEST=${2:?usage: stage-metal-plugin.sh <built-plugin-dir> <staging-dir>}

BUNDLE=$SRC/PongAdrenoMetal.bundle
[ -d "$BUNDLE" ] || { echo "stage-metal-plugin: $BUNDLE missing" >&2; exit 1; }

rm -rf "$DEST"
mkdir -p "$DEST"

for f in Info.plist PongAdrenoMetal PongMetalBridge.dylib libvulkan_freedreno.dylib; do
    [ -f "$BUNDLE/$f" ] || { echo "stage-metal-plugin: $BUNDLE/$f missing" >&2; exit 1; }
    cp -p "$BUNDLE/$f" "$DEST/$f"
done

for f in PongAdrenoMetal.clients PongAdrenoMetal.publish; do
    [ -f "$SRC/$f" ] || { echo "stage-metal-plugin: $SRC/$f missing" >&2; exit 1; }
    cp -p "$SRC/$f" "$DEST/$f"
done

echo "stage-metal-plugin: $DEST ($(du -sb "$DEST" | cut -f1) bytes, 6 files)"
