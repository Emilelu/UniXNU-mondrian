# ArmCpu：catalog 还是 fork —— iOS 27 stage-0 的裁决

> 官方锚点：<https://unixnu.com/zh/porting/platform#source-map>（本地 `E:/hackios/UniXNU/docs/zh/porting/platform.md:10-19`）把 ArmCpu 的职责写成「CPU 注册、定时器/GIC 初始化、secondary 入口与 IPI」。
> 口径：`E:/hackios/k60-gates/porting.toml:199` 的 2026-11-19 记录是**已记录的先验，不是已验证的事实**。本文逐条验证它，并把结论收敛到「换不换、什么时候必须回头」。

## 裁决

**27 stage-0 保留 fork（`drivers/ArmCpu/ArmCpu.cpp`，779 行），不切 catalog 93a5030c。** 三条独立理由：

1. **catalog 的 secondary 入口依赖 ADT `/psci` 节点，本板没有这个节点。** `ArmCpu-93a5030c.cpp:501-514` 的 `psciConduit()` 从 IORegistry `/psci` 读 `method`，注释写明「no default is assumed」；`startCPU()`（`:802-831`）没有 conduit 就起不来 secondary。本板 ADT 由 `scripts/make-pong-adt.py:235-269` 生成，只有 chosen/cpus/arm-io/defaults/options/product 六类节点，`/chosen` 里写的是 `psci-method = "smc"`（`:174`），**没有 `/psci`**。catalog 需要的 `/psci` 与 0540 读的 `/chosen/psci-method`（`patches/xnu-12377/0540-k60-psci-smp.patch:124-127`）不是一个东西：本板的既有接线是后者。
2. **catalog 的 secondary 是 boot-arg 选择进入的。** `probe()`（`:204-228`）只在 `sheng-smp` 引导参数存在且 logical id 在 `ARMCPU_SMP_SLOTS` 内时才接受 CPU nub；没有该参数时副核根本不 probe，SMP 静默退化单核。本板 `board.toml:194-206` 的 kernel_args 没有 `sheng-smp`，`board.toml:396-400` 也没有。sheng 自己是把 `sheng-smp=1`、`armcpu-spi-ipi=1`、`armcpu-self-ipi=1` 三个参数写进 `E:/hackios/UniXNU-sheng/board.toml:66` 的。
3. **catalog 93a5030c 没有睡眠能力，而本板 27 的归档里也没有睡眠调用者。** 这一条是双向的：切过去不会立刻断链（见 §3.2），但也没带来任何 27 需要的东西；把 5f37026 的 sleep 抬进来是另一件事，不是 stage-0 的活。

**记录的前提不是错，是版本不成立。** catalog 里真正带 sleep 的是 823c6b2 / 5f37026（`ArmCpu.cpp` 1443 行 + `ArmCpuSleep.h` 124 行），而 `components.toml:3-19` 钉的 93a5030c（875 行）没有；其 `os_abi` 是 `ipados-17.7.11-21H461`，不含 27。切 catalog 的真实动作是「升 rev 到 ≥5f37026，再补 `/psci`、补 `sheng-smp`、删 `pong_cpu_start`」，不是换一行 include。

**0532/0540 的定性**：它们是 fork 私有路径的补丁，这一点成立——catalog 不调 `pong_cpu_startup_finished`，也不引 `psci_smp_*`。但反过来说「因为有这两个补丁所以该切 catalog」不成立：catalog 在本板缺 `/psci` 与 `sheng-smp` 两个前置，切过去等于把一个已验证的 SMP 路径换成一条在本板从未跑过的路径。0541（`CNTP_CTL_EL0` 写保护）与 ArmCpu 选择无关，它改的是 `osfmk/arm64/machine_routines.c`，两条路线都要。

## 1. 两边是什么

| | catalog 93a5030c（钉住） | catalog 5f37026（HEAD 附近） | 本板 fork |
|---|---|---|---|
| 行数 | 875 | 1443 + `ArmCpuSleep.h` 124 | 779（自带 `ArmCpuSleep.h`） |
| 钉在哪 | `E:/hackios/UniXNU/components.toml:3-19`，`revision="93a5030c…"` | 未钉 | `board.toml:14` `include` 里的 `ArmCpu` 被 `drivers/ArmCpu/` 遮蔽 |
| os_abi | `ipados-17.7.11-21H461` | 未见 27 声明 | 16.6.1 线产物，现跑在 27 |
| secondary 入口 | `psciConduit()` 读 `/psci` + `psciCall(hvc, 0xc4000003, …)` | 同 | `psci_smp_start_cpu()`（0540 提供） |
| 睡眠 | 无 | `armcpu_sleep_register` + `ArmCpuSleep.h` | 有（`:283-312`） |
| SPI owner | 16 槽、无单飞 | 16 槽 | 4 槽、单飞 CAS |

另有一处文档不一致要记：官方页 `platform.md:10-19` 的源码对照表写 ArmCpu 是 rev `9066b53b`，`components.toml:3-19` 钉的是 `93a5030c`。结论不受影响（两个 rev 都早于 sleep 支持），但引用官方页时不要把它当版本号。

### 1.1 六棵参考树的现状（2026-11-21 核对）

| 树 | os_profile | ArmCpu 来源 | 副核入口 | 睡眠 |
|---|---|---|---|---|
| `E:/hackios/UniXNU-sheng` | `ipados-27.0.1-24A446` | `component:ArmCpu`（`board.toml:20/:117/:174`） | `/psci` + `sheng-smp=1`（`board.toml:66`） | 5f37026 之后 |
| `E:/hackios/xnekom-ios27` | `ios-27.0.1-24A446` | **fork 779 行，与本板逐字节相同**（`diff` 空） | 0532 + 0540（`patches/xnu-12377/series:65,:87`） | `armcpu-sleep-hook.patch` + `K60PlatformSleep.cpp:128` |
| `E:/hackios/UniXNU-t970` | `ipados-18.7.10-22H374` | 581 行旧 fork | 未查 | 未查 |
| `E:/hackios/UniXNU-zizhan` | `ipados-18.7.10-22H374` | 559 行旧 fork | 未查 | 未查 |
| `E:/hackios/UniXNU-pong` | `ipados-18.7.10-22H374` | 无 `drivers/ArmCpu` | 无 | 无 |
| 本板 | `ios-27.0.1-24A446` | fork 779 行 | 0532 + 0540 | fork 自带（27 归档未启用） |

**这行表是裁决的关键外部证据**：27 时代真正在跑的两棵树走了相反的路——sheng（SM8550 平板、无双核 PSCI 历史包袱）用 catalog + 引导参数；xnekom（Pong 族、`PongUfs`/`K60PlatformSleep` 同一套）用**和本板逐字节相同的 fork** + 0532/0540，而且该文件仍在被维护（`24746184 fix(power): mark secondary CPUs stopped before sleep`、`1c662ecd fix(power): keep the platform sleep path quiet until resume`）。本板与 xnekom 同源，因此「沿用 fork」不是守旧，是跟着 27 时代同源树的实际选择走；`porting.toml:199` 那条「用 catalog ArmCpu」的先验在 xnekom 这里没有兑现，原因正是 §0 的三条缺口。

## 2. 符号对账（Lead 要求 1）

“catalog 有”指 93a5030c；“fork”指 `E:/hackios/k60-platform27/drivers/ArmCpu/ArmCpu.cpp`；“补丁”指 `E:/hackios/k60-gates/patches/xnu-12377/`。

### 2.1 两边都有（组件内导出）

`armcpu_registered`、`armcpu_gic_ready`、`armcpu_timer_interrupts`、`armcpu_ipi_interrupts`、`armcpu_gic_boot[8]`、`armcpu_gic_typer_probe[2]`、`armcpu_gic_stride`、`armcpu_spi_attach`（语义不同，见 §3.1）。

### 2.2 只在 fork（27 必须处理，逐条见 §3）

| 符号 | fork 位置 | 调用者 |
|---|---|---|
| `armcpu_sleep_register` | `:293` | `drivers/PongPower/K60PlatformSleep.cpp:36, :128`（27 归档不含 PongPower，见 §3.2） |
| `armcpu_sleep_report` | `:303` | 同上文件族 + host fixture |
| `armcpu_sleep_stats` / `armcpu_sleep_last_cpu_off_rc` | `:45-54` | 观测/日志 |
| `armcpu_controller_attached` / `armcpu_controller_published` | `:29-30` | fork 自身诊断（2 处引用，无外部消费者） |
| `armcpu_cntv_state[5]` | `:31` | fork 自身日志（4 处） |
| `pong_cpu_start` | `:760-778` | `drivers/ArmDTPlatform/ArmDTPlatform.cpp:23` 声明、`:224` 调用 |

### 2.3 只在 catalog（27 用不到，但切过去会多出来）

`armcpu_spi_count(intid)`（`:868`）、`armcpu_spi_unhandled` / `armcpu_spi_unhandled_id`（`:204-207`）、`armcpu_ipi_sent`、`armcpu_ipi_selftest_sent`、`armcpu_core_timer[8]`、`armcpu_core_sgi[8]`、`armcpu_irq_phase/id/long_drains/drain_most`、`armcpu_quiesce_calls`、`armcpu_halt_calls`、`armcpu_smp_*`（requested/running/conduit/step/mpidr/seen_mpidr/fail/sys/psci_rc）、`armcpu_gic_diag()`、`armcpu_sgi_selfprobe()`、`armcpu_ipi_selftest()`。

### 2.4 两边都没有（由 XNU 或补丁提供）

| 符号 | 谁提供 | 位置 |
|---|---|---|
| `pong_cpu_startup_finished` | 0532 | `0532-k60-cpu-start-completion.patch`（`iokit/Kernel/IOCPU.cpp`，`#if !defined(PONG)`） |
| `psci_smp_init` / `psci_smp_start_cpu` / `psci_smp_cpu_running` / `psci_smp_cpu_off` | 0540 | `0540-k60-psci-smp.patch`（新增 `osfmk/arm64/psci_smp.c`） |
| `arm64_platform_sleep_hook` | `armcpu-sleep-hook.patch:13` | `void (*arm64_platform_sleep_hook)(boolean_t) = NULL;` |
| `ml_arm_sleep` | **XNU 自带**，不是补丁 | `E:/hackios/xnu-12377/osfmk/arm64/cpu.c:1024`，声明 `osfmk/arm/machine_routines.h:757` |
| `ml_is_quiescing` | XNU 自带 | `osfmk/kern/lock_rw_old.c:747` 等 |
| `processor_exit_reason` | XNU 自带 | `osfmk/kern/processor.c:1175` |

**这一格是本次核对最实质的修正**：fork 的睡眠路径只有 `arm64_platform_sleep_hook` 一个符号需要补丁，`ml_arm_sleep` 是 12377 的原生函数（`cpu.c:1024`，`noreturn`，在 boot CPU 上等所有副核 `cpu_sleep_token == ARM_CPU_ON_SLEEP_PATH`）。此前「sleep 三元组都要靠 fork」的印象不准确。

## 3. fork 独有能力 → 27 怎么办（Lead 要求 2）

### 3.1 SPI owner：`armcpu_spi_attach`

- **fork 语义**（`:657-694`）：`gSpi[4]`（`:39`）、单飞 `__atomic_compare_exchange_n(&gSpiRegistering, …)`（`:664`）、重复 owner 返回 `kIOReturnExclusiveAccess`、第 5 个返回 `kIOReturnNoResources`（`:669`）、结束时释放锁（`:692`）。
- **catalog 语义**（`:836-866`）：`ARMCPU_SPI_SLOTS 16`（`:199`）、`gSpi[16]`（`:201`）、**没有单飞锁**、槽满返回 `kIOReturnNoResources`（`:846`）、另有 `armcpu_spi_count()`。
- **调用者**：`patches/xnu-12377/0500-k60-bt-qbt-new-files.patch:1062`（BT UART）、`:1068`（TLMM）。27 stage-0 只用 2 个 SPI，`gSpiUsed` 上限 4 够用；16 槽也不缺，真正差的是单飞。
- **27 怎么办：保留 fork 版语义，不迁移。** 量化理由：驱动侧依赖的是「重复注册必须被拒」，host fixture `E:/hackios/k60-gates/scripts/tests/fixtures/bt-gic-shared.c` 明确断言第 5 个槽（intid 604）返回 `kIOReturnNoResources`、重复 owner 被拒、八线程并发注册只成功一次——它编码的是 fork 语义。切 catalog 会让这个 fixture 失败（16 槽）且并发路径无保护。
- **触发条件（必须回头的时点）**：① 27 的 BT 驱动改成走 IOKit provider 而不调 `armcpu_spi_attach`；或 ② 需要 >4 个 SPI owner（例如同时接触摸 + 按键 + 音频 amp）；或 ③ fixture 由 Lead 决定改成 16 槽语义。三者任一成立，就切 catalog 版并把 fixture 的期望值同步改掉——fixture 在 k60-gates（只读），改它需要 Lead 指派。

### 3.2 睡眠三元组：`armcpu_sleep_register` / `armcpuPlatformSleep` / `arm64_platform_sleep_hook`

- **fork 接线**：`prepareGic()`（`:461-483`）解析 `platform-sleep` 与 `platform-sleep-wake-after` 两个引导参数，只有 `platformSleep==1 && &arm64_platform_sleep_hook != nullptr` 时把 hook 装成 `armcpuPlatformSleep`（`:477-481`）；`armcpu_sleep_register()`（`:293-301`）存板级回调并返回 `gSleepEnabled ? KERN_SUCCESS : KERN_NOT_SUPPORTED`；`quiesceCPU()`（`:712-733`）在 `gSleepEnabled && ml_is_quiescing()` 时走 `ml_arm_sleep()`（`:724`）。
- **调用者**：`drivers/PongPower/K60PlatformSleep.cpp:36`（extern）、`:128`（`armcpu_sleep_register(&k60SleepBoard)`）。
- **27 的现状（决定性）**：`board.toml:14` 的 `include` 与 `board.toml:21` 的 `archives` 都只有 `ArmDTPlatform` / `ArmCpu` / `XnuPrelink` / `PongUfs`，**没有 PongPower**；`hardware.platform.paths` 也不含 `drivers/PongPower/`。因此 27 stage-0 归档里 `K60PlatformSleep.cpp` 不参与编译，`armcpu_sleep_register` 没有调用者。
- **27 怎么办：stage-0 不需要，且这不是静默丢弃，是归档表本来就排除。** 理由链：① 27 stage-0 目标是 arm64e 内核跑到 `bsd_init`（`configs/mondrian_ios27_defconfig` 第一行注释），没有 S2R 调用点；② 归档里没有 PongPower，切 catalog 不会造成 `armcpu_sleep_register` 未定义，保留 fork 也不会带来睡眠能力；③ 27 首飞是 0 字节日志（`E:/k60-work/scratch/LANE-CONTRACT-ios27.md` §4），睡眠排在更后面。
- **触发条件**：把 `PongPower`（或其 `K60PlatformSleep.cpp`）加进 27 的 `archives`，或 27 需要 S2R/深度睡眠——任一发生，必须先决定睡眠实现来自哪里：fork 的 `:110-312` 原样搬进 27 树，或升 catalog 到 ≥5f37026 用其 `ArmCpuSleep.h`。**在此之前，27 树不得把 `platform-sleep` 写进 kernel_args**（否则 fork 会装 hook 而板级回调没人注册，`armcpu_sleep_register` 返回 `KERN_NOT_SUPPORTED`，睡眠变成静默 no-op）。

### 3.3 `pong_cpu_start`

- **fork 语义**（`:760-778`）：遍历 ArmDTPlatform 的 `IOService` 子节点，找 `device_type=="cpu"` + 4 字节 `reg` 且 `ml_get_cpu_number(phys) == ml_get_boot_cpu_number()` 的那一个，`init/attach/start`。
- **调用者**：`drivers/ArmDTPlatform/ArmDTPlatform.cpp:23`（extern）、`:224`（`if (!pong_cpu_start(this))`，紧跟 `createDeviceNubs(provider)`，注释「All CPU nubs now exist. Register them together before PSCI CPU_ON.」）。
- **catalog 侧**：`ArmDTPlatform` 417ff95d（210 行）只发 nub，不调 `pong_cpu_start`；catalog ArmCpu 靠 IOService 匹配自己 probe。
- **27 怎么办：保留（fork 与本板 ArmDTPlatform 成对）。** 只切 ArmCpu 会在 `ArmDTPlatform.cpp:224` 留一个未定义符号——但这是编译期就炸，不会静默。触发条件：若 ArmDTPlatform 也切 catalog 417ff95d，则删 `:23` 与 `:224` 两行，同时接受失去 `/chosen/boot-epoch` 日历、per-nub 日志、以及 `pong_adreno_start_optional`/`pong_wifi_start_optional`/`k60_thermal_start` 三个 optional start——那是另三条线的事，需要 Lead 一起裁。

## 4. 如果将来要切 catalog，前置清单（按序，缺一项就别切）

1. `components.toml` 的 ArmCpu rev 从 `93a5030c` 升到 ≥`5f37026`，`os_abi` 加 `ios-27.0.1-24A446`（现为 `ipados-17.7.11-21H461`）。
2. ADT 生成器补 `/psci { compatible="arm,psci-1.0"; method="smc" }`（`scripts/make-pong-adt.py:235-269` 加节点，或 `dts/sm8475.dtsi:60-63` 的那个节点能被搬进 ADT）。
3. `board.toml:194-206` 加 `sheng-smp=1`（并确认 logical id 与 `ARMCPU_SMP_SLOTS` 的映射与我们 8 核一致）。
4. 删 `ArmDTPlatform.cpp:23` 与 `:224`（或给 catalog DTP 补 `pong_cpu_start`）。
5. `PongPower` 若进归档，睡眠实现改接 5f37026 的 `armcpu_sleep_register`。
6. 从 `patches/xnu-12377/series` 移除 0540 与 0532，否则 `psci_smp_*` 与 catalog `startCPU` 两条 CPU_ON 路径并存；0541 保留（与 ArmCpu 无关）。
7. 验证顺序：`armcpu_smp_step` 到 7 → 副核 `armcpu_smp_sys[8][5]` 有记录 → UFS 根能挂（SIGP 修好之后）。

## 5. 什么时候必须重开这个决定

| 触发 | 动作 |
|---|---|
| 27 上机后 SMP 起不来且 0540 路径被判死 | 重评 catalog + `/psci` + `sheng-smp`（§4 六步） |
| 27 需要 S2R | 先定睡眠实现来源（fork 搬入 / catalog ≥5f37026） |
| SPI owner 需求 > 4 | 切 catalog 的 16 槽 + 让 Lead 改 fixture 期望 |
| catalog 发布带 27 ABI 且默认有 `/psci` 的版本 | 按 §4 重跑一遍前置清单 |

## 6. 证据索引

- catalog 93a5030c：`E:/k60-work/scratch/platform27/ArmCpu-93a5030c.cpp`（`git show 93a5030c:ArmCpu.cpp` 于 `E:/hackios/ArmCpu`）；5f37026：`ArmCpu-5f37026.cpp`、`ArmCpuSleep-5f37026.h`。
- fork：`drivers/ArmCpu/ArmCpu.cpp`（779 行，行号见 §2/§3）。
- 补丁：`patches/xnu-12377/{0532,0540,0541}-*.patch`、`armcpu-sleep-hook.patch`；三者对 pristine `E:/hackios/xnu-12377` 的 `git apply --check` 全部通过（2026-11-21 复核）。
- XNU 原生：`osfmk/arm64/cpu.c:1024`（`ml_arm_sleep`）、`osfmk/kern/processor.c:1175`、`osfmk/arm/machine_routines.h:757`。
- 归档与参数：`board.toml:14`、`:21`、`:194-206`；`configs/mondrian_ios27_defconfig`。

## 6.5 三条缺口的只读检查（一条命令）

Lead 2026-11-21 批准的空窗期工具：`scripts/check-catalog-armcpu-gaps.py`。只读、离线、不碰 build、
不改 `board.toml`、不产出镜像；它读 `board.toml`（含 `os_overrides."ios-27.0.1-24A446"` 覆盖）、
`components.toml` 的 ArmCpu 钉版本、`scripts/make-pong-adt.py` 与 catalog 检出里那条 revision 的
`ArmCpu.cpp`，然后给三条缺口各一个三态结论：

| 状态 | 含义 | 退出码 |
|---|---|---|
| `SATISFIED` | 这条缺口在树里已经满足，切换时不必再算它 | — |
| `OPEN` | 缺口还在，并给出证明它的 `文件:行` | 1（有任一 OPEN） |
| `UNKNOWN` | 这里判不了，行里写明**缺哪个输入** | 2（无 OPEN 但有 UNKNOWN） |

`UNKNOWN` 是答案之一，不是敷衍：它必须打印缺什么（没有 catalog 检出 / 检出里没有那条 revision /
`components.toml` 没写 revision），这样下一个人知道去补哪一块，而不是把「读不到」当成「没问题」。

```sh
python3 scripts/check-catalog-armcpu-gaps.py            # 人读
python3 scripts/check-catalog-armcpu-gaps.py --json     # 机读
```

2026-11-21 实跑（本线工作树，钉版本 `93a5030c`）：

```
psci-node   OPEN      the ADT has the /psci node the catalog reads
    - catalog ArmCpu reads the /psci node: yes
    - ADT generator scripts\make-pong-adt.py: first psci mention at line 174; publishes a psci node: no
sheng-smp   OPEN      the 27 kernel_args opt the secondaries in
    - board.toml:396 is the 27 kernel_args list and none of its 7 entries is sheng-smp=1
sleep       OPEN      the catalog can register a platform sleep board
    - catalog revision pinned exports armcpu_sleep_register: no
    - the 27 archives/include carry PongPower: no
3 gap(s) still open        (rc=1)
```

三态是用样例树验过的，不是只跑了真实树：`E:/k60-work/scratch/platform27/selftest-gaps.py` 现搭两条
临时 lane —— 一条全满足（`psci` 节点在、`sheng-smp=1` 在、catalog 有 `armcpu_sleep_register`、归档
含 `PongPower`）报 `rc=0` 且三行全 `SATISFIED`；同一条把 `--catalog` 指向不存在的目录，两条相关缺口
转 `UNKNOWN` 并打印 `missing input: a catalog checkout with the pinned revision`、`rc=2`。结果
`SELFTEST OK`。

## 7. 外部证据（供 `porting.toml` 记录引用）

Lead（m00493 ②）把这条记录写进 `porting.toml`，本节只提供可复现的读数。全部命令在 2026-11-21 的本机 MSYS bash 里跑过，输出逐字照抄。

### 7.1 复现命令

```sh
cd E:/hackios/xnekom-ios27
git rev-parse --short HEAD
git log -1 --format=%s
diff -q drivers/ArmCpu/ArmCpu.cpp ../k60-platform27/drivers/ArmCpu/ArmCpu.cpp
md5sum drivers/ArmCpu/ArmCpu.cpp ../k60-platform27/drivers/ArmCpu/ArmCpu.cpp
grep -n '0532-k60-cpu-start-completion\|0540-k60-psci-smp\|0541-k60-virtual-timer' patches/xnu-12377/series
git log --oneline -5 -- drivers/ArmCpu/ArmCpu.cpp
grep -rln 'T0SZ_USER\|native_pmap_user_mappings\|pmap_pt_attr_4k_user' patches/
```

### 7.2 读数

| 项 | 读数 |
|---|---|
| xnekom-ios27 HEAD | `dec42748 docs(storage): show why three targets miss console`（分支 `feat/xnu27-data-gate`，`ahead 59, behind 19` 相对本仓库 main） |
| `diff -q` 两只 `ArmCpu.cpp` | 无输出，rc=0 —— 逐字节相同 |
| md5 | 两侧同为 `f05a3216b4e6f0feaa7a65babdffac59` |
| 27 series 行号 | `:65 0532-k60-cpu-start-completion.patch`、`:87 0540-k60-psci-smp.patch`、`:91 0541-k60-virtual-timer-guard.patch` |
| 该文件的维护提交 | `24746184 fix(power): mark secondary CPUs stopped before sleep`、`1c662ecd fix(power): keep the platform sleep path quiet until resume`（更早：`cea7d9bd`、`7e2d88b8`、`4216ae6d`） |
| xnekom 是否带 T0SZ/pmap 补丁 | 否 —— `grep -rln` 在 `patches/` 无输出；它的 27 树没有用户 VA 那组改动 |

### 7.3 这条证据能证明什么、不能证明什么

- 能证明：27 时代存在一棵与本板同源（`PongUfs` / `K60PlatformSleep` / 同一份 779 行 fork）的树，它用同一个 fork 走 27，并且还在为这个文件修睡眠路径；`porting.toml:199` 那条「用 catalog ArmCpu」的记录在同源树里没有兑现，原因正是 §0 的三条缺口。
- 不能证明：该 fork 能在 `24A446` 上把 SMP 拉起来。本板至今没有 27 的 SMP 上机记录（§5 第一行的触发条件仍开着），所以这条记录应写成「沿用同源树的实际选择」，不要写成「已验证可用」。
- `diff` 为空只说两份文件相同，不说它们都对；`behind 19` 意味着 xnekom 也没跟上本仓库 main 的这 19 个提交，比对时机见 7.1 的 HEAD。
