#!/usr/bin/env python3
"""Judge one K60 battery bring-up console log against the step-eight criteria.

Why this exists: docs/research/charger/07-DEVICE-CRITERIA.md defines three
criteria (C1 subscription, C2 four measured properties, C3 Android comparison)
that decide whether a battery flight passed.  Two failure shapes look alike in a
~230 KB console log and mean opposite things: "the lease was never published"
(there was nothing to judge: INVALID) and "the lease was published but the
subscription ACK never arrived" (a real failure: FAIL).  Reading that by eye is
error prone exactly when it matters, so this tool reads the log and prints one
line per criterion, every line carrying the log line number that proves it, and
a TOTAL line last (P-204: no TOTAL line means the judge did not run).

Verdicts per criterion:
  PASS     the criterion is proven by evidence in this log
  FAIL     the criterion is contradicted by evidence in this log
  INVALID  the criterion has no usable evidence (missing lease, no sample, ...)
  SKIP     C3 only: no Android-side samples were supplied, so it was not judged

The headline verdict covers every criterion that was evaluated, and names the
skipped ones: PASS without C3 is "C1+C2 passed", not "step eight accepted".

Usage:
    python3 scripts/judge-battery.py --log <console.log|usblog-dir>
    python3 scripts/judge-battery.py <console.log|usblog-dir>
    python3 scripts/judge-battery.py --log <usblog-dir> --android samples.tsv \
        --window-start 1763000000 --window-end 1763001800
    python3 scripts/judge-battery.py --log <usblog-dir> --android dmesg.txt \
        --window-start 6380 --window-end 6420
    python3 scripts/judge-battery.py --log <usblog-dir> --android samples.tsv \
        --android-current-sign positive --window-start 1763000000 \
        --window-end 1763001800

--android accepts either channel of 07 section 3.1, detected by content:
  * a transcribed file, one sample per line:
        <epoch_seconds> <voltage_mv> <current_ma> <soc_percent> <temp_c> <status>
    status: 2 Charging, 3 Discharging, 4 Not charging, 5 Full.
  * Android's own dmesg, matched on the
    "BATTERY_CHG: handle_message: [ADSP] fg_update_status::" lines (ssoc, vbat,
    ibat, temp).  dmesg prints no battery status, so charge state comes from the
    charger driver's usb_present line instead; the current magnitude is still
    normalized and compared, but its sign is not judged because dmesg carries
    no status field.  dmesg has no wall clock either, so the window is dmesg
    relative seconds, not epoch seconds.

K60's Android power_supply reports current_now negative while the pack is
charging (the qcom fuel gauge uses negative=charge, positive=discharge).  The
XNU power source follows Apple's positive=charging convention.  C3 therefore
normalizes Android current to positive=charging by default
(--android-current-sign negative); pass --android-current-sign positive for a
legacy capture that already used Apple's sign convention.

C3 runs only when C1 and C2 both PASS: whether the values exist is judged
before how far they are from Android's, because a distance measured against a
log that never subscribed is a confident number made from nothing.

Exit status: 0 PASS, 1 FAIL, 2 INVALID, 4 usage error (never a verdict).
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

# --- wire strings, copied from the driver (P-204: quote, never paraphrase) ---

# K60HandoffRuntime.cpp:55 and :48; K60Battery.cpp:432 and :276, :209-214.
LEASE_OK_RE = re.compile(
    r"K60Handoff: published authenticated PAS1 epoch=(\d+) bytes=104 flags=15")
LEASE_FAIL_RE = re.compile(
    r"K60Handoff: PAS1 bring-up/retained ownership failed rc=(-?\d+); no lease published")
BLOCKED_RE = re.compile(
    r"K60Battery: blocked rc=(-?\d+): no authenticated exclusive PAS1/SMEM/GLINK platform handoff")
ADOPT_RE = re.compile(
    r"K60Battery: adopting authenticated PAS1 GLINK epoch=(\d+) desc=([0-9a-f]+) "
    r"tx=([0-9a-f]+)/([0-9a-f]+) rx=([0-9a-f]+)/([0-9a-f]+)")
CHANNEL_UP_RE = re.compile(
    r"K60Battery: actual PMIC_RTR_ADSP_APPS channel up; measured sign=(-?\d+) "
    r"subscription-ack=(\d+)/(\d+)")
SAMPLE_RE = re.compile(
    r"K60Battery: (physical source published|physical source updated|physical source refreshed) "
    r"sample=(\d+) SOC=(\d+)\.(\d+)% charge=(\d+)/(\d+)mAh design=(\d+)mAh "
    r"cycles=(\d+) voltage=(\d+)mV current=(-?\d+)mA (?:current-source=[a-z]+ )?temp=(-?\d+)\.(\d+)C "
    r"external=(\d+) charging=(\d+) full=(\d+) subscribed=(\d+)")
# Failure lines that explain why no sample was published (07 section 2.4).
FAILURE_RE = re.compile(
    r"K60Battery: (?:no publication|hardware sample unavailable|measured battery absent|"
    r"physical transport (?:stopped|initialization rejected)|"
    r"GLINK epoch never became ready|source setup rejected|"
    r"captured board config invalid|physical PMIC request timeout)")

# Android's own dmesg channel (07 section 3.1): fg_update_status carries ssoc,
# vbat (mV), ibat (mA) and temp (0.1 C); usb_present comes from the charger
# driver and stands in for the battery status field dmesg does not print.
DMESG_FG_RE = re.compile(
    r"\[\s*(\d+\.\d+)\]\s+BATTERY_CHG: handle_message: \[ADSP\] fg_update_status:: "
    r"ssoc:(-?\d+), rsoc:-?\d+, raw_soc:-?\d+, vbat:(-?\d+), ibat:(-?\d+), "
    r"temp:(-?\d+),")
DMESG_USB_RE = re.compile(
    r"\[\s*(\d+\.\d+)\]\s+BATTERY_CHG: xm_charger_debug_info_print_work: "
    r"usb_present: (-?\d+)")

# --- ranges from 07 section 2.2 (the step-eight window, not the code clamp) ---
VOLTAGE_MV = (3300, 5000)        # 3.3 V .. 5.0 V
CURRENT_MA = (100, 6000)         # |I| 0.1 A .. 6 A; below 100 mA is ADC noise
SOC_HUNDREDTHS = (100, 10000)    # 1.00 % .. 100.00 %
TEMP_HUNDREDTHS = (0, 6000)      # 0.0 C .. 60.0 C; 0.00 本身不算（见下）
# 07 section 2.3: 0.00 C 与「温度传感器未就绪」在日志里不可分，下界必须是严格
# 不等号，否则一条未就绪的读数会被读成合格的 0 C。
TEMP_MIN_EXCLUSIVE = 0

# --- C3 thresholds from 07 section 3.3 (Lead 2026-11-15 23:27) ---
V_TOL_MV = 60
I_TOL_MA = 150
SOC_TOL_HUNDREDTHS = 300         # 3 percentage points
T_TOL_HUNDREDTHS = 300           # 3 C
MIN_PAIRS = 3


def read_lines(path: pathlib.Path):
    """Return (raw bytes, [(lineno, text)]) with lineno 1-based."""
    data = path.read_bytes()
    text = data.decode("utf-8", "replace")
    return data, [(i + 1, ln) for i, ln in enumerate(text.splitlines())]


def parse_samples(lines):
    """Every sample line, with the numbers already converted to base units."""
    samples = []
    for no, ln in lines:
        m = SAMPLE_RE.search(ln)
        if not m:
            continue
        temp_int = int(m.group(11))
        temp_frac = int(m.group(12))
        # "%d.%02u" prints the integer part signed and the fraction unsigned:
        # -3.05 C arrives as temp_int=-3, temp_frac=5.  Sign the whole number.
        sign = -1 if temp_int < 0 else 1
        samples.append({
            "line": no,
            "kind": m.group(1),
            "generations": int(m.group(2)),
            "soc_hundredths": int(m.group(3)) * 100 + int(m.group(4)),
            "charge_mah": int(m.group(5)),
            "full_mah": int(m.group(6)),
            "design_mah": int(m.group(7)),
            "cycles": int(m.group(8)),
            "voltage_mv": int(m.group(9)),
            "current_ma": int(m.group(10)),
            "temp_hundredths": sign * (abs(temp_int) * 100 + temp_frac),
            "external": int(m.group(13)),
            "charging": int(m.group(14)),
            "full": int(m.group(15)),
            "subscribed": int(m.group(16)),
        })
    return samples


def lease_state(lines):
    """Last lease event in the log: ('published'|'failed'|'blocked'|'absent', line, rc)."""
    events = []
    for no, ln in lines:
        m = LEASE_OK_RE.search(ln)
        if m:
            events.append(("published", no, int(m.group(1))))
            continue
        m = LEASE_FAIL_RE.search(ln)
        if m:
            events.append(("failed", no, int(m.group(1))))
            continue
        m = BLOCKED_RE.search(ln)
        if m:
            events.append(("blocked", no, int(m.group(1))))
            continue
    if not events:
        return "absent", None, None
    return events[-1]


def judge_c1(lines, lease, samples):
    """C1: the (1,16) subscription request went out and its ACK was accepted."""
    state, no, rc = lease
    if state != "published":
        why = {
            "failed": f"lease 未发布（K60Handoff rc={rc}, :{no}）→ INVALID，不是 FAIL",
            "blocked": f"lease 未发布（K60Battery blocked rc={rc}, :{no}）→ INVALID，不是 FAIL",
            "absent": "日志里没有 lease 发布行（K60Handoff: published authenticated PAS1 ...）",
        }[state]
        return "INVALID", 0, ([no] if no else []), [why]

    ups = []
    for no_, ln in lines:
        m = CHANNEL_UP_RE.search(ln)
        if m:
            ups.append((no_, int(m.group(1)), int(m.group(2)), int(m.group(3))))
    if not ups:
        return "INVALID", 0, [], [
            "日志里没有 channel up 行：无法证明订阅请求发出（K60Battery.cpp:276）"]

    bad = [u for u in ups if (u[2], u[3]) != (1, 16)]
    if bad and all((u[2], u[3]) == (0, 0) for u in bad):
        return "INVALID", 0, [bad[0][0]], [
            "subscription-ack=0/0：生成器没写常量或飞的是旧镜像，订阅静默关闭——本张镜像测不到 C1"]
    if bad:
        no_, _sign, t, b = bad[0]
        return "FAIL", 0, [no_], [
            f"subscription-ack={t}/{b} 不是 (1,16)（:{no_}）：配置常量错，k60_battmgr_init 的"
            "白名单之外的值会被拒绝（K60Battmgr.c:47-56）"]

    sign_zero = [u[0] for u in ups if u[1] == 0]
    if sign_zero:
        return "FAIL", 0, sign_zero[:3], [
            "measured sign=0：充电电流极性未定，k60_battmgr_sample() 会直接返回 0"
            "（K60Battmgr.c:216），后面不会有合格 sample 行"]

    last_up = ups[-1][0]
    after = [s for s in samples if s["line"] > last_up]
    if not after:
        return "INVALID", 0, [last_up], [
            "channel up 之后没有 sample 行：订阅 ACK 是否被接受无法证明"
            "（subscribed 只在 sample 行尾打印）"]
    subscribed = [s for s in after if s["subscribed"] == 1]
    if subscribed:
        return "PASS", 1, [last_up, subscribed[0]["line"]], [
            f"ACK 被接受（subscribed=1，:{subscribed[0]['line']}）；"
            "07 的 ≤10 s 窗口离线不可测（IOLog 行没有时间戳），这里只按行序判"]
    return "FAIL", 0, [last_up, after[0]["line"]], [
        f"sample 行 subscribed=0（:{after[0]['line']}）：ACK 未被接受，"
        "type/bytes/result 与 (1,16,全 0) 不符（K60Battmgr.c:162-171）"]


def judge_c2(lines, lease, samples):
    """C2: at least one sample line carries four properties inside the window."""
    state, no, rc = lease
    if state != "published":
        return "INVALID", 0, ([no] if no else []), [
            f"lease 未发布（{state} rc={rc}）：没有测量可判"]

    if not samples:
        fails = [(n, ln) for n, ln in lines if FAILURE_RE.search(ln)]
        if fails:
            n, ln = fails[0]
            return "FAIL", 0, [n], [
                "没有 sample 行，驱动打了失败行：" + ln.strip()[:180]]
        return "INVALID", 0, [], [
            "日志里没有 sample 行，也没有失败行：这份采集没跑到电池路径"]

    qualified, rejected = [], []
    for s in samples:
        bad = []
        if not VOLTAGE_MV[0] <= s["voltage_mv"] <= VOLTAGE_MV[1]:
            bad.append(f"voltage={s['voltage_mv']}mV 不在 {VOLTAGE_MV[0]}-{VOLTAGE_MV[1]}mV")
        if not SOC_HUNDREDTHS[0] <= s["soc_hundredths"] <= SOC_HUNDREDTHS[1]:
            bad.append(f"SOC={s['soc_hundredths'] / 100:.2f}% 不在 1.00-100.00%")
        if not TEMP_MIN_EXCLUSIVE < s["temp_hundredths"] <= TEMP_HUNDREDTHS[1]:
            bad.append(f"temp={s['temp_hundredths'] / 100:.2f}C 不在 (0.0, 60.0]C"
                       "（0.00 与传感器未就绪不可分）")
        # 07 section 3.2 rule 4: a current below 100 mA is only meaningful in a
        # steady charging/discharging window; an idle sample (not charging) is
        # not a current failure.
        if s["charging"] == 0 and abs(s["current_ma"]) < CURRENT_MA[0]:
            pass
        elif not CURRENT_MA[0] <= abs(s["current_ma"]) <= CURRENT_MA[1]:
            bad.append(f"current={s['current_ma']}mA 的 |I| 不在 {CURRENT_MA[0]}-{CURRENT_MA[1]}mA")
        if bad:
            rejected.append((s, bad))
        else:
            qualified.append(s)

    if qualified:
        notes = []
        first = qualified[0]
        notes.append(
            f"首帧 {first['kind']}（:{first['line']}）：voltage={first['voltage_mv']}mV "
            f"current={first['current_ma']}mA SOC={first['soc_hundredths'] / 100:.2f}% "
            f"temp={first['temp_hundredths'] / 100:.2f}C")
        if len(qualified) == 1:
            notes.append("只有 1 行 sample：sample 行是边沿触发（K60Battery.cpp:207-208），"
                         "稳态插电只有首帧，不因行数少判失败")
        return "PASS", len(qualified), [s["line"] for s in qualified[:3]], notes

    s, fields = rejected[0]
    return "FAIL", 0, [s["line"]], [
        "四属性不合格（:{}）：{}".format(s["line"], "；".join(fields))]


def parse_android_tsv(text: str):
    """The transcribed channel: six fields per line (07 section 3.1)."""
    rows = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.replace(",", " ").split()
        if len(parts) < 6:
            raise ValueError(f"Android sample needs 6 fields: {raw!r}")
        rows.append({
            "t": float(parts[0]),
            "voltage_mv": int(float(parts[1])),
            "current_ma": int(float(parts[2])),
            "soc_hundredths": int(round(float(parts[3]) * 100)),
            "temp_hundredths": int(round(float(parts[4]) * 100)),
            "status": int(float(parts[5])),
            "external": None,
        })
    return rows


def parse_android_dmesg(text: str):
    """Android's own dmesg: fg_update_status carries the same four quantities.

    Units differ from sysfs (2026-11-14 capture): vbat is already mV, ibat is
    mA, temp is 0.1 C, ssoc is percent.  Two fields are absent and are stated in
    the notes instead of guessed: there is no battery status, so charge state
    comes from the charger driver's own usb_present line (forward filled), and
    there is no wall clock, so the window is dmesg relative seconds.
    """
    usb = [(float(m.group(1)), int(m.group(2)))
           for m in DMESG_USB_RE.finditer(text)]
    rows = []
    for m in DMESG_FG_RE.finditer(text):
        t = float(m.group(1))
        external = None
        for mark_t, mark_v in usb:
            if mark_t <= t:
                external = mark_v
            else:
                break
        rows.append({
            "t": t,
            "voltage_mv": int(m.group(3)),
            "current_ma": int(m.group(4)),
            "soc_hundredths": int(m.group(2)) * 100,
            "temp_hundredths": int(m.group(5)) * 10,
            "status": None,
            "external": external,
        })
    return rows


def parse_android(path: pathlib.Path):
    """(rows, source) with source 'tsv' or 'dmesg', detected by content."""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if DMESG_FG_RE.search(text):
        rows, source = parse_android_dmesg(text), "dmesg"
    else:
        rows, source = parse_android_tsv(text), "tsv"
    rows.sort(key=lambda r: r["t"])
    return rows, source


def judge_c3(android_path, window, samples, c1_verdict, c2_verdict,
             current_sign="negative"):
    """C3: how far the XNU samples are from Android's, same window.

    Order matters: whether the values exist (C1, C2) is judged first, and only
    then how far they are.  Judging the distance against a log that never
    subscribed produces confident numbers from nothing.
    """
    if c1_verdict != "PASS" or c2_verdict != "PASS":
        return "INVALID", 0, [], [
            f"C1/C2 未通过（C1 {c1_verdict}、C2 {c2_verdict}）：先判有没有，再判差多少"]
    if android_path is None:
        return "SKIP", 0, [], [
            "未提供 --android：C3 需要两侧同时刻样本，本张镜像单独飞不能判"]
    if window is None:
        return "INVALID", 0, [], [
            "提供了 --android 但没给 --window-start/--window-end："
            "IOLog 行没有时间戳，配对时刻只能靠采集窗口"]
    start, end = window
    try:
        rows, source = parse_android(android_path)
    except (OSError, ValueError) as exc:
        return "INVALID", 0, [], [f"Android 样本文件不可用：{exc}"]

    inside = [r for r in rows if start <= r["t"] <= end]
    unit = "dmesg 相对秒" if source == "dmesg" else "epoch 秒"
    # K60 Android reports current_now negative while charging; XNU follows
    # Apple's positive=charging.  Normalize before comparing either sign or
    # magnitude, and keep the raw value for the evidence line.
    sign = -1 if current_sign == "negative" else 1
    if len(inside) < MIN_PAIRS or len(samples) < MIN_PAIRS:
        return "INVALID", 0, [], [
            f"有效对不足：窗口内 Android {len(inside)} 条、XNU {len(samples)} 条，"
            f"需要 ≥{MIN_PAIRS} 对（凑不满判 INVALID，不判 FAIL）"]

    pairs = list(zip(samples, inside))
    valid = 0
    violations = []
    worst = {"v": 0, "i": 0, "soc": 0, "t": 0}
    current_pairs = 0
    for s, r in pairs:
        xnu_charge_state = s["charging"] == 1 or s["full"] == 1
        if r["status"] is not None:
            if xnu_charge_state != (r["status"] in (2, 5)):
                violations.append(
                    f":{s['line']} 充电状态不一致（XNU charging={s['charging']} "
                    f"full={s['full']} vs Android status={r['status']}）")
                continue
        elif r["external"] is not None and bool(r["external"]) != bool(s["external"]):
            violations.append(
                f":{s['line']} 供电状态不一致（XNU external={s['external']} vs "
                f"Android usb_present={r['external']}；dmesg 无 status 字段，用供电代替充电状态）")
            continue
        android_current = r["current_ma"] * sign
        dv = s["voltage_mv"] - r["voltage_mv"]
        dsoc = s["soc_hundredths"] - r["soc_hundredths"]
        dt = s["temp_hundredths"] - r["temp_hundredths"]
        di = s["current_ma"] - android_current
        worst["v"] = max(worst["v"], abs(dv))
        worst["soc"] = max(worst["soc"], abs(dsoc))
        worst["t"] = max(worst["t"], abs(dt))
        bad = []
        if abs(dv) > V_TOL_MV:
            bad.append(f"ΔV={dv}mV/±{V_TOL_MV}mV")
        if abs(dsoc) > SOC_TOL_HUNDREDTHS:
            bad.append(f"ΔSOC={dsoc / 100:+.2f}pp/±{SOC_TOL_HUNDREDTHS / 100:g}pp")
        if abs(dt) > T_TOL_HUNDREDTHS:
            bad.append(f"ΔT={dt / 100:+.2f}C/±{T_TOL_HUNDREDTHS / 100:g}C")
        if (xnu_charge_state and abs(s["current_ma"]) >= CURRENT_MA[0]
                and abs(android_current) >= CURRENT_MA[0]):
            if r["status"] is not None and (s["current_ma"] > 0) != (android_current > 0):
                violations.append(
                    f":{s['line']} 充电时两侧电流符号相反（XNU {s['current_ma']}mA vs "
                    f"Android 原始 {r['current_ma']}mA，归一化 {android_current}mA）")
                continue
            current_pairs += 1
            worst["i"] = max(worst["i"], abs(di))
            if abs(di) > I_TOL_MA:
                bad.append(f"ΔI={di}mA/±{I_TOL_MA}mA")
        if bad:
            violations.append(f":{s['line']} " + "、".join(bad))
        else:
            valid += 1

    deltas = (f"最大差值（{len(pairs)} 对，窗口按 {unit}）："
              f"|ΔV|={worst['v']}mV/±{V_TOL_MV}mV、"
              f"|ΔSOC|={worst['soc'] / 100:.2f}pp/±{SOC_TOL_HUNDREDTHS / 100:g}pp、"
              f"|ΔT|={worst['t'] / 100:.2f}C/±{T_TOL_HUNDREDTHS / 100:g}C")
    if current_pairs:
        deltas += f"、|ΔI|={worst['i']}mA/±{I_TOL_MA}mA"
    else:
        deltas += "、|ΔI| 未比（两侧没有同时 ≥100 mA 的稳态窗口）"
    if source == "dmesg":
        convention = "negative（负值=充电）" if sign < 0 else "positive（正值=充电）"
        deltas += ("；输入是 Android dmesg：无 status 字段，用 usb_present 代替充电状态，"
                   f"电流按 {convention} 归一化后比较幅值，符号不校验")
    elif sign < 0:
        deltas += "；Android 电流按 negative 约定归一化（负值=充电）"

    if violations:
        evidence = [int(v.split(":")[1].split(" ")[0]) for v in violations[:3]]
        return "FAIL", valid, evidence, ["越界/不一致：" + v for v in violations[:5]] + [deltas]
    if valid < MIN_PAIRS:
        return "INVALID", valid, [], [
            f"只有 {valid} 对落在阈值内，需要 ≥{MIN_PAIRS} 对", deltas]
    return "PASS", valid, [s["line"] for s, _ in pairs[:3]], [
        f"{valid} 对全部在阈值内（±{V_TOL_MV}mV / ±{I_TOL_MA}mA / "
        f"±{SOC_TOL_HUNDREDTHS / 100:g}pp / ±{T_TOL_HUNDREDTHS / 100:g}C）", deltas]


def resolve_log(target: pathlib.Path):
    """Accept a console.log or a usblog capture directory."""
    if target.is_dir():
        candidate = target / "console.log"
        return candidate if candidate.is_file() else None
    return target if target.is_file() else None


class _ArgumentParser(argparse.ArgumentParser):
    """argparse exits 2 for a usage error, but 2 means INVALID here.

    A typo in a flag would then be indistinguishable from "the capture carried
    nothing to judge", which is the one distinction this exit table exists for.
    """

    def error(self, message):
        self.print_usage(sys.stderr)
        print("%s: error: %s" % (self.prog, message), file=sys.stderr)
        raise SystemExit(4)

def main() -> int:
    ap = _ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log", nargs="?", type=pathlib.Path,
                    help="console.log path, or a usblog directory containing console.log")
    ap.add_argument("--log", dest="log_opt", type=pathlib.Path, help="same as the positional argument")
    ap.add_argument("--android", type=pathlib.Path, default=None,
                    help="Android side: transcribed TSV ('<epoch_s> <voltage_mv> "
                         "<current_ma> <soc_pct> <temp_c> <status>') or an Android "
                         "dmesg with fg_update_status lines")
    ap.add_argument("--android-current-sign", choices=("negative", "positive"),
                    default="negative",
                    help="Android current_now convention: negative=charging (K60 "
                         "default) or positive=charging (legacy captures)")
    ap.add_argument("--window-start", type=float, default=None, help="capture window start, epoch seconds")
    ap.add_argument("--window-end", type=float, default=None, help="capture window end, epoch seconds")
    args = ap.parse_args()

    target = args.log_opt or args.log
    if target is None:
        print("usage: judge-battery.py --log <console.log|usblog-dir> "
              "[--android samples.tsv --window-start S --window-end S]", file=sys.stderr)
        return 4
    log = resolve_log(target)
    if log is None:
        print(f"battery-judge: no console.log at {target} -- INVALID, not a usage error", file=sys.stderr)
        return 2

    data, lines = read_lines(log)
    samples = parse_samples(lines)
    lease = lease_state(lines)
    window = None
    if args.window_start is not None and args.window_end is not None:
        window = (args.window_start, args.window_end)

    c1 = judge_c1(lines, lease, samples)
    c2 = judge_c2(lines, lease, samples)
    results = [
        ("C1 订阅成立", c1),
        ("C2 四属性可读", c2),
        ("C3 Android 同窗口", judge_c3(args.android, window, samples, c1[0], c2[0],
                                      args.android_current_sign)),
    ]
    evaluated = [v for _name, (v, _h, _e, _n) in results if v != "SKIP"]
    if "FAIL" in evaluated:
        verdict, code = "FAIL", 1
    elif "INVALID" in evaluated:
        verdict, code = "INVALID", 2
    else:
        verdict, code = "PASS", 0
    skipped = [name for name, (v, _h, _e, _n) in results if v == "SKIP"]

    scope = "C1+C2" if skipped else "C1+C2+C3"
    print(f"battery-judge: {verdict} ({scope}) ({log.name}, {len(data)} bytes on disk) [exit {code}]")
    for name, (v, hits, evidence, notes) in results:
        where = ", ".join(f":{n}" for n in evidence) if evidence else "无"
        print(f"{name} : {v} (命中 {hits} 次, 证据 {where})")
        for note in notes:
            print("  - " + note)
    if skipped:
        print("  - 未评估：" + "、".join(skipped) + "（C3 需要 --android 与采集窗口）")
    print(f"TOTAL: {evaluated.count('PASS')} PASS / {evaluated.count('FAIL')} FAIL / "
          f"{evaluated.count('INVALID')} INVALID")
    return code


if __name__ == "__main__":
    sys.exit(main())
