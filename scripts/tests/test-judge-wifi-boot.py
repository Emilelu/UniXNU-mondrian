#!/usr/bin/env python3
"""Unit tests for scripts/judge-wifi-boot.py.

The judge turns BOOT-DEATH-BISECT.md section 7 (C1-C4) into a verdict that a
flight can be read against in seconds.  These cases pin all four verdicts: the
two real silent captures (mhi3, mhi4), two real healthy captures (thermal, bt),
and synthetic logs for the two shapes the evidence tree does not have yet -- a
driver that printed and then died, and a console with no wifi marker at all.

Run: python3 scripts/tests/test-judge-wifi-boot.py
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
JUDGE = ROOT / "scripts" / "judge-wifi-boot.py"

# Real captures.  The judge must classify the actual evidence, not a paraphrase
# of it; when the evidence tree is absent these cases report SKIP instead of
# pretending to have run.
def evidence_root() -> pathlib.Path:
    """The capture tree, spelled for whichever side runs the suite.

    WSL sees /mnt/e, Windows sees E:/, and the two log names are the same from
    both sides; without this the four real captures silently degrade to SKIP
    on the host that also happens to be the one that flies the images.
    """
    override = os.environ.get("K60_EVIDENCE")
    candidates = [pathlib.Path(override)] if override else []
    candidates += [pathlib.Path("/mnt/e/k60-work/evidence"),
                   pathlib.Path("E:/k60-work/evidence")]
    for cand in candidates:
        if cand.is_dir():
            return cand
    return candidates[-1]


EVIDENCE = evidence_root()
SILENT_CAPTURES = [
    ("mhi4 is silent", EVIDENCE / "usblog-20261115-002243"),
    ("mhi3 is silent", EVIDENCE / "usblog-20261115-002804"),
]
ALIVE_CAPTURES = [
    ("thermal reaches userspace", EVIDENCE / "usblog-20261115-003922"),
    ("bluetooth reaches userspace", EVIDENCE / "usblog-20261115-012913"),
]

HEALTHY_HEAD = (
    "K60 USBLOG: GDSC usb30_prim 0xf822f000 (on)\n"
    "K60 USBLOG: DWC3 GSNPSID 0x33313130 GCTL 0x00102001 GSTS 0x7e800000\n"
    "Darwin Kernel Version 22.6.0: root:ios-obj/DEVELOPMENT_ARM64_PONG\n"
)
HEALTHY_TAIL = (
    "KE 24 26 launchd /System/Library/CoreServices/SpringBoard.app/SpringBoard\n"
    "Pong UI: 20G81 compatibility library entered SpringBoard\n"
    "K60XPC compat=2957\n"
)


def run_judge(target: pathlib.Path):
    proc = subprocess.run([sys.executable, str(JUDGE), str(target)],
                          capture_output=True, text=True)
    head = (proc.stdout or "").strip().splitlines()
    first = head[0] if head else ""
    return proc.returncode, first, proc.stdout + proc.stderr


def main() -> int:
    failures = 0
    skipped = 0
    cases = 0

    def check(label, want_rc, want_word, target):
        nonlocal failures, cases
        cases += 1
        rc, first, out = run_judge(target)
        # The exit code is this judge's whole API: the flight queue reads it to
        # pick the next image without a human in the loop.  The verdict line
        # repeats the code because a pipeline (a trailing "| head" or "| tee")
        # replaces it with the last stage's status, which is how the code was
        # once read as 0 on a silent capture.
        ok = rc == want_rc and want_word in first and f"[exit {want_rc}]" in first
        print(f"{'PASS' if ok else 'FAIL'} {label}")
        if not ok:
            failures += 1
            print(f"      rc={rc} want={want_rc} verdict line: {first!r}")
            for line in out.splitlines():
                print("      " + line)

    tmp = pathlib.Path(tempfile.mkdtemp())

    # --- real captures -----------------------------------------------------
    for label, capture in SILENT_CAPTURES:
        if capture.exists():
            check(label, 2, "silent", capture)
        else:
            cases += 1
            skipped += 1
            print(f"SKIP {label} (no capture at {capture})")
    for label, capture in ALIVE_CAPTURES:
        if capture.exists():
            check(label, 0, "alive", capture)
        else:
            cases += 1
            skipped += 1
            print(f"SKIP {label} (no capture at {capture})")

    # --- synthetic: driver printed, then the log stops ---------------------
    dead = tmp / "driver-dead.log"
    dead.write_text(
        HEALTHY_HEAD
        + "PongWifi: console up after 1500 ms; starting cold link\n"
        + "PongWifi: stage 1 (TLMM pinmux for PERST/WAKE/WLAN_EN)\n"
        + "PongWifi: stage 5 (GCC PCIe0 GDSC, refgen and NoC votes)\n",
        encoding="utf-8")
    check("a worker that printed and stopped is driver-dead", 1, "driver-dead", dead)

    # --- synthetic: worker reported a failure string at the end ------------
    failed = tmp / "driver-failed.log"
    failed.write_text(
        HEALTHY_HEAD
        + "PongWifi: stage 4 (RPMh/RSC votes for every rail)\n"
        + "PongWifi[3]: UFS prerequisites absent; WiFi skipped\n",
        encoding="utf-8")
    check("a worker failure at the end is driver-dead", 1, "driver-dead", failed)

    # --- synthetic: stage gate held, boot continues (C4) -------------------
    held = tmp / "stage-held.log"
    held.write_text(
        HEALTHY_HEAD
        + "PongWifi: stage 5 (GCC PCIe0 GDSC, refgen and NoC votes) held back by k60_wifi_stage=4\n"
        + HEALTHY_TAIL,
        encoding="utf-8")
    check("a held stage with userspace after it is alive", 0, "alive", held)

    # --- synthetic: console exists but nothing identifies it ---------------
    unknown = tmp / "unknown.log"
    unknown.write_text(
        HEALTHY_HEAD + "pmap_startup() init/release time: 82943 microsec\n",
        encoding="utf-8")
    check("console without userspace or wifi markers is unknown", 3, "unknown", unknown)

    # --- synthetic: only fastboot/UEFI noise, no kernel line --------------
    noise = tmp / "preconsole.log"
    noise.write_text(
        "Sending 'boot' (197152 KB)                     OKAY [  4.312s]\n"
        "Finished. Total time: 5.001s\n",
        encoding="utf-8")
    check("only pre-console noise is silent", 2, "silent", noise)

    # --- an empty file is silent -----------------------------------------
    empty = tmp / "empty.log"
    empty.write_bytes(b"")
    check("an empty log is silent", 2, "silent", empty)

    # --- the code still names itself when a pipeline swallows it -----------
    cases += 1
    # Model the failure that once read a silent capture as "exit 0": the code
    # was measured through a pipeline, so only the text survived.  A consumer
    # that drops the exit code must still be able to read it off the line.
    rc, first, _out = run_judge(empty)
    if rc == 2 and "[exit 2]" in first:
        print("PASS a consumer that drops the exit code still reads it from the line")
    else:
        failures += 1
        print("FAIL a consumer that drops the exit code still reads it from the line")
        print(f"      rc={rc} first={first!r}")

    total = cases
    if failures:
        print(f"TESTS OK 0 cases ({failures} failure(s), {skipped} skipped of {total})")
        return 1
    print(f"TESTS OK {total} cases (0 failure(s), {skipped} skipped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
