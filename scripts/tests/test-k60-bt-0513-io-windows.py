#!/usr/bin/env python3
# Static, host-side check for patches/xnu/0513-k60-bt-io-windows.patch
# (twin: patches/bt/0007-k60-bt-io-windows.patch).
#
# bt-d4-late (2026-11-16 05:52) put the first kernel panic of the whole S4
# effort on the console:
#   K60PANICARGS kmem_alloc(0xfffffff3447b1240, 1048576, 0x100021): failed with 3
# 1048576 = 1 MiB, 0x100021 = KMEM_NOFAIL|KMEM_PAGEABLE|KMEM_PERMANENT, and 3 =
# KERN_NO_SPACE.  That flag combination is exactly what io_map() uses for the
# io_submap branch (osfmk/arm/io_map.c:120-129), and io_submap is 8 MiB for the
# whole kernel (:65).  The BT ladder charges 2 MiB (GCC) + 1 MiB (TLMM) + 1 MiB
# (apps SMMU) to it.  This patch moves those three windows to
# ml_io_map_unmappable(), which allocates from kernel_map instead.
# The test asserts the patch text, so it runs on the host without a build.
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
XNU_PATCH = ROOT / "patches" / "xnu" / "0513-k60-bt-io-windows.patch"
BT_PATCH = ROOT / "patches" / "bt" / "0007-k60-bt-io-windows.patch"
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


print("test-k60-bt-0513-io-windows")
text = XNU_PATCH.read_text(encoding="utf-8")
check(text.startswith("diff --git a/bsd/dev/qbt_k60.c b/bsd/dev/qbt_k60.c"),
      "0513 patch starts with the qbt_k60.c section")

# 1. Structure: one file only.  0513 must not touch kern_exec.c - 0512 owns the
# Data-mount junction and 0610/0614/0616 anchor on it.
sections = text.split("diff --git ")[1:]
paths = [s.split("\n", 1)[0] for s in sections]
check(len(sections) == 1, "patch has one section", f"found {len(sections)}: {paths}")
check(paths[0] == "a/bsd/dev/qbt_k60.c b/bsd/dev/qbt_k60.c", "the section is qbt_k60.c")
check("kern_exec.c" not in text, "0513 does not touch kern_exec.c")

# 2. Twin parity (patches/bt/series maps 0007 <-> 0513).
check(BT_PATCH.is_file(), "the patches/bt twin exists")
if BT_PATCH.is_file():
    check(sha256(XNU_PATCH) == sha256(BT_PATCH),
          "patches/bt/0007 is byte-identical to patches/xnu/0513")

# 3. The escape itself.
check("extern vm_offset_t ml_io_map_unmappable(vm_offset_t phys, vm_size_t size," in text,
      "ml_io_map_unmappable is declared for the BSD compilation unit")
check("#define K60_WIMG_IO 0x7u" in text,
      "VM_WIMG_IO is pinned to 0x7 (osfmk/arm/memory_types.h:43)")
check("static int k60_map_big(struct k60_region *r, uint64_t phys, size_t bytes) {" in text,
      "k60_map_big exists")
check("r->va = (volatile uint32_t *)ml_io_map_unmappable((vm_offset_t)phys," in text,
      "k60_map_big uses the unmappable allocator")
check("    if (r->va) return 0;" in text, "k60_map_big keeps the idempotent early return")
check("    return r->va ? 0 : -ENOMEM;" in text, "k60_map_big keeps the error contract")

# 4. Every window of 1 MiB or more goes through it, and nothing smaller does.
big = [
    ("gcc in the ladder", "k60_map_big(&k60.gcc, K60_GCC_BASE, K60_GCC_SIZE)"),
    ("tlmm in the ladder", "k60_map_big(&k60.tlmm, K60_TLMM_BASE, K60_TLMM_SIZE)"),
    ("apps smmu", "k60_map_big(&k60.smmu, K60_APPS_SMMU_BASE, K60_APPS_SMMU_SIZE)"),
    ("gcc in the probe", "k60_map_big(&k60.gcc, K60_GCC_BASE, K60_GCC_SIZE)"),
]
added = [line[1:] for line in text.splitlines() if line[:1] == "+"]
for label, call in big:
    check(any(call in line for line in added), f"{label} uses k60_map_big")
small = ["K60_BT_UART_SIZE", "K60_BT_QUP_WRAPPER_SIZE", "K60_GIC_DIST_SIZE"]
for macro in small:
    check(not any("k60_map_big" in line and macro in line for line in added),
          f"{macro} stays on ml_io_map (it is far below the io_submap budget)")
check("k60_map(&k60.uart, K60_BT_UART_BASE, K60_BT_UART_SIZE)" in text,
      "the uart window still uses k60_map (it is a context line here, so scan the whole diff)")

# 5. Observability: one line right after the mappings, so a silent image can be
# told apart from an image where the change did not take effect.
check('k60_log(NULL, 1, "full: windows mapped, gcc/tlmm/smmu charged to kernel_map");' in text,
      "the ladder announces the new allocator")
log_at = text.index("full: windows mapped, gcc/tlmm/smmu charged to kernel_map")
check(text.index("k60_map(&k60.gic, K60_GIC_DIST_BASE, K60_GIC_DIST_SIZE)") < log_at,
      "the announcement comes after every window is mapped")

# 6. Series wiring.  0513 answers the same panic as main's 0621 from the other
# side, so the two are alternatives, not halves of one fix (the Lead's rule: one
# variable at a time).  Three legal states:
#   d5  - 0621 in the series, 0513 on disk only;
#   d6  - both in the series, 0513 last (the one-variable step past d5);
#   neither - the plain full-ladder recipe, 0513 still on disk.
# What is never legal: 0513 anywhere but last, 0513 without 0512 in front of it.
xnu_series = [l.strip() for l in SERIES.read_text(encoding="utf-8").splitlines() if l.strip()]
in_series = "0513-k60-bt-io-windows.patch" in xnu_series
has_0621 = "0621-k60-io-submap-budget.patch" in xnu_series
if in_series:
    check(xnu_series[-1] == "0513-k60-bt-io-windows.patch",
          "0513 is the last entry in patches/xnu/series")
    check(xnu_series[-2] == "0512-k60-bt-late-start.patch",
          "0512 sits directly before 0513")
    check(has_0621, "the d6 recipe keeps 0621 under 0513 (one variable added)")
else:
    check(XNU_PATCH.is_file(), "0513 stays on disk while the d5 recipe leaves it out")
    check(has_0621, "the d5 recipe is the one that carries 0621")
bt_series = [l.strip() for l in BT_SERIES.read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.startswith("#")]
check(bt_series[-1] == "0007-k60-bt-io-windows.patch", "0007 is the last entry in patches/bt/series")

# 7. The panic it answers is quoted in the patch, so the next reader can find
# the flight without leaving the diff.
check("failed with 3" in text, "the patch records the panic it answers")
check("io_map.c:65" in text, "the patch records the 8 MiB io_submap")
check("io_map.c:120-129" in text, "the patch records where the allocator splits")

print(f"TESTS OK {cases} case(s)" if not failures else f"TESTS FAILED {failures}/{cases}")
sys.exit(1 if failures else 0)
