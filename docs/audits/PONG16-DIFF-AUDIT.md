# PONG16-DIFF-AUDIT

移植与 pong `ios16` 分支的机械差异审计。

- 我方：`E:/hackios/UniXNU-mondrian`，分支 `fix/k60-measured-high-window`。审计开始时 HEAD 为 `78452b44ac55`；审计期间 Lead 在同一分支提交了 `17892ae`（只新增 `docs/120HZ-PORT-PLAN.md`，不触及本审计的文件范围），本次提交落在 `17892ae` 之上。
- 参照：`E:/hackios/UniXNU-pong`，`FETCH_HEAD` = `7798f1e5f261e7121d01d7e4807ed73512737ded`，`.git/FETCH_HEAD` 第一行写明 `branch 'ios16' of https://github.com/Chengdong-Yu/UniXNU-pong`。
- 参照读取方式：`git -C E:/hackios/UniXNU-pong archive --format=tar -o ... FETCH_HEAD` 后解包到临时目录；未 checkout、未切分支、未改动 pong 仓库。
- 基线核对：两侧 `patches/xnu` 均以 `xnu-8796.141.3` / `1b191cb58250d0705d8a51287127505aa4bc0789` 为目标（`scripts/build-xnu-4k-baseline.sh:8-10`），冲突试验使用同一 commit 的上游 tarball（sha256 `6F725962608800B26767242A0A19B8ED1C79E2BF1A0F659506F15AB0737C5ACC`）。

## ① 结论摘要

1. **集合规模不是主要差异，"应用方式"才是。** pong 用 `scripts/build-xnu-4k-baseline.sh:71` 的 `patches/xnu/*.patch` glob 直接按字母序应用 103 个补丁；我们用 `board.toml:20` 的 `patch_series = ["device:patches/xnu/series"]` 加 129 条显式顺序（`patches/xnu/series:16-144`），且 `scripts/build-xnu-4k-baseline.sh:42-44` 在 `UNIXNU_PATCH_LIST` 存在时整段跳过 glob。
2. **补丁集合：pong 103，我们 155（HEAD 只有 153 + 2 个未跟踪），series 129。** 103 个 pong 补丁名在我们树里全部存在；其中 20 个未进我们的 series。我们另有 52 个 pong 没有的补丁，46 个已进 series，6 个未进。另有 6 个同名补丁内容已分叉（不是原样照搬）。
3. **userland 在分支层面完全一致，驱动与脚本只在少数文件上分叉。** `userland/` 14 个文件在 HEAD 上与 pong 的 blob 全部相同；工作区只有 `userland/init.c` 有 +7/−1 的未提交改动。`drivers/` 156 个文件清单完全一致，仅 4 个文件内容不同。`scripts/` 里 pong 的 42 个脚本我们一个不缺，另有 36 个自有脚本，12 个同名脚本内容不同。
4. **`board.toml` 与 `porting.toml` 是两套模型。** pong 没有 `porting.toml`，`board.toml` 只有 54 行、没有 `[userdata]`/`[windows]`，但 `[ipsw]` 有 `fetch` 键（`board.toml:16`）。我们的 `board.toml` 162 行，`[userdata]` 在 31-35 行、`windows` 在 35 行，另有 `[components]`、`[device_tree]`、`[payload]`、`[payload."adt"]`；`porting.toml` 189 行、`[device]` 加 13 个 `[[area]]`。
5. **按 pong 字母序全量应用 155 个补丁不可行。** 在干净的 xnu-8796.141.3 上实测：111 个干净应用、14 个靠 fuzz/offset 应用、30 个失败。把同一批文件交给 pong 的这段脚本逻辑，第 1 个补丁就会 `exit 1`（`scripts/build-xnu-4k-baseline.sh:126-128`）：`0210` 排在字母序第 1 位，但它的目标文件 `iokit/Kernel/MiniIOMobileFramebuffer.cpp` 要等第 115 位的 `zzzzzzzzzzzzzzzzzzz-pong-hackios-ui-foundation.patch` 才被创建。即使把顺序修对，显示补丁与 pong 的 `pong-gpu-scanout`/`pong-gpu-only-display` 仍在同一函数同一 hunk 上相撞。

## ② 补丁集合差异表

### 2.1 集合账目

| 项 | pong16 | 我们 | 证据 |
|---|---|---|---|
| `patches/xnu/*.patch` | 103 | 155（工作区）/ 153（HEAD） | `Get-ChildItem ... *.patch`；`git ls-tree -r HEAD patches/xnu` 计 153；`git status` 显示 `?? 0243`、`?? ...quiet-watch` |
| 生效顺序 | 无 `series`，glob 字母序 | `patches/xnu/series` 129 条 | `Test-Path pong/patches/xnu/series` = False；`series` 非注释行 129 |
| 同名补丁 | 103 | 103 全部存在 | 集合差 `pong_not_present = 0` |
| 同名但内容不同 | — | 6 | 逐文件 sha256 比较 |
| pong 有、我们未启用 | — | 20 | 见 2.2 |
| 我们独有 | — | 52（46 在 series，6 未列） | 见 2.3 |
| 未跟踪但被 series 引用 | — | `0243-k60-console-export.patch`（series:139） | `git status --short` = `?? patches/xnu/0243-k60-console-export.patch` |

**应用机制逐行对照**

| 机制 | pong16 | 我们 |
|---|---|---|
| glob 入口 | `scripts/build-xnu-4k-baseline.sh:71` `PATCHES=("$ROOT"/patches/xnu/*.patch)` | `scripts/build-xnu-4k-baseline.sh:42-44` 当 `UNIXNU_PATCH_LIST` 非空时跳过 44-172 整段 glob 路径；顺序由 `board.toml:20` + `patches/xnu/series` 提供 |
| late patch reverse-then-reapply | `38-70`：先反向 `zz*pong*.patch`，再补 `zzz-boot-progress.patch`、`zzy-native-gpu-addon-mount.patch`，按名字倒序反向、正序重放 | `38-73`：同一逻辑，ours 整体 +3 行 |
| 条件跳过（pong 的三个重点） | `76-78` `external-archive-dependencies`；`80-82` `native-aes-personality`；`84-88` `ios16-native-ufs-personality`（另 `89-92` `native-ram-block-personality`、`94-97` `offline-owner-systemos-mount`、`98-101` `offline-pgz-alignment-probe`/`pgz-aligned-validation`、`102-105` `public-entitlements-header`、`106-109` `published-freezer-condition`、`110-113` `zzy`、`114-117` `zzz-boot-progress`） | `80-92` 同样三条；`93-150` 另有 `native-ram-block`、`offline-owner-systemos-mount`、PGZ、`public-entitlements`、`published-freezer`、`zzy`、`zzz-boot-progress`，并新增 `122-125` `zzzzzz-pong-writable-data`、`126-130` `...-pong-upstream-oct22` + `SKIP_PONG_SUFFIX`、`137-141` `...-pong-init-envp-default`、`142-150` `...-pong-init-envp-plumbing` |
| 应用失败策略 | `118-128`：`git apply` 严格 → `patch --fuzz=3` → 失败即 `exit 1` | `151-161`：同一策略，失败即 `exit 1` |
| 补丁数 | 103（glob） | 129（series），工作区 155 个文件 |

### 2.2 pong16 有、我们没有启用（20 个）

判定标准：补丁文件存在于我们的树，但不在 `patches/xnu/series` 的 129 条里。20 个之中，10 个在我们的脚本里有显式门控，另外 10 个只是没写进 series（glob 兜底路径也不会跳过它们）。

| 补丁 | 目标文件 | 类别 | 依据 |
|---|---|---|---|
| `external-archive-dependencies.patch` | makedefs/MakeInc.kernel | ABI | makedefs/MakeInc.kernel；由 XNU_EXTRA_LD_ARCHIVES 门控 |
| `native-aes-personality.patch` | iokit/KernelConfigTables.cpp | ABI | iokit/KernelConfigTables.cpp 的 IOClass 人格 |
| `offline-pgz-alignment-probe.patch` | osfmk/kern/zalloc.c | 诊断 | osfmk/kern/zalloc.c 的 PGZ 对齐探针/校验 |
| `pgz-aligned-validation.patch` | osfmk/kern/zalloc.c | 诊断 | osfmk/kern/zalloc.c 的 PGZ 对齐探针/校验 |
| `public-entitlements-header.patch` | EXTERNAL_HEADERS/CoreEntitlements/CoreEntitlements.h, bsd/net/necp_client.c | 权限 | CoreEntitlements.h + bsd/net/necp_client.c |
| `published-freezer-condition.patch` | bsd/kern/kern_memorystatus_freeze.c | 诊断 | kern_memorystatus_freeze.c；8796 源无此文件 |
| `zzy-native-gpu-addon-mount.patch` | bsd/kern/kern_exec.c, bsd/miscfs/bindfs/bind_vfsops.c, bsd/miscfs/bindfs/bind_vnops.c 等 5 个 | 存储 | kern_exec.c + bindfs + startup.c 的挂载点注入 |
| `zzz-boot-progress.patch` | bsd/kern/bsd_init.c, bsd/kern/kern_exec.c, bsd/kern/kern_exit.c 等 11 个 | 诊断 | 11 个文件的启动进度/控制台埋点 |
| `zzzzzz-pong-writable-data.patch` | bsd/kern/kern_exec.c | 存储 | kern_exec.c 的 Data 窗口/挂载 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-upstream-oct22.patch` | bsd/kern/kern_exec.c, bsd/kern/ubc_subr.c, bsd/miscfs/bindfs/bind_vfsops.c 等 9 个 | 存储 | bindfs + vm_fault + kern_exec 的上游十月合并 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-container-path.patch` | bsd/kern/kern_minimac.c | 容器 | kern_minimac.c 的容器路径策略 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch` | bsd/conf/files, bsd/dev/pong_goodix.c, bsd/dev/pong_input.c 等 6 个 | 设备专属 | Goodix 触摸/物理按键驱动 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-physical-keys.patch` | bsd/conf/files, bsd/dev/pong_buttons.c, bsd/dev/pong_input.c 等 5 个 | 设备专属 | Goodix 触摸/物理按键驱动 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-goodix-resume.patch` | bsd/dev/pong_goodix.c | 设备专属 | Goodix 触摸/物理按键驱动 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-settings-pmsg.patch` | bsd/kern/kern_exit.c, osfmk/arm64/pong_ramoops_console.h | 诊断 | pong_ramoops_console.h + kern_exit.c 的 pmsg |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-gpu-scanout.patch` | iokit/Kernel/MiniIOMobileFramebuffer.cpp | 显示 | MiniIOMobileFramebuffer/MiniIOSurface 的扫描输出 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-gpu-only-display.patch` | iokit/Kernel/MiniIOMobileFramebuffer.cpp, iokit/Kernel/MiniIOSurface.cpp | 显示 | MiniIOMobileFramebuffer/MiniIOSurface 的扫描输出 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-source-row-pitch.patch` | iokit/Kernel/MiniIOMobileFramebuffer.cpp | 显示 | MiniIOMobileFramebuffer/MiniIOSurface 的扫描输出 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-union-lower-directory.patch` | bsd/vfs/vfs_lookup.c | 容器 | vfs_lookup.c 的联合下层目录 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-ufs-data.patch` | bsd/kern/kern_exec.c | 存储 | kern_exec.c 的 Data 窗口/挂载 |

**我们的脚本对这些补丁的门控**

| 补丁 | 我们脚本行 | 条件 |
|---|---|---|
| `external-archive-dependencies.patch` | 80 | `XNU_EXTRA_LD_ARCHIVES` 为空则跳过 |
| `native-aes-personality.patch` | 84 | `XNU_NATIVE_AES != 1` 则跳过 |
| `ios16-native-ufs-personality.patch` | 88 | `KernelConfigTables.cpp` 已有 `NativeUfs` 则跳过 |
| `native-ram-block-personality.patch` | 93 | 已有 `NativeRamBlock` 则跳过 |
| `offline-owner-systemos-mount.patch` | 98 | `XNU_OWNER_CACHE_MOUNT != 1` 则跳过 |
| `offline-pgz-alignment-probe.patch` / `pgz-aligned-validation.patch` | 102 | `XNU_ZONE_PGZ_ALIGNMENT_PROBE != 1` 则跳过 |
| `public-entitlements-header.patch` | 106 | `XNU_VERSION != 10063.141.1` 则跳过 |
| `published-freezer-condition.patch` | 110 | 同上，8796 源无此文件 |
| `zzy-native-gpu-addon-mount.patch` | 114 | `XNU_NATIVE_OFFLINE_GPU != 1` 则跳过 |
| `zzz-boot-progress.patch` | 118 | `XNU_BOOT_PROGRESS != 1` 则跳过 |
| `zzzzzz-pong-writable-data.patch` | 122 | `XNU_OWNER_DATA_MOUNT != 1` 则跳过 |
| `...-pong-upstream-oct22.patch` | 126-130 | `XNU_OWNER_DATA_MOUNT != 1` 则跳过并把后续 `zz*` 一并跳过 |
| `...-pong-init-envp-default.patch` | 137 | 源文件已含 `user_addr_t init_envp = USER_ADDR_NULL;` 则跳过 |
| `...-pong-init-envp-plumbing.patch` | 142/147 | 源文件已含四参数路径，或 `XNU_OWNER_CACHE_MOUNT=1` 则跳过 |

20 个里没有显式门控的 10 个是：container-path、touch-console、physical-keys、goodix-resume、settings-pmsg、gpu-scanout、gpu-only-display、source-row-pitch、union-lower-directory、ufs-data。上表还列了 `ios16-native-ufs-personality`、`native-ram-block`、`offline-owner-systemos-mount`、`init-envp-default`、`init-envp-plumbing`——它们不在 `pong_not_enabled` 里（前三个在 series 内，后两个属我们自有），列出来只为说明脚本的同类门控。计数：10 + 10 = 20。

### 2.3 pong16 没有、我们有的 52 个

"series 行"为 `—` 表示连我们自己的 series 也没有启用。分类按主目标文件判定；跨类的在"目标文件"列给出第二依据。

| 补丁 | series 行 | 目标文件 | 类别 |
|---|---|---|---|
| `0210-k60-display-native-canvas.patch` | 101 | iokit/Kernel/MiniIOMobileFramebuffer.cpp | 显示 |
| `0211-k60-display-startup.patch` | 102 | iokit/Kernel/MiniIOSurface.cpp | 显示 |
| `0212-k60-empty-accelerator.patch` | 103 | iokit/Kernel/MiniAcceleratorES.cpp, iokit/Kernel/MiniDrivers.h, iokit/Kernel/MiniIOSurface.cpp 等 4 个 | 显示 |
| `0213-k60-display-first-frame.patch` | 104 | iokit/Kernel/MiniIOMobileFramebuffer.cpp | 显示 |
| `0214-k60-console-font-scale.patch` | 114 | osfmk/console/video_console.c | 显示 |
| `0215-k60-data-keybags-probe.patch` | 115 | bsd/kern/kern_exec.c | 存储 |
| `0216-k60-aks-bag-selectors.patch` | 116 | iokit/Kernel/MiniAppleKeyStore.cpp | 存储 |
| `0217-k60-aks-status.patch` | 117 | bsd/kern/kern_exec.c, iokit/Kernel/MiniAppleKeyStore.cpp | 存储 |
| `0218-k60-data-keybag-file.patch` | 118 | bsd/kern/kern_exec.c | 存储 |
| `0219-k60-iowatchdog.patch` | 119 | iokit/Kernel/MiniIOSurface.cpp | 诊断 |
| `0220-k60-coredump-off.patch` | 120 | bsd/kern/kern_core.c | 诊断 |
| `0221-k60-watchdog-status.patch` | 121 | bsd/kern/kern_exec.c, iokit/Kernel/MiniIOSurface.cpp | 诊断 |
| `0222-k60-disable-watchdogd.patch` | 122 | bsd/kern/kern_exec.c | 诊断 |
| `0230-k60-exc-resource-early-out.patch` | 123 | osfmk/kern/task.c | 诊断 |
| `0231-k60-accel-stub-adreno-gate.patch` | 125 | iokit/Kernel/MiniIOSurface.cpp | 显示 |
| `0232-k60-pong-adreno-ramoops-bridge.patch` | 126 | osfmk/arm/arm_init.c | 显示 |
| `0233-k60-mfb-selector-success.patch` | 127 | iokit/Kernel/MiniIOMobileFramebuffer.cpp | ABI |
| `0234-k60-seed-boot-preferences.patch` | 128 | bsd/kern/kern_exec.c | 容器 |
| `0235-k60-exec-exit-trace.patch` | 129 | bsd/kern/kern_exec.c, bsd/kern/kern_exit.c, iokit/Kernel/MiniIOMobileFramebuffer.cpp | 诊断 |
| `0236-k60-managed-memory-and-panel.patch` | 130 | osfmk/arm64/arm_vm_init.c | 显示 |
| `0237-k60-keybag-watch-opt-in.patch` | 131 | bsd/kern/kern_exec.c | 存储 |
| `0238-k60-exit-reason-observer.patch` | 132 | bsd/kern/kern_exit.c | 诊断 |
| `0239-k60-runtime-directories.patch` | 133 | bsd/kern/kern_exec.c | 容器 |
| `0240-k60-sandbox-policy-always.patch` | — | bsd/kern/kern_minimac.c | 权限 |
| `0241-k60-skip-launch-constraints.patch` | 134 | security/mac_process.c | 权限 |
| `0242-k60-entitlements-include-shim.patch` | — | bsd/kern/kern_exec.c | 权限 |
| `0243-k60-console-export.patch` | 139 | bsd/conf/files, bsd/dev/k60_console_export.c, osfmk/arm/arm_init.c 等 4 个 | 诊断 |
| `0301-k60-sandbox-kx-histogram.patch` | 140 | bsd/kern/kern_exit.c, bsd/kern/kern_minimac.c | 权限 |
| `0302-data-cap-execerr-kxp.patch` | 141 | bsd/kern/kern_exec.c, bsd/kern/kern_exit.c | 诊断 |
| `0303-k60-heartbeat.patch` | 142 | bsd/kern/kern_exec.c, bsd/kern/kern_exit.c | 诊断 |
| `0304-kxq-rate-ler-lw.patch` | 143 | bsd/kern/kern_exec.c | 诊断 |
| `0305-kxq-site-tags.patch` | 144 | bsd/kern/kern_exec.c | 诊断 |
| `zzyb-native-cryptex-os-view.patch` | — | bsd/kern/kern_exec.c | 容器 |
| `zzyc-owner-skip-launch-constraints.patch` | — | security/mac_process.c | 权限 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-init-envp-default.patch` | 97 | bsd/kern/kern_exec.c | 容器 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-init-envp-plumbing.patch` | — | bsd/kern/kern_exec.c | 容器 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-prelink-security-init.patch` | 99 | libkern/c++/OSKext.cpp | 容器 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-duplicate-class-soft.patch` | 100 | libkern/c++/OSMetaClass.cpp | 容器 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-panic-report.patch` | 105 | osfmk/kern/debug.c, pexpert/arm/pe_init.c, pexpert/pexpert/pexpert.h | 诊断 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-cpp-void-ptr-assert.patch` | 106 | osfmk/kern/kalloc.h | 诊断 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-v-crypto-syntax.patch` | 107 | osfmk/arm64/corecrypto/arm64_isa_compatibility.h | 诊断 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-pgo-runtime-stub.patch` | 108 | libkern/c++/OSKext.cpp | 诊断 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-rwlock-caller-trace.patch` | 109 | osfmk/kern/lock_rw.c | 诊断 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-ppl-lock-sleepable.patch` | 110 | osfmk/arm/pmap/pmap.c | 诊断 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-trustcache-defer-img4.patch` | 111 | bsd/kern/kern_trustcache.c | 权限 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-trustcache-ready-guard.patch` | 112 | bsd/kern/kern_trustcache.c | 权限 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-second-static-trust-cache.patch` | 113 | config/MASTER.arm64.pong | 权限 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-cache-report.patch` | 136 | bsd/kern/kern_exit.c | 诊断 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-mactable-summary.patch` | 135 | bsd/kern/kern_sig.c, security/mac_vfs.c | 诊断 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-mem-report.patch` | 137 | iokit/Kernel/MiniIOMobileFramebuffer.cpp, osfmk/arm64/arm_vm_init.c | 诊断 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-quiet-wakes.patch` | 138 | osfmk/kern/task.c | 诊断 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-quiet-watch.patch` | — | osfmk/kern/task.c | 诊断 |

### 2.4 同名但内容已分叉的 6 个补丁

这 6 个不是"照搬 pong"，而是我们自己的修订版；任何"用 pong 覆盖我们"的操作都会丢掉这些改动。

| 同名补丁（内容分叉） | 说明 |
|---|---|
| `offline-owner-systemos-mount.patch` | pong 与我们的 blob 不同 |
| `zzzzz-pong-ramoops-minimal.patch` | pong 与我们的 blob 不同 |
| `zzzzzz-pong-init-scratch-allocation.patch` | pong 与我们的 blob 不同 |
| `zzzzzzzzz-pong-development-root-policy.patch` | pong 与我们的 blob 不同 |
| `zzzzzzzzzzzzzzzzzzzzz-pong-psci-smp.patch` | pong 与我们的 blob 不同 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-settings-pmsg.patch` | pong 与我们的 blob 不同 |

| 补丁 | 变更行（pong → 我们，忽略 CR） |
|---|---|
| `offline-owner-systemos-mount.patch` | +253 / −26 |
| `zzzzz-pong-ramoops-minimal.patch` | +116 / −72 |
| `zzzzzz-pong-init-scratch-allocation.patch` | +5 / −3 |
| `zzzzzzzzz-pong-development-root-policy.patch` | +5 / −2 |
| `zzzzzzzzzzzzzzzzzzzzz-pong-psci-smp.patch` | +7 / −2 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-settings-pmsg.patch` | +1 / −1 |

证据：`git diff --no-index --numstat --ignore-cr-at-eol <pong-extract> <ours>`，逐文件输出见 ⑥。

## ③ userland / drivers / scripts 差异

### 3.1 `userland/`：14 个文件，HEAD 全部字节一致

`git ls-tree -r HEAD` 与 `git ls-tree -r FETCH_HEAD` 的 blob SHA 逐一比较：14/14 相同。工作区因为 `userland/init.c` 有未提交改动（`git diff --numstat` = `7 1 userland/init.c`）才出现 1 个差异；其余 13 个工作区文件与 pong 规范化后相同。`build.py` 一致这一点成立，且另外 13 个也一致。

| 文件（userland/） | HEAD blob 与 pong 相同 | 工作区规范化后相同 |
|---|---|---|
| `LICENSE-HackiOS` | 是 | 是 |
| `build.py` | 是 | 是 |
| `icons_cpu.c` | 是 | 是 |
| `init-entitlements.plist` | 是 | 是 |
| `init.c` | 是 | 否（工作区 init.c +7/−1） |
| `libmini/mini.c` | 是 | 是 |
| `libmini/mini.h` | 是 | 是 |
| `libmini/start.S` | 是 | 是 |
| `mkjobs.py` | 是 | 是 |
| `touch.c` | 是 | 是 |
| `touch.h` | 是 | 是 |
| `ui_compat.c` | 是 | 是 |
| `var/mobile/Library/Preferences/com.apple.migration.plist` | 是 | 是 |
| `var/mobile/Library/Preferences/com.apple.purplebuddy.plist` | 是 | 是 |

结论修正：任务说明"已知 build.py 一致，请核实其余 13 个"——其余 13 个在 HEAD 上同样全部一致；唯一的工作区差异是 `userland/init.c` 的 +7/−1。该改动未提交，任何 clean checkout 的构建都不包含它。

### 3.2 `drivers/`：清单零差异，内容 4 个文件分叉

`drivers/` 共 156 个文件（8 个目录 155 个 + 顶层 `PongProbe.h`），pong 与我们的文件集合完全相同（`only_pong = only_ours = 0`）。内容差异只有 4 个：`DarwinBoot22/.../DarwinBoot.c`（+10/−0）、`NativeUfs/NativeUfs.cpp`（+4/−1）、`NativeUfs/PongUfsTransport.cpp`（+53/−5）、`NativeUfs/RootLayout.h`（+6/−1）。

| 驱动目录 | pong 文件数 | 我们文件数 | 仅 pong | 仅我们 | 内容不同 | 不同文件 |
|---|---|---|---|---|---|---|
| ArmCpu | 3 | 3 | 0 | 0 | 0 | — |
| ArmDTPlatform | 3 | 3 | 0 | 0 | 0 | — |
| DarwinBoot22 | 18 | 18 | 0 | 0 | 1 | DarwinBoot.c |
| NativeMetal | 0 | 0 | 0 | 0 | 0 | — |
| NativeRamBlock | 6 | 6 | 0 | 0 | 0 | — |
| NativeUfs | 10 | 10 | 0 | 0 | 3 | NativeUfs.cpp, PongUfsTransport.cpp, RootLayout.h |
| PongAdreno | 103 | 103 | 0 | 0 | 0 | — |
| PongMetal | 12 | 12 | 0 | 0 | 0 | — |

`NativeMetal` 需要单独说明：`FETCH_HEAD` 里没有这个目录（0 文件），我们的 HEAD 也没有文件，工作区只有一个空目录；pong 的工作区里有一个**未跟踪的嵌套 git 仓库** `drivers/NativeMetal/`（85 个文件条目，含 `.git` 指针；`git status` = `?? drivers/NativeMetal/`），它不属于 `ios16` 分支。审计只对 `FETCH_HEAD` 负责，因此该项结论是"两边分支都没有"。

### 3.3 `scripts/`：pong 的 42 个一个不缺，另有 36 个自有

pong 42 个脚本、我们 78 个；`only_pong = 0`，即 `install-*.py`、`build-*.py` 没有缺失。12 个同名脚本内容不同，其中 `build-xnu-4k-baseline.sh` 是 +91/−11（应用机制差异的主要载体）。

| pong 有且我们内容不同（12 个脚本） |
|---|
| `build-bootimg.py` |
| `build-ios16-pong-macos.py` |
| `build-payload-probe.py` |
| `build-pong-armcpu-macos.py` |
| `build-pong-platform-macos.py` |
| `build-pong-ram-block-macos.py` |
| `build-pong-ufs-probe-macos.py` |
| `build-xnu-4k-baseline.sh` |
| `inspect-install-readiness.py` |
| `test-initrd-qemu.py` |
| `test-window-qemu.py` |
| `verify-firmware.py` |

我们独有的 36 个脚本：

| 仅我们有（36 个脚本，节选见正文） |
|---|
| `adt-generate.py` |
| `apply-core-patches.sh` |
| `audit-forks.py` |
| `build-darwin24-console.py` |
| `build-darwin24-linux.sh` |
| `build-darwin24-platform.py` |
| `build-k60-platform-archives.py` |
| `build-pong-adreno-platform-linux.py` |
| `check-kernel-entry.py` |
| `check-kernel-thread-entry.py` |
| `check-porting-paths.py` |
| `derive-ios16-storage-bindings.py` |
| `dump-boot-img-layout.py` |
| `emit_prelink_autoslide.py` |
| `extract-kernelcache-kexts.py` |
| `inspect-k60-data.py` |
| `install-k60-ufs-data.py` |
| `k60-bootstrap-pt-model.py` |
| `k60-compare-components.py` |
| `k60-device.sh` |
| `k60-macos-preflight.sh` |
| `k60-make-data-seed.py` |
| `k60-prelink-darwin24.py` |
| `k60-prelink-local.py` |
| `k60-ramoops-read.sh` |
| `k60-sync-refs.sh` |
| `make-k60-gpt-data-image.py` |
| `parse-kernelcache-im4p.py` |
| `patch-armcpu-validate.py` |
| `sync-repos.sh` |
| `verify-boot-img-payload.py` |
| `verify-boot-img-shim.py` |
| `verify-darwin24-img.sh` |
| `verify-k60-boot-img.sh` |
| `verify-kernel-platform-symbols.sh` |
| `verify-loader-abi.py` |

## ④ board.toml / porting.toml 差异

### 4.1 `board.toml`

| 项 | pong16（54 行） | 我们（162 行） |
|---|---|---|
| 顶层 | `[board]:1`、`[ipsw]:8`、`[kernel]:18`、`[firmware]:22`、`[firmware.defines]:48` | `schema_version = 2:1`、`[board]:3`、`[components]:13`、`[kernel]:16`、`[userdata]:31`、`[device_tree]:37`、`[firmware]:41`、`[firmware.defines]:66`、`[payload]:73`、`[payload."adt"]:148` |
| `[userdata]` | **没有**；只有注释 `21: # Prelink and userdata geometry will be added after Pong-specific validation.` | **有**，`31-35`：`first_lba = 53342976:32`、`last_lba = 61731583:33`、`lba_bytes = 4096:34`、`windows = [...]:35` |
| `[windows]` | 没有 | 没有独立段；`windows` 是 `[userdata]` 的键（`board.toml:35`） |
| `fetch` | 有，`[ipsw]` 的键：`board.toml:16 fetch = ["KernelCache", "DeviceTree", "StaticTrustCache", "Cryptex1,SystemTrustCache"]` | 没有 |
| 我们多出的段/键 | — | `[components]:13`、`[device_tree]:37`、`[payload]:73`、`[payload."adt"]:148`、`[userdata]:31`、`pong_native_driver_source:29` |
| pong 多出的 | `[ipsw]:8` 整段（URL/product/version/build/device_class/chip_id/board_id/fetch） | — |

### 4.2 `porting.toml`

pong `FETCH_HEAD` 里**没有** `porting.toml`（`Test-Path` = False）。我们的 189 行，`[device]:3`，随后 13 个 `[[area]]`（`9,23,37,51,65,79,93,107,121,135,149,163,177` 行），id 依次为 configuration、firmware、cpu、memory、storage、display、input、gpu、network、audio、power、packaging、diagnostics。相对 pong，多出来的是整个设备记录文件，而不是某几个段。

`[userdata]`/`windows`/`fetch` 在 `porting.toml` 里都不存在；它们只出现在 `board.toml`，结论见 4.1。

## ⑤ "全量应用"冲突清单与取舍顺序

### 5.1 试验方法

把工作区 155 个 `patches/xnu/*.patch` 按 basename 的 ASCII 字母序排序（等价于 pong 的 bash glob 顺序：数字在字母前），依次应用到 xnu-8796.141.3 的干净解包树；每个补丁先 `git apply` 严格应用，失败再 `patch -p1 --batch --fuzz=3`，与 `scripts/build-xnu-4k-baseline.sh:118-128`（pong）/`151-161`（我们）的策略一致。失败后继续下一个补丁，以便得到全量清单；若按脚本原逻辑，会在第一个失败处 `exit 1`。

结果：**111 clean / 14 fuzz / 30 FAIL**。命令与原始日志见 ⑥。

### 5.2 30 个失败

| 序 | 补丁 | 原因 | 证据（缺失文件 / 失败 hunk） |
|---|---|---|---|
| 1 | `0210-k60-display-native-canvas.patch` | 前置文件不存在 | iokit/Kernel/MiniIOMobileFramebuffer.cpp |
| 2 | `0211-k60-display-startup.patch` | 前置文件不存在 | iokit/Kernel/MiniIOSurface.cpp |
| 3 | `0212-k60-empty-accelerator.patch` | 前置文件不存在 | iokit/Kernel/MiniDrivers.h; iokit/Kernel/MiniIOSurface.cpp |
| 4 | `0213-k60-display-first-frame.patch` | 前置文件不存在 | iokit/Kernel/MiniIOMobileFramebuffer.cpp |
| 7 | `0216-k60-aks-bag-selectors.patch` | 前置文件不存在 | iokit/Kernel/MiniAppleKeyStore.cpp |
| 8 | `0217-k60-aks-status.patch` | 前置文件不存在 | iokit/Kernel/MiniAppleKeyStore.cpp |
| 10 | `0219-k60-iowatchdog.patch` | 前置文件不存在 | iokit/Kernel/MiniIOSurface.cpp |
| 12 | `0221-k60-watchdog-status.patch` | 前置文件不存在 | iokit/Kernel/MiniIOSurface.cpp |
| 15 | `0231-k60-accel-stub-adreno-gate.patch` | 前置文件不存在 | iokit/Kernel/MiniIOSurface.cpp |
| 17 | `0233-k60-mfb-selector-success.patch` | 前置文件不存在 | iokit/Kernel/MiniIOMobileFramebuffer.cpp |
| 19 | `0235-k60-exec-exit-trace.patch` | 前置文件不存在 | iokit/Kernel/MiniIOMobileFramebuffer.cpp |
| 22 | `0238-k60-exit-reason-observer.patch` | 上下文冲突 | Hunk#1@1589 |
| 24 | `0240-k60-sandbox-policy-always.patch` | 前置文件不存在 | bsd/kern/kern_minimac.c |
| 26 | `0242-k60-entitlements-include-shim.patch` | 上下文冲突 | Hunk#1@183 |
| 27 | `0243-k60-console-export.patch` | 前置文件不存在 | osfmk/arm64/pong_ramoops_console.h |
| 28 | `0301-k60-sandbox-kx-histogram.patch` | 前置文件不存在 | bsd/kern/kern_minimac.c |
| 29 | `0302-data-cap-execerr-kxp.patch` | 上下文冲突 | Hunk#5@7509; Hunk#6@7519 |
| 30 | `0303-k60-heartbeat.patch` | 上下文冲突 | Hunk#5@7574; Hunk#2@1666 |
| 31 | `0304-kxq-rate-ler-lw.patch` | 上下文冲突 | Hunk#3@2173; Hunk#4@2212 |
| 32 | `0305-kxq-site-tags.patch` | 上下文冲突 | Hunk#2@2178; Hunk#4@2233 |
| 80 | `pgz-aligned-validation.patch` | 上下文冲突 | Hunk#1@1474 |
| 81 | `public-entitlements-header.patch` | 上下文冲突 | Hunk#1@68 |
| 82 | `published-freezer-condition.patch` | 上下文冲突 | Hunk#1@133 |
| 90 | `zzyc-owner-skip-launch-constraints.patch` | 上下文冲突 | Hunk#2@892 |
| 91 | `zzz-boot-progress.patch` | 上下文冲突 | Hunk#4@7393; Hunk#3@1673 |
| 126 | `zzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-init-envp-plumbing.patch` | 上下文冲突 | Hunk#1@6926; Hunk#2@6998; Hunk#3@7092 |
| 129 | `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-upstream-oct22.patch` | 上下文冲突 | Hunk#2@143 |
| 138 | `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-settings-pmsg.patch` | 上下文冲突 | Hunk#3@123 |
| 148 | `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-mem-report.patch` | 上下文冲突 | Hunk#1@1039 |
| 155 | `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-ufs-data.patch` | 上下文冲突 | Hunk#1@7176; Hunk#2@7208 |

注意：`0217`、`0235`、`0243` 等补丁里还有能应用的 hunk，但只要有 hunk/文件失败，整个补丁就记为 FAIL；`patch` 的 dry-run 失败时不会写入任何改动。

### 5.3 失败主因：字母序把"创建文件"排到了"使用文件"之后

我们的 `02xx` 补丁排在字母序最前面（位置 1-32），但它们的若干目标文件由 pong 的 `zz*` 补丁创建，位置在 94-120。按脚本原逻辑，位置 1 就会退出。

| 补丁（字母序位置） | 缺失目标 | 创建者（位置） | 证据 |
|---|---|---|---|
| `0210`（1） | `iokit/Kernel/MiniIOMobileFramebuffer.cpp` | `zzzzzzzzzzzzzzzzzzz-pong-hackios-ui-foundation.patch`（115） | apply-log：`No such file or directory`；creator 表 |
| `0211`（2） | `iokit/Kernel/MiniIOSurface.cpp` | 同上（115） | 同上 |
| `0212`（3） | `MiniDrivers.h`、`MiniIOSurface.cpp` | 同上（115） | 同上 |
| `0213`（4） | `MiniIOMobileFramebuffer.cpp` | 同上（115） | 同上 |
| `0216`（7） | `iokit/Kernel/MiniAppleKeyStore.cpp` | `zzzzzzzzzzzzzzzzzzzzzzzz-pong-software-keybag.patch`（120） | 同上 |
| `0217`（8） | `MiniAppleKeyStore.cpp` | 同上（120） | 同上 |
| `0219`（10） | `MiniIOSurface.cpp` | ui-foundation（115） | 同上 |
| `0221`（12） | `MiniIOSurface.cpp` | ui-foundation（115） | 同上 |
| `0231`（15） | `MiniIOSurface.cpp` | ui-foundation（115） | 同上 |
| `0233`（17） | `MiniIOMobileFramebuffer.cpp` | ui-foundation（115） | 同上 |
| `0235`（19） | `MiniIOMobileFramebuffer.cpp` | ui-foundation（115） | 同上 |
| `0240`（24） | `bsd/kern/kern_minimac.c` | `zzzzzzz-pong-hackios-userland-abi.patch`（98） | 同上 |
| `0243`（27） | `osfmk/arm64/pong_ramoops_console.h` | `zzzzz-pong-ramoops-minimal.patch`（94） | 同上 |
| `0301`（28） | `bsd/kern/kern_minimac.c` | userland-abi（98） | 同上 |

创建者证据（`--- /dev/null` 后接 `+++ b/<path>`）：

| 缺失文件 | 创建它的补丁（`--- /dev/null`） |
|---|---|
| iokit/Kernel/MiniIOMobileFramebuffer.cpp | `zzzzzzzzzzzzzzzzzzz-pong-hackios-ui-foundation.patch` |
| iokit/Kernel/MiniIOSurface.cpp | `zzzzzzzzzzzzzzzzzzz-pong-hackios-ui-foundation.patch` |
| iokit/Kernel/MiniAppleKeyStore.cpp | `zzzzzzzzzzzzzzzzzzzzzzzz-pong-software-keybag.patch` |
| iokit/Kernel/MiniDrivers.h | `zzzzzzzzzzzzzzzzzzz-pong-hackios-ui-foundation.patch` |
| bsd/kern/kern_minimac.c | `zzzzzzz-pong-hackios-userland-abi.patch` |
| osfmk/arm64/pong_ramoops_console.h | `zzzzz-pong-ramoops-minimal.patch` |

这不是"上下文差几行"，而是**文件尚不存在**；`git apply` 与 `patch` 都无法用 fuzz 修好。

### 5.4 同一文件、同一区域的真实重叠（跨家族）

以下范围是补丁 hunk 的**基准坐标**（`@@ -old_start,old_len`），用于定位"同一函数/同一段"；在叠加树上实际行号会偏移。`patch:line` 是该 hunk 在补丁文件中的行号。

| 补丁 A | A 位置 | 补丁 B | B 位置 | 重叠/距离 | 函数上下文 |
|---|---|---|---|---|---|
| `0210-k60-display-native-canvas.patch:37` | MFB.cpp 386+9 | `...-pong-gpu-scanout.patch:14` | MFB.cpp 386+6 | 完全同起点 | `IOMobileFramebuffer::start` |
| `0210:61` | MFB.cpp 408+10 | `...-pong-gpu-scanout.patch:14` | MFB.cpp 386+6 | 同函数、位于 386 段之后 | `IOMobileFramebuffer::start` |
| `0213-k60-display-first-frame.patch:14` | MFB.cpp 356+6 | `...-pong-gpu-only-display.patch:28` | MFB.cpp 351+6 | 区间 351-361 相交 | `IOMobileFramebuffer::publishModes` |
| `0211-k60-display-startup.patch:5` | MiniIOSurface.cpp 1916+10 | `...-pong-gpu-only-display.patch:3` | MiniIOSurface.cpp 1917+12 | 区间 1916-1928 相交 | `native_pong_ui_services_start` |
| `0235-k60-exec-exit-trace.patch:99` | MFB.cpp 32+6 | `...-pong-gpu-scanout.patch:3` | MFB.cpp 41+6 | 上下文相隔 3 行 | 文件头/静态区 |
| `0235:116` | MFB.cpp 791+6 | `...-pong-gpu-scanout.patch:23` | MFB.cpp 801+9 | 相隔 4 行 | 扫描输出路径 |
| `0235:107` | MFB.cpp 253+6 | `...-pong-gpu-only-display.patch:20` | MFB.cpp 242+6 | 相隔 5 行 | 显示状态区 |
| `zzzzzz-pong-writable-data.patch:41` | kern_exec.c 7244+6 | `zzy-native-gpu-addon-mount.patch:88` | kern_exec.c 7250+6 | 区间 7250-7256 相交 | `native_owner_data_prepare` |
| `0302-data-cap-execerr-kxp.patch:108` | kern_exec.c 7434+7 | `...-pong-ufs-data.patch:56` | kern_exec.c 7437+7 | 区间 7437-7440 相交 | `native_owner_data_prepare` |
| `0302:117` | kern_exec.c 7444+11 | `...-pong-ufs-data.patch:56` | kern_exec.c 7437+7 | 区间 7444-7447 相交 | 同上 |
| `0303-k60-heartbeat.patch:79` | kern_exec.c 7507+6 | `zzyb-native-cryptex-os-view.patch:165` | kern_exec.c 7517+6 | 相隔 4 行 | 同上 |
| `0303:88` | kern_exec.c 7519+10 | `zzyb-native-cryptex-os-view.patch:165` | kern_exec.c 7517+6 | 区间 7519-7523 相交 | 同上 |
| `0239-k60-runtime-directories.patch:3` | kern_exec.c 7509+15 | `zzyb-native-cryptex-os-view.patch:165` | kern_exec.c 7517+6 | 区间 7517-7523 相交 | 同上 |
| `0239:3` | kern_exec.c 7509+15 | `0303-k60-heartbeat.patch:79` | kern_exec.c 7507+6 | 区间 7509-7514 相交 | 同上 |

`0302/0303/0304/0305` 之间还有大量 2110-2233 的互相重叠；它们在 series 里是 140-144 行的固定栈，按 0302→0303→0304→0305 顺序应用是设计内行为，本表只列跨家族行。

### 5.5 `K60DATA` 专项（kern_exec.c）

`K60DATA` 是挂在 `kern_exec.c` 的 Data 窗口/挂载代码里的日志标签，不是宏。带该字符串的补丁共 9 个（`Select-String -Pattern K60DATA`）：`0215`、`0218`、`0222`、`0234`、`0237`、`0239`、`0302`、`0303`、`offline-owner-systemos-mount`。

该区域的"母补丁"是 `offline-owner-systemos-mount.patch`（我们相对 pong 改了 +253/−26），它在 `kern_exec.c` 6821-6951 一带建立挂载/种子逻辑；`0302` 在 7434/7444 加 `K60DATA UFS window` 日志，`0303` 在 7507/7519/7571 加 mount/root 日志并定义心跳。与 pong 的冲突集中在 `native_owner_data_prepare()`：

- `zzy-native-gpu-addon-mount.patch:88` 在 7250+6 重写该函数入口，`zzzzzz-pong-writable-data.patch:41` 在 7244+6 改同一函数；两者在 7250-7256 相交。
- `...-pong-ufs-data.patch:56` 在 7437+7 再加一段，`0302:108`（7434+7）与 `0302:117`（7444+11）正好压在它的两端。
- `zzyb-native-cryptex-os-view.patch:165`（7517+6）与 `0239:3`（7509+15）、`0303:88`（7519+10）三者在 7517-7523 相交。

实测结果与坐标一致：`...-pong-ufs-data.patch` 在 7176/7208 两个 hunk 失败，`zzyb`/`0303`/`0239` 的组合也互相踩踏。这个函数的爆炸半径是 root/Data 挂载，属于最高风险区。

### 5.6 建议取舍顺序

1. **保留 format-2 series，禁止把 pong 的 glob 顺序套到我们的 155 个补丁上。** 证据：5.1 的 30 个失败、5.3 的文件创建顺序；`board.toml:20` 与 `scripts/build-xnu-4k-baseline.sh:42-44` 已经是正确机制。
2. **若要引入 pong 的新补丁，只能追加到 series 第 144 行之后，或插在创建者之后。** 特别是 `ui-foundation`（115）、`software-keybag`（120）、`ramoops-minimal`（94）必须先于任何引用其文件的 `02xx`；`0243` 依赖 `pong_ramoops_console.h`，不能排在其创建者之前。
3. **显示补丁与 pong GPU 补丁二选一，或重写。** 若启用 `pong-gpu-scanout`/`pong-gpu-only-display`，必须先把 `0210`/`0213`/`0211` 在它们之上重做；否则 `IOMobileFramebuffer::start`（386）、`publishModes`（351-361）、`native_pong_ui_services_start`（1916-1927）三处必然冲突。
4. **存储/挂载补丁按 `zzy → writable-data → ufs-data` 排队，且把 `0302/0303/0239/zzyb` 重基到同一函数版本。** 现状是 7250、7437、7517 三个交点；不重基就会重复 5.5 的失败。
5. **先提交 `0243-k60-console-export.patch`，再决定 `quiet-watch`。** `series:139` 引用了未跟踪文件；clean checkout 会缺文件。`zzzz...quiet-watch.patch` 未跟踪且未进 series，属于未决实验。
6. **处理 `userland/init.c` 的 +7/−1。** HEAD 与 pong 完全一致；这 7 行是工作区私有改动，提交或回退都要明确，否则"分支对比"与"工作区对比"会给出不同答案。

## ⑥ 证据与命令

### 6.1 版本与集合

```text
git -C E:/hackios/UniXNU-mondrian branch --show-current
fix/k60-measured-high-window
git -C E:/hackios/UniXNU-mondrian rev-parse --short=12 HEAD
78452b44ac55
git -C E:/hackios/UniXNU-pong rev-parse --short=12 FETCH_HEAD
7798f1e5f261
Get-Content E:/hackios/UniXNU-pong/.git/FETCH_HEAD -TotalCount 1
7798f1e5f261e7121d01d7e4807ed73512737ded    branch 'ios16' of https://github.com/Chengdong-Yu/UniXNU-pong
```

```text
Get-ChildItem pong/patches/xnu/*.patch | Measure-Object   -> 103
Get-ChildItem ours/patches/xnu/*.patch | Measure-Object   -> 155
git -C ours ls-tree -r HEAD patches/xnu | Measure-Object  -> 153
series non-comment lines                                   -> 129
Test-Path pong/patches/xnu/series                          -> False
```

### 6.2 逐文件比较

- 分支级：`git ls-tree -r -z HEAD` 与 `git ls-tree -r -z FETCH_HEAD` 的 blob SHA 逐路径比较。`userland` 14/14 相同；`drivers` 152/156 相同；`scripts` 30/42 相同；`patches/xnu` 97/103 相同。
- 工作区级：对两侧文件做 `\r\n → \n` 规范化后 sha256。原因：`git archive` 在 Windows 上解出的文本是 CRLF，而我们的工作区是 LF；直接比字节会把行尾差异误报成内容差异。规范化后 `userland` 13/14 相同（仅 `init.c` 不同），`drivers` 152/156 相同，`scripts` 30/42 相同。
- 内容差异行数：`git diff --no-index --numstat --ignore-cr-at-eol <pong> <ours>`，结果见 2.4、3.1、3.2、3.3。

### 6.3 冲突试验

```text
base: codeload xnu tar.gz @ 1b191cb58250d0705d8a51287127505aa4bc0789
sha256: 6F725962608800B26767242A0A19B8ED1C79E2BF1A0F659506F15AB0737C5ACC
for patch in sorted(155): 
  git -C xnu apply --whitespace=nowarn patch  || 
  patch -p1 --dry-run --batch --fuzz=3 -d xnu -i patch && patch -p1 --batch --fuzz=3 ...
result: clean=111  fuzz=14  FAIL=30
```

fuzz/offset 的 14 个（说明"能应用"也不等于"对"）：

```text
0215 offset -69 fuzz 2/3
0218 fuzz 3
0222 fuzz 3
0232 offset +187 fuzz 2
0234 fuzz 3
0239 offset -302 fuzz 2
external-archive-dependencies fuzz 3
native-aes-personality fuzz 3
offline-owner-systemos-mount fuzz 3 / offset -15
offline-owner-z-air-init offset -7208 fuzz 2
zzy-native-gpu-addon-mount offset -33 / +14 fuzz 1
zzyb-native-cryptex-os-view fuzz 3 / offset +728
zzzzzz-pong-writable-data offset +124 / +220
...-k60-quiet-watch fuzz 3
```

`0232` 的 `offset +187`、`offline-owner-z-air-init` 的 `offset -7208` 是典型的"fuzz 到了错误位置"，比直接失败更危险。

### 6.4 未核实项

- pong 的完整 macOS 内核构建未在本机执行；本审计只验证补丁应用层，不断言最终内核行为。
- pong 工作区中未跟踪的 `drivers/NativeMetal/`（嵌套仓库 85 个条目）不属于 `FETCH_HEAD`，其内容未纳入逐文件比较，标为"未核实（不在 ios16 分支）"。
- 我们工作区还有大量与本审计范围无关的未提交文档/脚本改动（`git status` 共数十项）；本审计只在 `patches/xnu`、`userland`、`drivers`、`scripts`、`board.toml`、`porting.toml` 六个范围内下结论。
