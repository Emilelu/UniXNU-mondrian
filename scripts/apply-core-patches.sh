#!/bin/sh
# Apply the K60 framework patch to a UniXNU checkout, when it still applies.
#
# The patch was written against the framework commit the 16.6.1 line was built
# on. On the iOS 27 branch it is obsolete and no longer applies:
#   * the boot-image verify() it patched now supports v3/v4 upstream;
#   * the initrd FAT scan, the ramoops dump, the -1 timeout and the volume
#     diagnostics live in uefi-mondrian's vendored UniXNUPkg, which
#     Platforms/Xiaomi resolves before the framework's copy.
# Refusing is the correct move for a stale patch; a silent skip would hide a
# real regression if the pin moves again.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
CORE=${1:-../UniXNU}
PATCH="$ROOT/patches/unixnu-core/k60-unixnu-core.patch"

if git -C "$CORE" apply --check "$PATCH" 2>/dev/null; then
	git -C "$CORE" apply "$PATCH"
	echo "applied $PATCH"
	exit 0
fi

cat >&2 <<'EOF'
k60-unixnu-core.patch does not apply to this UniXNU checkout.
On feat/ios27 that is expected: the boot-image v3/v4 verify is upstream and the
K60 initrd/ramoops/config deltas are in uefi-mondrian's vendored UniXNUPkg.
Do not force it. If the checkout is meant to be the 16.6.1 framework commit,
check out that commit first (see docs/engineering/IOS27.md).
EOF
exit 1
