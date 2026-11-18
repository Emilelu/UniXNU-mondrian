# 平台睡眠（官网 §5 末段）调研

状态：**调研记录 + 纯逻辑模块（host 53 项断言），未上机**。官网 `https://unixnu.com/zh/porting/power` 的平台睡眠段落
（快照 `E:/k60-work/scratch/power-page-20261117.txt:119-121`）描述的是板级 XNU 睡眠 hook 与
ArmCpu 挂起路径；本仓库当前没有任何实现。本文记录 sheng 参考实现的事实、K60 现场 FDT 能确认的
硬件映射，以及真正实现前缺什么。

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

- `drivers/ArmCpu` 只有 `ArmCpu.cpp`/`Info.plist`/`LICENSE`，没有
  `ArmCpuSleep.cpp/.h`；全树 grep `armcpu_sleep`、`platform-sleep` 均为 0 命中。
- 没有 TLMM 访问层：`K60PmicRail` 只读 RPMh，`K60CpuFreqProbe` 只映射 EPSS 窗口，
  没有任何引脚/中断配置代码。
- 没有 `BootReset`/看门狗喂狗接口；官方要求的 10 秒喂狗在本树无落点。
- 没有背光/触摸的睡眠恢复回调；`PongTouch` 不在本分支。
- 显示与音频分支各自持有相关驱动，平台睡眠必须等它们落主线后再接入，否则会重复实现。

## 5. 实现顺序（建议）

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
  `k60_sleep_deadline_reached`、`k60_sleep_woke_by`。
- 没有开盖分支：K60 FDT 没有 hall 节点，`K60WakePower` 与 wake-after 是仅有的来源。
- `scripts/tests/test-k60-sleep-plan.c`：53 项断言，覆盖保留区、非 AP target 不变、
  已关闭位不变、容量不足不写、PON 实时/锁存、按键吞掉与释放、deadline、唤醒原因文本。
  运行：`cc -Wall -Wextra -Werror -std=c11 -o /tmp/tk60sleep scripts/tests/test-k60-sleep-plan.c drivers/PongPower/K60SleepPlan.c && /tmp/tk60sleep`
  → `TESTS OK 53 checks (0 failures)`。
- 模块没有调用者：没有 TLMM 映射、没有 PON 读取、没有 ArmCpu 注册；这些仍属 §5 的实现步骤。
  引脚总数 210 来自同一 TLMM IP 的参考值，现场 FDT 未给出，接板级 hook 时要先读硬件计数。

## 7. 边界

- 本文的代码只有纯逻辑掩码模块，没有内核挂起路径、TLMM/PON 访问与真机睡眠；§5 的 CPU 探针/投票（`docs/research/power/01-EPSS-PROBE.md`）
  与本文无关，不要混为“§5 已完成”。
- 没有上机证据前，平台睡眠状态只能是“未实现”。官网 §5 的其余部分（GPU 的 GMU 读取/HFI 投票、
  外设投票所有权、fence 等待）同样未实现。

## 8. 参考

- 官网快照：`E:/k60-work/scratch/power-page-20261117.txt:119-121`。
- sheng：`origin/main` `package/ShengSleep.h`、`ShengSleep.cpp`、
  `tests/sheng_sleep_host.c`；`porting.toml` power 区记录 `platform-sleep=1`。
- K60 现场 FDT：`E:/k60-work/reports/live-6033dbec-fdt.dtb`（TLMM、PON、gpio-keys 节点）。
- 本仓库：`drivers/ArmCpu/`、`drivers/PongPower/K60CpuFreqProbe.cpp`、`K60PmicRail.h`。
