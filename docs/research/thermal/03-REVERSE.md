# 03 · 反编译 / 交叉取证：三组参考实现读 tsens 的方式

本篇回答"别人是怎么做的、我们能抄什么"。三类证据：同族 UniXNU 移植（SM8550）、有实测的 Linux 移植
（SM6375 / POCO X5 Pro）、以及它们的工具链。**注意：K60 自身下游内核驱动的反编译尚未做**，缺口写在 §6。

---

## 1. 参考实现 A：UniXNU-sheng（同族 UniXNU，SM8550）

路径 `E:/k60-work/references/UniXNU-sheng/package/`（注意：`/mnt/e/hackios/UniXNU-sheng/package` 里
`grep tsens` 无命中，热管理只在 `E:/k60-work/references` 的这份副本里，别被空 grep 误导）。

### 1.1 它读什么

- `ThermalProbe.h:5-11` 文件头注释：三个 TSENS v2 控制器（`thermal-sensor@c271000/@c272000/@c273000`），
  每个都有 TM 块与 SROT 块；`tsens-v2.c` 的 `Sn_STATUS` 在 `0xa0 + 4*n`；`tsens.c` 最多读三次直到 VALID。
  —— 与我们 02 篇查到的上游语义**完全一致**，说明同族实现也是照上游写的。
- `ThermalProbe.h:27-39` 常量表：`THERMAL_CONTROLLERS=3`、`THERMAL_SENSORS=16`、
  `THERMAL_TM_STATUS=0xa0(+4*sensor)`、`TEMP_MASK=0xfff`、`VALID=1u<<21`、
  `FLAGS_SHIFT=16` / `MASK=0x1f`、`SROT_VERSION=0x0`、`SROT_CTRL=0x4`、`CTRL_ENABLE=1u<<0`、
  `CTRL_SENSOR_SHIFT=3`、`WINDOW=0x1000`、`READ_TRIES=3`。
  → 与 `tsens-v2.c:12-27,94-101` 一一对应（0xa0 / 0xfff / bit21 / 0x0 / 0x4 / bit0 全部吻合）。
- `ThermalProbe.h:38-39`：TM 基址 `{0x0c271000,0x0c272000,0x0c273000}`，
  SROT 基址 `{0x0c222000,0x0c223000,0x0c224000}` —— SM8550 的三个 SROT 块是**连续**的
  c222000/c223000/c224000，而 K60 只有两个：c222000/c223000（mondrian.dts:16440,16450），同型缩小。

### 1.2 它怎么读

- `ThermalProbe.cpp:83-90 mapWindow()`：`IODeviceMemory::withRange(base, 0x1000)` +
  `map(kIOMapAnywhere | kIOMapInhibitCache)` —— 映射 4K，**非缓存**。K60 的 `reg` 只声明 0x1ff，
  但我们同样可按 4K 页映射（MMIO 页粒度），不违反 DT。
- `ThermalProbe.cpp:92-119 sampleTemperatures()`：先读 SROT 的 `ctrl`，再逐传感器
  `rd(gTm[c], 0xa0 + 4*s)`，最多 3 次直到 VALID 置位。
- `ThermalProbe.h:64-69 thermal_status_mc()`：12 位字段按 bit `0x800` 符号扩展成 tenths，再 ×100 → m°C。
- `ThermalProbe.h:73-80 thermal_pick()`：优先取第一个 VALID 的读数；否则取"连续两次一致"的值
  （防撕裂读，比单纯重试更稳）。
- `ThermalProbe.h:83-86 thermal_sensor_enabled()`：`ctrl` bit0 且 `(ctrl >> (3 + sensor)) & 1`。
  → 每个传感器在 SROT 里有独立使能位；上游也这么认为（`tsens.c:983-985` 从 srot_map 分配
  `rf[SENSOR_EN]`）。**这是可以抄来做"该传感器是否真被固件打开"的判据**。
- `ThermalProbe.cpp:195-224 sheng_thermal_probe()`：boot-arg `thermal=` / `thermal-ms=` 开关，
  映射 TM+SROT，读版本与 ctrl。文件头 `:5` 明确写："Nothing is written to any of these blocks and
  no interrupt is taken" —— **纯只读、不开中断**，正是我们第一阶段要的策略。

### 1.3 它额外做了什么（本阶段不抄）

- `ThermalProbe.cpp:62-72`：还映射 EPSS cpufreq 域（0x17d91000/2/3）与 GICD（0x17100000+0x204）
  看 LMh 限频中断挂起 —— 需要 GIC 与 cpufreq 域知识，K60 的 EPSS 地址不同，本阶段不做。
- `ThermalLevel.cpp/.h`：把"热压力等级"交给 macOS（IOPMrootDomain 压力通知），与 tsens 读数解耦。
  另一个子系统，不属于 thermal 线第一阶段。
- `BootLog.c:1530-1539`：把读数（最多 8 行）打到启动日志；`weak_import` 声明在 `:211-214`。
  → **日志形态可抄**：我们第一阶段也不该有控制逻辑，只把 32 个读数打到串口日志供比对。

---

## 2. 参考实现 B：phk110-port（POCO X5 Pro / SM6375，**有实测**）

路径 `E:/k60-work/references/phk110-port/drivers/power/hakios.thermal.c`（283 行）。

### 2.1 最关键的一条：TM 基址与 K60 完全相同

`:93-129` 的传感器表由 `tools/dt-thermal.py` 从该机 DTB 生成，其 TM 基址就是
`0xc263000` 与 `0xc265000`（`:130-131` 的 `REFERENCE_TM0/TM1`）。
`docs/phk110/research/f14-sd778g-zendot-survey.md:116` 也记："同基址 v2，16×2=32 传感器 | 换参"。
→ 相邻平台复用同一组基址，这增强了我们 0xc263000/0xc265000 的可信度（本板 DT 仍是主要依据）。

### 2.2 它怎么读（可直接照抄的最小实现）

- `:179-183`：

```c
status = *(volatile uint32_t *)(tm_va + TM_STATUS(n));   /* TM_STATUS(n) = 0xa0 + 4*n */
value  = (int32_t)(status << 20) >> 20;                  /* bit11 符号扩展 = sign_extend_12 */
```

  无效（`!(status & (1u<<21))`）或超出 -400..1600（tenths）就跳过该传感器。
- `:206`：tenths × 100 = m°C。
- `:87-91`：`TM_SIZE=0x200`、`TM_VALID=1u<<21`、`TEMP_MIN_TENTHS=-400`、`TEMP_MAX_TENTHS=1600`。
  它映射 **0x200** 字节（DT 写 0x1ff），而 sheng 映射 0x1000 —— 两者都行，页粒度由映射器决定。
- `:11-13` 的论断与 02 篇 §2.2/§2.3 一致："标定由 secure 固件在 OS 前完成；status 字里已经是度数"。
  → 来自实测过的移植，是"不做标定换算"的**第二个独立佐证**。

### 2.3 它的实测结论（我们唯一有真实读数的证据源）

`:34-39`：2026-10-27 四次运行，**27/27 传感器全部有读数**，静置 33.3-39.5℃，CPU 核比周围高 1-2℃，
跨运行数值会变化。**未**验证：负载下读数、`thermal_stop`（默认 105℃，连续三次即 `loader_return()`）触发。

对我们的价值：

1. 证明"只读 status 字"在真机上确实出数（不是理论可行）。
2. 给出合理静置区间（33-40℃）与"CPU 核略高"的形态 —— K60 上机时的第一条 sanity check。
3. 说明必须自己做量程校验（它用 -40..160℃ 夹逼；坏读数会被过滤掉）。

### 2.4 GPU 侧同法直读（第二处交叉印证）

`drivers/gpu/hakios.adreno.c:3541-3567`：GPU 驱动里直接读 tsens1 ——
`static struct block tsens = {"tsens1", 0x0c265000, 0x200}`；`TSENS_STATUS(s) = (0xa0 + 4*(s))`；
`TSENS_VALID (1u<<21)`；读 `rd(tsens.base + TSENS_STATUS(1 + i))`。
→ 同一 IP 在**第二个驱动**里用同样三个常量读，说明这套偏移不是某个驱动的私有魔数。

---

## 3. 参考实现 C：dt-thermal.py（生成器，可直接改用）

`E:/k60-work/references/phk110-port/tools/dt-thermal.py`（76 行）：从 Qualcomm DTB 抽"传感器表"。

- `:38-40`：挑 `compatible` 含 `qcom,tsens26xx` 且带 phandle 的节点，建 phandle → reg 映射，
  取 `reg[2]`（第二段的第一个 cell）作为 TM 基址。
- `:42-55`：遍历 `/soc/thermal-zones/*`，取 `thermal-sensors = <&tsensN id>` 得到 (控制器, 索引)。
- `:56-73`：按 `-step` / `-usr` 后缀归一化 zone 名，把最小/最大 trip 当 slow/give-up 阈值，`--c` 输出 C 表。

**复用方式**：把匹配串从 `qcom,tsens26xx` 改成 `qcom,tsens-v2`（我们的 compatible，mondrian.dts:16439），
其余不动，即可为 K60 生成 32 行 C 表。这是第 5 步（方案）里"生成式而非手抄"的关键工具 ——
手抄 32 行索引表是错误温床。

---

## 4. 三平台对照：哪些能直接复用，哪些必须按 DT 改

| 项目 | K60（本板） | SM8550（sheng） | SM6375（phk110，实测） | 能否复用 |
|---|---|---|---|---|
| 控制器数 | 2（mondrian.dts:16438,16448） | 3 | 2 | 参数化 |
| TM 基址 | c263000 / c265000 | c271000/c272000/c273000 | c263000 / c265000 | **phk110 与本板相同** |
| SROT 基址 | c222000 / c223000 | c222000/c223000/c224000 | 表里未用 | 前两个与本板相同 |
| 每控制器传感器数 | 16 / 16（#qcom,sensors） | 16 / 16 / 16 | 15 / 12（表内 27 条） | 必须按 DT，不可套 |
| STATUS 偏移 | 0xa0 + 4*n | 同 | 同 | 直接复用 |
| VALID 位 | bit21 | bit21 | bit21 | 直接复用 |
| 温度字段 | [11:0]，0.1℃ | 同 | 同 | 直接复用 |
| 符号扩展 | bit11（<<20>>20 或 sign_extend32(...,11)） | 同 | 同 | 直接复用 |
| 换算 | ×100 → m°C | 同 | 同 | 直接复用 |
| 每传感器使能位 | SROT ctrl (3+n)（待上机确认） | 同（thermal_sensor_enabled） | 未用 | 可作 sanity check |
| **zone↔索引映射** | 见 01 篇 §3 | 自有分组表（ThermalProbe.h:50-60） | aoss-0=0, cpu-0-0..3=1..4, cpuss-0..1=5..6, cpu-1-0..7=7..14 | **绝不可套用** |
| 中断 | uplow/critical = SPI 506/508、507/509 | 自有 | 未用 | 本阶段不开 |
| 标定 | DT 无 nvmem（calibrationless） | 未查 | 不用 | 读数路径不需要 |
| 策略 | 待定 | 纯只读 + 打日志 | 只读 + 105℃ 三次则 loader_return() | 第一阶段抄"纯只读" |

**最需要注意的一条**：SM6375 的 cpu-0-0..3 在 **TM0 的 idx 1..4**，而 K60 的 cpu-0-0..3 在 **TM1 的
idx 1..4**（K60 TM0 的 idx 1..4 是 cpuss-0..3）。同 IP、同基址，**索引语义完全不同** —— 说明
"传感器编号"是板级/固件级约定，唯一可信来源是本板 DT（01 篇 §3 就是逐条从 DT 抄的）。

---

## 5. 复用清单（明确到"抄哪几行、改哪里"）

**直接复用（证据充分）**：

1. 读法：`status = *(volatile uint32_t*)(tm + 0xa0 + 4*n)`；`temp = (int32_t)(status<<20)>>20`；`mC = temp*100`
   （phk110 `:179-183,206`；sheng `ThermalProbe.h:64-69`；上游 `tsens.c:346-347`）。
2. VALID 判定 + 重试 + 量程夹逼（phk110 `:15-16,179-183`；sheng `ThermalProbe.h:73-80,83-86`；
   上游 `tsens.c:750-779`）。
3. 映射窗口：0x200（DT 长度）或整页 0x1000，非缓存映射（sheng `ThermalProbe.cpp:83-90`；
   phk110 `:248-282`）。
4. 纯只读策略 + 打日志（sheng 头注释 `:5`；phk110 `:10`）。
5. 生成器：`dt-thermal.py` 改 compatible 匹配串，生成本板 32 行表。

**需要改动后才可用**：

6. 控制器数量与基址：从 DT 读（我们 2 个），不硬编码 3 个。
7. 传感器数：从 `#qcom,sensors`（16）读，不硬编码 15/12/13。
8. 传感器命名：用本板 zone 名（01 篇 §3），不抄 SM8550 的分组表。
9. 日志格式：把 sheng 的"最多 8 行"改成"32 个全打（4 行 × 8）"以便上机比对。

**不可复用（本阶段明确排除）**：

10. 阈值/中断编程（THRESHOLD / CLEAR / MASK / INT_EN）：需要标定与 GIC，见 02 篇 §3。
11. `thermal_stop` 强制回 bootloader（phk110 `:220-235`）：那是产品决策；第一阶段只观测，不做关机决策
    （是否要做由 Lead 定，属第 6 步之后）。
12. EPSS / LMh / GICD 寄存器（sheng `ThermalProbe.cpp:62-72`）：需要 K60 自己的 EPSS 地址与 GIC 初始化。
13. QMI 远端 25 个 zone：需要 QMI/GLINK 通路（我们没有）。

---

## 6. 反编译缺口（为什么第 3 步 done=false）

本篇三组证据都是**同族/同 IP 的移植代码**，属"广查"性质的交叉印证，不等同于对 **K60 自身下游内核**的
反编译。严格意义上"第 3 步"要求的是本板 Android 侧 tsens 驱动 / thermal-engine 的行为证据：

- 缺：K60 vendor kernel 的 tsens 驱动（drivers/thermal/qcom 或 techpack）符号与实现 —— 需从
  boot.img / vendor_boot / ko 里取，本阶段没有取到（也还没做 vmlinux 反汇编）。
- 缺：`/vendor/etc/thermal-engine*.conf`（QCOM thermal-engine 的 trip 表），能解释 125℃ / 115℃ / 110℃
  这些数在 Android 侧的真实用途。
- 为什么这不阻塞"读温度"：读数语义已由上游驱动（层②）+ 本板 DT（层①）+ 两台真机实测（参考实现 A/B）
  三重锁定，且我们只读不写。真正需要本板下游反编译的是**第 6 步（深入）**：阈值语义、thermal-engine
  策略、以及"固件是否真的使能了 32 个传感器"。

→ 因此 EIGHT-STEPS.toml 里 thermal 的 `step.decompile` 记 `done = false`，缺的证据就是上面两条。
