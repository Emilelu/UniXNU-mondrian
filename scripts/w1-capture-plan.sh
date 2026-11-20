#!/usr/bin/env bash
# Print, never execute, the one read-only capture that settles W1.
#
# Running this printer has no device side effects.  It emits a host-side shell
# plan; the adb commands in that plan are for Lead to run with a device.
set -eu

cat <<'PLAN'
#!/usr/bin/env bash
# W1 LUN read-only capture plan.
# EXPECT = field and range; IF = next step when it does not hold.
# Never writes a block device, never mounts, never runs fastboot.
set -u
CAP="${K60_W1_CAPTURE_DIR:-/mnt/e/k60-work/evidence/w1-lun-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$CAP"
printf 'capture=%s\n' "$CAP"

# LEG A1: resolve modemst1 to its block node.
# EXPECT: one /dev/block/sdX[N] path; RANGE: X a-z, N digits.
# IF: empty -> write PENDING and still run Leg B; do not guess sdf.
adb shell readlink -f /dev/block/by-name/modemst1 | tr -d '\r' | tee "$CAP/modemst1-node.txt"
PART="$(cat "$CAP/modemst1-node.txt")"
if [ -z "$PART" ]; then
  printf 'PENDING Leg A: no modemst1 block node; do not guess sdf.\n' >> "$CAP/PENDING.txt"
else
  # LEG A2: strip the partition digits to get the parent disk.
  # EXPECT: /dev/block/sdf or /dev/block/sda; RANGE: no trailing digits.
  SDF="$(printf '%s' "$PART" | sed 's/[0-9]*$//')"
  printf '%s\n' "$SDF" | tee "$CAP/sdf.txt"

  # LEG A3: resolve the SCSI device and keep the H:C:T:L tail.
  # EXPECT: one path ending H:C:T:L; RANGE: L=0..31, T=0, C=0.
  # IF: no /device or malformed tail -> PENDING; the sd letter is not a LUN.
  adb shell "readlink -f /sys/class/block/$SDF/device" | tr -d '\r' | tee "$CAP/device-link.txt"
  HCTL="$(basename "$(cat "$CAP/device-link.txt")")"
  printf '%s\n' "$HCTL" | tee "$CAP/hctl.txt"

  # LEG A4: independent kernel view of the same target.
  # EXPECT: Host: scsiH Channel: 0 Id: 0 Lun: L; L must equal A3's fourth field.
  # IF: no matching line -> FAIL; the capture is inconsistent, recapture.
  adb shell cat /proc/scsi/scsi | tr -d '\r' | tee "$CAP/proc-scsi-scsi.txt"
fi

# LEG B1: find a UFS bsg character device.
# EXPECT: /dev/bsg/* or /dev/ufs-bsg*; RANGE: one char device.
# IF: none -> PENDING Leg B (no bsg), not a contradiction.
adb shell 'ls -l /dev/bsg /dev/ufs-bsg* 2>/dev/null' | tee "$CAP/bsg-nodes.txt"
BSG="$(adb shell 'ls -1 /dev/bsg/* /dev/ufs-bsg* 2>/dev/null | head -n 1' | tr -d '\r')"
printf '%s\n' "$BSG" | tee "$CAP/bsg.txt"

# LEG B2: find the UFS query tool.
# EXPECT: an absolute path; RANGE: ufs-tool or ufs-utils.
# IF: none -> PENDING Leg B; sg_inq cannot replace UPIU QUERY.
UFS_TOOL="$(adb shell 'command -v ufs-tool || command -v ufs-utils || true' | tr -d '\r')"
printf '%s\n' "$UFS_TOOL" | tee "$CAP/ufs-tool.txt"

# LEG B3: read Unit Descriptor IDN 0x02, index 5, selector 0.
# EXPECT: rc=0 and a binary file of at least 5 bytes.
# RANGE: byte0 bLength >=5; byte1=0x02; byte2=0x05; byte3=0x01; byte4=0..2.
# IF: EACCES -> retry once via adb root only if the build allows it; else PENDING.
if [ -n "$BSG" ] && [ -n "$UFS_TOOL" ]; then
  adb shell "$UFS_TOOL desc -t 2 -i 5 -s 0 -r -D /data/local/tmp/unit-desc-L5.bin -p $BSG"
  adb pull /data/local/tmp/unit-desc-L5.bin "$CAP/unit-desc-L5.bin"
  od -An -tx1 -N16 "$CAP/unit-desc-L5.bin" | tee "$CAP/unit-desc-head.txt"
else
  printf 'PENDING Leg B: no bsg or no ufs-tool/ufs-utils; record the gap, do not substitute sg_inq.\n' >> "$CAP/PENDING.txt"
fi

# LEG C: identity only; this cannot settle W1.
# EXPECT: VPD 0x83 identity; RANGE: any; no standard SCSI VPD page reports UFS LUN.
# IF: sg_inq absent -> skip; it is not Leg B evidence.
adb shell 'command -v sg_inq >/dev/null && sg_inq -p 0x83 "$(readlink -f /dev/block/by-name/modemst1)" || true' | tee "$CAP/vpd-83.txt"

# Judge: 0 PASS, 2 PENDING, 1 FAIL.
# IF: 2 -> attach the missing-leg note; IF: 1 -> recapture, do not edit bytes.
REPO="${K60_REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
python3 "$REPO/scripts/check-w1-lun-evidence.py" "$CAP" --expect-lun 5; RC=$?
printf 'judge_rc=%s\n' "$RC"

# AUTOCHECK: local files only; no adb and no device access in this step.
# It composes the W1 judge with the W2 console/full-block judges when present.
# Set K60_CONSOLE=<log> for W2 headers and K60_EFS_BLOCKS="1=... 2=..." for
# full 4096-byte blocks. Missing families print SKIP, not a fake PASS.
AUTO=()
[ -s "$CAP/device-link.txt" ] && AUTO+=(--leg-a "$CAP/device-link.txt")
[ -s "$CAP/unit-desc-L5.bin" ] && AUTO+=(--leg-b "$CAP/unit-desc-L5.bin")
[ -s "$CAP/README.txt" ] && AUTO+=(--readme "$CAP/README.txt")
[ -s "$CAP/proc-scsi-scsi.txt" ] && AUTO+=(--proc "$CAP/proc-scsi-scsi.txt")
if [ -n "${K60_CONSOLE:-}" ]; then AUTO+=(--console "$K60_CONSOLE"); fi
for pair in ${K60_EFS_BLOCKS:-}; do AUTO+=(--efs-block "$pair"); done
if [ ${#AUTO[@]} -eq 0 ]; then
  printf 'bundle_rc=2 (no local capture files)\n'
  BRC=2
else
  python3 "$REPO/scripts/check-capture-bundle.py" "${AUTO[@]}"; BRC=$?
fi
printf 'bundle_rc=%s\n' "$BRC"
if [ "$RC" -ne 0 ]; then exit "$RC"; fi
exit "$BRC"
PLAN

printf '%s\n' 'run on a device with adb root; Lead runs this, not the lane'
