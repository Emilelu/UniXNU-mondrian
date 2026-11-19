# LEVEL-MAP · 154 个 DTS trip 怎么变成可发布的等级

> 2026-11-15。回答 Lead 的问题：把 DTS 154 个 trip 里的 passive 档映射成 `Thermal_Level_Warning`
> 1/2/3 的只读映射层（不注册执行器、不降频）。
> **结论：发布板子自己的 0..3 档，不发布 Apple 的 0/5/100/110。** 32 个 tsens zone 各带 2–3 档被动
> trip，最高 zone 胜出；冷机用 `pong_thermal_bias` 也能验证 1/2/3 三档。

## 0 三问三答

| 问题 | 答案 | 章节 |
| --- | --- | --- |
| 用哪些 trip？ | 32 个 tsens zone 的 101 个 passive trip，按温度去重后 **83 档**；25 个 QMI zone 与 mx-pe/isense_trim 排除 | §1 §2 |
| 档位怎么算？ | 每个 zone 独立算 0..档数，已越过的 trip 只在低于「温度 − DT hysteresis」时释放；板级取最高 zone | §3 |
| 发布什么？ | `0..3` 原样发到 `Thermal_Level_Warning`，纯遥测；100/110 才动 `thermalWarningState`，本阶段不发 | §4 |
| 怎么验证？ | `pong_thermal_bias` 抬 45/70/80 K，看 `level 1/2/3` 与 `closest` 行的余量 | §5 |

## 1 数据基础：154 个 trip 的全貌

- `/thermal-zones` 在 `mondrian.dts:6643-8422`：**58 个 zone、154 个 trip**，其中 8 个 `active`（全在
  mdmss-0..3，102000/105000）与 146 个 `passive`。
- 146 个 `passive` 里有 4 个不是温度：mx-pe 的 `1/2/3`（`mondrian.dts:8344`、`:8351`、`:8358`，且
  `:8336` 是 `status = "disabled"`）与 isense_trim 的 `2`（`:8397`）。
- 32 个 tsens zone 占 **101 个** passive trip；其余 41 个在 25 个走 QMI 代理的 zone 上
  （`thermal-sensors = <0x5c …>`，phandle `0x5c` 是 `qmi-ts-sensors`，`mondrian.dts:16774`）。
- 101 个里 **18 个是重复的 125℃**：13 个 CPU zone、2 个 gpuss、3 个 nspss 同时带 thermal-engine 与
  thermal-hal 两份 125℃ trip（例：`mondrian.dts:7220` 与 `:7288` 都是 cpu-1-0 的 125℃）。
  按温度去重后 = **83 档**，即 `K60ThermalZones.c:22` 那张表的 32 行。
- 档数分布：**19 个 zone 3 档**（13 个 CPU + 2 个 GPU + 3 个 NPU + 1 个 DDR），**13 个 zone 2 档**
  （aoss-0/1、cpuss-0..3、video、mdmss-0..3、camera-0/1）。
- 档位温度只有 5 个值：125℃（每个 zone 的顶档）、115℃（每个 zone 都有）、110℃（13 个 CPU zone 的最低档）、
  95℃（gpuss-0/1 与 nspss-0..2 的最低档）、90℃（只有 ddr）。**没有一个全板统一的档位阶梯** —— 这是 §4 的出发点。

## 2 排除项

### 2.1 25 个 QMI zone

这些 zone 的 `thermal-sensors` 指向 `0x5c`（qmi-ts-sensors，`mondrian.dts:16774`），温度来自 modem 侧代理，
不在本内核映射的任何窗口里（XNU 只有 tsens0/tsens1 两个 TM 窗口，`01-SAME-HARDWARE.md` §1）。
它们的 passive trip 一律是 125℃（或 125℃ 两份），没有低档可映射，本地也读不到：

```
pa(0) pa1(1) bcl-warn(31) sdr0-pa0(32) sdr0(38) sdr1-pa0(39) sdr1(45)
sdr-mmw-therm(29) mmw0..3(46-49) mmw_pa1..3(26-28) mmw-ific0(50)
sub1-modem-cfg(51) sub1-lte-cc(52) sub1_mcg_fr1_cc(53) sub1_mcg_fr2_cc(54)
sub1_scg_fr1_cc(55) sub1_scg_fr2_cc(56) sdr0-pa(64) sdr1-pa(65) isense_trim(130)
```

（括号里是 `thermal-sensors` 的传感器索引；isense_trim 的 passive 值 `2` 也不是温度。）

### 2.2 mx-pe

没有 `thermal-sensors`，三个 passive 值是 `1/2/3`（不是温度），且 `mondrian.dts:8336` 写着
`status = "disabled"`。它的 cooling-map 指向 cdsp/kgsl/modem（`mondrian.dts:8369-8384`），
本来就不是给 AP 自己用的。

## 3 等级定义与算法

| level | 含义（`K60ThermalZones.h:14-18`） |
| --- | --- |
| 0 | 这个 zone 没有任何被动 trip 被越过 |
| 1 | 最低温被动 trip 被越过 |
| 2 | 第二档被越过 |
| 3 | 第三档被越过（只有 2 档的 zone 停在 2） |

板的等级 = **所有 zone 等级的最大值**（`K60ThermalZones.c:135-154`）。

**滞回**：已经越过的 trip 只有在低于「温度 − DT 给的 hysteresis」时才释放，直接复用
`K60ThermalLevel.c:95-115` 的 `k60tl_input_level()`（`K60ThermalZones.c:128` 调用它，
自己不再实现一遍）：threshold = crossed ? trips[t].milli_c − trips[t].hysteresis_mc : trips[t].milli_c；
`if (milli_c < threshold) break;`。

**无读数**：`K60TL_NO_READING`（INT32_MIN）→ 该 zone 等级 0 且清空它的 crossed
（`K60ThermalLevel.c:103` 的 `if (milli_c == K60TL_NO_READING) return 0;`，经 `K60ThermalZones.c:128` 转调）
—— 一路读不到的传感器既不能抬高等级，也不能把等级卡住。

**为什么取最高 zone 而不是平均或最热传感器**：zone 是 DTS 的热区粒度；不同 zone 的档位温度本来就不同
（GPU 95℃、CPU 110℃、DDR 90℃），取「最高 zone」就是「谁最接近它自己的真实 trip」，这是唯一不需要
跨传感器发明权重的口径。

## 4 为什么发布 0..3，而不是 Apple 的 0/5/100/110

`IOPMrootDomain` 对任何值都会记进 "Power Status" 字典并广播（`iokit/Kernel/IOPMrootDomain.cpp:8172-8188`），
但只有 **100（Warning）与 110（Trap）** 会把 `thermalWarningState` 置 1（`:8133-8134`）；0/5/10 发出去
只有记录，没有动作。所以「发哪个数」决定的不是「系统能不能看见」，而是「要不要触发警告状态」。

三个理由说明本阶段不该发 100/110：

1. **档位不齐，硬映射要发明规则**：DTS 的 95℃ 在 GPU 是第 1 档、在 CPU 只是第 2 档；110℃ 在 CPU 是第 1 档、
   在 GPU 是第 3 档。要把 0..3 映射成 100/110，就得先决定「GPU 第 1 档算不算 Warning」——
   这是跨传感器策略，不是映射。
2. **本板没有执行器**：`TRIP-DESIGN.md` §3.5 的结论是只上报不注册执行器；`thermalWarningState` 唯一的效果是
   睡眠策略（`IOPMrootDomain.cpp:7411-7412`、`:7485`、`:7514`），在 45–56℃ 的冷板上发 Warning 只会让系统误判。
3. **没有消费者**：`thermalmonitord` 目前被 `userland/mkjobs.py:217` 的 DENY 列表挡住；`mTPL` 是 SMC 键，
   要 `AppleSMCSensorDispatcher`（kext 路线，`06`/`07` 篇），不是这条 in-tree 路线。

**什么条件下改发 100/110**（重考触发条件，与 `TRIP-DESIGN.md` §3.5 的三条并列）：

- 出现真正的用户态消费者（`thermalmonitord` 或自己的 daemon 读 "Power Status"）；
- 有了至少一个执行器，让 Warning 有动作可做；
- 或 Apple 侧 prelink/kext 路线需要 `mTPL`，那时在 kext 里发 100/110，而不是在这里改。

在那之前，`0..3` 是**纯遥测**：`pong_thermal_pm.cpp` 不去查任何 Apple 常量表，直接 `value = (uint32_t)level;`
（`drivers/PongThermal/pong_thermal_pm.cpp:100`），日志里也就没有「level 1 = 什么 Apple 值」的歧义。

## 5 上机判据

### 5.1 不需要 bias 就能看到的

`thermal-20261114f` 已给出控制器行与 31 路读数（`08-KERNEL-DRIVER.md` §5 第 2 条）。新版应多出这一行（45℃ 冷机示例）：

```
PongThermal: level 0/3 nominal (domains 0/3); closest ddr 45.0 C, 45.0 C below tier 1
```

它证明阶梯在跑、且能报出「离最低档还有多远」——冷机上 level 永远是 0，没有 `closest` 就分不清
「阶梯正常但没到档」与「阶梯没跑」。

### 5.2 用 `pong_thermal_bias` 验证 1/2/3

`pong_thermal_bias` 给每路有效读数加一个固定偏移（`pong_thermal.c` 的 `pong_thermal_bias()`），
只改上报值、不改硬件。45℃ 冷板上的算式：

| bias（mC） | 哪一路先到档 | 期望 level | 期望 closest 行 |
| --- | --- | --- | --- |
| +45000 | ddr 90.0（90000） | 1 | `closest ddr 90.0 C, 25.0 C below tier 2` |
| +70000 | cpu-1-x / ddr / gpuss 115.0 | 2 | `closest ddr 115.0 C, 10.0 C below tier 3` |
| +80000 | cpu-1-x / ddr 125.0 | 3 | `closest ddr 125.0 C, every tier crossed` |

建议实际用 **+50000 / +75000 / +85000**：读数会漂 ±2℃，留 5℃ 余量比卡在边界上好判。
三档各自应伴随一行 `PongThermal: level N/3 … published as Thermal_Level_Warning=N`（发布层只在等级变化时发）。

**`pong_thermal_bias` 是构建期参数，不是运行期参数。** `build-strict.sh --kernel-arg pong_thermal_bias=<mC>`
把它写进 payload 的 `unixnu.toml`（`payload.py:130-133` 对 `--kernel-arg` 给的名字会剥掉 board 值再追加），
固件只读那份 TOML 传给内核（P-159），镜像头 `cmdline` 里的东西固件不用。所以**每一档 = 一次构建 + 一次上机**，
不是拿一张镜像飞三次改参数。已按此出一张 `thermal-20261115b`（`--kernel-arg pong_thermal_bias=85000`），
对应上表第三行；若 85000 没推到 `level 3/3`，再回头构建 50000 与 75000 两档。

「只在等级变化时发」是设计，不是丢行：`pong_thermal_pm.cpp:87-89` 里 `pong_thermal_pm_have_last && level == last`
就直接 return。所以冷机全程 0 档、208 轮采样，日志里**恰好只有一条** published 行 ——
`CRITERIA.toml` 的 `published.line` 因此写 `min = 1, max = 1`：少一条是发布层没跑，
多一条才说明去重坏了（同等级发两次）。bias 档中途真跨档时会合法地多出一条，那是信息不是误报。

### 5.3 判据表

人眼版（下表）；同一批判据的可机读版本在 `docs/research/thermal/CRITERIA.toml`（34 条），
由 `scripts/check-thermal-log.py` 施加到日志上，不用再逐行对着看：

```sh
python3 scripts/check-thermal-log.py                      # 取最新的 usblog-*/console.log
python3 scripts/check-thermal-log.py --log <console.log>   # 指定一份
python3 scripts/check-thermal-log.py --profile cold        # 强制 profile（默认从 bias 行推断）
python3 scripts/check-thermal-log.py --self-test           # 自测：干净的日志必须过、每一处改动必须挂
```

退出码 0 只在所选 profile 的 required 判据全过时给出；advisory 只打印不改变退出码。
每条判据 = 正则 + 期望 + 失败解释（`why` 字段就是下表「先查哪里」那一列）。

| 现象 | 判定 |
| --- | --- |
| `level 1/2/3` 与 `published as …=1/2/3` 同时出现 | 阶梯与发布层都正确 |
| `level` 变了但 `published` 没变 | 发布去重正常（只在等级变化时发），看是否有多次变化 |
| 冷机日志里 published 行多于 1 条 | 去重坏了（同等级重复发布）—— `published.line` 的 `max = 1` 会挂 |
| 全程 `level 0/3` 但 `closest` 有读数 | 阶梯在跑，只是没到档（冷机正常） |
| 没有 `closest` 行 | 32 路全部无读数 —— 异常，先查控制器行与传感器行 |
| `bias` 行不出现 | boot-arg 没传进去（检查拼写与 boot-args 长度预算） |
| 32 路里少 1 路 | 控制台并发丢行，不是传感器故障（`08-KERNEL-DRIVER.md` §5 第 2 条已查实 cpuss-2 那一路） |

### 5.4 不要做的

不要用 `pong_thermal_bias` 当标定（本板没有 `qcom,tsens-calibration`，`01-SAME-HARDWARE.md` §4），
不要因为它能造出 125℃ 就去写 trip 或 SROT_CTRL —— 这条线始终只读（`TRIP-DESIGN.md` §3.5）。

### 5.5 下一次上机判据（cooling map 之后）

冷却映射接线之后要判的是「压档真的压到了硅」，三件事同时成立才算过：

1. `PongThermal: level 3/3 trapping` —— 阶梯到了最高档（`drivers/PongThermal/pong_thermal.c:187` 的 `every tier crossed` 分支，`K60ThermalZones.c` 的 3 档 zone 全过）；
2. `PongThermal: level trapping (3) published as Thermal_Level_Warning=3` —— 发布层把 3 送进 `IOPMrootDomain`（`drivers/PongThermal/pong_thermal_pm.cpp:112`）；
3. **CPU 频率读数下降** —— 这一条目前**没有接口**，必须先补读数。下面是 2026-11-15 的查证结果。

#### 频率从哪读

| 候选 | 结论 |
| --- | --- |
| `hw.cpufrequency` / `_min` / `_max` sysctl | 存在（`bsd/kern/kern_mib.c:894-896`，handler `bsd/kern/kern_mib.c:829-848`），但读的是 `gPEClockFrequencyInfo`，**只在启动时从 ADT 的 `clock-frequency` 填一次**（`pexpert/arm/pe_identify_machine.c:149-151`），是静态值，证明不了 DVFS |
| `IOCPU` 的 `clock-frequency` 属性 | 同上：`iokit/Kernel/IOCPU.cpp:369-374` 把同一份静态值发布成属性 |
| `CPU_Speed_Limit` 键 | 只有定义（`iokit/IOKit/pwr_mgt/IOPM.h:734`），树内零消费者，发布它不会降频 |
| EPSS 性能状态寄存器 | **唯一诚实的活动读数**：`mondrian.dts:854-858` 有 `qcom,cpufreq-hw-epss`，`freq-domain0/1/2` = `0x17d91000` / `0x17d92000` / `0x17d93000`（各 0x1000），另有 `0x17d09804` / `0x17d09808` / `0x17d0980c` 三个 pdmem 寄存器；`mondrian.dts:869-872` 是配套的 debug 节点 |

EPSS 读法按 mainline `qcom-cpufreq-hw.c` 的语义：读每个 domain 的 perf-state 寄存器得到 LUT 下标，下标变小 = 频率下降。
**常数已核（2026-11-15，不再是凭记忆）**：mainline v6.6 `drivers/cpufreq/qcom-cpufreq-hw.c` 的 `epss_soc_data`（L408-415）= `reg_enable 0x0`、`reg_freq_lut 0x100`（L412，4 字节一行）、`reg_volt_lut 0x200`、`reg_perf_state 0x320`（L415）；读法 = `readl_relaxed(base + soc_data->reg_perf_state)`（L159）取 LUT 下标、`readl_relaxed(base + soc_data->reg_freq_lut + …)`（L238）取频率行。epss 表按 compatible `qcom,cpufreq-epss` 匹配、不分 SoC（L421），SM8475 与 SM8550 同代 EPSS。
本机还有一份已实现的参考：`D:/Android/k60-ios/UniXNU-sheng/package/CpuFreqProbe.cpp`（commit 0215f34a，BSD-2-Clause-Patent，SM8550 EPSS 探针）用同一套偏移（reg_enable 0x0、reg_domain_state 0x20、reg_dcvs_ctrl 0xb0、reg_freq_lut 0x100、reg_perf_state 0x320，多核 perf-state 行 +4×i），并给了 LUT 行解码：bit31:30 源、bit18:16 核数（1=turbo）、bit7:0 L 值（19.2 MHz bi_tcxo_div2 的倍数）。
DTS 里没有 CPU 的 OPP 表（`mondrian.dts:8965` 的 `operating-points-v2` 是 sdhc2 的），所以**只能判下标方向，判不了绝对 MHz**；要 MHz 得把 LUT（0x100）行读出来按 bit7:0 × 19.2 MHz 解，那是下一步的事。

落地形态：在 `drivers/PongThermal/pong_thermal.c` 用已有的 `ml_io_map` 路径多映射三个 0x1000 窗口（只读），
每次采样打印一行 `PongThermal: freq d0=%u d1=%u d2=%u`（下标），判据 = 压档前后同一 domain 的下标下降。
**在打印行存在之前不许往 `CRITERIA.toml` 加这条**（`docs/engineering/JUDGE-CONTRACT.md` §一.9：判据必须真的能出现在日志里）。

#### 判不了怎么办

如果 EPSS 读回全 0、三个 domain 全相同、或者映射失败：**写「无法判」，不许拿温度代替**。
温度只证明热了，不证明降频；这条是 Lead 在 2026-11-15 明确要求的（"读不到就诚实写无法判，别用温度代替"）。

#### 与 TRIP-DESIGN 的关系

46 条 cooling map 里本板能指望的执行器与这里的读数是一对：执行器负责「压」，EPSS 读数负责「证」。
`qcom,cpufreq-cdev`（`mondrian.dts:16790-16793`）、`qcom,devfreq-cdev`（`:16795-16798`）、`display-fps`（`:16803`）
这些存在但不被引用的节点要改哪个 DT 节点、改哪个驱动，等 Lead 放行 (b) 段后再写进 `TRIP-DESIGN.md`，本节只钉读数。


## 6 32 个 zone 的全表

（`slot` 是驱动采样顺序 = `pong_thermal_sensors` 的下标；温度单位 mC；`@` 是 DTS 行号；
`active … not used` 是该 zone 的主动 trip，本层不用。）

| slot | 控制器 | zone | 档数 | passive trips（温度 / 滞回 @DTS 行） |
| --- | --- | --- | --- | --- |
| 0 | tsens0[0] | aoss-0 | 2 | 115000/5000 @7121, 125000/1000 @7115 |
| 1 | tsens0[1] | cpuss-0 | 2 | 115000/5000 @7142, 125000/1000 @7136 |
| 2 | tsens0[2] | cpuss-1 | 2 | 115000/5000 @7163, 125000/1000 @7157 |
| 3 | tsens0[3] | cpuss-2 | 2 | 115000/5000 @7184, 125000/1000 @7178 |
| 4 | tsens0[4] | cpuss-3 | 2 | 115000/5000 @7205, 125000/1000 @7199 |
| 5 | tsens0[5] | cpu-1-0 | 3 | 110000/10000 @7238, 115000/5000 @7232, 125000/1000 @7220 |
| 6 | tsens0[6] | cpu-1-1 | 3 | 110000/10000 @7272, 115000/5000 @7266, 125000/1000 @7254 |
| 7 | tsens0[7] | cpu-1-2 | 3 | 110000/10000 @7306, 115000/5000 @7300, 125000/1000 @7288 |
| 8 | tsens0[8] | cpu-1-3 | 3 | 110000/10000 @7348, 115000/5000 @7342, 125000/1000 @7330 |
| 9 | tsens0[9] | cpu-1-4 | 3 | 110000/10000 @7390, 115000/5000 @7384, 125000/1000 @7372 |
| 10 | tsens0[10] | cpu-1-5 | 3 | 110000/10000 @7432, 115000/5000 @7426, 125000/1000 @7414 |
| 11 | tsens0[11] | cpu-1-6 | 3 | 110000/10000 @7474, 115000/5000 @7468, 125000/1000 @7456 |
| 12 | tsens0[12] | cpu-1-7 | 3 | 110000/10000 @7516, 115000/5000 @7510, 125000/1000 @7498 |
| 13 | tsens0[13] | cpu-1-8 | 3 | 110000/10000 @7558, 115000/5000 @7552, 125000/1000 @7540 |
| 14 | tsens0[14] | gpuss-0 | 3 | 95000/5000 @7600, 115000/5000 @7594, 125000/1000 @7582 |
| 15 | tsens0[15] | gpuss-1 | 3 | 95000/5000 @7642, 115000/5000 @7636, 125000/1000 @7624 |
| 16 | tsens1[0] | aoss-1 | 2 | 115000/5000 @7672, 125000/1000 @7666 |
| 17 | tsens1[1] | cpu-0-0 | 3 | 110000/10000 @7705, 115000/5000 @7699, 125000/1000 @7687 |
| 18 | tsens1[2] | cpu-0-1 | 3 | 110000/10000 @7747, 115000/5000 @7741, 125000/1000 @7729 |
| 19 | tsens1[3] | cpu-0-2 | 3 | 110000/10000 @7789, 115000/5000 @7783, 125000/1000 @7771 |
| 20 | tsens1[4] | cpu-0-3 | 3 | 110000/10000 @7831, 115000/5000 @7825, 125000/1000 @7813 |
| 21 | tsens1[5] | nspss-0 | 3 | 95000/5000 @7873, 115000/5000 @7867, 125000/1000 @7855 |
| 22 | tsens1[6] | nspss-1 | 3 | 95000/5000 @7915, 115000/5000 @7909, 125000/1000 @7897 |
| 23 | tsens1[7] | nspss-2 | 3 | 95000/5000 @7957, 115000/5000 @7951, 125000/1000 @7939 |
| 24 | tsens1[8] | video | 2 | 115000/5000 @7987, 125000/1000 @7981 |
| 25 | tsens1[9] | ddr | 3 | 90000/5000 @8008, 115000/5000 @8015, 125000/1000 @8002 |
| 26 | tsens1[10] | mdmss-0 | 2 | 115000/5000 @8068, 125000/1000 @8048 active 102000 @8054, 105000 @8061 not used |
| 27 | tsens1[11] | mdmss-1 | 2 | 115000/5000 @8131, 125000/1000 @8111 active 102000 @8117, 105000 @8124 not used |
| 28 | tsens1[12] | mdmss-2 | 2 | 115000/5000 @8194, 125000/1000 @8174 active 102000 @8180, 105000 @8187 not used |
| 29 | tsens1[13] | mdmss-3 | 2 | 115000/5000 @8257, 125000/1000 @8237 active 102000 @8243, 105000 @8250 not used |
| 30 | tsens1[14] | camera-0 | 2 | 115000/5000 @8306, 125000/1000 @8300 |
| 31 | tsens1[15] | camera-1 | 2 | 115000/5000 @8327, 125000/1000 @8321 |

## 7 复现

```sh
# zone 表与 DTS 的对应（每行注释都带 @行号）
grep -n 'tsens[01]\[' drivers/PongThermal/K60ThermalZones.c
# 阶梯算术的 host 测试（478 条断言）
cc -std=c11 -O1 -Wall -Wextra -Werror -I drivers/PongThermal \
   scripts/tests/test-k60-thermal-zones.c -o build/thermal/test-zones && build/thermal/test-zones
# 补丁与母本一致性（14 项，含 zone 表检查）
python3 scripts/check-thermal-kernel-patch.py
# 判据表本身能不能失败（干净日志必须过、每处改动必须挂）
python3 scripts/check-thermal-log.py --self-test
# 把判据施加到一份真实日志上
python3 scripts/check-thermal-log.py --log /mnt/e/k60-work/evidence/usblog-20261115-003922/console.log
```

## 8 与其它文档的关系

- `01-SAME-HARDWARE.md` §5：58 个 zone 的完整 trip 表（本层的原始数据）。
- `04-ANDROID-EVIDENCE.md` §5：现场 `trip_point_*_temp` 与 DT 逐项相同（阈值只有 DT 一份）。
- `TRIP-DESIGN.md` §1-§3：阈值来源、cooling device 清单、为什么只上报不注册执行器。
- `08-KERNEL-DRIVER.md` §3：发布层实现与 `pong_thermal_bias`；§5：首次上机日志。
- `06`/`07` 篇：kext 路线的 `mTPL`（SMC 键），与本层的 `Thermal_Level_Warning` 是两条独立通路。

