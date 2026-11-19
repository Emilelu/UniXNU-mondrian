#!/usr/bin/env python3
"""Unit tests for scripts/judge-battery.py.

The judge turns 07-DEVICE-CRITERIA.md (C1 subscription, C2 four measured
properties, C3 Android comparison) into a verdict a battery flight can be read
against in seconds.  The cases below pin the two shapes that are easy to
confuse and expensive to confuse: "no lease published" must be INVALID (there
was nothing to measure), while "lease published but the subscription ACK was
rejected" must be FAIL.  A third shape -- one sample line only -- must not be a
failure at all, because sample lines are edge-triggered (K60Battery.cpp:207-208).

Every case also asserts the last line is a TOTAL line (P-204: a judge that does
not print its totals did not run).

Run: python3 scripts/tests/test-judge-battery.py
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
JUDGE = ROOT / "scripts" / "judge-battery.py"

LEASE_OK = "K60Handoff: published authenticated PAS1 epoch=1 bytes=104 flags=15\n"
LEASE_FAIL = (
    "K60ADSP owner stage=1 rc=-1000\n"
    "K60Handoff: PAS1 bring-up/retained ownership failed rc=-1000; no lease published\n"
)
BLOCKED = (
    "K60Battery: blocked rc=-4: no authenticated exclusive PAS1/SMEM/GLINK platform "
    "handoff; no MMIO, FIFO writes or power-source publication\n"
)
CHANNEL_UP = (
    "K60Battery: actual PMIC_RTR_ADSP_APPS channel up; measured sign=1 "
    "subscription-ack=1/16\n"
)
CHANNEL_UP_NO_CONST = (
    "K60Battery: actual PMIC_RTR_ADSP_APPS channel up; measured sign=1 "
    "subscription-ack=0/0\n"
)
CHANNEL_UP_BAD_CONST = (
    "K60Battery: actual PMIC_RTR_ADSP_APPS channel up; measured sign=1 "
    "subscription-ack=2/24\n"
)
# The real shape of the sample line, from K60Battery.cpp:209-214.
def sample(voltage=4333, current=836, soc=(57, 30), temp=(35, 80), external=1,
           charging=1, full=0, subscribed=1, kind="physical source published",
           generations=1, source="usb"):
    origin = f" current-source={source}" if source else ""
    return (
        f"K60Battery: {kind} sample={generations} SOC={soc[0]}.{soc[1]:02d}% "
        f"charge=2865/5000mAh design=5000mAh cycles=120 voltage={voltage}mV "
        f"current={current}mA{origin} temp={temp[0]}.{temp[1]:02d}C external={external} "
        f"charging={charging} full={full} subscribed={subscribed}\n"
    )


def run_judge(log: pathlib.Path, *extra: str):
    proc = subprocess.run(
        [sys.executable, str(JUDGE), "--log", str(log), *extra],
        capture_output=True, text=True)
    out = proc.stdout or ""
    tail = [ln for ln in out.strip().splitlines() if ln.strip()]
    return proc.returncode, out, (tail[-1] if tail else "")


def main() -> int:
    failures = 0
    cases = 0
    tmp = pathlib.Path(tempfile.mkdtemp())

    def write(name: str, text: str) -> pathlib.Path:
        path = tmp / name
        path.write_text(text, encoding="utf-8")
        return path

    def check(label: str, log: pathlib.Path, want_rc: int, want_words, *extra: str):
        nonlocal failures, cases
        cases += 1
        rc, out, last = run_judge(log, *extra)
        problems = []
        if rc != want_rc:
            problems.append(f"rc={rc} want={want_rc}")
        if f"[exit {want_rc}]" in out is False:
            problems.append("verdict line does not carry [exit N]")
        for word in want_words:
            if word not in out:
                problems.append(f"missing {word!r}")
        if not last.startswith("TOTAL: "):
            problems.append(f"last line is not a TOTAL line: {last!r}")
        ok = not problems
        print(f"{'PASS' if ok else 'FAIL'} {label}")
        if not ok:
            failures += 1
            for p in problems:
                print("      " + p)
            for line in out.splitlines():
                print("      " + line)

    # --- 1. a healthy flight: lease, channel up, one qualified sample ------
    healthy = write("healthy.log", LEASE_OK + CHANNEL_UP + sample())
    check("a lease + (1,16) channel up + subscribed=1 sample is PASS", healthy, 0,
          ["C1 订阅成立 : PASS", "C2 四属性可读 : PASS", "TOTAL: 2 PASS / 0 FAIL / 0 INVALID"])

    # --- 1b. the pre-current-source shape still parses -------------------
    legacy = write("legacy.log", LEASE_OK + CHANNEL_UP + sample(source=None))
    check("a sample line without current-source still parses", legacy, 0,
          ["C2 四属性可读 : PASS"])

    # --- 2. no lease: nothing was measurable, so INVALID not FAIL ----------
    blocked = write("blocked.log", LEASE_FAIL + BLOCKED)
    check("blocked rc=-4 with no lease is INVALID, never FAIL", blocked, 2,
          ["battery-judge: INVALID", "C1 订阅成立 : INVALID", "C2 四属性可读 : INVALID"])

    # --- 3. lease is up but the ACK was rejected: a real failure -----------
    sub0 = write("subscribed0.log", LEASE_OK + CHANNEL_UP + sample(subscribed=0))
    check("channel up with subscribed=0 is FAIL on C1", sub0, 1,
          ["battery-judge: FAIL", "C1 订阅成立 : FAIL", "C2 四属性可读 : PASS"])

    # --- 4. a single sample line is not a failure (edge-triggered) ---------
    single = write("single.log", LEASE_OK + CHANNEL_UP + sample())
    check("one sample line alone is not judged a failure", single, 0,
          ["只有 1 行 sample", "C2 四属性可读 : PASS"])

    # --- 5. a property outside the step-eight window is FAIL ---------------
    overvolt = write("overvolt.log", LEASE_OK + CHANNEL_UP + sample(voltage=6200))
    check("voltage above 5000 mV is FAIL on C2", overvolt, 1,
          ["C1 订阅成立 : PASS", "C2 四属性可读 : FAIL", "voltage=6200mV"])
    cold = write("cold.log", LEASE_OK + CHANNEL_UP + sample(temp=(0, 0)))
    check("temperature of 0.00 C is FAIL on C2 (sensor not ready)", cold, 1,
          ["C2 四属性可读 : FAIL", "temp=0.00C"])

    # --- 6. an empty log is INVALID ---------------------------------------
    empty = write("empty.log", "")
    check("an empty log is INVALID (no lease, no sample)", empty, 2,
          ["battery-judge: INVALID", "C1 订阅成立 : INVALID"])

    # --- 7. constants that never reached the kernel -----------------------
    noconst = write("noconst.log", LEASE_OK + CHANNEL_UP_NO_CONST + sample())
    check("subscription-ack=0/0 is INVALID (old image, constant absent)", noconst, 2,
          ["C1 订阅成立 : INVALID", "subscription-ack=0/0"])
    badconst = write("badconst.log", LEASE_OK + CHANNEL_UP_BAD_CONST + sample())
    check("subscription-ack=2/24 is FAIL (constant outside the whitelist)", badconst, 1,
          ["C1 订阅成立 : FAIL", "subscription-ack=2/24"])

    # --- 8. a failure line instead of a sample is FAIL on C2 --------------
    failed = write("failed.log", LEASE_OK + CHANNEL_UP +
                   "K60Battery: no publication sample=3 fresh=2 errors=1 sign=1 "
                   "raw-current=0 raw-temp=0\n")
    check("a failure line with no sample is FAIL on C2", failed, 1,
          ["C2 四属性可读 : FAIL", "no publication sample=3"])

    # --- 9. C3 with Android samples in the window -------------------------
    # 07 section 3.3 requires at least MIN_PAIRS (3) paired samples; a single
    # pair is INVALID by design, so the fixtures below carry three of each.
    triples = write("triples.log", LEASE_OK + CHANNEL_UP
                    + sample(soc=(57, 30), temp=(35, 80))
                    + sample(soc=(57, 40), temp=(35, 85), kind="physical source updated")
                    + sample(soc=(57, 50), temp=(35, 90), kind="physical source updated"))
    # K60 Android reports current_now negative while charging; C3 normalizes
    # that to XNU's positive=charging before comparing sign or magnitude.
    android_ok = write("android-ok.tsv",
                       "# epoch voltage_mv current_ma soc_pct temp_c status\n"
                       "1763000100 4330 -830 57.2 35.7 2\n"
                       "1763000101 4331 -832 57.3 35.8 2\n"
                       "1763000102 4332 -834 57.4 35.9 2\n")
    check("C3 passes when both sides agree inside the window", triples, 0,
          ["C3 Android 同窗口 : PASS", "TOTAL: 3 PASS / 0 FAIL / 0 INVALID"],
          "--android", str(android_ok), "--window-start", "1763000000",
          "--window-end", "1763000200")
    android_far = write("android-far.tsv",
                        "1763000100 4500 -830 57.2 35.7 2\n"
                        "1763000101 4501 -832 57.3 35.8 2\n"
                        "1763000102 4502 -834 57.4 35.9 2\n")
    check("C3 fails when voltage differs by more than 60 mV", triples, 1,
          ["C3 Android 同窗口 : FAIL", "ΔV="],
          "--android", str(android_far), "--window-start", "1763000000",
          "--window-end", "1763000200")
    android_flip = write("android-flip.tsv",
                         "1763000100 4330 830 57.2 35.7 2\n"
                         "1763000101 4331 832 57.3 35.8 2\n"
                         "1763000102 4332 834 57.4 35.9 2\n")
    check("C3 fails when charging current has the opposite sign", triples, 1,
          ["C3 Android 同窗口 : FAIL", "符号相反"],
          "--android", str(android_flip), "--window-start", "1763000000",
          "--window-end", "1763000200")
    android_legacy = write("android-legacy.tsv",
                           "1763000100 4330 830 57.2 35.7 2\n"
                           "1763000101 4331 832 57.3 35.8 2\n"
                           "1763000102 4332 834 57.4 35.9 2\n")
    check("C3 accepts a positive=charging capture with the legacy flag", triples, 0,
          ["C3 Android 同窗口 : PASS", "|ΔI|=6mA/±150mA"],
          "--android", str(android_legacy), "--android-current-sign", "positive",
          "--window-start", "1763000000", "--window-end", "1763000200")
    android_out = write("android-out.tsv",
                        "1763009000 4330 -830 57.2 35.7 2\n"
                        "1763009001 4331 -832 57.3 35.8 2\n"
                        "1763009002 4332 -834 57.4 35.9 2\n")
    check("C3 is INVALID when the Android samples are outside the window", triples, 2,
          ["C3 Android 同窗口 : INVALID"],
          "--android", str(android_out), "--window-start", "1763000000",
          "--window-end", "1763000200")

    # --- 10. C3 without Android input is SKIP, and the headline says so ---
    cases += 1
    rc, out, last = run_judge(healthy)
    ok = (rc == 0 and "C3 Android 同窗口 : SKIP" in out
          and "battery-judge: PASS (C1+C2)" in out and last.startswith("TOTAL: "))
    print(f"{'PASS' if ok else 'FAIL'} C3 without --android is SKIP and the verdict names the scope")
    if not ok:
        failures += 1
        for line in out.splitlines():
            print("      " + line)

    # --- 12. C3 is gated on C1/C2: how far comes after whether -----------
    gated = write("gated.log", LEASE_OK + CHANNEL_UP + sample(subscribed=0))
    check("C3 is not evaluated when C1 fails", gated, 1,
          ["C3 Android 同窗口 : INVALID", "C1/C2 未通过"],
          "--android", str(android_ok), "--window-start", "1763000000",
          "--window-end", "1763000200")

    # --- 13. Android's own dmesg is a usable C3 channel --------------------
    dmesg_fg = (
        "[ {t}] BATTERY_CHG: handle_message: [ADSP] fg_update_status:: "
        "ssoc:100, rsoc:99, raw_soc:9806, vbat:{v}, ibat:{i}, temp:{temp}, ffc:0, "
        "rm:4412, bf:4499, bc:3, fcc_NightVoterC:0, icl_plat:1450\n")
    dmesg_usb = ("[ {t}] BATTERY_CHG: xm_charger_debug_info_print_work: "
                 "usb_present: {p}\n")
    dmesg_ok = write("android-ok.dmesg",
                     dmesg_usb.format(t="6380.100000", p=1)
                     + dmesg_fg.format(t="6380.688186", v=4332, i=-350, temp=286)
                     + dmesg_fg.format(t="6390.215558", v=4333, i=-351, temp=287)
                     + dmesg_fg.format(t="6400.215558", v=4334, i=-352, temp=288))
    dmesg_xnu = write("dmesg-xnu.log", LEASE_OK + CHANNEL_UP
                      + sample(voltage=4332, current=350, soc=(100, 0), temp=(28, 60))
                      + sample(voltage=4333, current=351, soc=(100, 0), temp=(28, 70),
                               kind="physical source updated")
                      + sample(voltage=4334, current=352, soc=(100, 0), temp=(28, 80),
                               kind="physical source updated"))
    check("C3 reads Android dmesg and prints every measured delta", dmesg_xnu, 0,
          ["C3 Android 同窗口 : PASS", "最大差值", "dmesg 相对秒"],
          "--android", str(dmesg_ok), "--window-start", "6380", "--window-end", "6420")

    # --- 14. dmesg has no status field, so the supply line stands in ------
    dmesg_unplugged = write("android-unplugged.dmesg",
                            dmesg_usb.format(t="6380.100000", p=0)
                            + dmesg_fg.format(t="6380.688186", v=4332, i=-350, temp=286)
                            + dmesg_fg.format(t="6390.215558", v=4333, i=-351, temp=287)
                            + dmesg_fg.format(t="6400.215558", v=4334, i=-352, temp=288))
    check("C3 fails when Android says unplugged but XNU says external", dmesg_xnu, 1,
          ["C3 Android 同窗口 : FAIL", "供电状态不一致"],
          "--android", str(dmesg_unplugged), "--window-start", "6380", "--window-end", "6420")

    # --- 15. current is compared only when both sides are in steady state -
    # |I| >= 100 mA on both sides, so the delta line must carry |ΔI| instead of
    # claiming it could not be compared.
    check("C3 compares current when both sides carry a steady load", triples, 0,
          ["C3 Android 同窗口 : PASS", "|ΔI|=6mA/±150mA"],
          "--android", str(android_ok), "--window-start", "1763000000",
          "--window-end", "1763000200")

    # --- 11. a missing log is a usage error, never a verdict --------------
    cases += 1
    proc = subprocess.run([sys.executable, str(JUDGE), "--log", str(tmp / "nope.log")],
                          capture_output=True, text=True)
    ok = proc.returncode == 4 and "[exit" not in (proc.stdout or "")
    print(f"{'PASS' if ok else 'FAIL'} a missing log exits 4 and prints no verdict")
    if not ok:
        failures += 1
        print(f"      rc={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}")

    if failures:
        print(f"TESTS OK 0 cases ({failures} failure(s) of {cases})")
        return 1
    print(f"TESTS OK {cases} cases (0 failure(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
