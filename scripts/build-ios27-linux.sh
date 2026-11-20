#!/bin/sh
# Build the iOS 27 arm64e kernel and payload on a Linux host (F1, build-only).
#
# Prerequisites, once per host:
#   sudo python3 UniXNU/scripts/linux/setup-toolchain.py --jobs 12 /opt/unixnu-linux
#   sudo install -m 755 scripts/linux/ditto /usr/local/bin/ditto
#   sudo mv /usr/sbin/sysctl /usr/sbin/sysctl.procps
#   sudo install -m 755 scripts/linux/sysctl /usr/sbin/sysctl
#   sudo install -m 755 scripts/linux/sw_vers /usr/local/bin/sw_vers
#
# The fileset reference builds here without --lto (see board.toml): its two
# LLVM profile-runtime calls are stubbed, and the prelink consumes the result.
#
#   sh scripts/build-ios27-linux.sh [extra unixnu build kernel arguments]
#
# UNIXNU points at the framework checkout (default ../UniXNU next to this repo);
# UNIXNU_OUT at the output root (default $HOME/ios27-out). UNIXNU_UEFI points at
# a staged uefi-mondrian checkout with its submodules; when it is set the script
# also builds the firmware volume and packs boot.img.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
UNIXNU=${UNIXNU:-$ROOT/../UniXNU}
UNIXNU_UNIQUE_CHIP_ID=${UNIXNU_UNIQUE_CHIP_ID:-4d4f4e445249414e}   # synthetic MONDRIAN ECID

if [ ! -f "$UNIXNU/scripts/unixnu/kernel.py" ]; then
	echo "build-ios27-linux: no UniXNU checkout at $UNIXNU (set UNIXNU=...)" >&2
	exit 2
fi

# A WSL session started from Windows can export HOME as a Windows path; the
# build uses it for caches and the toolchain's temporary files.
case "${HOME:-}" in
/*) ;;
*) HOME=$(getent passwd "$(id -u)" | cut -d: -f6); export HOME ;;
esac
UNIXNU_OUT=${UNIXNU_OUT:-$HOME/ios27-out}
export UNIXNU_OUT
BOARD_DIR="$UNIXNU_OUT/mondrian/ios-27.0.1-24A446/mondrian_ios27"

# UniXNU resolves profiles/os/<name> from its own tree; install ours first.
bash "$ROOT/scripts/install-os-profile.sh" "$UNIXNU"

sh "$ROOT/scripts/apply-core-patches.sh" "$UNIXNU"
cd "$UNIXNU"
python3 ./unixnu fetch --device "$ROOT"
python3 ./unixnu defconfig mondrian_ios27_defconfig --device "$ROOT"
# Seam 1 (P-266): K60 carries the conf/files entries for in-tree drivers in a
# hook rather than in a patch, because a hunk cannot survive the tree being
# re-seeded. The builder calls it after .cache/xnu-work exists; all this has to
# do is name it. Left unset when it is not on disk -- a hook that aborted on an
# owner whose sources are not in this tree would make stage 0 unbuildable.
if [ -f "$ROOT/scripts/k60-conf-files-hook.py" ]; then
	K60_CONF_FILES_HOOK="$ROOT/scripts/k60-conf-files-hook.py"
	export K60_CONF_FILES_HOOK
fi

# Seam 2 (P-260): the audio driver wants -DXNU_PONG_AUDIO for its own object
# only. EXTRA_MAKE_ARGS is reset inside the builder, so the define has to arrive
# as a real make variable, and a dotted name cannot be exported by this shell.
env "PongAudioAmp.o_CFLAGS_ADD=-DXNU_PONG_AUDIO=1" \
	python3 ./unixnu build kernel --device "$ROOT" "$@"

# The collection's `com.apple.kernel` child must carry the collection's own
# cpusubtype before the loader will look at it. The local clang cannot emit the
# kernel form of the arm64e label (MachObjectWriter.cpp promotes arm64e to
# versioned-but-user) and ld64 adopts the object's value, so the label is
# corrected here, after linking and before the payload copies it. It rewrites
# one byte of that label and refuses anything else (P-282).
python3 "$ROOT/scripts/k60-fileset-stamp.py" "$BOARD_DIR/kernel/kernel.macho" --apply

python3 ./unixnu build payload --device "$ROOT" --unique-chip-id "$UNIXNU_UNIQUE_CHIP_ID"

if [ -n "${UNIXNU_UEFI:-}" ]; then
	if [ ! -f "$UNIXNU_UEFI/Resources/Scripts/mkbootimg.py" ]; then
		echo "build-ios27-linux: no uefi-mondrian checkout at $UNIXNU_UEFI" >&2
		exit 2
	fi
	# Which DarwinBoot the DSC compiles decides whether the volume can read a 27
	# collection at all -- a different question from the collection's own
	# headers, and today the answer is the vendored copy, which cannot. Report
	# here without --strict: the structural build still has to produce artifacts
	# for the other gates; the flight gate is where this becomes fatal.
	python3 "$ROOT/scripts/check-ios27-firmware.py" --board "$ROOT" \
		--uefi "$UNIXNU_UEFI" \
		--tree "$BOARD_DIR/tree" \
		--edk2 "$UNIXNU/third_party/edk2" || true
	python3 ./unixnu build firmware --device "$ROOT" --uefi "$UNIXNU_UEFI" -j "${UNIXNU_JOBS:-$(nproc)}"
	# No [bootimg] dtb in board.toml: the appended tree is the hardware DTS the
	# payload step compiled.
	python3 ./unixnu bootimg --device "$ROOT" --uefi "$UNIXNU_UEFI" \
		--dtb "$BOARD_DIR/device-tree/hardware.dtb"
	python3 "$ROOT/scripts/check-ios27-artifacts.py"
fi

echo "build-ios27-linux: artifacts under $UNIXNU_OUT"
