#!/bin/bash
# Offline only: never accesses a device or physical memory.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../.." && pwd)
OUT=${1:?usage: run-k60-handoff-host.sh DURABLE_OUTPUT PRE_0619_XNU_TREE}
XNU=${2:?a supported pre-0619 .cache/xnu-work tree is required}
mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
exec > >(tee "$OUT/host-tests.log") 2>&1
cd "$REPO"
export PYTHONUTF8=1
CFLAGS=(-std=c11 -O1 -Wall -Wextra -Werror -I drivers/PongPower)
cc "${CFLAGS[@]}" scripts/tests/test-k60-handoff-publish.c \
  drivers/PongPower/K60HandoffPublish.c drivers/PongPower/K60HandoffBuild.c \
  drivers/PongPower/K60Smem.c drivers/PongPower/K60BatteryConfig.c -o "$OUT/publish"
"$OUT/publish"
# This legacy fixture includes the two C implementation units directly.
cc "${CFLAGS[@]}" scripts/tests/test-k60-handoff-build.c \
  drivers/PongPower/K60BatteryConfig.c -o "$OUT/builder"
"$OUT/builder"
OWNER_SOURCES=(drivers/PongPower/K60AdspOwner.c drivers/PongPower/K60AdspOwnerStages.c
  drivers/PongPower/K60AdspMdt.c drivers/PongPower/K60Smem.c
  drivers/PongPower/K60HandoffBuild.c drivers/PongPower/K60HandoffPublish.c
  drivers/PongPower/K60BatteryConfig.c)
cc "${CFLAGS[@]}" scripts/tests/test-k60-adsp-owner.c "${OWNER_SOURCES[@]}" -o "$OUT/owner"
"$OUT/owner"
for stage in claim prepare auth build publish; do
  cc "${CFLAGS[@]}" "scripts/tests/test-k60-owner-$stage.c" "${OWNER_SOURCES[@]}" -o "$OUT/owner-$stage"
  "$OUT/owner-$stage"
done
cc "${CFLAGS[@]}" scripts/tests/test-k60-adsp-startup.c drivers/PongPower/K60AdspStartup.c -o "$OUT/startup"
"$OUT/startup" 1
"$OUT/startup" 2
python3 scripts/tests/test-k60-adsp-mdt.py --output "$OUT/mdt" --firmware /mnt/e/k60-work/firmware/adsp
python3 scripts/tests/test-k60-notification-qualification.py
python3 scripts/tests/test-battery-units.py
python3 scripts/tests/test-k60-handoff-integration.py --xnu "$XNU"
SDK=$(cd "$XNU/../fakeroot" && pwd)
FRAMEWORK=$SDK/System/Library/Frameworks/Kernel.framework/Versions/A
clang++ -target arm64-apple-ios16.0 -isysroot "$SDK" -mkernel -ffreestanding \
  -fno-builtin -fno-stack-protector -mgeneral-regs-only -DKERNEL=1 \
  -DKERNEL_PRIVATE=1 -DXNU_KERNEL_PRIVATE=1 -DARM64_BOARD_CONFIG_PONG=1 \
  -I "$FRAMEWORK/Headers" -I "$FRAMEWORK/PrivateHeaders" -I drivers/PongPower \
  -fno-exceptions -fno-rtti -std=gnu++17 -fblocks -Wno-deprecated-declarations \
  -fsyntax-only drivers/PongPower/K60HandoffRuntime.cpp
printf "TESTS OK: arm64 Darwin kernel adapter syntax (not a link)\n"
