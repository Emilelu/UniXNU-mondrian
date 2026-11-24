# PONG 机器配置在 xnu-12377 上需要什么（只读核实 + 补丁草案）

状态：提案，未进 series、未编译、未上机。分支 `feat/platform-27`。
对应官方页：`../UniXNU/docs/zh/porting/platform.md:10`（`## 源码与接口 {#source-map}`，ArmCpu 一行）与 `:21`（`## 1. 描述 CPU 和中断资源`）。

## 0. 结论（先看这三行）

1. **PONG 机器配置需要 7 个文件**：Lead 点名的 `config/MASTER.arm64.pong`、`PONG.h`、`board_config.h`、`MakeInc.def`、`proc_reg.h`，加上 `osfmk/arm64/start.s:148` 的 MPIDR 掩码条件，和 `pexpert/pexpert/arm64/Makefile`（不列进去头文件不会进导出目录）。草案 `patches/proposed/9003-pong-machine-config-12377.patch`（282 行，7 文件）在**已打 `bcm2837-machine-config.patch` 的 27 构建树**上 `git apply --check` 通过。
2. **但它不解决 `pe_arm_map_interrupt_controller` 那两行**。那个函数没有任何板级条件编译：`grep -n "PONG\|BCM2837" ../xnu-12377/pexpert/arm/pe_identify_machine.c` 为 0 行；16.6.1 的树里同一个函数在 `../UniXNU/out/mondrian/tree/.cache/xnu-work/pexpert/arm/pe_identify_machine.c:521`，调用点 `pexpert/arm/pe_init.c:455` 也一样。**16.6.1 基线同样会打这两行**，它照样能起。
3. 两行的实际后果只有一处：`pe_arm_init_interrupts()` 提前返回，跳过 `pe_arm_init_timer()` → `ml_init_timebase(args, empty_funcs, 0, 0)`（`../xnu-12377/osfmk/arm64/machine_routines.c:1012-1027`），而 arm64 上这个函数只把一组空 `tbd_ops` 记到 `BootCpuData`。真正的 GIC/定时器在 ArmCpu 里（`drivers/ArmCpu/ArmCpu.cpp:568` `initCPU(true)`、`:620-655` 的 INTID 27 → `rtclock_intr(0)`）。所以它是**诊断噪声，不是死因**。

要让两行消失，最小改动在 ADT，不在机器配置：`scripts/make-pong-adt.py:182-187` 的 `intc` 节点没有 `interrupt-controller` 属性，整棵树也没有 `device_type = "timer"` 的节点（`node()` 只自动写 `name`，`:39-45`）。参考实现见共享库 `kebab-stevedang67889.md §配置`：「arm-io/gic interrupt-controller master, virtual-timer-intid 27」——即 `gic` 节点带 `interrupt-controller = "master"` 与 `virtual-timer-intid = 27`。这条改动会改变 DT 形状、只能上机验，本线冻结期只列提案，不落盘。

## 1. PONG 与现在实际在跑的 BCM2837 配置差在哪

| 维度 | 现在（`bcm2837-machine-config.patch`） | PONG 草案 |
| --- | --- | --- |
| 宏 | `BCM2837` | `PONG` |
| 缓存行 | `MMU_I_CLINE/MMU_CLINE = 6` | 同 6（`SM8475` 64 B） |
| `MAX_CPUS` / `MAX_CPU_CLUSTERS` | 8 / 2 | 8 / 2（照抄，见 §4 未决 2） |
| 编译标志 | `-DARM64_BOARD_CONFIG_BCM2837` | `-DARM64_BOARD_CONFIG_PONG -mstrict-align` |
| 语义 | 借 Raspberry Pi 3 的板名 | 自己的板名，之后可独立调拓扑 |

差别只在名字与自由度；**不涉及**任何 PE 查询路径。

## 2. 六个文件与插入点（行号按已打 BCM2837 补丁的 27 构建树）

构建树根：`../UniXNU/out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/.cache/xnu-work`。

| 文件 | 现状 | 草案动作 |
| --- | --- | --- |
| `config/MASTER.arm64.pong` | 不存在（`config/` 只有 `MASTER.arm64.bcm2837`） | 新增 128 行，由 `MASTER.arm64.bcm2837` 改名而来 |
| `pexpert/pexpert/arm64/PONG.h` | 不存在 | 新增 41 行，形状照 `BCM2837.h`（含 `__ARM_PAN_AVAILABLE__` 与 arm64e 的 `HAS_APPLE_PAC`/`HAS_NATIVE_PAC`） |
| `pexpert/pexpert/arm64/board_config.h` | `:307-315` 是 BCM2837 块 | 在其前插入 PONG 块（`MAX_L2_CLINE 6`、`MAX_CPUS 8`、`MAX_CPU_CLUSTERS 2`、`CORE_NCTRS 8`） |
| `pexpert/pexpert/arm64/Makefile` | `:37` `BCM2837.h` | 加 `PONG.h` |
| `makedefs/MakeInc.def` | `:32` `SUPPORTED_ARM64_MACHINE_CONFIGS = BCM2837 T6000 …`；`:82` BCM2837 标志 | 列表头加 `PONG`；`:83` 新增 `MACHINE_FLAGS_ARM64_PONG` |
| `osfmk/arm64/proc_reg.h` | `:246` `#elif defined (BCM2837)` | 在其前插入 `#elif defined (PONG)`，同样 6/6 |
| `osfmk/arm64/start.s` | `:148` `#if HAS_CLUSTER \|\| defined(BCM2837)` | 追加 `\|\| defined(PONG)` |

`start.s` 这条是决定性的：`HAS_CLUSTER` 只在 `pexpert/pexpert/arm64/H13.h:40`…`H17.h:38` 里定义，BCM2837/PONG 都没有。少了这条，PONG 构建会退回 `and x0, x15, #0xFF`（`:150`），8 核时 MPIDR Aff1 被截掉，`ResetHandlerData` 按物理号找不到条目。

## 3. 不搬的 16 系列内容（每一条都有理由）

- `osfmk/kern/startup.c` 的 `#if (!defined(BCM2837) && !defined(PONG)) || …`：12377 的 `osfmk/kern/startup.c` 没有 `XNU_NATIVE_TRUST_CACHE`（`grep -n` 0 行），没有可扩展的守卫，硬搬会制造一个不存在的条件。
- 16 树 `PONG.h` 的 `PONG_LEGACY_UACCESS` / `SCTLR_PONG_UACCESS_DEFAULT` 一组：27 构建树里没有任何 `PONG_LEGACY_UACCESS` 消费者（`grep -rn` 除 `PONG.h` 外 0 行），搬过来是死代码且会让人以为 uaccess 走的是另一条路。
- `GENERIC_PSCI_SMP`：16 系列用它来开 `start.s` 的 16 位掩码；27 上这次改用 `defined(PONG)`，因为这棵树没有 `GENERIC_PSCI_SMP` 的任何消费者。

## 4. 两个未决（写 unknown，不猜）

1. **`start.s:148` 的 `|| defined(BCM2837)` 来源不明**。它在 27 构建树里，但：框架 `../UniXNU/patches/xnu-12377/` 24 个补丁里 `grep -rn HAS_CLUSTER` 只命中 `apple-only-cpu-tunables.patch` 的上下文行；设备 `patches/xnu-12377/` 61 个补丁里 0 命中；SoC 层 `../UniXNU-sm8475-common/patches/xnu/series` 是空注释。**怎么定案**：问准备 F1 构建树的人，或用干净 checkout 重跑一遍准备步骤后 `diff` 这一行。
2. **`MAX_CPU_CLUSTERS` 该是几**。草案照抄 BCM2837 的 2；SM8475 实际是 1+3+4 三个物理簇。16 系列的 PONG 块写 1，并在 `zzzzzzzzzzzzzzzzzzzzz-pong-psci-smp.patch:30-33` 的注释里说 `HAS_CLUSTER` 未定义时物理簇由 `cluster-type` 推。F1 是**单核**（`scripts/make-pong-adt.py:74 --cpus 1`），这条读不出来。**怎么定案**：8 核阶段用 `ml_parse_cpu_topology` 的日志核对，再定 2 还是 3。

## 5. 验证记录

- `git apply --check --verbose` 对上面 6 个文件：7 个 `Checking patch …` 全过，RC=0（验证目录是构建树 6 个文件的干净副本 + `git init`）。
- `git apply --stat`：`7 files changed, 192 insertions(+), 3 deletions(-)`（含两个新文件）。
- 未做：任何编译、任何链接、任何上机。`-fsyntax-only` 也做不了——`proc_reg.h`/`start.s` 依赖 XNU 头与汇编器，属于「必须链 XNU 头」的一类，按规矩留给 F1 之后的构建轮。
- 与 `bcm2837-machine-config.patch` 的关系：草案以它为父补丁（同一批插入点）。两者**不能同时按原样入 series**——`MakeInc.def`/`proc_reg.h`/`board_config.h` 三处共享上下文。落地时的正确形态是把 PONG 并进框架那个补丁文件（一次生成两个板级块），而不是再加一个独立补丁。这条由 Lead 决定。

## 6. 下一步判据

- 若只为消掉 `failed to find the interrupt-controller/timer` 两行：改 ADT（`intc` 加 `interrupt-controller = "master"` + `virtual-timer-intid = 27`，另加 `device_type = "timer"` 节点），判据是那次启动的日志里这两行消失且 `pe_arm_init_interrupts` 不再提前返回。**不要**为此改机器配置。
- 若要真正切到 PONG 机器配置：先定 §4.1 的 `start.s` 来源，再把草案并进 `bcm2837-machine-config.patch`；判据是 `./unixnu status --json` 里 `MACHINE_CONFIGS=PONG` 能过 `SUPPORTED_ARM64_MACHINE_CONFIGS` 这一关（当前会报 `Unsupported CURRENT_MACHINE_CONFIG PONG`，见 `../k60-gates/scripts/legacy/README.md`）。
