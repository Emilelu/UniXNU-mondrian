# COOLING-DEVICES · 46 条 cooling-map 归类与三个没人实现的冷却设备

> 只读设计文档：不写代码、不建图、不上机。数据源：`/tmp/mondrian.dts`（SM8475 mondrian 设备树，行号即 DTS 行号）。
> 与 `TRIP-DESIGN.md` §2.2（46 条 map 原始全表）互补：那份是「谁指向谁」，这份是「每一类在本移植动得了动不了 + 怎么知道的」。

## 0 结论

| 类 | 条数 | 在本移植能不能执行 | 依据（三选一：read 到 file:line / grep 零命中 / 日志失败行） |
| --- | --- | --- | --- |
| 停核（`qcom,thermal-pause`） | 15 | 能（ddr 的 `0x19`/`0x1c` 优先）；ArmCpu 有单向 halt/start | read `drivers/ArmCpu/ArmCpu.cpp:489` haltCPU、`:497` startCPU |
| 频率框架（kgsl / ddr-cdev） | 4 | 不能：本树无 GPU/DDR 频率执行框架 | grep `'kgsl\|devfreq'` → `.cache/xnu-work/` 零命中；grep `'cooling\|cdev'` → `drivers/` 仅 PongThermal 两条注释 |
| QMI 远端（lte / nr_scg / nr / cdsp / cdsp_hw） | 27 | 不能：本树无 QMI 传输 | grep `-rln 'qmi'` → `xnu-work/bsd/dev` + `xnu-work/osfmk` 零命中 |

三个 DTS 里有定义、但 46 条 map 一条都没引用、也没有任何驱动实现的设备：`cpufreq-cdev`、`devfreq-cdev`、`display-fps`（§2 各给「DTS 节点 + 需要实现它的驱动文件」两行）。

## 1 46 条 cooling-map 三类标注

三类 = 停核 / 频率框架 / QMI。逐条行号来自 `/tmp/mondrian.dts`；类级证据在表后。

| # | zone | trip 温度 | 目标 phandle → 设备 | 类 | map 行号 |
| --- | --- | --- | --- | --- | --- |
| 1 | cpu-1-2 | 110℃ | 0x5f → cpu5-pause | 停核 | :7318 |
| 2 | cpu-1-3 | 110℃ | 0x5f | 停核 | :7360 |
| 3 | cpu-1-4 | 110℃ | 0x62 → cpu6-pause | 停核 | :7402 |
| 4 | cpu-1-5 | 110℃ | 0x62 | 停核 | :7444 |
| 5 | cpu-1-6 | 110℃ | 0x65 → cpu7-pause | 停核 | :7486 |
| 6 | cpu-1-7 | 110℃ | 0x65 | 停核 | :7528 |
| 7 | cpu-1-8 | 110℃ | 0x65 | 停核 | :7570 |
| 8 | cpu-0-0 | 110℃ | 0x6d → cpu0-pause | 停核 | :7717 |
| 9 | cpu-0-1 | 110℃ | 0x6f → cpu1-pause | 停核 | :7759 |
| 10 | cpu-0-2 | 110℃ | 0x71 → cpu2-pause | 停核 | :7801 |
| 11 | cpu-0-3 | 110℃ | 0x73 → cpu3-pause | 停核 | :7843 |
| 12 | gpuss-0 | 95℃ | 0x69 → kgsl-3d0 lv0..max | 频率框架 | :7612 |
| 13 | gpuss-1 | 95℃ | 0x69 | 频率框架 | :7654 |
| 14 | nspss-0 | 95℃ | 0x75 → cdsp_sw | QMI | :7885 |
| 15 | nspss-1 | 95℃ | 0x75 | QMI | :7927 |
| 16 | nspss-2 | 95℃ | 0x75 | QMI | :7969 |
| 17 | ddr | 90℃ | 0x19 → cpu@400（cpu4） | 停核 | :8026 |
| 18 | ddr | 90℃ | 0x1c → cpu@700（cpu7） | 停核 | :8031 |
| 19 | ddr | 90℃ | 0x79 → ddr-cdev | 频率框架 | :8036 |
| 20 | mdmss-0 | active 102℃ | 0x7b → lte lv8 | QMI | :8079 |
| 21 | mdmss-0 | active 102℃ | 0x7c → nr_scg lv10 | QMI | :8084 |
| 22 | mdmss-0 | active 102℃ | 0x7d → nr lv6 | QMI | :8089 |
| 23 | mdmss-0 | active 105℃ | 0x7b → lte lv255 | QMI | :8094 |
| 24 | mdmss-0 | active 105℃ | 0x7d → nr lv255 | QMI | :8099 |
| 25 | mdmss-1 | active 102℃ | 0x7b lv8 / 0x7c lv10 / 0x7d lv6 | QMI | :8142/:8147/:8152 |
| 26 | mdmss-1 | active 105℃ | 0x7b lv255 / 0x7d lv255 | QMI | :8157/:8162 |
| 27 | mdmss-2 | active 102℃ | 0x7b lv8 / 0x7c lv10 / 0x7d lv6 | QMI | :8205/:8210/:8215 |
| 28 | mdmss-2 | active 105℃ | 0x7b lv255 / 0x7d lv255 | QMI | :8220/:8225 |
| 29 | mdmss-3 | active 102℃ | 0x7b lv8 / 0x7c lv10 / 0x7d lv6 | QMI | :8268/:8273/:8278 |
| 30 | mdmss-3 | active 105℃ | 0x7b lv255 / 0x7d lv255 | QMI | :8283/:8288 |
| 31 | mx-pe | 值 1（非温度） | 0x75 → cdsp lv1 | QMI | :8369 |
| 32 | mx-pe | 值 2（非温度） | 0x69 → kgsl lv1 | 频率框架 | :8374 |
| 33 | mx-pe | 值 3（非温度） | 0x7b → lte lv10 | QMI | :8379 |
| 34 | mx-pe | 值 3（非温度） | 0x7c → nr_scg lv10 | QMI | :8384 |
| 35 | isense_trim | 值 2（非温度） | 0x19 → cpu@400 lv15 | 停核 | :8408 |
| 36 | isense_trim | 值 2（非温度） | 0x1c → cpu@700 lv15 | 停核 | :8413 |
| 37 | isense_trim | 值 2（非温度） | 0x8a → cdsp_hw lv1 | QMI | :8418 |

（mdmss 四个 zone 每 zone 5 条 map 完全同构，上表按 zone 合并为 10 行；单条行号已全部列出。）

### 1.1 类级证据（每条结论的「怎么知道」）

- **停核 15 条**：目标 phandle 全部落在 `qcom,cpu-pause` 块（mondrian.dts:16458-16547：cpu0-pause :16461、cpu5-pause :16485、cpu6-pause :16491、cpu7-pause :16497，phandle 0x6d/0x6f/0x71/0x73/0x5f/0x62/0x65）或 `/cpus`（0x19 = cpu@400 :560、0x1c = cpu@700 :627）。执行路径存在（read）：`drivers/ArmCpu/ArmCpu.cpp:489` `void ArmCpu::haltCPU(void)`、`:492` `setCPUState(kIOCPUStateStopped)`、`:497` `kern_return_t ArmCpu::startCPU(...)`、`:15` `extern "C" kern_return_t psci_smp_start_cpu(int);`。
- **频率框架 4 条**：0x69 = `qcom,kgsl-3d0@3d00000`（:16170，`#cooling-cells` :16193）；0x79 = `qcom,ddr-cdev`（:16612-16619，`qcom,freq-table=<0x22c>` → thermal-ddr-freq-table :16607-16610）。缺执行框架的证据（grep 零命中，模式与范围如下）：`grep -rn 'kgsl\|devfreq' .cache/xnu-work/` 零命中；`grep -n 'cooling\|cdev' drivers/` 仅 2 命中且都是 PongThermal 注释（K60ThermalZones.c:12、K60ThermalLevel.h:45），零注册代码；本仓库 GPU 侧只有寄存器读写管道 `drivers/PongAdreno/PongAdrenoPlatform.cpp:318` clock_read / `:323` clock_write（read），没有把 trip 接到 GPU 频率的执行器。
- **QMI 27 条**：0x75 / 0x8a / 0x7b / 0x7c / 0x7d 全在 `qmi-tmd-devices` 块（:16629 起，compatible `"qcom,qmi-cooling-devices"`；子节点带 `qcom,qmi-dev-name` "cdsp_sw" / "cdsp_hw"）。执行要走 QMI 传输的证据（grep 零命中，模式与范围如下）：`grep -rln 'qmi' .cache/xnu-work/bsd/dev .cache/xnu-work/osfmk` 零命中 → 本树没有任何 QMI 客户端，27 条永远动不了，除非移植 qmux/glink（超出本线）。
- **两个非温度 zone**：mx-pe 自身 `status="disabled"`（:8336），它的 4 条（#31-34）永远不会触发；mx-pe 与 isense_trim 的 trip 值是 1/2/3 不是温度（见 LEVEL-MAP §2）。

## 2 三个没人实现的冷却设备（各两行）

「没人实现」的总证据（grep，模式与范围如下）：`grep -rn 'cpufreq-cdev\|devfreq-cdev\|display-fps' /mnt/e/hackios/k60-thermal/` 只在 `docs/research/thermal/TRIP-DESIGN.md:132-134` 命中（文档表格），代码零命中。

### 2.1 cpufreq-cdev

- DTS 节点：mondrian.dts:16790-16793（compatible `"qcom,cpufreq-cdev"`；`qcom,cpus=<0x15 0x19 0x1c>` = cpu0/cpu4/cpu7；**无 phandle、无 `#cooling-cells`** → 任何 cooling-map 都无法引用它）。
- 需要实现它的驱动文件：本树还没有——频率域寄存器在 mondrian.dts:854-858（`qcom,cpufreq-hw-epss`，freq-domain0/1/2 = 0x17d91000 / 0x17d92000 / 0x17d93000）。XNU 侧需新增 `drivers/PongThermal/pong_cpufreq.c`（复用 `drivers/PongThermal/pong_thermal.c:206/:208` 的 ml_io_map 只读先例），并在 `bsd/conf/files` 登记（0617 patch 已有四文件先例）。先做只读采样（LEVEL-MAP §5.5），写语义未验证、不在本设计内。

### 2.2 devfreq-cdev

- DTS 节点：mondrian.dts:16795-16798（compatible `"qcom,devfreq-cdev"`；`qcom,devfreq=<0x69>` = `qcom,kgsl-3d0@3d00000` :16170；**无 phandle**）。
- 需要实现它的驱动文件：本树没有 GPU 频率框架（`grep -rn 'kgsl\|devfreq' .cache/xnu-work/` 零命中，范围=整个 xnu-work）；本仓库 GPU 侧只有寄存器读写管道 `drivers/PongAdreno/PongAdrenoPlatform.cpp:318` clock_read / `:323` clock_write（read）。要把 trip 接到 GPU 频率，须先在 PongAdreno 上加执行器，或交 gpu-user 线（k60-gpu-user worktree）。本线不实现。

### 2.3 display-fps

- DTS 节点：mondrian.dts:16800-16808（`qcom,userspace-cdev` 块；display-fps :16803-16807，`qcom,max-level=4`，phandle 0x43c）。
- 需要实现它的驱动文件：不在本线——本仓库 `drivers/` 无显示驱动（`grep -n 'brightness\|backlight\|refresh' drivers/` 命中全在 PongPower 电池刷新，如 K60Battmgr.c:69；目录清单 9 个组件无 display）；46 条 map 里 0x43c 零引用。归 display 线（k60-display worktree）。本线不实现。

## 3 设计（只写设计）

### 3.1 可动集排序

1. **ddr 的 0x19/0x1c（cpu4/cpu7 停核）**：90℃ 是全部 map 里最低的真实温度档。`ArmCpu::haltCPU`（ArmCpu.cpp:489-495）= quiesceCPU + `setCPUState(kIOCPUStateStopped)` + daifset + wfi 死循环（单向）；恢复走 `startCPU`（:497-500 → psci_smp_start_cpu）。风险：quiesceCPU 停一个就绪的核之后，恢复路径从未在热压场景验证过——接线前必须先验证 startCPU 能把它带回来。
2. **cpufreq-cdev（EPSS 频率域）**：先做 LEVEL-MAP §5.5 的只读采样（三个 perf-state 下标），闭环证明「压档后下标下降」再考虑写。寄存器常数待核上游源码（LEVEL-MAP §5.5 已声明）。
3. **不动**：kgsl / ddr-cdev（缺框架，P-204 教训：不能拿 iokit/Kernel/IOCPU.cpp:369-374 的静态 clock-frequency 充数）、QMI 27 条（缺传输）、display-fps（display 线）。

### 3.2 触发分层

- 触发：已有 `k60tz_step` 的 zone level（1/2/3，LEVEL-MAP §3）——档次对上 §1 表的 trip 温度。
- 接线表：§1 表就是候选接线表；只有「停核」与「cpufreq（未来）」两类允许接执行器，其余标 read-only。
- 判据：LEVEL-MAP §5.5 三件套 + EPSS 下标；读不到就判「无法判」，不拿温度代替。

### 3.3 与 TRIP-DESIGN §4 的关系

TRIP-DESIGN.md §4 的候选排序「充电限流 > 背光/HBM > Thermal_Level_Warning > CPU pause > DVFS」是 2026-11-14 按 (b) 库存做的初排；本文件按 46 条 map 的可行性把可动集收敛为「ddr 停核 > cpufreq(EPSS)」两档，并给每类「怎么知道不能动」的证据。TRIP-DESIGN §4 加一行指向本文件。

## 4 复现

```
# 46 条 map 全表（花括号深度解析，输出 zones.json）
python3 /mnt/e/k60-work/scratch/dts_parse.py
# 三个设备的节点本体
sed -n '16790,16808p' /tmp/mondrian.dts
# 「没人实现」的零命中 grep（模式与范围）
grep -rn 'kgsl\|devfreq' /opt/k60/trees/thermal-out/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work/
grep -rln 'qmi' /opt/k60/trees/thermal-out/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work/bsd/dev /opt/k60/trees/thermal-out/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work/osfmk
grep -rn 'cpufreq-cdev\|devfreq-cdev\|display-fps' /mnt/e/hackios/k60-thermal/
# 停核执行路径
grep -n 'haltCPU\|startCPU\|setCPUState' /mnt/e/hackios/k60-thermal/drivers/ArmCpu/ArmCpu.cpp
```

## 5 与其它文档的关系

- TRIP-DESIGN.md §2.2：46 条 map 的原始全表（本文件 §1 是它的三类标注版）。
- LEVEL-MAP.md §5.5：下一次上机的频率判据（EPSS 下标）与本文件 §3.1 第 2 条同源。
- 08-KERNEL-DRIVER.md §3：驱动现状（worker 只采样、只发布，无执行器）。

