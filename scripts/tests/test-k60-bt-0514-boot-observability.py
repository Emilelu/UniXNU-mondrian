#!/usr/bin/env python3
# Static, host-side check for patches/xnu/0514-k60-bt-boot-observability.patch
# (twin: patches/bt/0008-k60-bt-boot-observability.patch).
#
# Why this exists: bt-d5-iomap and bt-d6-iowin both reached the controller
# (QCA controller version 0x12110201, rampatch and NVM served) and then stopped
# without ever printing the "[bluetooth] power=..." line.  qbt_boot() has no
# overall deadline: every TLV segment carries its own 10 s QBT_COMMAND_TIMEOUT,
# so a controller that stops answering makes the loop march through segments
# for hours.  This patch adds stage log lines and one boot budget that ends the
# startup path so the result line always prints.
#
# The boundary is the point of the test: ONLY observation is allowed.  No state
# machine, clock, SMMU or window change may ride along, otherwise a silent
# flight cannot be blamed on the code under test.
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
XNU_PATCH = ROOT / "patches" / "xnu" / "0514-k60-bt-boot-observability.patch"
BT_PATCH = ROOT / "patches" / "bt" / "0008-k60-bt-boot-observability.patch"
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


print("test-k60-bt-0514-boot-observability")
text = XNU_PATCH.read_text(encoding="utf-8")
check(text.startswith("diff --git a/bsd/dev/qbt/btqca.c b/bsd/dev/qbt/btqca.c"),
      "the patch starts with the btqca hunk")

# --- 1. file set -----------------------------------------------------------
files = [line.split(" b/", 1)[1] for line in text.splitlines()
         if line.startswith("diff --git ")]
check(files == ["bsd/dev/qbt/btqca.c", "bsd/dev/qbt/qbt_core.c",
                "bsd/dev/qbt/qbt_internal.h", "bsd/dev/qbt/qbt_linux.c",
                "bsd/dev/qbt_k60.c"],
      "exactly the five observation files are touched", str(files))

# --- 2. the twin is byte identical ----------------------------------------
check(BT_PATCH.exists(), "the patches/bt twin exists")
check(BT_PATCH.exists() and sha256(BT_PATCH) == sha256(XNU_PATCH),
      "the twin is byte identical to the xnu patch")

# --- 3. every added line is observation, not behaviour --------------------
added = [line[1:] for line in text.splitlines() if line.startswith("+") and not line.startswith("+++")]
removed = [line[1:] for line in text.splitlines() if line.startswith("-") and not line.startswith("---")]
check(len(removed) == 1, "exactly one line is replaced (the run() timeout branch)", str(removed))
check(all("k60_map" not in line and "ml_io_map" not in line for line in added),
      "no window mapping is touched")
check(all("k60_gcc_set_se_rate" not in line and "k60_smmu_bypass" not in line for line in added),
      "no clock or SMMU call is touched")
check(all("k60.stage" not in line and "k60.no_smmu" not in line and "k60.no_rcg" not in line
          and "k60.no_boot" not in line and "k60.late_boot" not in line for line in added),
      "no existing switch changes meaning")
check(not any(line.startswith("#define QBT_COMMAND_TIMEOUT") for line in removed),
      "the per-command timeout keeps its value")

# --- 4. the budget exists and is armed only inside qbt_boot() -------------
check("#define QBT_BOOT_BUDGET 90000000000ULL" in text,
      "a 90 s boot budget is defined")
check("uint64_t boot_deadline;" in text, "the qbt struct carries one budget field")
check("q->boot_deadline=q->ops.now_ns(q->ops.context)+QBT_BOOT_BUDGET;" in text,
      "qbt_boot() arms the budget after it resets the context")
check("q->boot_deadline=0;" in text,
      "qbt_boot() disarms the budget before it returns")
check(text.count("q->boot_deadline=0;") == 1,
      "the service phase is left with the old deadline behaviour")
check("if (q->boot_deadline && t >= q->boot_deadline) {" in text,
      "run() checks the budget before the per-command deadline")
check("boot: budget exhausted at op=0x%04x" in text,
      "the budget abort names the opcode it was waiting on")
check("boot: command timeout op=0x%04x" in text,
      "a per-command timeout also names its opcode")

# --- 5. the four stage lines the Lead asked for ---------------------------
for label in ("boot: rampatch done", "boot: nvm done",
              "boot: bdaddr check done", "full: qbt_boot returned e=%d"):
    check(label in text, f"the stage line '{label}' is present")
for label in ("boot: enter speed=%u", "boot: soc version done e=%d",
              "boot: set speed done e=%d", "boot: uart setup done e=%d",
              "boot: set bdaddr done e=%d", "boot: return e=%d baud=%u"):
    check(label in text, f"the step line '{label}' is present")
check("boot: hci reset done" in text, "the hci reset step line is present")

# --- 6. every stage line is level 1 (level <= 3 is what reaches the log) --
stage_lines = [line for line in added if "boot:" in line or "qbt_boot returned" in line]
check(len(stage_lines) >= 11, "at least eleven observation lines are added", str(len(stage_lines)))
check(all(", 1," in line or ",1," in line for line in stage_lines if "qbt_linux_log" in line),
      "every qbt_linux_log stage line uses level 1")

# --- 7. series wiring -----------------------------------------------------
xnu_series = [line.strip() for line in SERIES.read_text(encoding="utf-8").splitlines() if line.strip()]
bt_series = [line.strip() for line in BT_SERIES.read_text(encoding="utf-8").splitlines() if line.strip()]
in_series = "0514-k60-bt-boot-observability.patch" in xnu_series
if in_series:
    check(xnu_series[-1] == "0514-k60-bt-boot-observability.patch",
          "0514 sits at the end of the series")
    check(xnu_series[-2] == "0512-k60-bt-late-start.patch",
          "0514 follows the late-start patch")
else:
    check(XNU_PATCH.exists(), "0514 stays on disk while the recipe leaves it out")
check("0008-k60-bt-boot-observability.patch" in bt_series,
      "the bt series lists the twin")

print()
if failures:
    print(f"TESTS OK {cases - failures} case(s) ({failures} failure(s))")
    sys.exit(1)
print(f"TESTS OK {cases} case(s)")
