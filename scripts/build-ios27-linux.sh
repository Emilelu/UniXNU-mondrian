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

# Where the fifteen minutes go. A stage that is slow stays slow until it is
# measured, and "the build feels slow" is not a number (P-290: a claim nothing
# checks is not a finding). Each mark reports its own stage and the total.
T0=$(date +%s)
LAST=$T0
mark() {
	now=$(date +%s)
	printf 'stage %-24s %4ds    total %4ds\n' "$1" "$((now - LAST))" "$((now - T0))"
	LAST=$now
}
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

# Memory geometry costs a second and fails before the kernel build. XNU builds
# the physmap from /chosen/dram-base and dram-size, so an arena that crosses a
# hole between the banks this phone reports boots into nothing (P-231).
python3 "$ROOT/scripts/check-ios27-geometry.py"

sh "$ROOT/scripts/apply-core-patches.sh" "$UNIXNU"
cd "$UNIXNU"
python3 ./unixnu fetch --device "$ROOT"
python3 ./unixnu defconfig mondrian_ios27_defconfig --device "$ROOT"
mark profile-fetch-defconfig
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
#
# Seam 3 (P-301): the ramoops console hooks are compiled unconditionally.
# The first cut guarded them with XNU_PONG_RAMOOPS_CONSOLE and handed the define
# over the same `env` prefix as seam 2, and the define never reached the
# compiler: osfmk/DEVELOPMENT/serial_console.o.json held zero occurrences of it
# while startup.o.json held -DXNU_NATIVE_TRUST_CACHE from the builder's own
# EXTRA_MAKE_ARGS.  The kernel therefore shipped with no console for the third
# time.  The hooks are self-guarding at run time (every write checks
# pong_ramoops_base, which stays NULL until the map succeeds), so the patch now
# compiles them always and there is no switch left to get wrong.
#
# ccache: XNU carries the switch itself (makedefs/MakeInc.def:170 `CCACHE ?=`,
# :175 `KCC = $(CCACHE) $(CC)`), and unixnu/kernel.py:186 passes this shell's
# environment down to the builder, so exporting CCACHE is the whole wiring.
#
# ccache 4.9 refuses any command line with -MJ ("Compiler option -MJ is
# unsupported"), and every XNU compile rule passes -MJ $(@:o=o.json), so plain
# ccache was pure overhead: every call uncacheable, 1394 s against 578 s without.
# scripts/k60-ccache.py strips -MJ, runs the compiler through ccache, and writes
# the same JSON record clang would have written -- the record only has to exist
# (kernel.py:205 uses it to detect a first bootstrap pass), and its `arguments`
# keep what the compiler saw.  Enabled whenever ccache is installed; a value
# preset by the caller still wins.
#
# CCACHE_DIR is pinned to the directory the documentation reads, because
# ccache's default is ~/.cache/ccache and `ccache -s` elsewhere would report 0
# hits for a build that never wrote there.  An exported CCACHE_DIR still wins.
if [ -z "${CCACHE+x}" ] && command -v ccache >/dev/null 2>&1; then
	CCACHE="python3 $ROOT/scripts/k60-ccache.py $(command -v ccache)"
	export CCACHE
	if [ -z "${CCACHE_DIR+x}" ] && [ -d /opt/k60/trees/.ccache ]; then
		CCACHE_DIR=/opt/k60/trees/.ccache
		export CCACHE_DIR
	fi
fi

# Measured 2026-11-22: `unixnu build kernel` costs 271 s and ran on every build,
# because nothing compared the inputs it reads. Same shape as the payload stage
# below: one key over everything the kernel step reads, recorded next to the
# macho that step produced. The device tree is deliberately not in this key --
# the payload stage compiles hardware.dtb, its key carries the tree, and a dts
# edit must rebuild the payload, not the kernel (P-155: a key says "same", a
# timestamp says "recent").
KERNEL_KEY="$BOARD_DIR/kernel/kernel.inputs.sha256"
kernel_key=$(python3 "$ROOT/scripts/ios27-inputs.py" kernel --device "$ROOT" \
	--out "$BOARD_DIR" --unixnu "$UNIXNU")
if [ -z "${K60_FORCE_KERNEL:-}" ] && [ -f "$KERNEL_KEY" ] &&
	[ -f "$BOARD_DIR/kernel/kernel.macho" ] &&
	[ "$(cat "$KERNEL_KEY")" = "$kernel_key" ]; then
	echo "note kernel: reused (inputs unchanged since $kernel_key)"
	mark kernel-reused
else
	env "PongAudioAmp.o_CFLAGS_ADD=-DXNU_PONG_AUDIO=1" \
		python3 ./unixnu build kernel --device "$ROOT" "$@"

	# The collection's `com.apple.kernel` child must carry the collection's own
	# cpusubtype before the loader will look at it. The local clang cannot emit the
	# kernel form of the arm64e label (MachObjectWriter.cpp promotes arm64e to
	# versioned-but-user) and ld64 adopts the object's value, so the label is
	# corrected here, after linking and before the payload copies it. It rewrites
	# one byte of that label and refuses anything else (P-282).  The key is
	# written only after this, so a recorded key always stands for a stamped
	# macho.
	python3 "$ROOT/scripts/k60-fileset-stamp.py" "$BOARD_DIR/kernel/kernel.macho" --apply
	mkdir -p "$(dirname "$KERNEL_KEY")"
	printf '%s\n' "$kernel_key" >"$KERNEL_KEY"
	mark kernel
fi

# The payload step shares 452 s of the build with the kernel and packs the same
# 192 MB again when nothing it reads has moved. Reuse it when the key of those
# inputs is the one recorded next to the image, rebuild it otherwise.
#
# The skip is the whole stage, never a repack: `build payload --kernelcache`
# would not replace a packed kernel at all, only `--kernel` does (P-177), so a
# payload that is stale against the kernel must be rebuilt, not patched. Two
# independent readings keep that honest -- the kernel is inside the key, and
# check-ios27-artifacts.py compares payload.json against kernel.macho.
PAYLOAD_KEY="$BOARD_DIR/payload/payload.inputs.sha256"
payload_key=$(python3 "$ROOT/scripts/ios27-inputs.py" payload --device "$ROOT" \
	--out "$BOARD_DIR" --unique-chip-id "$UNIXNU_UNIQUE_CHIP_ID" \
	--series-fingerprint "$(python3 "$ROOT/scripts/series-fingerprint.py")")
if [ -z "${K60_FORCE_PAYLOAD:-}" ] && [ -f "$PAYLOAD_KEY" ] &&
	[ -f "$BOARD_DIR/payload/payload.img" ] &&
	[ "$(cat "$PAYLOAD_KEY")" = "$payload_key" ]; then
	echo "note payload: reused (inputs unchanged since $payload_key)"
	mark payload-reused
else
	payload_done=
	if [ -z "${K60_NO_FAST_PAYLOAD:-}" ] && [ -f "$BOARD_DIR/payload/payload.json" ]; then
		if python3 "$ROOT/scripts/k60-fast-payload.py" --device "$ROOT" --board "$BOARD_DIR" \
			--kernel "$BOARD_DIR/kernel/kernel.macho"; then
			payload_done=1
			mark payload-fast
		else
			echo "note payload: in-place refresh not possible; falling back to a full pack"
		fi
	fi
	if [ -z "$payload_done" ]; then
		python3 ./unixnu build payload --device "$ROOT" --unique-chip-id "$UNIXNU_UNIQUE_CHIP_ID"
		mark payload
	fi
	mkdir -p "$(dirname "$PAYLOAD_KEY")"
	printf '%s\n' "$payload_key" >"$PAYLOAD_KEY"
fi

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
	# Measured 2026-11-21: the volume costs 519 s of a 975 s build and does not
	# depend on the kernel, the boot-args or the ADT -- only on the firmware
	# inputs. Rebuild it when those change, reuse it otherwise. The key is the
	# inputs themselves, not a timestamp: board.toml, the uefi checkout and its
	# submodules, and the EDK II drop the builder patches (P-155: a timestamp
	# says "recent", a key says "same").
	FW_KEY="$BOARD_DIR/firmware/inputs.sha256"
	FW_FD=$(find "$UNIXNU_UEFI/Build" -name 'SILICIUM_UEFI.fd' 2>/dev/null | head -1 || true)
	fw_key=$( {
		sha256sum "$ROOT/board.toml" | cut -d' ' -f1
		git -C "$UNIXNU_UEFI" rev-parse HEAD
		git -C "$UNIXNU_UEFI" submodule status --recursive | awk '{print $1, $2}'
		ls -1 "$UNIXNU/patches/uefi" 2>/dev/null || true
	} | sha256sum | cut -d' ' -f1 )
	if [ -n "${K60_FORCE_FIRMWARE:-}" ] || [ -z "$FW_FD" ] ||
		[ ! -f "$FW_KEY" ] || [ "$(cat "$FW_KEY")" != "$fw_key" ]; then
		python3 ./unixnu build firmware --device "$ROOT" --uefi "$UNIXNU_UEFI" -j "${UNIXNU_JOBS:-$(nproc)}"
		mkdir -p "$(dirname "$FW_KEY")"
		printf '%s\n' "$fw_key" >"$FW_KEY"
		mark firmware-built
	else
		echo "note firmware: reused the volume at $FW_FD (inputs unchanged since the recorded key)"
		mark firmware-reused
	fi
	# No [bootimg] dtb in board.toml: the appended tree is the hardware DTS the
	# payload step compiled. Packing gzips the payload into the image -- 171 s of
	# the 975 s build -- and it reads nothing but the firmware volume, that
	# payload, the compiled tree and the Mu-Silicium pieces that lay the image
	# out. The fd is resolved the way `unixnu bootimg` resolves it (board.toml
	# [firmware] fd with the DEBUG target), not from a second find (P-155).
	BOOT_KEY="$BOARD_DIR/boot/bootimg.inputs.sha256"
	boot_key=$(python3 "$ROOT/scripts/ios27-inputs.py" bootimg --device "$ROOT" \
		--out "$BOARD_DIR" --uefi "$UNIXNU_UEFI")
	if [ -z "${K60_FORCE_BOOTIMG:-}" ] && [ -f "$BOOT_KEY" ] &&
		[ -f "$BOARD_DIR/boot/boot.img" ] &&
		[ "$(cat "$BOOT_KEY")" = "$boot_key" ]; then
		echo "note bootimg: reused (inputs unchanged since $boot_key)"
		mark bootimg-reused
	else
		boot_done=
		if [ -z "${K60_NO_KERNEL_SWAP:-}" ] && [ -f "$BOARD_DIR/boot/boot.img" ]; then
			if python3 "$ROOT/scripts/k60-kernel-swap.py" --kernel "$BOARD_DIR/kernel/kernel.macho" \
				--payload "$BOARD_DIR/payload/payload.img" --boot "$BOARD_DIR/boot/boot.img" --apply; then
				boot_done=1
				mark bootimg-swapped
			else
				echo "note bootimg: in-place kernel swap not possible; falling back to a full pack"
			fi
		fi
		if [ -z "$boot_done" ]; then
			python3 ./unixnu bootimg --device "$ROOT" --uefi "$UNIXNU_UEFI" \
				--dtb "$BOARD_DIR/device-tree/hardware.dtb"
			mark bootimg-built
		fi
		mkdir -p "$(dirname "$BOOT_KEY")"
		printf '%s\n' "$boot_key" >"$BOOT_KEY"
	fi
	python3 "$ROOT/scripts/check-ios27-artifacts.py"
	mark artifacts
fi

# A root build leaves kernel/payload/boot owned by root with mode 0600, and then the
# registry -- which runs as the developer -- cannot read them. check-kernel-archives.py
# treats "unreadable" as exit 2 on purpose (P-279: cannot judge is not the same as
# passing), so the whole registry turns red for an ownership reason. Hand the outputs
# back to the account that owns the trees.
if [ "$(id -u)" = 0 ] && [ -n "${K60_ARTIFACT_OWNER:-}" ]; then
	for part in kernel payload boot; do
		if [ -d "$BOARD_DIR/$part" ]; then
			chown -R "$K60_ARTIFACT_OWNER": "$BOARD_DIR/$part" || true
		fi
	done
	echo "build-ios27-linux: handed $K60_ARTIFACT_OWNER the outputs under $BOARD_DIR"
fi

echo "build-ios27-linux: artifacts under $UNIXNU_OUT"
