#!/usr/bin/env bash
# ============================================================================
# route-a-18: build the darwin24 (xnu-11417.140.69 / iOS 18.7.10) kernel for
# the pong SM8475 board on a Linux host.
#
# First working version: 2026-10-31, artifact
#   mach.development.pong.unstripped.noctf  20,847,560 B
#   sha256 57b01c6476e3398d2f7a18bc9e096db18f41eed1012bf146ffd64879ff1ac024
#
# What had to be solved, in order (each was a hard failure before):
#   1. tree layout          pong expects refer/ipados18/<name> checkouts
#   2. aggregate patch      patches/xnu-ipados18/0001-pong-darwin24.patch
#   3. MACHINE_CONFIG       darwin24 whitelists PONG (not BCM2837)
#   4. PLATFORM=iPhoneOS    otherwise "Unsupported PLATFORM <path>"
#   5. availability.pl      AvailabilityVersions-143.7 into the fakeroot
#   6. fakeroot SDK         libplatform headers + libdispatch os/* via unifdef
#   7. libcc_kext.a         must be BUILT for this LLVM, not borrowed: the
#                           profile runtime is what supplies the
#                           ___-prefixed PGO symbols OSKext.cpp needs
#   8. LD_KERNEL_ARCHIVES   firehose + local support archive
#   9. LD_KERNEL_LIBS       libcc_kext.a
#
# Usage: bash build-darwin24-linux.sh [--clean]
# ============================================================================
set -uo pipefail

PONG=/home/emilelu/hackios/UniXNU-pong
TREE=/tmp/k60build/out/route-a18/Pong-iPadOS18-native
WORK=$TREE/.cache/xnu-work
FAKEROOT=$TREE/.cache/fakeroot
LOGS=/tmp/k60build/out/route-a18/logs
FEEDS=/tmp/k60build/out/feeds
TOOLCHAIN=/opt/unixnu-linux
CLT=$TOOLCHAIN/CommandLineTools/usr
XCT=$TOOLCHAIN/XcodeDefault.xctoolchain/usr
SUPPORT=$TREE/build/route-a18-support/libRouteA18Support.a
mkdir -p "$LOGS"

export PATH="$CLT/bin:$TOOLCHAIN/bin:$TOOLCHAIN/llvm/bin:$PATH"
export LC_ALL=C PLATFORM=iPhoneOS JOBS=8
export CLT_PREFIX="$CLT" XCTOOLCHAIN_PREFIX="$XCT"
export XNU_TOOLCHAIN_BIN="$CLT/bin $XCT/bin"
export HOST_CC="$CLT/bin/xnu-host-cc"
export MIGCOM="$CLT/libexec/migcom"
export UNIXNU_SDKROOT="$FAKEROOT" UNIXNU_SDK_VERSION=18.0
export CROSS_CLANG="$TOOLCHAIN/llvm/bin/clang"
export DARWIN_TRIPLE=arm64-apple-ios18.0
export CROSS_EXTRA_FLAGS="-mllvm -disable-atexit-based-global-dtor-lowering"
export CCC_OVERRIDE_OPTIONS='# +-Wno-missing-designated-field-initializers +-Wno-unused-but-set-global'
export XNU_DARWIN=24.6.0 XNU_VERSION=11417.140.69
export MEMORY_SIZE=$(( $(getconf _PHYS_PAGES) * $(getconf PAGE_SIZE) ))
export SYSCTL_HW_PHYSICALCPU=$(nproc) SYSCTL_HW_LOGICALCPU=$(nproc)

step() { printf '\n===== %s =====\n' "$1"; }

step "1. xnu-work"
if [ ! -d "$WORK/.git" ]; then
  git clone --quiet --shared --no-checkout "$FEEDS/xnu-11417" "$WORK"
fi
git -C "$WORK" checkout --quiet 43a90889846e00bfb5cf1d255cdc0a701a1e05a4

step "2. darwin24 aggregate patch"
PATCH=$PONG/patches/xnu-ipados18/0001-pong-darwin24.patch
if git -C "$WORK" apply --reverse --check "$PATCH" >/dev/null 2>&1; then
  echo "already applied"
else
  git -C "$WORK" apply "$PATCH" || exit 1
fi

step "3. reference checkouts (libplatform / libdispatch / AvailabilityVersions)"
for spec in libplatform:libplatform-349.140.6 libdispatch:libdispatch-1521.140.2; do
  name=${spec%%:*}; tag=${spec##*:}
  if [ ! -d "$TREE/refer/ipados18/$name/.git" ]; then
    git clone --quiet --depth 1 --branch "$tag" \
      "https://github.com/apple-oss-distributions/$name.git" "$FEEDS/$name-darwin24"
    git clone --quiet --shared "$FEEDS/$name-darwin24" "$TREE/refer/ipados18/$name"
  fi
done

step "4. availability.pl (symbol aliasing needs it before installhdrs)"
if [ ! -x "$FAKEROOT/usr/local/libexec/availability.pl" ]; then
  [ -d "$FEEDS/AvailabilityVersions-143.7/.git" ] || \
    git clone --quiet --depth 1 --branch AvailabilityVersions-143.7 \
      https://github.com/apple-oss-distributions/AvailabilityVersions.git \
      "$FEEDS/AvailabilityVersions-143.7"
  make -C "$FEEDS/AvailabilityVersions-143.7" install -j8 \
    OBJROOT="$TREE/build/availability" SYMROOT="$TREE/build/availability" \
    DSTROOT="$FAKEROOT" > "$LOGS/availability.log" 2>&1 || exit 1
fi

step "5. fakeroot SDK headers"
python3 /mnt/c/Users/Emilelu/Documents/deepseek-harness/default-workspace/k60-work/route-a18-fakeroot.py || exit 1

step "6. installhdrs"
if [ ! -f "$FAKEROOT/.xnu-$XNU_VERSION-headers" ]; then
  make -C "$WORK" installhdrs SDKROOT=macosx ARCH_CONFIGS=ARM64 \
    MACHINE_CONFIGS=PONG KERNEL_CONFIGS=DEVELOPMENT \
    RC_DARWIN_KERNEL_VERSION=$XNU_DARWIN RC_ProjectSourceVersion=$XNU_VERSION \
    MAKEJOBS=-j8 OBJROOT="$TREE/build/xnu/obj" SYMROOT="$TREE/build/xnu/sym" \
    DSTROOT="$FAKEROOT" > "$LOGS/installhdrs.log" 2>&1 || {
      tail -30 "$LOGS/installhdrs.log"; exit 1; }
  touch "$FAKEROOT/.xnu-$XNU_VERSION-headers"
fi

step "7. libcc_kext.a (profile runtime, must be built for this LLVM)"
if [ ! -f "$FAKEROOT/usr/local/lib/kernel/libcc_kext.a" ]; then
  python3 "$TREE/scripts/linux/prepare-xnu.py" libs || exit 1
fi

step "8. local link support (pong_ramoops_diagnostic_write)"
if [ ! -f "$SUPPORT" ]; then
  python3 /mnt/c/Users/Emilelu/Documents/deepseek-harness/default-workspace/k60-work/route-a18-ramoops2.py || exit 1
fi

step "9. build + link"
make -C "$WORK" build SDKROOT=iphoneos ARCH_CONFIGS=ARM64 \
  MACHINE_CONFIGS=PONG KERNEL_CONFIGS=DEVELOPMENT \
  ARCH_STRING_FOR_CURRENT_MACHINE_CONFIG=arm64 \
  LARGE_MEMORY_DEFINE=-UARM_LARGE_MEMORY \
  ARM64_LINK_ADDR=0xfffffff007004000 ARM64_PLKSEG_ADDR=0xfffffff004004000 \
  DEPLOYMENT_TARGET_FLAGS="-miphoneos-version-min=18.0 -DXNU_TARGET_OS_IOS" \
  DEPLOYMENT_LINKER_FLAGS="-Wl,-ios_version_min,18.0" \
  RC_DARWIN_KERNEL_VERSION=$XNU_DARWIN RC_ProjectSourceVersion=$XNU_VERSION \
  BUILD_LTO=0 BUILD_STATIC_LINK=0 BUILD_DSYM=0 BOUND_CHECKS=0 BUILD_WERROR=0 \
  MAKEJOBS=-j8 \
  LD_KERNEL_ARCHIVES="-L$FAKEROOT/usr/local/lib/kernel -lfirehose_kernel -Wl,-force_load,$SUPPORT" \
  LD_KERNEL_LIBS="$FAKEROOT/usr/local/lib/kernel/libcc_kext.a" \
  OBJROOT="$TREE/build/xnu/ios-obj" SYMROOT="$TREE/build/xnu/ios-sym" \
  DSTROOT="$TREE/build/xnu/ios-dst" > "$LOGS/build.log" 2>&1
rc=$?
if [ $rc -ne 0 ]; then
  echo "BUILD FAILED; undefined symbols:"
  grep -A2 'Undefined symbols' -m1 "$LOGS/build.log"
  grep '^  "' "$LOGS/build.log" | head -20
  exit 1
fi

art=$TREE/build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/mach.development.pong.unstripped.noctf
step "DONE"
ls -la "$art"
sha256sum "$art"
