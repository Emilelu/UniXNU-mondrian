#!/usr/bin/env python3
# Static, host-side check for patches/xnu/0515-k60-bt-tlv-counters.patch
# (twin: patches/bt/0009-k60-bt-tlv-counters.patch).
#
# Why this exists: d7 printed "boot: budget exhausted at op=0xfc00 waiting=1"
# twice and never printed a single "boot: command timeout".  A 10 s per-command
# timeout that never fires means no segment actually hung; the 90 s boot budget
# simply ran out while the NVM download kept walking one segment at a time.
# Nobody could tell whether that walk is slow-but-correct or spent at the edge
# of each 10 s deadline, because the TLV counters qbt.h already maintains were
# never printed.  This patch prints them per segment and once at the end.
#
# The boundary is the point of the test: ONLY observation is allowed.  No state
# machine, budget, segment size, download mode, clock, SMMU or window change may
# ride along, otherwise the rate measurement cannot be trusted.
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
XNU_PATCH = ROOT / "patches" / "xnu" / "0515-k60-bt-tlv-counters.patch"
BT_PATCH = ROOT / "patches" / "bt" / "0009-k60-bt-tlv-counters.patch"
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


print("test-k60-bt-0515-tlv-counters")
text = XNU_PATCH.read_text(encoding="utf-8")
check(text.startswith("diff --git a/bsd/dev/qbt/btqca.c b/bsd/dev/qbt/btqca.c"),
      "the patch starts with the btqca hunk")

# --- 1. file set -----------------------------------------------------------
files = [line.split(" b/", 1)[1] for line in text.splitlines()
         if line.startswith("diff --git ")]
check(files == ["bsd/dev/qbt/btqca.c", "bsd/dev/qbt_k60.c"],
      "exactly the two observation files are touched", str(files))

# --- 2. the twin is byte identical ----------------------------------------
check(BT_PATCH.exists(), "the patches/bt twin exists")
check(BT_PATCH.exists() and sha256(BT_PATCH) == sha256(XNU_PATCH),
      "the twin is byte identical to the xnu patch")

added = [line[1:] for line in text.splitlines()
         if line.startswith("+") and not line.startswith("+++")]
removed = [line[1:] for line in text.splitlines()
           if line.startswith("-") and not line.startswith("---")]

# --- 3. the three observations Lead asked for ------------------------------
joined = "\n".join(added)
check('"tlv seg i=%u size=%d dt_ms=%u e=%d sent=%llu acks=%llu"' in joined,
      "each segment prints index, size, elapsed ms, error and both counters")
check('"tlv done type=%d segs=%u sent=%llu acks=%llu final=%llu ret=%d"' in joined,
      "the download prints one summary line before it leaves")
check("tlv_sent=%llu tlv_acks=%llu tlv_final=%llu" in joined,
      "the power= result line carries the three TLV counters")
check("unsigned segs = 0;" in joined, "a segment counter is added")
check("qbt_get_stats(" in joined, "the counters come from qbt_get_stats()")

# --- 4. only the two call sites are rewritten ------------------------------
allowed_removed = [
    "\t\tret = qca_tlv_send_segment(hdev, segsize, segment,",
    "\t\t\t\t\t   config->dnld_mode, soc_type);",
    '    printf("[bluetooth] power=%u result=%d baud=%u firmware=%s\\n",',
    "           enabled, error, info.baud, info.firmware);",
]
check(sorted(removed) == sorted(allowed_removed),
      "only the send call and the result printf are rewritten", str(removed))

# --- 5. the measurement cannot change behaviour ----------------------------
for banned in ("QBT_BOOT_BUDGET", "QBT_COMMAND_TIMEOUT", "MAX_SIZE_PER_TLV_SEGMENT",
               "dnld_type", "k60_map", "ml_io_map", "board.toml",
               "pong_bt_", "k60_gcc_set_se_rate", "k60_smmu_bypass"):
    check(not any(banned in line for line in added),
          f"no added line mentions {banned}")

# --- 6. every new log line is level 1 (level <= 3 reaches the console) -----
log_added = [line for line in added if "qbt_linux_log(" in line]
check(len(log_added) == 2, "exactly two log calls are added", str(len(log_added)))
check(all("qbt_linux_log(hdev->q, 1," in line for line in log_added),
      "both log calls use level 1")

# --- 7. the segment log is emitted after the send, not before -------------
def first(predicate):
    return next(i for i, line in enumerate(added) if predicate(line))


i_send = first(lambda line: "ret = qca_tlv_send_segment(hdev, segsize, segment," in line)
i_stats = first(lambda line: "qbt_get_stats(hdev->q, &stats);" in line)
i_log = first(lambda line: '"tlv seg i=%u' in line)
i_inc = first(lambda line: "segs++;" in line)
check(i_send < i_stats < i_log < i_inc,
      "send, then counters, then the log line, then the counter bump",
      str([i_send, i_stats, i_log, i_inc]))
check([line.strip() for line in added if "qca_tlv_send_segment(" in line or "config->dnld_mode, soc_type" in line]
      == [line.strip() for line in removed if "qca_tlv_send_segment(" in line or "config->dnld_mode, soc_type" in line],
      "the download call keeps its arguments and only moves inside a block")

# --- 8. series wiring -----------------------------------------------------
xnu_series = [line.strip() for line in SERIES.read_text(encoding="utf-8").splitlines() if line.strip()]
bt_series = [line.strip() for line in BT_SERIES.read_text(encoding="utf-8").splitlines() if line.strip()]
check("0515-k60-bt-tlv-counters.patch" in xnu_series,
      "the xnu series lists 0515")
if "0515-k60-bt-tlv-counters.patch" in xnu_series:
    at = xnu_series.index("0515-k60-bt-tlv-counters.patch")
    check(at == len(xnu_series) - 1, "0515 sits at the end of the series")
    check(xnu_series[at - 1] == "0514-k60-bt-boot-observability.patch",
          "0515 follows the boot observability patch")
check("0009-k60-bt-tlv-counters.patch" in bt_series,
      "the bt series lists the twin")

print()
if failures:
    print(f"TESTS OK {cases - failures} case(s) ({failures} failure(s))")
    sys.exit(1)
print(f"TESTS OK {cases} case(s)")
