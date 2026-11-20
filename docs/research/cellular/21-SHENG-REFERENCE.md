# 21. sheng 作为内核层参考：17 条补丁的逐条裁决（iOS 27.0.1 / 24A446）

> 状态：三个裁决（picked / deferred / not-applicable）已给，**没有一条落成代码**。
> 测量时间 2026-11-20 12:35，sheng 检出 HEAD `a68ee4e`，我们这一侧是 `feat/cellular-ios27` 工作树 `/mnt/e/k60-work/wt-pitfall`。

## 21.1 为什么有这一节

铁则 12（用户 2026-11-20 原话：「每个agent的目标怎么漏掉了内核和驱动也可以参考的sheng的？」）与 Lead 12:30 第 5 条：内核层与驱动层的参考源必须包含 sheng，**逐条对照**，不许只写「参考过」。

sheng 是唯一与我们**同一个 OS profile** 的参考实现：

| 事实 | sheng | 我们（27 线） |
|---|---|---|
| OS profile | `UniXNU-sheng/board.toml:9` `os_profile = "ipados-27.0.1-24A446"` | 同一个 24A446 |
| SoC | SM8550 | SM8475（同代，同 QCOM 基带栈形状） |
| 页表 | 4 KiB、arm64e、PAC（`CONFIG_XNU_ARMVIRT_PLATFORM=n`） | 4 KiB、arm64e、PAC（`configs/mondrian_ios27_defconfig:1`/`:8`） |
| 内核补丁目录 | `patches/xnu-12377/series` | `patches/xnu-12377/series`（同目录名） |
| 存储 | `component:ShengUfs` + `build-sheng-source-storage.py --policy-dir scripts/policies/ipados-27.0.1-24A446` | `component:PongUfs`（27 override 摘掉，F3 回来） |

三条要点先写在前面：

1. 17 条补丁里 **12 条能直接 apply 到我们的 27 种子树**（`git apply --check`），5 条因上下文漂移被拒（21.2 表末列）。
2. 真正与我们的读通路/启动顺序有关的只有三条：`zzzz-sheng-ipados27-bringup.patch` 里的 `sheng_sigp_recover`、`source-storage-runtime.patch` 的插件式启动形状、`zzyd-sheng-audio-addon-mount.patch` 的 overlay 挂载形状。
3. **逐字搬运 `T0SZ_USER != T0SZ_BOOT` 在我们板上是 no-op**，因为它的门是 `defined(BCM2837)`（21.4）。这条是本轮最重要的判据。

> 更正一条既有记录：sheng 的 series 是 **18 行、17 条补丁**（第 1 行是注释 `# Board patch paths for xnu-12377, one per line in application order.`），不是「18 条补丁」。

## 21.2 17 条补丁的逐条裁决

「apply」列是对**我们的 27 种子树**（`.cache/xnu-work`，git `ac9718f`）跑 `git apply --check` 的结果；「裁决」列是我们这个目标（基带/EFS 读通路 + 27 迁移）的态度。

| # | 补丁 | 字节 | 改哪里 | 做什么 | apply | 裁决 |
|---|---|---|---|---|---|---|
| 1 | `zzye-sheng-cpu-idle.patch` | 834 | `osfmk/kern/processor.c` | 导出 `sheng_cpu_idle_mach(int cpu)`，板级读 CPU idle 时间（`recount_processor_usage`） | ok | not-applicable：我们没有板级 governor 调它；若以后做 dvfs，借它「未知 CPU 返回 0」的边界写法 |
| 2 | `zzyf-sheng-amp.patch` | 4,623 | `sched_clutch.c`、`pexpert/.../BCM2837.h` | 没有 performance controller 时按固定优先级分桶 | ok | not-applicable：SM8475 有 perf controller，前提不成立 |
| 3 | `zzyd-sheng-audio-addon-mount.patch` | 1,771 | `bsd/kern/kern_exec.c` | `/private/var/ngpu/audio` → `/System/Library/Audio/Plug-Ins/HAL`，复用 `native_gpu_addon_mount(p, scratch, 0xa00, ...)` | ok | deferred：音频线要它；我们 F3 的 EFS 影子挂载**复用同一个形状**（21.5 第 2 条） |
| 4 | `source-storage-runtime.patch` | 391 | `bsd/kern/bsd_init.c` | `vfsinit()` 之后用 `weak_import` 声明 `native_source_storage_start`，取址判空后才调用 | ok | **本轮最有参考价值**：它与我们的 PongUfs 缺口（P-267「链接一条路径不等于有人产出」）是同一形状，见 21.5 第 1 条 |
| 5 | `zzzz-sheng-ipados27-bringup.patch` | 84,847 | 35 文件 | sigp 恢复、`T0SZ_USER`、`pmap_pt_attr_4k_user`、`start.s` 的 TCR、`bsd_init` 的 `sheng-log` | **reject @ bsd_init.c:800** | deferred，按块取：唯一与我们有关的是 21.3（sigp）与 21.4（T0SZ）；整包按他们的 bsd_init/launchd 假设写，不能整包 |
| 6 | `zzzzzz-sheng-latency-trace.patch` | 607 | `osfmk/kern/exception.c` | 全局钩子 `sheng_user_fault_hook` | ok | not-applicable：我们的判据是 console 行，不引第三方钩子 |
| 7 | `zzzzzzzz-sheng-exit-latency.patch` | 826 | `bsd/kern/kern_exit.c` | 钩子 `sheng_user_exit_hook` | ok | not-applicable（同上） |
| 8 | `zzzzzzzzz-sheng-unnest-trace.patch` | 794 | `bsd/vm/vm_unix.c` | 钩子 `sheng_unnest_hook` | ok | not-applicable（同上） |
| 9 | `sheng-wifi-launchd-cache.patch` | 1,585 | `bsd/kern/kern_exec.c` | `/private/var/ngpu/xpc` overlay 到 `/System/Library/xpc`，注释要求 retaining every original entry | ok | not-applicable（wifi 线），但**「overlay 必须保留原条目」是我们 EFS 影子挂载的规矩** |
| 10 | `sheng-bluetooth-runtime.patch` | 1,715 | `bsd/kern/kern_exec.c` | boot-arg `sheng-bluetooth=1` 时挂 `/private/var/ngpu/bluetooth-lib` 与 `bin` | **reject @ kern_exec.c:8711** | not-applicable（蓝牙线） |
| 11 | `sheng-wifi-association-event.patch` | 1,017 | `bsd/kern/kern_event.c` | 802.11 事件结果结构 540 字节，上限从 `MLEN` 改 `MCLBYTES` | ok | not-applicable（wifi 线），判据形状可借：**事件大小上限是按 profile 的事实，不是常量** |
| 12 | `sheng-main-thread-profile.patch` | 3,503 | `osfmk/arm64/sleh.c`、`mach_msg.c` | `sheng_pmu_fixup`（EL1 上 PMU 系统寄存器访问的修正） | ok | not-applicable：他们的 PMU 虚拟化假设 |
| 13 | `sheng-cache-input-diagnostic.patch` | 2,946 | `osfmk/kern/exception.c` | boot-arg `sheng-cache-log`，针对 launchd 的 cache 回溯 | **reject @ exception.c:1064** | not-applicable（诊断） |
| 14 | `sheng-bluetooth-exit-diagnostic.patch` | 2,543 | `kern_exit.c`、`exception.c` | `log-bluetooth=2` 时转储 bluetoothd/BlueTool 的用户栈 | **reject @ kern_exit.c:1650** | not-applicable（蓝牙线） |
| 15 | `zzzzzzzzzz-sheng-sigp-reinit-assert.patch` | 423 | `osfmk/arm/cpu_common.c` | 把 `assert` 放宽成「`sheng_sigp_recovered` 还是 0 才断言」 | ok | **不能单独取**：它依赖 21.3 的恢复函数，单取只是把断言放松 |
| 16 | `sheng-appsync-runtime.patch` | 3,239 | `bsd/kern/kern_exec.c` | boot-arg `appsync=1` 时先挂 owner-signed 副本 | **reject @ kern_exec.c:8727** | not-applicable（AMFI/AppSync 线） |
| 17 | `sheng-appsync-user-trust.patch` | 9,672 | `bsd/kern/appsync_trust.inc` 等 5 文件 | 用户 App 加载签名时授予 boot-lifetime trust | ok | not-applicable（同上） |

12 ok / 5 reject。五条 reject 的行号是 27 种子树上的实际失败位置；除 bringup 外的四条都是 16 线 kern_exec/kern_exit/exception 的 addon 段在 27 上还不存在造成的**上下文漂移**，不是语义冲突（与 Lead 07:41 的「psci/CPU-start 缺口」同一个成因）。

## 21.3 sheng_sigp_recover：它治的是什么，我们是否暴露

sheng 的注释逐字（`zzzz-sheng-ipados27-bringup.patch`）：

> a started core whose SIGPdisabled is still set lost the self-IPI that should have cleared it (seen as random early hangs and UFS root failures under SMP: the I/O thread's wakeup IPI to that core was silently dropped)

实现（同一补丁）：

- `sheng_sigp_recover(target_proc)`：只有目标核 `cpu_flags` 同时有 `InitState | StartedState` 时，才 `os_atomic_andnot(&target_proc->cpu_signal, SIGPdisabled, acq_rel)`，并 `os_atomic_inc(&sheng_sigp_recovered)`。
- `cpu_signal_internal` 的两个循环里各插一次：`if ((current_signals & SIGPdisabled) == SIGPdisabled && sheng_sigp_recover(target_proc)) current_signals = target_proc->cpu_signal;`。
- 断言放宽：`else if (os_atomic_load(&sheng_sigp_recovered, relaxed) == 0)` 才继续原来那条 `assert`。

我们的树现状（`osfmk/arm/cpu_common.c`）：`SIGPdisabled` 出现在 `:441`（xcall 循环）、`:484`（非 xcall 循环，self 时 `panic("cpu_signal of self while signals are disabled")`）、`:505`（`cpu_signal_internal` 入口判据）、`:583`、`:629-638`（`cpu_signal_setup` 的置位/清除）；**没有** `sheng_sigp_recover`、没有 `sheng_sigp_recovered`。

对我们 EFS/UFS 读通路的暴露面（这是 Lead 点名要回答的问题）：

| 环节 | 我们怎么走 | 是否依赖「某个核收到 IPI」 |
|---|---|---|
| QRTR pump | `k60_modem_probe_from_handoff()`（`K60ModemBoot.c:178`）在 `native_owner_data_prepare()` 里同步跑，四分钟 `for` 循环 + `qcom_glink_poll()`（`K60ModemLink.c:1899`） | 否：就在 exec 的线程上下文里跑 |
| RMTFS 读 | `k60_qrtr_rmtfs_rw()`（`K60ModemLink.c:605`）→ `native_pong_ufs_read_named_volume()` → `hostRead4k()` → `hostScsi(..., 1000000)` | 否：`RootCommands.h:274-300` 是**同步轮询**命令完成，不靠中断、不靠工作环唤醒 |
| 页表/映射 | `ml_io_map_unmappable`、`kmem_alloc_contig`、`flush_dcache64` | **部分**：TLB shootdown 走 `cpu_signal` 与 `flush_core_tlb`，目标核 `SIGPdisabled` 未清时 `cpu_signal_internal` 直接 `KERN_FAILURE`，调用点多数只记 rc 不中止 |
| memshare/SCM | `k60_modem_assign_call()`（`smc #0`） | 否 |

结论：**sheng 那条具体故障（I/O 线程唤醒 IPI 被丢）不会以同样方式咬我们**，因为我们的读不是在等待某个核被唤醒，而是在自己这条线程里刷命令。但同一根因的第二个面——停摆核上的 TLB/DCache 维护被静默跳过——仍然存在：`:441` 那一支返回 `KERN_FAILURE` 后，pmap 侧调用点不会 panic，只是「flush 没发生」。

裁决：**deferred**。触发搬过来的条件是 F2/F3 上出现下列任一条：

- `panic("CPU%u has failed to respond to cross-call after %llu nanoseconds ...")`（`cpu_common.c` 里已有，不需要新补丁）；
- EFS 读回字节与 Android 侧独立参照（doc 20 §29 的 W2）**随机**不一致，而同一镜像重飞一次就一致；
- 出现「`K60UFS volume name=...` 有行、紧跟着 `rmtfs rw ... refused`」的间歇形态，且 `smp2p stop released` 按时出现。

搬的时候要连 `zzzzzzzzzz-sheng-sigp-reinit-assert.patch` 一起（断言放宽与恢复函数是一对），并保留 `sheng_sigp_recovered` 计数行——它是「这次到底恢复过没有」的唯一证据。

## 21.4 T0SZ_USER != T0SZ_BOOT：逐字搬过来在我们板上是 no-op

sheng 的改动分五处（都在 bringup 里）：

1. `osfmk/arm64/proc_reg.h`：新增 `#if defined(BCM2837) && !defined(__ARM_16K_PG__) && defined(__arm64e__)` → `#define T0SZ_USER 17ULL`，`#else` → `#define T0SZ_USER T0SZ_BOOT`；
2. 同文件 `#define TCR_EPD0_DISABLE (1ULL << 7)` 与 `#if T0SZ_USER != T0SZ_BOOT` 下的 `TCR_EL1_KVA_ENTRY`；
3. `osfmk/arm/arm_init.c` 加 `#if T0SZ_USER != T0SZ_BOOT` → `set_tcr(TCR_EL1_KVA_ENTRY); flush_core_tlb();`；
4. `osfmk/arm64/start.s` 加 `MOV64 x1, TCR_EL1_KVA_ENTRY` / `MSR_TCR_EL1_X1` / `isb sy` / `tlbi vmalle1` / `dsb ish`；
5. `osfmk/mach/arm/vm_param.h` 与 `osfmk/arm/pmap/pmap.c`：`VM_USER_STRIP_MASK` 与 `pmap_pt_attr_4k_user.pta_root_level = (T0SZ_USER - 16) / 9`、`pmap_switch_user_ttb`、`pmap_user_va_bits`。

关键在门：`defined(BCM2837)` 是他们的虚拟平台。我们的板没有这个宏，所以

- `T0SZ_USER == T0SZ_BOOT` ⇒ 第 2、3、4 处全部被预处理器丢掉；
- `#define T0SZ_USER T0SZ_BOOT` 本身也无害但无用；
- 也就是说：**把整段复制过来，编译能过、行为一点不变**。这种「看起来搬了、实际上什么都没发生」的改动，比搬错更难发现——它不会失败，只会让人以为已经处理过。

我们的现状：

| 事实 | 值 | 位置 |
|---|---|---|
| 页大小 | 4 KiB（`__ARM_16K_PG__` 未定义） | `configs/mondrian_ios27_defconfig:1`、`:8`、`board.toml:329`、`:365` |
| `T0SZ_BOOT` | 25（无 subpage L1）或 26（subpage L1） | `osfmk/arm64/proc_reg.h:1094-1102` |
| 用户页表根层级 | `.pta_root_level = (T0SZ_BOOT - 16) / 9` = 1 | `osfmk/arm/pmap/pmap.c:282-284` |
| `T0SZ_USER` | **不存在** | `grep -rn T0SZ_USER` 零命中 |
| `VM_USER_STRIP_MASK` | `(-1ULL >> (T0SZ_BOOT))` | `osfmk/mach/arm/vm_param.h:296` |

为什么这仍然可能与我们有关系：我们跑的也是 **arm64e + 4 KiB**。sheng 的理由逐字是「arm64e user code expects pointer authentication codes above bit 46 (libobjc strips isa with a 43-bit mask)」。`pta_root_level = 1` 意味着 TTBR0 从 level 1 起走，用户 VA 只有 38/39 位；47 位用户 VA 要求 `pta_root_level = 0`，会连带改 `pt_attr_twig_offmask`（`pmap_pt_geometry.h:365`、`:628`）与 commpage 层级。

裁决：**deferred，决定权在 Lead**，理由三条：

1. 逐字搬是 no-op（上一段）；要真生效必须**有意去掉 `BCM2837` 这个门**，那是改语义，不是移植。
2. 我们 4 KiB 基线已经跑到 bsd_init（F1），改用户 VA 宽度会让 F1 的结论作废；这不是 cellular 线能单方面决定的事。
3. 判据可在 F1/F2 直接观测：用户态第一个 Mach-O 的 slide/地址、`pmap_user_va_bits` 若被打印、dyld 阶段的 `EXC_BAD_ACCESS` / PAC 失败。**如果 F1 停在 dyld 且所有用户地址都在 0x1_0000_0000 以下，就是这一条。**

**这条裁决有门禁。** `scripts/check-ios27-readiness.py` 的 `user_va_width()` 把上表两行记成期望：`T0SZ_USER` 必须仍然零命中，且 4 KiB 用户页表根层级必须仍是 `(T0SZ_BOOT - 16) / 9`。三种结局：

| 情形 | 输出 |
|---|---|
| 与上表一致 | `K60 READY ok   user tables still start at T0SZ_BOOT (38/39-bit VA), as deferred` |
| 有人把 sheng 的 `T0SZ_USER` 搬进来了 | `K60 READY DRIFT the 27 tree now defines T0SZ_USER: revisit the deferred decision in docs/research/cellular/21-SHENG-REFERENCE.md 21.4` |
| 根层级那一行变了但没定义 `T0SZ_USER` | `K60 READY DRIFT the 4 KiB page-table root level changed: <该行原文>` |

两条 DRIFT 都用假树取证过（定义 `T0SZ_USER` 的树；根层级改成 0 的树），各自 rc=1。这门的用意不是拦住改动，而是**逼改动必须同时改这份文档**——用户 VA 宽度一改，F1 的结论就不再是当前结论。

## 21.5 我们能直接借的三个形状

1. **插件式启动**（`source-storage-runtime.patch`）：`weak_import` 声明 + 取址判空 + 只在存在时调用。我们的 `K60ModemLink.c:42-52` 弱定义兜底已经是同一形状；F3 把 PongUfs 的强定义带回来时**不需要改一行调用点**——这正是 P-267 那条缺口的正确结局。
2. **overlay 保留原条目**（`sheng-wifi-launchd-cache.patch` 的注释 retaining every original entry）：我们 F3 的 EFS 影子挂载必须守同一条——影子只加不减，删条目会把系统自己的挂载点一起抹掉。
3. **断言必须带「为什么可以放宽」的原子变量**（`zzzzzzzzzz-sheng-sigp-reinit-assert.patch`）：不是删断言，而是给它一个可观测的前置条件。我们 27 线以后加 SMP 相关断言时照这个形状写。

## 21.6 与三条线的接口

| 线 | 从 sheng 取什么 | 不取什么 |
|---|---|---|
| F1（`arm_init` → `bsd_init`） | 什么都不取 | 全部 |
| F2（root mount / cupid） | 若 hang 在 IPI/核心启动 → `sheng_sigp_recover` + 断言放宽（成对）；若 hang 在 dyld 且地址低 → 讨论 `T0SZ_USER`（去掉 BCM2837 门，要 Lead 裁决） | BCM2837 专属的 AMP/PMU/start.s TCR 路径 |
| F3（EFS 字节） | `source-storage-runtime` 的形状（我们已等价实现）、overlay 保留原条目的规矩 | 他们的 `ShengUfs` 组件与 policy 目录 |

## 21.7 边界（写在最后，防止被误读）

- 本文的「apply ok」只说明 `git apply --check` 在 27 种子树上通过，**不说明编译过、更不说明构建树可用**。构建树的证据链是 `verify-27-line.sh`（克隆里的补丁 + 追加 + 编译）与 Lead 在 main 侧另加的「`bsd/conf/files` 19 条真在、`link.filelist` 真有 .o」两条，缺一条都不能说「构建树已通过」。
- sheng 的 17 条没有一条进我们的 series。要取的时候按块取，并在这份文档里改裁决与理由。
- sheng 的 `patches/xnu-12377/series` 里没有 `psci_smp` / `pong_cpu_startup_finished` / `ArmCpu` 命中：他们用 catalog 的 `component:ArmCpu`（`ArmCpu.cpp` 自带 `psciCall(hvc, 0xc4000003, affinity, ml_static_vtop(LowResetVectorBase), 0)`）。我们 27 线那六个未定义符号来自**设备仓 `drivers/ArmCpu`（779 行 fork）遮蔽 catalog 组件**，与 sheng 无关，但同一类问题。
