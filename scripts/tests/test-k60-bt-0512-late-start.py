#!/usr/bin/env python3
# Static, host-side check for patches/xnu/0512-k60-bt-late-start.patch
# (twin: patches/bt/0006-k60-bt-late-start.patch).
#
# The full Bluetooth ladder is the first code that writes SE/GCC/SMMU registers,
# and every image that ran it during early boot died silently (bt-bisect-h123,
# bt-s4b-20261115c: 0 bytes on the console).  Contrast: h12, which only runs the
# read-only probe, reaches the desktop.  This patch moves the ladder to the
# K60DATA deploy point (pong_bt_late=1) and adds one switch per mechanism
# hypothesis so a single flight can disable exactly one of them.
# The test asserts the patch text, so it runs on the host without a kernel build.
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
XNU_PATCH = ROOT / "patches" / "xnu" / "0512-k60-bt-late-start.patch"
BT_PATCH = ROOT / "patches" / "bt" / "0006-k60-bt-late-start.patch"
SERIES = ROOT / "patches" / "xnu" / "series"
BT_SERIES = ROOT / "patches" / "bt" / "series"

failures = 0
cases = 0


def check(condition, label, detail=""):
    global failures, cases
    cases += 1
    if condition:
        print(f"  ok: {label}")
    else:
        failures += 1
        print(f"  FAIL: {label}" + (f" - {detail}" if detail else ""))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


print("test-k60-bt-0512-late-start")
text = XNU_PATCH.read_text(encoding="utf-8")
check(text.startswith("diff --git a/bsd/dev/qbt_k60.c b/bsd/dev/qbt_k60.c"),
      "0512 patch starts with the qbt_k60.c section")

# 1. Structure: exactly two files, the driver and the Data-mount call site.
sections = text.split("diff --git ")[1:]
paths = [s.split("\n", 1)[0] for s in sections]
check(len(sections) == 2, "patch has two sections", f"found {len(sections)}: {paths}")
check(paths[0] == "a/bsd/dev/qbt_k60.c b/bsd/dev/qbt_k60.c", "section 1 is qbt_k60.c")
check(paths[1] == "a/bsd/kern/kern_exec.c b/bsd/kern/kern_exec.c", "section 2 is kern_exec.c")

# 2. Twin parity (patches/bt/series maps 0006 <-> 0512).
check(BT_PATCH.is_file(), "the patches/bt twin exists")
if BT_PATCH.is_file():
    check(sha256(XNU_PATCH) == sha256(BT_PATCH),
          "patches/bt/0006 is byte-identical to patches/xnu/0512")

# 3. Late start: the worker waits, the deploy point releases it.
check('k60_log(NULL, 1, "late: armed, waiting for the K60DATA deploy point");' in text,
      "the worker announces the armed wait")
check("while (!__atomic_load_n(&k60.late_go, __ATOMIC_ACQUIRE))" in text,
      "the worker spins on late_go with an acquire load")
gate = text.index("late: armed, waiting for the K60DATA deploy point")
power_on = text.index("    int e = k60_bt_power_on();")
check(gate < power_on, "the late gate appears before the power_on call")
check("+void qbt_k60_late_start(void) {" in text, "qbt_k60_late_start is exported")
check("    if (!k60.late_boot || !k60.started) return;" in text,
      "the release is a no-op unless the image asked for late start")
check("extern void qbt_k60_late_start(void);" in sections[1],
      "kern_exec.c declares qbt_k60_late_start")
check("qbt_k60_late_start();" in sections[1], "kern_exec.c calls it")
uilib = sections[1].index("(void)k60_uilib_deploy();")
call = sections[1].index("qbt_k60_late_start();")
check(uilib < call, "the call sits after the uilib deploy in the Data-mount block")

# 4. Boot args: the gate and one switch per mechanism hypothesis.
for arg in ["pong_bt_late", "pong_bt_smmu", "pong_bt_rcg", "pong_bt_noboot"]:
    check(f'PE_parse_boot_argn("{arg}"' in text, f"{arg} is parsed from the boot args")

# 4b. No boot argument means no change: every switch defaults to "off" and
# every branch it adds sits behind its own guard.  P-208 is the same accident
# in another driver - a switch whose default quietly altered the old path.
check("    unsigned late = 0;" in text, "pong_bt_late defaults to 0")
check("    unsigned noboot = 0;" in text, "pong_bt_noboot defaults to 0")
check("    unsigned smmu = 1;" in text and "    unsigned rcg = 1;" in text,
      "pong_bt_smmu and pong_bt_rcg default to 1 (the switches read 'off')")
for field, expr in [
        ("no_smmu", 'PE_parse_boot_argn("pong_bt_smmu", &smmu, sizeof(smmu)) && smmu == 0'),
        ("no_rcg", 'PE_parse_boot_argn("pong_bt_rcg", &rcg, sizeof(rcg)) && rcg == 0'),
        ("no_boot", 'PE_parse_boot_argn("pong_bt_noboot", &noboot, sizeof(noboot)) && noboot != 0'),
        ("late_boot", 'PE_parse_boot_argn("pong_bt_late", &late, sizeof(late)) && late != 0')]:
    check(f"k60.{field} = {expr};" in text,
          f"k60.{field} stays false when its argument is absent")
# The original lines may survive only as removals ('-'); no added or context
# line may carry the unguarded form, or the default path changed.
kept = [line[1:] for line in text.splitlines() if line[:1] in ("+", " ")]
for bare, label in [
        ("        e = k60_smmu_bypass(k60.dma_pa, k60.dma_bytes);",
         "the bare stream-bypass call is gone (only the guarded form remains)"),
        ("    if (!e) e = k60_gcc_set_se_rate(hz);",
         "the bare SE rate call is gone (only the guarded forms remain)"),
        ("        if (!e) e = qbt_boot(k60.core, K60_BT_RUN_BAUD, k60.address);",
         "the bare firmware download is gone (only the guarded forms remain)")]:
    check(bare not in kept, label)
check(" k60.warm_boot = PE_parse_boot_argn(\"k60bt_warm\", &warm, sizeof(warm)) && warm != 0;" in text,
      "the pre-0512 warm-boot default line is untouched")

# 5. The three isolation switches guard exactly the expected lines.
check("e = k60.no_smmu ? 0 : k60_smmu_bypass(k60.dma_pa, k60.dma_bytes);" in text,
      "pong_bt_smmu=0 skips only the stream bypass")
check(text.count("if (!e && !k60.no_rcg) e = k60_gcc_set_se_rate(hz);") == 2,
      "pong_bt_rcg=0 guards both SE rate writes",
      f"found {text.count('if (!e && !k60.no_rcg) e = k60_gcc_set_se_rate(hz);')}")
check("full: qbt_boot skipped (pong_bt_noboot=1)" in text,
      "pong_bt_noboot=1 stops before the firmware download")
check("full: qbt_boot enter" in text, "the firmware download is announced")

# 6. Markers that localise a silent death inside power_on.
check("full: power_on enter" in text, "power_on entry is announced")
check("full: dma buffer and smmu bypass ready" in text,
      "the DMA/SMMU step is announced")
check("full: uart pins parked" in text, "the TLMM pin write is announced")

# 7. Series registration.
series = SERIES.read_text(encoding="utf-8").splitlines()
names = [line.strip() for line in series if line.strip()]
check("0512-k60-bt-late-start.patch" in names, "0512 is in patches/xnu/series")
if "0512-k60-bt-late-start.patch" in names and names:
    # The insertion point is the tail of the 0340 uilib block, and 0610/0614/0616
    # anchor on that same junction.  Landing last keeps every later hunk intact.
    check(names.index("0512-k60-bt-late-start.patch") == len(names) - 1,
          "0512 is the last entry in the series")
bt_series = BT_SERIES.read_text(encoding="utf-8")
check("0006-k60-bt-late-start.patch" in bt_series, "patches/bt/series lists 0006")

print(f"TESTS {'OK' if failures == 0 else 'FAILED'} {cases} case(s) ({failures} failure(s))")
sys.exit(1 if failures else 0)
