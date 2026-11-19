#!/bin/sh
# Apply the UniXNU framework patches this device branch carries.
#
# Each top-level patches/unixnu-core/*.patch changes the framework checkout in a
# way the build needs, and each patches/xnu-prelink/*.patch changes the
# kits/XnuPrelink submodule (the prelink tool) the same way. Apply them once
# after cloning or updating the framework:
#
#   sh scripts/apply-core-patches.sh ../UniXNU
#
# Already-applied patches are reported, not failed, so a rebuild can run this
# safely. patches/unixnu-core/legacy/ holds k60-unixnu-core.patch from the
# 16.6.1 line; it targets an older framework and is never applied here.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
CORE=${1:-../UniXNU}
status=0

apply_all() {
	repo=$1
	directory=$2
	label=$3
	for patch in "$directory"/*.patch; do
		[ -f "$patch" ] || continue
		name=$(basename "$patch")
		if git -C "$repo" apply --check "$patch" 2>/dev/null; then
			git -C "$repo" apply "$patch"
			echo "applied $label/$name"
		elif git -C "$repo" apply --reverse --check "$patch" 2>/dev/null; then
			echo "already applied $label/$name"
		else
			echo "$label/$name does not apply to $repo" >&2
			status=1
		fi
	done
}

apply_all "$CORE" "$ROOT/patches/unixnu-core" patches/unixnu-core
if [ -e "$CORE/kits/XnuPrelink/.git" ]; then
	apply_all "$CORE/kits/XnuPrelink" "$ROOT/patches/xnu-prelink" patches/xnu-prelink
else
	echo "skipped patches/xnu-prelink: $CORE/kits/XnuPrelink is not checked out" >&2
fi

if [ "$status" -ne 0 ]; then
	cat >&2 <<'EOF'
A framework patch neither applies nor is present. Check out the framework
commit recorded in docs/engineering/IOS27.md and run this script again; do not
force the patch, a rejected hunk means the framework moved under it.
EOF
fi
exit "$status"
