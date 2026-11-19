#!/usr/bin/env python3
"""Run the negative-sample table of 07-DEVICE-CRITERIA.md section 6.

Why this exists: the judge (scripts/judge-battery.py) is the only thing between a
231 KB console log and a PASS/FAIL sentence, and every rule in it was added in
response to a specific misreading.  A future edit that quietly turns "lease never
published" back into FAIL, or lets a 0.00 C sample through, would not fail any
existing test -- those tests pin the shapes somebody thought of.  This table pins
the shapes that were actually met in the field, one row per misreading, and it is
cheap to run: one command, a table, a TOTAL line.

Each row names a criterion, a sample, the verdict that sample must produce, and
why the sample is a negative.  Rows marked "real" point at a capture in the
evidence tree; rows marked "synthetic" are minimal logs built here, and the
comment says which real shape they reproduce.  The evidence tree today has 535
console.log captures and not one of them carries a channel up line, so the C1/C2
FAIL shapes have no real capture yet -- the table says so instead of pretending.

Run: python3 scripts/tests/test-judge-battery-negatives.py
     K60_EVIDENCE=/path/to/evidence python3 scripts/tests/test-judge-battery-negatives.py
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
JUDGE = ROOT / "scripts" / "judge-battery.py"

CRITERIA = ("C1 订阅成立", "C2 四属性可读", "C3 Android 同窗口")


def evidence_root() -> pathlib.Path:
    """The capture tree, spelled for whichever side runs this suite."""
    override = os.environ.get("K60_EVIDENCE")
    candidates = [pathlib.Path(override)] if override else []
    candidates += [pathlib.Path("/mnt/e/k60-work/evidence"),
                   pathlib.Path("E:/k60-work/evidence")]
    for cand in candidates:
        if cand.is_dir():
            return cand
    return candidates[-1]


EVIDENCE = evidence_root()

# --- wire strings, copied from the driver (P-204: quote, never paraphrase) ---
LEASE_OK = ("K60Handoff: published authenticated PAS1 epoch=3 bytes=104 flags=15\n")
CHANNEL_UP = ("K60Battery: actual PMIC_RTR_ADSP_APPS channel up; measured sign=1 "
              "subscription-ack=1/16\n")
CHANNEL_UP_NO_CONST = ("K60Battery: actual PMIC_RTR_ADSP_APPS channel up; measured sign=1 "
                       "subscription-ack=0/0\n")
CHANNEL_UP_BAD_CONST = ("K60Battery: actual PMIC_RTR_ADSP_APPS channel up; measured sign=1 "
                        "subscription-ack=2/24\n")


def sample(voltage=4333, current=836, soc=(57, 30), temp=(35, 80), external=1,
           charging=1, full=0, subscribed=1, kind="physical source published"):
    """The real shape of the sample line, from K60Battery.cpp:209-214."""
    return (
        f"K60Battery: {kind} sample=1 SOC={soc[0]}.{soc[1]:02d}% "
        f"charge=2865/5000mAh design=5000mAh cycles=120 voltage={voltage}mV "
        f"current={current}mA temp={temp[0]}.{temp[1]:02d}C external={external} "
        f"charging={charging} full={full} subscribed={subscribed}\n")


def run_judge(path: pathlib.Path, *extra: str):
    proc = subprocess.run([sys.executable, str(JUDGE), "--log", str(path), *extra],
                          capture_output=True, text=True)
    verdicts = {}
    for line in (proc.stdout or "").splitlines():
        for name in CRITERIA:
            if line.startswith(name + " : "):
                verdicts[name] = line.split(" : ", 1)[1].split(" ", 1)[0]
    return proc.returncode, verdicts, (proc.stdout or "")


def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp())

    def write(name: str, text: str) -> pathlib.Path:
        path = tmp / name
        path.write_text(text, encoding="utf-8")
        return path

    triples = write("triples.log", LEASE_OK + CHANNEL_UP
                    + sample(soc=(57, 30), temp=(35, 80))
                    + sample(soc=(57, 40), temp=(35, 85), kind="physical source updated")
                    + sample(soc=(57, 50), temp=(35, 90), kind="physical source updated"))
    tsv_ok = write("android-ok.tsv",
                   "1763000100 4330 830 57.2 35.7 2\n"
                   "1763000101 4331 832 57.3 35.8 2\n"
                   "1763000102 4332 834 57.4 35.9 2\n")
    tsv_far = write("android-far.tsv",
                    "1763000100 4500 830 57.2 35.7 2\n"
                    "1763000101 4501 832 57.3 35.8 2\n"
                    "1763000102 4502 834 57.4 35.9 2\n")
    window = ("--window-start", "1763000000", "--window-end", "1763000200")
    # The synthetic TSV uses Apple's positive=charging sign, the same as the
    # XNU sample line above; the judge defaults to K60 Android's
    # negative=charging convention (773452af), so say so explicitly here.
    window_positive = window + ("--android-current-sign", "positive")

    # (criterion, label, kind, log path, extra args, expected verdict, expected rc,
    #  what the row defends)
    rows = [
        ("C1 订阅成立", "usblog-20261115-223916 (lease failed rc=-1000)", "real",
         EVIDENCE / "usblog-20261115-223916", (), "INVALID", 2,
         "lease 未发布是 INVALID，不是 FAIL：没有测量可判"),
        ("C1 订阅成立", "usblog-20261116-015128 (blocked rc=-4)", "real",
         EVIDENCE / "usblog-20261116-015128", (), "INVALID", 2,
         "K60Battery: blocked 同理：缺前置，不是回归"),
        ("C1 订阅成立", "subscription-ack=0/0", "synthetic",
         write("noconst.log", LEASE_OK + CHANNEL_UP_NO_CONST + sample()), (), "INVALID", 2,
         "常量没写进内核＝本张镜像测不到，判 FAIL 会误读成代码回归"),
        ("C1 订阅成立", "subscription-ack=2/24", "synthetic",
         write("badconst.log", LEASE_OK + CHANNEL_UP_BAD_CONST + sample()), (), "FAIL", 1,
         "白名单外的常量是真的错，必须 FAIL"),
        ("C1 订阅成立", "subscribed=0 after (1,16)", "synthetic",
         write("sub0.log", LEASE_OK + CHANNEL_UP + sample(subscribed=0)), (), "FAIL", 1,
         "channel up 行是配置常量，不是回包证据（P-212）"),
        ("C2 四属性可读", "usblog-20261116-015128 (blocked rc=-4)", "real",
         EVIDENCE / "usblog-20261116-015128", (), "INVALID", 2,
         "blocked 时没有 sample，也不能拿失败行当四属性"),
        ("C2 四属性可读", "no publication line", "synthetic",
         write("nopub.log", LEASE_OK + CHANNEL_UP +
               "K60Battery: no publication sample=3 fresh=2 errors=1 sign=1 "
               "raw-current=0 raw-temp=0\n"), (), "FAIL", 1,
         "驱动打了失败行＝真的失败，不是缺证据"),
        ("C2 四属性可读", "voltage=6200mV", "synthetic",
         write("overvolt.log", LEASE_OK + CHANNEL_UP + sample(voltage=6200)), (), "FAIL", 1,
         "越界读数必须 FAIL，不能被「有 sample 就算过」吞掉"),
        ("C2 四属性可读", "temp=0.00C", "synthetic",
         write("cold.log", LEASE_OK + CHANNEL_UP + sample(temp=(0, 0))), (), "FAIL", 1,
         "0.00 与传感器未就绪不可分，下界取开区间 (0,60]"),
        ("C3 Android 同窗口", "usblog-20261116-015128 + dmesg", "real",
         EVIDENCE / "usblog-20261116-015128",
         ("--android", str(EVIDENCE / "wifi-trial" / "dmesg-android-20261114.txt"),
          "--window-start", "6380", "--window-end", "6420"), "INVALID", 2,
         "C1/C2 未过时不评估 C3：先判有没有，再判差多少"),
        ("C3 Android 同窗口", "3 pairs inside tolerance", "synthetic",
         triples, ("--android", str(tsv_ok)) + window_positive, "PASS", 0,
         "阈值内必须 PASS，并打印每个量的最大差值"),
        ("C3 Android 同窗口", "3 pairs, voltage off by 170 mV", "synthetic",
         triples, ("--android", str(tsv_far)) + window_positive, "FAIL", 1,
         "系统性电压差必须 FAIL，不能只报一个数字"),
        ("C3 Android 同窗口", "no --android", "synthetic",
         triples, (), "SKIP", 0,
         "没给 Android 侧就是 SKIP，headline 要写 C1+C2 而不是全过"),
    ]

    failures = 0
    print("判据 / 负样本 / 期望 / 实际 / 结果")
    for crit, label, kind, log, extra, want, want_rc, why in rows:
        if kind == "real" and not pathlib.Path(log).is_dir():
            print(f"{crit} / {label} / {want} / SKIP (证据树不存在) / SKIP")
            continue
        if kind == "real" and not (pathlib.Path(log) / "console.log").is_file():
            print(f"{crit} / {label} / {want} / SKIP (无 console.log) / SKIP")
            continue
        rc, verdicts, out = run_judge(pathlib.Path(log), *extra)
        got = verdicts.get(crit, "?")
        ok = got == want and rc == want_rc
        if not ok:
            failures += 1
        print(f"{crit} / {label} / {want} / {got} (exit {rc}, 期望 {want_rc}) / "
              f"{'OK' if ok else 'MISMATCH'}")
        if not ok:
            for line in out.splitlines():
                print("      " + line)
            print(f"      这一行防的是：{why}")
    print(f"NEGATIVES: {len(rows)} rows, {len(rows) - failures} ok, {failures} mismatch")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
