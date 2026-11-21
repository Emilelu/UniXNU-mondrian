# `native_pmap_user_mappings`：补丁草案（未进 27 series）

> 触发：Lead m00493 ①。本文与 `patches/proposed/9001-osfmk-arm-native-pmap-user-mappings.patch` 一起交；Lead 审完再决定进不进 `patches/xnu-12377/series`。
> 前提：它**不在**我们的 27 系列里——`patches/xnu-12377/series` 101 条条目没有任何 pmap 导出；整个符号在 `E:/hackios/k60-gates/patches/` 下 0 命中。

## 0. 一句话

sheng 27 补丁里 `pmap.c` 的第 10 个 hunk 是一个**只给 GPU 诊断用的导出函数**，与 T0SZ 用户 VA 无关；它在 pristine 12377 上无法原样应用（锚点在别人的组合树里），本文把它重锚成一份独立草案，并写清它真正被需要时的条件。

## 1. 它解决什么

- **语义**：给一个 `ppnum`，数「除 `kernel_pmap` 之外还有哪些 pmap 映射着这一页」，并把第一个的 pmap、VA 和（`MACH_ASSERT` 下）`pmap_procname` 回给调用者。`pvh_lock(pai)` 下遍历 pv 链，跳过 `pvh_ptep_is_iommu()` 的条目。
- **为什么要这个数**：NativeAdreno 的 BO view 只持有物理页、不持引用。释放前若用户任务还映射着该页，`pmap_assert_free` 会在「页在映射中仍被释放」处触发；改成断开映射又会让下一次访问把页重新 fault 进来（页的下一个持有者）。所以释放方必须先问 pmap。
- **谁调用**：**目前没有任何调用者**。sheng 的树只定义、不调用（`grep -rn native_pmap_user_mappings E:/hackios/UniXNU-sheng` 只命中补丁自身两行：声明与定义）；`E:/hackios/k60-gates/patches/` 零命中；t970 与 pong 的 `migration/ipados18/services114-gpu-parity.md:25` 直接写「Darwin24 没有上游可选的 `native_pmap_user_mappings` 诊断导出，因此该诊断后端不可用」。也就是说它是 GPU 诊断后端缺的那块拼图，不是 stage-0 的依赖。

## 2. 为什么它不能跟着 `pmap.c` 整包打

两条独立理由，任一成立都不能把 sheng 的 `pmap.c` 段当一包搬：

1. **锚点不在 pristine 里。** sheng 的 hunk 头是 `@@ -15301,3 +15370,76 @@ pmap_pending_preemption(void)`，上下文最后一行是 `#endif /* SCHED_HYGIENE_DEBUG && (DEBUG || DEVELOPMENT) */`。pristine `E:/hackios/xnu-12377/osfmk/arm/pmap/pmap.c` 只有 15,273 行（`wc -l`），全文没有 `SCHED_HYGIENE_DEBUG`（`grep -n SCHED_HYGIENE_DEBUG pmap.c` 无输出），旧侧行号 15,301 已经越过文件末尾——那段 `#endif` 是 sheng 自己的组合树里由别的补丁加进来的。实测 `git apply --check` 单独打这一 hunk 报 `error: patch failed: osfmk/arm/pmap/pmap.c:15301`。
2. **一个补丁里混了两件不相干的事。** sheng 的 `pmap.c` 段共 10 个 hunk：前 9 个是 T0SZ 的用户 VA 几何（`pmap_pt_attr_4k_user`、`pmap_user_tcr`、`pmap_apply_user_tcr`、`pmap_switch_user_ttb`、`pmap_user_va_bits` …），第 10 个才是这个 GPU 导出。`docs/research/ios27/PLATFORM-BUDGETS.md` §2.2 记的「9/10」就是这件事。整包搬等于把一个**没有调用者的 GPU 诊断函数**焊进平台线的补丁里，将来出问题没人认领。

## 3. 草案做了什么

- 文件：`patches/proposed/9001-osfmk-arm-native-pmap-user-mappings.patch`，单文件 `osfmk/arm/pmap/pmap.c`，`74 insertions(+)`。
- 函数体逐字保留 sheng 的版本，只改锚点与文件头：
  1. 锚点改到 pristine 文件真正的末尾（上下文三行 `\treturn KERN_SUCCESS;` / `}` / `#endif /* DEVELOPMENT || DEBUG */`），于是 `git apply --check` 在 `xnu-12377 ac9718f` 上通过（2026-11-21 实测）；
  2. 去掉对 sheng 组合树 `SCHED_HYGIENE_DEBUG` 段的依赖；
  3. 补丁头写明来源、重锚原因与「未进 series」。
- 依赖符号在 pristine 全部存在，不存在「打了也编不过」的缺口：

| 用到 | 定义处 |
|---|---|
| `pvh_lock` / `pvh_unlock` | `osfmk/arm/pmap/pmap_data.h:317` / `:329` |
| `pvh_test_type` / `pvh_ptep` / `pvh_pve_list` | `pmap_data.h:347` / `:363` / `:380` |
| `pve_get_ptep` / `pve_next` | `pmap_data.h:654` / `:626` |
| `pvh_ptep_is_iommu` / `ptep_get_pmap` / `ptep_get_va` | `pmap_data.h:471` / `:971` / `:1109` |
| `PTE_PER_PVE` / `PT_ENTRY_NULL` / `PV_ENTRY_NULL` | `pmap.h:139` / `pmap.h:129` / `pmap_data.h:108` |
| `pmap_procname[17]` | `pmap.h:413` |
| `strlcpy` | 文件已 `#include <string.h>`（`pmap.c:28`），且本文件已用过两次 |

## 4. 打上之后与 xnekom 的差异

- xnekom-ios27 的 27 树**完全没有**这个符号（`grep -rln 'native_pmap_user_mappings' patches/` 无输出），也没有 T0SZ/pmap 那组补丁——它的 `patches/` 里没有任何 `pmap.c` 改动。
- 因此本草案与 xnekom 无冲突：两边在 `pmap.c` 上没有重叠区域。反过来说，若 xnekom 将来也搬 T0SZ 组，他们同样要处理这个 hunk，这里的重锚定做法可以直接复用。
- 本板侧的差异只是「多一个导出符号」，对链接无影响；进程名那段在 `#if MACH_ASSERT` 内，RELEASE 内核不读 `pmap_procname`。
- 两边真正一致的是 CPU 路径：xnekom `patches/xnu-12377/series:65` 是 0532、`:87` 是 0540、`:91` 是 0541，与本板同序（见 `docs/research/ios27/FORK-DECISION.md` §7）。本草案只补齐 GPU 那一半，不动这条关系。

## 5. 决定与触发

**裁决（Lead，2026-11-21T16:34）**：先不进 series。理由是他给的两条——这个导出没有调用者，而 27 stage-0 的单核路径不经过 `pmap_enter` 的 user 分支。草案留在 `patches/proposed/`，等 F2 有日志证明「需要它」再进。

- 本线自己的依据与之一致：`configs/mondrian_ios27_defconfig` 里 `CONFIG_XNU_NATIVE_ADRENO=n`，没有 BO view 的调用者；`patches/xnu-12377/series` 里也没有实现。
- **触发条件**（任一条成立就把本草案交给 Lead 审进 series）：① GPU 线打开 NativeAdreno BO view 的释放路径、需要「用户还映射着吗」这个判断；② 出现 `pmap_assert_free` 相关 panic 且调用栈指向 BO 释放；③ F2 的日志里出现 `native_pmap_user_mappings` 缺失导致的失败；④ xnekom 或上游先合了这个导出。
- **审查点**：这是新增导出，不改任何既有路径。若只想先拿诊断能力，可以只打这一个补丁，不必连带 T0SZ 组。
- 文件保持可打：`git apply --check` 每次改到它都要重跑（2026-11-21 通过，74 行新增）。文稿里的「待评审」措辞即指本裁决之前的悬置状态，裁决之后按上面四条触发。

## 6. 核对记录（2026-11-21 实测）

| 检查 | 结果 |
|---|---|
| `git apply --check` 于 `xnu-12377 ac9718f` | 通过（`Checking patch osfmk/arm/pmap/pmap.c...`） |
| `git apply --stat` | `1 file changed, 74 insertions(+)` |
| sheng 原 hunk 单独应用 | 失败：锚点 `SCHED_HYGIENE_DEBUG` 不存在（旧侧行号 15,301 > 15,273） |
| 依赖符号 | 上表 13 个全部在 pristine 存在 |
| 编译 | **未做**：`-fsyntax-only` 需要 XNU 完整 include / generated 头与机器配置 defines，只能在 F1 的内核构建里验；本线禁止构建 |
| 运行 | 未做：没有调用者，也没有设备侧触发点 |
