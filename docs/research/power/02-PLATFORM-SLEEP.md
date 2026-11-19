# 平台睡眠（官网 §5 末段）调研

状态：**ArmCpu 等待路径 + XNU hook + 板级 hook 已实现，host 73 + 1038 项断言，未上机**。官网
`https://unixnu.com/zh/porting/power` 的平台睡眠段落（快照 `E:/k60-work/scratch/power-page-20261117.txt:119-121`）
描述的是板级 XNU 睡眠 hook 与 ArmCpu 挂起路径。2026-11-19 已把 UniXNU/ArmCpu 组件的
`ArmCpuSleep.h` 与等待路径移植进本仓库的 vendored `drivers/ArmCpu`，补丁 `0623` 提供 XNU 侧
hook，板级记录在 `drivers/PongPower/K60PlatformSleep.cpp`；本文保留 sheng 参考事实、K60 现场
FDT 映射和剩余缺口（电源键 SPI 路由、看门狗喂狗、背光/触摸恢复）。

## 1. 官网要求

原文（:119-121）要点：

- `platform-sleep=1` 选择板级 XNU 睡眠 hook 和 ArmCpu 挂起路径。
- 辅助 CPU 通过 PSCI `CPU_OFF` 关闭，启动 CPU 单独等待开盖、电源键或
  `platform-sleep-wake-after=<秒数>` 指定的期限。
- 被拒绝的中断要被确认，唤醒后恢复保存的中断使能状态。
- 睡眠期间板级回调每 10 秒喂一次已接管的固件看门狗。
- 开盖或按电源键请求完整唤醒；背光等两帧显示后恢复，最长 1500 ms，没有帧计数时 600 ms；
  触摸板报告间隔超过 60 ms 时重新建立触点位置；合盖时释放屏幕触点，开盖后恢复触摸报告。

这些是平板（sheng，带键盘盖/霍尔传感器）的语义。K60 是手机，没有开盖传感器，
对应关系见 §3。

## 2. sheng 参考实现

文件（`origin/main`，BSD-2-Clause-Patent）：

| 文件 | 大小 | 作用 |
| --- | --- | --- |
| `package/ShengSleep.h` | 90 行 | 纯逻辑：引脚过滤、INTR_CFG 掩码、开盖/电源键判定、唤醒原因文本 |
| `package/ShengSleep.cpp` | 195 行 | 板级 hook、TLMM 映射、ArmCpu 注册、睡眠/唤醒通知 |
| `drivers/ArmCpu/ArmCpuSleep.*`（XNU 树） | — | `armcpu_sleep_register`、GIC 掩码、PSCI `CPU_OFF`、唤醒等待 |
| `package/tests/sheng_sleep_host.c` | 7,084 B | 纯逻辑 host 测试 |

关键事实：

- 入口 boot-arg `platform-sleep=1`；`sheng_sleep_probe()` 先映射 TLMM，再
  `kernel_thread_start` 一个名为 `sheng sleep` 的线程。
- `armcpu_sleep_board`（56 字节）字段：`prepare`、`should_wake`、`restore`、
  `wake_spis`、`wake_spi_count`、`tick`、`tick_s`；`armcpu_sleep_stats` 48 字节，
  读 `phase/entries/spurious/last_intid/last_reason/cpu_off_failures/asleep_ticks/masked/ticks/unarmed`。
- 唤醒源：霍尔传感器 TLMM GPIO 171（低有效，0 = 合盖），走 TLMM 汇总中断 SPI 208
  （INTID 240）；电源键 PMK8550 PON 中断 bit 7（`0x80`），走 SPMI arbiter 的
  PDC 唤醒（SPI 481，INTID 513）。
- TLMM：sheng 映射 210 个引脚，`TB_TLMM_BASE` + `TB_GPIO_STRIDE`；保留区
  `gpio-reserved-ranges = <36 4>`（36..39 安全引脚，访问会 abort）。
- 寄存器：`IO 0x4`（bit0 电平）、`INTR_CFG 0x8`（bit0 enable、bit1 polarity、
  bits3:2 detection：0 电平/1 上升/2 下降/3 双边、bits7:5 target，3 = AP）、
  `INTR_STATUS 0xc`。
- `prepare`：保存全部 210 个 INTR_CFG；除开盖引脚外，把所有 target=AP 的 enable 关掉；
  开盖时若合盖，则把开盖引脚设为电平+极性并使能（开盖即挂起中断）。
- `should_wake`：读开盖引脚电平，或调用 `sheng_buttons_sleep_check()` 查电源键；
  读到合盖时清状态，让汇总中断落下。
- `restore`：把保存的 INTR_CFG 写回；睡眠期间锁存的状态保留给驱动。
- 睡眠/唤醒兴趣：`kIOMessageSystemWillSleep` 记录合盖状态并打印
  `sheng sleep: sleeping, lid ...`；`kIOMessageSystemWillPowerOn` 调
  `root->claimSystemWakeEvent(root, 0x1, ...)`；`kIOMessageSystemHasPoweredOn`
  打印 `sheng sleep: woke by %s (intid %u) after %llu ms; sleeps ... cpu_off failures ...`
  并调 `root->requestUserActive`。
- 看门狗：`boot_reset_watchdog_ping()` 弱符号，ArmCpu 的 `tick` 每 10 秒调用一次。
- 唤醒日志来源：`lid` / `power` / `timer` / `storm` / `nothing`。
- 限制：唤醒它的按键按下与释放不会报告给 macOS（`sheng_sleep_swallow` 吞掉）。

## 3. K60 现场 FDT 能确认的硬件

来源：`E:/k60-work/reports/live-6033dbec-fdt.dtb`（真机 FDT 转 `/tmp/live.dts`，34,801 行）。

| 项 | K60 值 | 与 sheng 的差异 |
| --- | --- | --- |
| TLMM 节点 | `pinctrl@f000000`（`reg = <0xf000000 0x1000000>`，`compatible = "qcom,cape-pinctrl"`） | 基址不同（sheng 用 `TB_TLMM_BASE`），窗口更大 |
| TLMM 汇总中断 | `interrupts = <0 0xd0 4>` = SPI 208，INTID 240 | **相同** |
| 保留 GPIO | `qcom,gpios-reserved = <28 29 30 31 36 37 38 39>` | sheng 只有 36..39 |
| 开盖/霍尔 | FDT 中没有 hall/lid 节点，`gpio-keys` 只有 `vol_up` | K60 无开盖语义 |
| 电源键 | PMK8350 PON `pwrkey`，`interrupts = <0 0x13 0x07 0x03>`（SPMI slave 0、peripheral 0x13、irq 7、双边） | 与 sheng 的 PON bit7 同类，但 SPMI 中断到 GIC 的映射未确认 |
| PMIC arbiter | `qcom,spmi@c42d000`（`spmi-pmic-arb`） | 唤醒所需 PDC/SPI 号未在 FDT 里直接给出 |
| 键盘盖/触摸 | 本分支 `drivers/` 没有 `PongTouch`；触摸与键盘盖在别的分支 | 背光/触摸恢复时序只能等触摸分支 |

结论：K60 的可行唤醒源是**电源键**和 `platform-sleep-wake-after` 期限；没有开盖传感器，
sheng 的 lid 路径应整体去掉，TLMM 掩码逻辑仍可复用（汇总中断 INTID 相同）。

## 4. 本仓库缺什么

- ~~`drivers/ArmCpu` 只有 `ArmCpu.cpp`/`Info.plist`/`LICENSE`，没有
  `ArmCpuSleep.cpp/.h`~~：2026-11-19 已加入 `ArmCpuSleep.h` 并把等待路径并进 `ArmCpu.cpp`。
- 没有 TLMM 访问层：`K60PmicRail` 只读 RPMh，`K60CpuFreqProbe` 只映射 EPSS 窗口，
  没有任何引脚/中断配置代码。
- 没有 `BootReset`/看门狗喂狗接口；官方要求的 10 秒喂狗在本树无落点。
- 没有背光/触摸的睡眠恢复回调；`PongTouch` 不在本分支。
- 显示与音频分支各自持有相关驱动，平台睡眠必须等它们落主线后再接入，否则会重复实现。

## 5. 实现顺序（建议；2026-11-19 的落点见 §7）

1. **XNU 侧**：从 sheng 的 XNU 树移植 `ArmCpuSleep`（GIC 掩码、PSCI `CPU_OFF`、
   启动核等待、`armcpu_sleep_register` 与 stats）。这是最大的一块，且改动的是调度/中断核心路径，
   必须单独分支、单独评审。
2. **板级 hook**：新建 `K60Sleep.cpp`，映射 TLMM `0x0f000000`，读 PON 状态，
   实现 `prepare/should_wake/restore`；没有 lid，`should_wake` 只查电源键。
   纯逻辑（掩码计算、唤醒原因）可先做成 `K60SleepPlan.c` 并 host 测试，和 EPSS 的做法一致。
3. **PMIC 唤醒映射**：确认 PMK8350 PON 中断经 SPMI arbiter/PDC 到 GIC 的 SPI 号，
   否则 `should_wake` 读不到按键。
4. **看门狗**：确认固件看门狗是否已被本树接管；未接管就不要喂，避免掩盖真实挂起。
5. **显示/触摸恢复**：等显示与触摸分支合并后接背光 1500/600 ms 与触摸 60 ms 规则。
6. **真机验证**：`platform-sleep=1`，记录 `sheng sleep:` 等价日志、唤醒源、唤醒耗时、
   `cpu_off failures`，并做一次 30 秒以上的 `wake-after` 睡眠。

## 6. 已实现的纯逻辑模块（2026-11-18）

没有内核挂起路径，但掩码/唤醒判定可以先独立验证，和 EPSS 的
`K60CpuFreqPlan` 做法一致：

- `drivers/PongPower/K60SleepPlan.h` + `.c`：210 引脚计数、保留区
  `28..31/36..39`、`INTR_CFG` 的 enable/polarity/detection/target 位、
  `k60_sleep_pin_usable`、`k60_sleep_mask_tlmm`（只清 target=AP 且可用引脚的
  enable，保留脚不动，容量不足返回 0 且不写输出）、`k60_sleep_pin_pending`、
  `k60_sleep_power_wakes`（PON bit7，实时或锁存）、`k60_sleep_swallow`、
  `k60_sleep_deadline_reached`、`k60_sleep_woke_by`，以及 2026-11-19 补上的唤醒路径数值：
  `k60_sleep_watchdog_due`（睡眠中每 10 s 喂狗）、`k60_sleep_wake_after_ms`
  （`platform-sleep-wake-after` 秒→毫秒）、`k60_sleep_backlight_ready`（两帧，最长
  1500 ms，无帧计数 600 ms）、`k60_sleep_touch_reestablish`（报告间隔严格大于 60 ms
  才重建触点，0 表示无接触）。
- 没有开盖分支：K60 FDT 没有 hall 节点，`K60WakePower` 与 wake-after 是仅有的来源。
- `scripts/tests/test-k60-sleep-plan.c`：73 项断言，覆盖保留区、非 AP target 不变、
  已关闭位不变、容量不足不写、PON 实时/锁存、按键吞掉与释放、deadline、唤醒原因文本，
  以及喂狗周期、wake-after 换算、背光两帧/1500/600 三条路径和触摸 60/61 ms 边界。
  运行：`cc -Wall -Wextra -Werror -std=c11 -o /tmp/tk60sleep scripts/tests/test-k60-sleep-plan.c drivers/PongPower/K60SleepPlan.c && /tmp/tk60sleep`
  → `TESTS OK 73 checks (0 failures)`。整套离线电源套件用 `bash scripts/tests/run-k60-power-host.sh` 一次跑完（七个套件 1530 项，见 `00-POWER-PAGE-CONFORMANCE.md` §6）。
- 模块没有调用者：没有 TLMM 映射、没有 PON 读取、没有 ArmCpu 注册；喂狗、背光、
  触摸三个判定也只是把官网数值钉进 host 断言，显示/触摸驱动与看门狗接管都还没接；
  这些仍属 §5 的实现步骤。
  引脚总数 210 来自同一 TLMM IP 的参考值，现场 FDT 未给出，接板级 hook 时要先读硬件计数。

## 7. 实现（2026-11-19）

- `drivers/ArmCpu/ArmCpuSleep.h`（124 行，BSD-2-Clause-Patent，取自 UniXNU/ArmCpu
  `73c2360`）提供 `armcpu_sleep_board`（56 B）、`armcpu_sleep_stats`（48 B）与
  keep/decide/deadline/timer/pending/storm 的内联规则；`ArmCpu.cpp` 增加等待路径：
  `prepareGic()` 读 `platform-sleep` 与 `platform-sleep-wake-after`，仅在值为 1 且
  XNU 侧符号存在时安装 `arm64_platform_sleep_hook`；`quiesceCPU()` 在
  `gSleepEnabled && ml_is_quiescing()` 时先进入 `ml_arm_sleep()`。
- 启动核在 `sleepBootWait()` 保存 GICD_ISENABLER，按板级 `wake_spis` 只保留唤醒源，
  其余 SPI 关闭，CNTV 期限取 wake-after 与 10 s tick 的较小值，WFI 后用 timer PPI 27、
  GICD_ISPENDR 与 `should_wake()` 判定；被拒中断确认并计数，同一 INTID 在 1 ms 窗口
  内达到 1000 次即 masks 该线并返回 storm；结束时恢复保存的使能。其他核在
  `sleepCoreOff()` 里关 CNTV/GIC 后调用本仓库已有的 `psci_smp_cpu_off()`。
- XNU 补丁 `patches/xnu/0623-k60-platform-sleep.patch`（33 行，接在 `0622` 之后）在
  `ml_arm_sleep` 启动核 `mt_sleep()` 之后调用 hook 并 `arm_init_cpu()`，在辅助核
  `arm64_prepare_for_sleep(true)` 之前调用 hook(FALSE)。没有 IOPMrootDomain 解锁块：
  `gSleepDisabledFlag` 默认为 0，当前树里也没有 `sleep-disabled` 属性；没有 sheng 的
  `sheng_sigp_recover` 自 IPI 恢复块，等真机需要时再加。
- 板级 `drivers/PongPower/K60PlatformSleep.cpp` 注册一个 timer-only 的 board
  （`wake_spis=nullptr`、10 s tick），`prepare/restore/tick` 各打一条 `K60Sleep:` 日志；
  从 `k60_physical_battery_start()` 调用，早于电池 lease 检查。PON 电源键的 SPI 481/
  INTID 513 路由尚无驱动配置，因此第一版不注册它，避免把一条永远不触发的线当成唤醒源。
- 验证：`scripts/tests/test-armcpu-sleep.c`（组件 host 测试适配，1038 项）覆盖掩码、
  决策、绝对期限、tick、pending、storm 与结构体大小；`bash scripts/tests/run-k60-power-host.sh`
  七套件 1530 项全过。battery archive 140,048 B sha256 `f867efca…`；ArmCpu 目标文件
  37,400 B，`llvm-nm` 可见 `_armcpu_sleep_register`、`_armcpu_sleep_stats`、
  `_armcpu_sleep_last_cpu_off_rc`，并引用 `_arm64_platform_sleep_hook`/`_ml_arm_sleep`。
  image z 第一次链接在 bootstrap 阶段失败：该阶段只强制加载 GPU 与电池 archive，
  没有加载 ArmCpu，电池 archive 里新增的 `armcpu_sleep_register` 引用因此未定义；
  commit 407ea557 在电池之前补上 `-Wl,-force_load,$ROOT/build/armcpu/libArmCpu.a`，
  image z（默认不带 `platform-sleep`）随后构建成功：boot.img 201,887,744 B sha256
  `b167d4f9…`、kernel `df50f894…`、payload `facd5bc5…`；`llvm-nm` 在 kernel 里看到
  `_armcpu_sleep_register`、`_k60_platform_sleep_register`、`_arm64_platform_sleep_hook`。
  未上机。

## 8. 边界

- 已实现的是等待路径与 XNU 接线，不是“平台睡眠已验收”：image z 必须先在默认参数下
  正常启动，证明 hook 只在 `platform-sleep=1` 时生效；随后才用
  `platform-sleep=1 platform-sleep-wake-after=5` 做一次 5 s 睡眠/唤醒。
- 电源键唤醒仍缺 SPMI/PDC 到 SPI 481 的路由与 PON 锁存清除；看门狗没有可写的固件
  端点（`IOWatchdog` 只是软件 check-in 服务），tick 只记录；背光 1500/600 ms 与触摸
  60 ms 恢复要等显示/触摸分支提供回调。以上都不影响 timer 路径的首次验证。
- §5 的 CPU 探针/投票（`docs/research/power/01-EPSS-PROBE.md`）与本文件是两条线，
  不要混为“§5 已完成”。

## 9. 参考

- 官网快照：`E:/k60-work/scratch/power-page-20261117.txt:119-121`。
- sheng：`origin/main` `package/ShengSleep.h`、`ShengSleep.cpp`、
  `tests/sheng_sleep_host.c`；`porting.toml` power 区记录 `platform-sleep=1`。
- K60 现场 FDT：`E:/k60-work/reports/live-6033dbec-fdt.dtb`（TLMM、PON、gpio-keys 节点）。
- 本仓库：`drivers/ArmCpu/`、`drivers/PongPower/K60CpuFreqProbe.cpp`、`K60PmicRail.h`。
