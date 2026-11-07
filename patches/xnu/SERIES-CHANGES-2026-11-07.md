# SERIES-CHANGES-2026-11-07 — GPU scanout + K60 touch 补丁启用记录

> 范围：`patches/xnu/*.patch` 与 `patches/xnu/series`。未改 `userland/`、`drivers/`、`scripts/`、`docs/`。
> 目的：一次构建同时带上 Pong/Adreno GPU scanout 与 K60 Goodix 触摸。所有验证使用 `git apply --check`，**未使用 fuzz**。

## 1. 基准树

- 源码版本：`1b191cb58250d0705d8a51287127505aa4bc0789`（xnu-8796.141.3）。
- 测试树：`/opt/k60/trees/k60build/out-baseline/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work` 的临时副本（原树只读访问，未改动）。
- 说明：干净的 xnu-8796.141.3 源码本身没有 `iokit/Kernel/MiniIOMobileFramebuffer.cpp`、`MiniIOSurface.cpp`——它们由 `zzzzzzzzzzzzzzzzzzz-pong-hackios-ui-foundation.patch` 创建。因此 GPU/touch 补丁只能在“series 前序补丁已应用”的树（xnu-work）上做 `git apply --check`；这也是实际构建时的 apply 状态。

## 2. 补丁改动

### 2.1 `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-gpu-scanout.patch`

- **hunk 2（patch 第 14 行，`@@ -386,6 +390,8 @@`）**：按 `0210-k60-display-native-canvas.patch` 的 `k60PanelNative()` 结构重排。`pong_scanout_initialize(...)` 仍插在 `fPanelWidth/fPanelHeight/fRowBytes = vinfo...` 之后；其后的上下文从 pong 原版的三行（`fWidth = gFBWidth ? ...` / `fHeight = ...` / `if (gFBScale ...`）改为 K60 的：
  - `if (k60PanelNative()) {`
  - `/* The panel's own grid: see the contract at the top of the file. */`
  - `if ((gFBWidth != 0 && gFBWidth != K60_PANEL_WIDTH) ||`
- **hunk 5（patch 第 66 行）**：原 `@@ -905,7 +937,7 @@` 在实际 K60 树上无法匹配（原上下文有 `PE_initialize_console(NULL, kPEReleaseScreen);`，K60 的 `pong-hackios-ui-foundation`/`0213` 版本是 `fGraphics = true; PE_initialize_console(NULL, kPEGraphicsMode);`）。已改为 `@@ -988,7 +1020,7 @@` 并按实际上下文取三行前置、三行后置；`drawLayer` 前插入 `if(!gpuFrame)` 的语义不变。
- 其余 hunk 1/3/4 未改。

### 2.2 `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-gpu-only-display.patch`

- **删除 hunk 1（原 patch 第 1–17 行）**：即 `iokit/Kernel/MiniIOSurface.cpp` `@@ -1917,12 +1917,12 @@` 的 `native_pong_ui_services_start()` 启动门。保留 `0211-k60-display-startup.patch` 的 `pong_software_ui` 默认开启逻辑（`0211` 在 series 第 102 行）。
- **最后一个 hunk（patch 第 62 行）**：原 `@@ -937,7 +950,7 @@` 改为 `@@ -988,7 +1020,7 @@`，上下文按 K60 实际 `fGraphics` 块改为 `fGraphics = true;` + `PE_initialize_console(NULL, kPEGraphicsMode);` + `if (!gpuFrame) drawLayer(...)`；只把 `if(!gpuFrame)drawLayer` 规范为 `if (!gpuFrame) drawLayer`，逻辑不变。
- 其余 5 个 hunk（类字段、`start()` 解析 `pong_gpu_only`、注释、`pong_scanout_frame` 判定、`sid == 0` 清屏）未改。

### 2.3 `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch`

- **第 65 行断言**：`max_x==1080 && max_y==2412` → `max_x==14400 && max_y==32000`（K60 live FDT 的 `goodix,panel-max-x/y`）。其余 8 个属性断言保持原样。
- **pins 断言未改**：`pins[0..5] == 16,17,18,19,21,20`（live FDT 实测）。
- **MFB hunk（patch 第 1055 行）**：原 `@@ -900,6 +900,10 @@` 改为 `@@ -1032,6 +1032,10 @@`，并把尾随上下文 `drawLayer(s, src, dst);` 更新为 GPU 补丁后的 `if (!gpuFrame) drawLayer(s, src, dst);`。插入内容（`PE_initialize_console(NULL, kPEReleaseScreen);` 及注释）未变。原因：本补丁在 series 中位于 GPU 三补丁之后。

### 2.4 `zzz-boot-progress.patch`（为可入 series 做的上下文 rebase）

原补丁是针对其他 XNU 版本/树状态的，直接追加会 6 个文件、8 个 hunk 失败；按“失败 hunk 的实际上下文重做偏移”处理，保留全部原有插入行（逐行比对 additions 完全一致），仅改上下文/插入位置：

- `osfmk/arm/arm_init.c`：`arm_vm_init` 前后埋点改到 K60 实际调用处（`@@ -862,7 +864,9 @@`；原 `@@ -529` 附近已被 0232/ramoops 等改动移位）。
- `osfmk/console/video_console.c`：`vcputc_options()` 入口的 `boot_progress_active()` 检查改到 `0365` 注释块之前（`@@ -1240,6 +1241,7 @@`）。
- `bsd/kern/kern_exec.c`：`load_init_program()` 入口埋点改到实际函数（`@@ -8203`）；SystemOS/Data mount 埋点改到实际 `native_owner_cache_prepare()` / `native_owner_data_prepare()` 调用处，watchdog policy 块保留在 `XNU_BOOT_PROGRESS` 条件内。
- `osfmk/arm64/sleh.c`：`#include <kern/boot_progress.h>` 的版权年份上下文改为 8796 的 2012-2020；`boot_progress_user_abort()` 插到实际 `handle_abort()` 入口（原锚点 `user_fault_in_self_restrict_mode` 在 8796 不存在）。
- `osfmk/kern/Makefile`：`XNU_ONLY_EXPORTS` 的 `boot_progress.h` 改到实际列表开头（`@@ -113,6 +113,7 @@`）。
- `bsd/kern/kern_exit.c`：`boot_progress_exit()` 改到实际 `proc_prepareexit()` 的 crash 处理前（`@@ -2220,6 +2226,10 @@`；原上下文 `task_t task = proc_task(p)` 在 8796 该函数不存在）。

> 未在 `zzz-boot-progress.patch` 中新增任何行为或删除任何原有埋点；`XNU_BOOT_PROGRESS != 1` 时全部宏展开为空。

## 3. `series` 新增

在 `series` 末尾（`0389-k60-kx-pc-lr.patch` 之后）按顺序追加 8 行：

```text
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-gpu-scanout.patch
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-gpu-only-display.patch
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-source-row-pitch.patch
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-goodix-resume.patch
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-physical-keys.patch
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-container-path.patch
zzz-boot-progress.patch
```

- **本次提交**基于 `HEAD` 的 150 行 series，追加后为 158 行，新增行位于第 151–158 行（提交只包含本任务的文件；`0300`–`0373` 的并发分支合并不在本次提交内）。
- 记录生成时工作树另有并发合并的 `0300`–`0373` 条目；该状态下同一块位于第 191–198 行，全量 198 条 dry-run 见 §4.2。
- **未加入**：`...-pong-union-lower-directory.patch`、`zzy-native-gpu-addon-mount.patch`；`offline-native-gpu-broker.patch` 保持原有的 series 第 52 行，不重复追加。
- `0232-k60-pong-adreno-ramoops-bridge.patch` 仍在 series（第 126 行），它是 `pong_ramoops_diagnostic_write` 的唯一实现。

## 4. `git apply --check` 结果

### 4.1 逐个补丁（series-tip 临时副本，按顺序）

| # | 补丁 | check |
|---:|---|---|
| 1 | `...-pong-gpu-scanout.patch` | rc=0 |
| 2 | `...-pong-gpu-only-display.patch` | rc=0（依赖 #1 已应用） |
| 3 | `...-pong-source-row-pitch.patch` | rc=0（依赖 #2 已应用） |
| 4 | `...-pong-touch-console.patch` | rc=0（依赖 #1–#3 已应用） |
| 5 | `...-pong-goodix-resume.patch` | rc=0（依赖 #4 已应用） |
| 6 | `...-pong-physical-keys.patch` | rc=0（依赖 #4–#5 已应用） |
| 7 | `...-pong-container-path.patch` | rc=0 |
| 8 | `zzz-boot-progress.patch` | rc=0（依赖 #1–#7 已应用） |

### 4.2 全量 series 验证

从 feed `/opt/k60/trees/k60build/out-baseline/feeds/xnu-c465a9f8` 克隆 xnu-8796.141.3（`1b191cb`）到临时树，按当前 `patches/xnu/series` 的 198 条顺序逐条 `git apply`：

```text
ALL APPLIED: 198 patches
```

没有任何 fuzz、没有任何 hunk 失败。`xnu-work` 原树未被修改。

## 5. 失败 / 未决项

- 本记录中的 4 个改动补丁（SCANOUT、GPUONLY、touch-console、zzz-boot-progress）及全量 198 条 series 均 `git apply --check` 通过；无 apply 失败。
- 唯一需上机确认的遗留：`zzz-boot-progress.patch` 的 `sheng_boot_watchdog_policy()` 在仓库内没有实现（原补丁既有问题；仅在 `XNU_BOOT_PROGRESS=1` 时编译该块，默认 `XNU_BOOT_PROGRESS=0` 不受影响）。如果以后打开 `XNU_BOOT_PROGRESS=1`，需先提供该函数或删掉该条件块。
- 运行期风险仍按 `docs/plans/GPU-ENABLE-PLAN.md` §6：`K60 FB: ... -> INSIDE managed range` 是硬停止；首次上机先 `pong_adreno_start=1`，再 `pong_gpu_scanout=1`，`pong_gpu_only=1` 只做一轮决定性实验。
