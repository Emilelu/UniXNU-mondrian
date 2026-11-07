#!/usr/bin/env bash
# K60 device state machine: never ask the user to power-cycle when a software
# transition is possible.
#
#   k60-device.sh state        print adb | fastboot | none
#   k60-device.sh android      get to Android (from either mode), then poll for adb
#   k60-device.sh bootloader   get to fastboot (from either mode), then poll
#   k60-device.sh boot IMG     boot IMG with fastboot (never flashes)
#
# Transitions:
#   fastboot -> Android   fastboot reboot
#   adb      -> Android   adb reboot (already there: no-op)
#   adb      -> fastboot  adb reboot bootloader
#   fastboot -> fastboot  no-op
# When neither mode answers the board is hung with USB down; only a physical
# power cycle helps, so say that once and stop.
#
# Env: K60_SERIAL (default 6033dbec), ANDROID_TOOLS (default /mnt/d/Android/platform-tools)
set -u

SERIAL="${K60_SERIAL:-6033dbec}"
TOOLS="${ANDROID_TOOLS:-/mnt/d/Android/platform-tools}"
ADB="$TOOLS/adb.exe"
FASTBOOT="$TOOLS/fastboot.exe"
POLL_SECONDS="${POLL_SECONDS:-60}"

die() { echo "k60-device: $*" >&2; exit 1; }

state() {
	if "$FASTBOOT" devices 2>/dev/null | tr -d '\r' | grep -q "^${SERIAL}"; then
		echo fastboot
	elif "$ADB" devices 2>/dev/null | tr -d '\r' | grep -q "^${SERIAL}[[:space:]]*device"; then
		echo adb
	else
		echo none
	fi
}

wait_for() {
	local want="$1" waited=0
	while [ "$waited" -lt "$POLL_SECONDS" ]; do
		[ "$(state)" = "$want" ] && return 0
		sleep 3
		waited=$((waited + 3))
	done
	return 1
}

go_android() {
	case "$(state)" in
	adb)      echo "already in Android"; return 0 ;;
	fastboot) echo "fastboot reboot"; "$FASTBOOT" -s "$SERIAL" reboot >/dev/null 2>&1 ;;
	none)
		echo "no adb, no fastboot: the board is hung with USB down."
		echo "A physical power cycle is the only way out; nothing to script here."
		return 1 ;;
	esac
	wait_for adb || { echo "timed out waiting for Android"; return 1; }
	echo "Android up"
}

go_bootloader() {
	case "$(state)" in
	fastboot) echo "already in fastboot"; return 0 ;;
	adb)      echo "adb reboot bootloader"; "$ADB" -s "$SERIAL" reboot bootloader >/dev/null 2>&1 ;;
	none)
		echo "no adb, no fastboot: the board is hung with USB down."
		echo "A physical power cycle is the only way out; nothing to script here."
		return 1 ;;
	esac
	wait_for fastboot || { echo "timed out waiting for fastboot"; return 1; }
	echo "fastboot up"
}

case "${1:-state}" in
state)      state ;;
android)    go_android ;;
bootloader) go_bootloader ;;
boot)
	[ $# -ge 2 ] || die "boot needs an image path"
	[ -f "$2" ] || die "no such image: $2"
	# fastboot.exe is a Windows binary: it cannot open /mnt/d/... paths.
	image="$2"
	if command -v wslpath >/dev/null 2>&1; then
		image="$(wslpath -w "$2")"
	fi
	go_bootloader || exit 1
	"$FASTBOOT" -s "$SERIAL" boot "$image"
	;;
*) die "unknown command: $1" ;;
esac
