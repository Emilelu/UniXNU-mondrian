#!/bin/bash
# Build one arm64e driver object for the iOS 27 tree on Linux.
#
#   scripts/build-k60-driver.sh <Tree> <Component> [Extra build-arm-driver args...]
#
# The framework's build-arm-driver.py defaults to a C record and never passes
# -target, which makes clang fall back to the host triple. This wrapper copies
# the script, applies the three measured changes (see
# docs/research/ios27/DRIVER-COMPILE-RECIPE.md) and runs the copy, so the tree
# itself stays untouched.
set -euo pipefail

TREE=${1:?usage: build-k60-driver.sh <Tree> <Component> [args...]}
COMPONENT=${2:?usage: build-k60-driver.sh <Tree> <Component> [args...]}
shift 2

RECORD=${UNIXNU_DRIVER_RECORD:-build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/IOCommandGate.cpo.json}
PATCHED="$TREE/scripts/.build-k60-driver.generated.py"

python3 - "$TREE/scripts/build-arm-driver.py" "$PATCHED" <<'PY'
import sys
src, dst = sys.argv[1], sys.argv[2]
text = open(src).read()
anchor = "command.extend(['-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',"
assert text.count(anchor) == 1, "the build-arm-driver command assembly changed"
text = text.replace(anchor, "command += ['-target', TRIPLE]\n" + anchor)
text = text.replace("'-Wno-unnecessary-virtual-specifier'",
                    "'-Wno-unnecessary-virtual-specifier', '-Wno-missing-designated-field-initializers'", 1)
open(dst, "w").write(text)
PY

cd "$TREE"
PATH="$TREE/scripts/linux:$PATH" \
UNIXNU_XNU_ARCH=${UNIXNU_XNU_ARCH:-arm64e} \
UNIXNU_IOS_VERSION=${UNIXNU_IOS_VERSION:-27.0} \
UNIXNU_DRIVER_RECORD="$RECORD" \
PYTHONPATH="$TREE/scripts" \
python3 "$PATCHED" "$COMPONENT" "$@"

status=$?
rm -f "$PATCHED"
exit $status
