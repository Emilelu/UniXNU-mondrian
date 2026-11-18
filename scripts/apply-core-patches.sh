#!/bin/sh
# Apply the UniXNU framework patches this device branch carries.
#
# Each top-level patches/unixnu-core/*.patch changes the framework checkout in a
# way the build needs. Apply them once after cloning or updating the framework:
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

for patch in "$ROOT"/patches/unixnu-core/*.patch; do
	[ -f "$patch" ] || continue
	name=$(basename "$patch")
	if git -C "$CORE" apply --check "$patch" 2>/dev/null; then
		git -C "$CORE" apply "$patch"
		echo "applied $name"
	elif git -C "$CORE" apply --reverse --check "$patch" 2>/dev/null; then
		echo "already applied $name"
	else
		echo "$name does not apply to $CORE" >&2
		status=1
	fi
done

if [ "$status" -ne 0 ]; then
	cat >&2 <<'EOF'
A framework patch neither applies nor is present. Check out the framework
commit recorded in docs/engineering/IOS27.md and run this script again; do not
force the patch, a rejected hunk means the framework moved under it.
EOF
fi
exit "$status"
