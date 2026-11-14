# TRIP-DESIGN · trip 阈值从哪来、板上有哪些 cooling device、XNU 侧该不该做执行器

> 范围：只回答 Lead 在 2026-11-14 交办的三个问题（阈值来源 / cooling device / 执行器决策），
> **不含驱动代码，也不改任何实现**。每一条结论后面都带 `文件:行`。
>
> 证据三类：
> ① 板级 DTS `/tmp/mondrian.dts`（由 UEFI 的 `sm8475-xiaomi-mondrian.dtb` 反编译；与 `vendor_boot`
>    里的 DTB 实质相同，只有根节点三行差异，见 `04-ANDROID-EVIDENCE.md:236-256`）。下文所有
>    `mondrian.dts:N` 都指这份文件，重建命令见 §5。
> ② Android 现场取证 `/mnt/e/k60-work/evidence/thermal-android-20261114/`（设备 6033dbec，2026-11-14 11:43-12:01）。
> ③ 本树源码与内核导出表：`/opt/k60/trees/thermal-out/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work`
>    与同树 `build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/all-kpi.exp`。

## 0. 三个答案

| 问题 | 答案 | 一句话证据 |
|---|---|---|
| (a) 32 路传感器的 trip 阈值从哪来 | **只有板级 DTS 一处**。Android 侧没有任何独立的阈值来源 | 58 个 zone 的 154 个 trip 全部写在 `mondrian.dts:6643-8422`；`thermal-engine.conf` 是 84 B 的空文件（`04-ANDROID-EVIDENCE.md:231`） |
| (b) 本板有没有 cooling device | **有 46 条 cooling-map、16 个被引用的 cooling device，但没有一个能在本移植执行** | `mondrian.dts` 全文 50 处 `cooling-device`，其中 46 处在 `thermal-zones` 内；能本地做的只有停核，其余是 QMI 远端或需要 GPU/DDR 频率框架（§2） |
| (c) XNU 该注册执行器还是只上报 | **只上报**。唯一可选的发布动作是 `IOPMrootDomain::systemPowerEventOccurred`，而它只影响睡眠策略，不降频 | 本树没有 `IOHWMControl`/`AppleSMC` 类（grep 零命中）；`IOPMrootDomain.cpp:8133` 只把 warning 变成一个布尔量 |

## 1. (a) trip 阈值：来源是 DTS，且只有 DTS

### 1.1 154 个 trip 的直方图（DTS 实测）

`thermal-zones` 块从 `mondrian.dts:6643` 到 `:8422`，含 58 个 zone（57 个两格 `thermal-sensors`，`mx-pe` 用单格 `<0x85>`）、
154 个 trip（146 `passive` + 8 `active`）。温度原值直方图：

| 原值 | m°C | 个数 | trip 名（同族） | 例（DTS 行） |
|---|---|---|---|---|
| `0x1e848` | 125000 | 91 | `thermal-engine-config` / `thermal-hal-config` | `:6654`、`:6660` |
| `0x1c138` | 115000 | 32 | `reset-mon-cfg` | `:7122`、`:7143` |
| `0x1adb0` | 110000 | 13 | `cpuX-emergN-cfg` | `:7239`、`:7273` |
| `0x19a28` | 105000 | 4 | `mdmssN-config1`（**active**） | `:8062` |
| `0x18e70` | 102000 | 4 | `mdmssN-config0`（**active**） | `:8055` |
| `0x17318` | 95000 | 5 | `tj_cfg`（GPU）/ `junction-config`（NPU） | `:7601`、`:7643` |
| `0x15f90` | 90000 | 1 | `ddr0-config` | `:8009` |
| `0x01` / `0x02` / `0x03` | — | 1 / 2 / 1 | `mx-pe-config1..3` 与 `isense_trim` 的 trip（**不是温度**） | `:8344`、`:8351`、`:8358`、`:8397` |

两点必须说清楚：

- 125000 出现 91 次，是因为同一 zone 里 `thermal-engine-config` 与 `thermal-hal-config` 是两条同值 trip
  （`01-SAME-HARDWARE.md:176-178`），不是 91 个不同阈值；
- 8 个 `active` trip 全部属于 modem 侧 `mdmss-0..3` 的 102/105℃（温度行 `:8055/8062`、`:8118/8125`、`:8181/8188`、`:8244/8251`，
  每个 zone 的 `type = "active"` 就在对应温度行下一行），AP tsens 侧一个 `active` 都没有（`01-SAME-HARDWARE.md:183-185`）。

### 1.2 三个候选来源逐个核查

| 候选来源 | 实测结论 | 证据 |
|---|---|---|
| `/vendor/etc/thermal-engine.conf` | **不是来源**：84 字节，内容是 `# File empty by default`。本机不用 thermal-engine，用 thermald | `04-ANDROID-EVIDENCE.md:231`；`/mnt/e/k60-work/evidence/thermal-android-20261114/thermal-engine.conf` |
| `/vendor/etc/thermald-devices.conf` | **只列执行器，不列阈值**：2266 B 明文，21 个 `[name:...]` 块，全是 `cooling_name`/`path`/`def_target`，没有温度 | `thermald-devices.conf:1-169`；`04-ANDROID-EVIDENCE.md:232` |
| `thermal-map.conf` / `thermal-normal.conf` / `thermal-phone.conf` | **不可解**：厂商加密二进制（`xxd` 头部 `01f8 9f93…`，无 gzip 头，`strings` 无明文），已放弃 | `04-ANDROID-EVIDENCE.md:266` |
| 固件（`qcom_tsens.ko`） | **不含阈值表**：`.rodata` 只有寄存器字段表 `tsens_v2_regfields`，trip 由 vendor 内核从 DT 注册 | `04-ANDROID-EVIDENCE.md:153-174` |
| 现场 `/sys/class/thermal/thermal_zone*/trip_point_*_temp` | **与 DTS 逐项相同**：例如 aoss-0/cpuss-0/video 的 trip0=125000、trip1=115000，ddr 的 trip0/1/2=125000/90000/115000 | `04-ANDROID-EVIDENCE.md:85-99` |

**结论**：阈值只有 DTS 一份，Android 的配置文件要么是空的、要么只写执行器、要么加密；现场读数是 DT 的
运行时投影。所以 XNU 侧取阈值时**不需要再去 Android 里找第二来源**，直接引 DTS 行号即可。

### 1.3 XNU 侧已经在用的子集（`K60ThermalLevel.c`）

五个域各取三条（本域警告点 / 复位监控点 / 板级 thermal-engine 点），温度与滞回都照抄 DT：

| 域 | XNU trip 表（温度/滞回 m°C） | 代码 | DTS 出处 |
|---|---|---|---|
| 小核 cpu-0-0..3 | 110000/10000、115000/5000、125000/1000 | `K60ThermalLevel.c:13-15` | `:7706/:7707`、`:7700/:7701`、`:7688/:7689` |
| 大核 cpu-1-0..8 | 同上（两簇同值，共用一张表） | `K60ThermalLevel.c:9-15` | `:7239/:7240`、`:7233/:7234`、`:7221/:7222` |
| GPU gpuss-0/1 | 95000/5000、115000/5000、125000/1000 | `K60ThermalLevel.c:17-21` | `:7601/:7602`、`:7595/:7596`、`:7583/:7584` |
| NPU nspss-0..2 | 95000/5000、115000/5000、125000/1000 | `K60ThermalLevel.c:23-27` | `:7874/:7875`、`:7868/:7869`、`:7856/:7857` |
| DDR | 90000/5000、115000/5000、125000/1000 | `K60ThermalLevel.c:29-33` | `:8009/:8010`、`:8016/:8017`、`:8003/:8004` |

传感器到域的映射见 `K60ThermalLevel.c:43-58`（aoss/cpuss/video/mdmss/camera 归 `K60TlNoInput`：
它们有 trip，但本板对它们没有任何可执行的降温动作，`K60ThermalLevel.h:43-46`）。

### 1.4 对"要不要做 trip 编程"的含义

- 只读路径**不需要**任何标定系数：v2 在 `adc=0` 分支的读数路径本身就是 deci-Celsius ×100
  （`04-ANDROID-EVIDENCE.md:175-198`、`:219-225`）。
- 若要**写**硬件阈值（上游 `tsens_set_trips` → `degc_to_code()`，`tsens.c:290-315`），必须先把
  温度码换算成硬件码，而这一步依赖标定；本板 DT 没有 `nvmem-cells`/`qcom,tsens-calibration`
  （`04-ANDROID-EVIDENCE.md:199-226`）。**这就是本阶段不做 trip 编程的技术原因**，而不是排期原因
  （`04-ANDROID-EVIDENCE.md:222-223` 已把这条写成明确边界）。

## 2. (b) cooling device：46 条映射，本地一条都执行不了

### 2.1 定义清单（16 个被 map 引用 + 若干未被引用）

| phandle | 节点 | DTS 行 | 类型 | 本移植能否执行 |
|---|---|---|---|---|
| `0x6d/0x6f/0x71/0x73` | `cpu0-pause`…`cpu3-pause` | `:16461-16483` | `qcom,thermal-pause`（`:16459`），`qcom,cpus`=`0x15/0x16/0x17/0x18` | 只有停核语义，见 §3.3 |
| `0x5f` | `cpu5-pause` | `:16485-16489` | 同上，`qcom,cpus=<0x1a>`（CPU5） | 同上 |
| `0x62` | `cpu6-pause` | `:16491-16495` | `qcom,cpus=<0x1b>`（CPU6） | 同上 |
| `0x65` | `cpu7-pause` | `:16497-16501` | `qcom,cpus=<0x1c>`（CPU7） | 同上 |
| `0x69` | `qcom,kgsl-3d0@3d00000` | `:16170`（`#cooling-cells` `:16193`） | Adreno GPU | **不能**：需要 GPU 频率框架 |
| `0x75` | `cdsp`（`qmi-tmd-devices` 下，`qmi-dev-name="cdsp_sw"`） | `:16629-16640` | QMI 远端 NPU/DSP | **不能**：QMI 通路 |
| `0x8a` | `cdsp_hw` | `:16642-16646` | QMI 远端 | **不能** |
| `0x7b/0x7c/0x7d` | `mmodem_lte_dsc_kr` / `modem_nr_scg_dsc_kr` / `modem_nr_dsc_kr` | `:16629` 块内 | QMI 远端 modem | **不能** |
| `0x19` / `0x1c` | `/cpus/cpu@400` / `cpu@700`（CPU4/CPU7） | `:547/:560`、`:614/:627` | cpufreq cooling（Android 侧 LMH） | **不能**：没有 cpufreq 框架 |
| `0x79` | `qcom,ddr-cdev` | `:16612-16619` | DDR 频率 | **不能**：没有 DDR 频率框架 |

CPU phandle 对照：`0x15`=cpu@0 `:479`、`0x16`=cpu@100 `:507`、`0x17`=cpu@200 `:522`、
`0x18`=cpu@300 `:544`、`0x19`=cpu@400 `:560`、`0x1a`=cpu@500 `:582`、`0x1b`=cpu@600 `:604`、
`0x1c`=cpu@700 `:627`。
### 2.2 46 条 cooling-map：谁在什么温度压什么

| zone（DTS 行） | trip | cooling device | 档位 | 本移植可执行? |
|---|---|---|---|---|
| cpu-1-2/3（`:7281/:7323`） | 110℃ | `0x5f` cpu5-pause（map `:7318/:7360`） | 1..1 | 停核语义 |
| cpu-1-4/5（`:7365/:7407`） | 110℃ | `0x62` cpu6-pause（`:7402/:7444`） | 1..1 | 停核语义 |
| cpu-1-6/7/8（`:7449/:7491/:7533`） | 110℃ | `0x65` cpu7-pause（`:7486/:7528/:7570`） | 1..1 | 停核语义 |
| cpu-0-0..3（`:7680/:7722/:7764/:7806`） | 110℃ | `0x6d/0x6f/0x71/0x73`（`:7717/:7759/:7801/:7843`） | 1..1 | 停核语义 |
| gpuss-0/1（`:7575/:7617`） | 95℃ | `0x69` kgsl（`:7612/:7654`） | 0..max | 否 |
| nspss-0/1/2（`:7848/:7890/:7932`） | 95℃ | `0x75` cdsp（`:7885/:7927/:7969`） | 1..max | 否（QMI） |
| ddr（`:7995`） | 90℃ | `0x19` CPU4 + `0x1c` CPU7 + `0x79` ddr-cdev（`:8026/:8031/:8036`） | 1..max / 1..1 | 否 |
| mdmss-0..3（`:8041/:8104/:8167/:8230`） | 102℃ | `0x7b` lv8、`0x7c` lv10、`0x7d` lv6（`:8079/:8084/:8089` 起，每 zone 三条） | 固定档 | 否（QMI） |
| mdmss-0..3 | 105℃ | `0x7b` lv255、`0x7d` lv255（`:8094/:8099` 起，每 zone 两条） | 最大档 | 否（QMI） |
| mx-pe（`:8336`，`status="disabled"`） | 1/2/3 | cdsp lv1 / kgsl lv1 / lte lv10 / nr_scg lv10（`:8369-8384`） | 固定档 | 否，且该 zone 运行时不存在 |
| isense_trim（`:8389`） | 2 | `0x19` lv15、`0x1c` lv15、`0x8a` cdsp_hw lv1（`:8408/:8413/:8418`） | 固定档 | 否 |

合计 46 条，分布在 23 个 zone 上；形状见 `01-SAME-HARDWARE.md:262-269`
（`trip = <phandle>` + `cooling-device = <phandle 下限 上限>`）。

### 2.3 定义了但没有任何 map 引用的节点（不能当"已有执行器"）

| 节点 | DTS 行 | 说明 |
|---|---|---|
| `apc1-pause`（`0x420`） | `:16503-16507` | `qcom,cpus=<0x1a 0x1b 0x1c>`，但 46 条 map 里没有一条引用它 |
| `cpu-6-7-pause`（`0x421`） | `:16509-16513` | 同上 |
| `qcom,cpu-hotplug` 的 `cpu0..7-hotplug`（`0x422-0x428`） | `:16551-16595` | 有 `#cooling-cells`，但无 map 引用 |
| `qcom,cpu-voltage-cdev/apc1-cluster`（`0x429`） | `:16597-16605` | 电压域 cooling，无引用 |
| `thermal-ddr-freq-table`（`0x22c`） | `:16607-16610` | 只是 `qcom,ddr-cdev` 的频率表指针 |
| `qcom,userspace-cdev/display-fps`（`0x43c`） | `:16800-16807` | `qcom,max-level=4`，无引用 |
| `qcom,cpufreq-cdev` | `:16790-16793` | **无 phandle、无 `#cooling-cells`**，`qcom,cpus=<0x15 0x19 0x1c>` |
| `qcom,devfreq-cdev` | `:16795-16798` | **无 phandle**，`qcom,devfreq=<0x69>` |

结论：DT 里"能当执行器的节点"比"被策略引用的执行器"多得多；**没有被 map 引用的节点不能算作现成能力**
（`01-SAME-HARDWARE.md:258-260` 只把它们记作补充节点）。

### 2.4 没有风扇

`grep -ci fan` 在整份 DTS 里 **0 命中**；`grep -ci pwm` 只有 1 命中，且是 `mondrian.dts:9064` 的
`qcom,bus-vector-names` 字符串（`PWM_G1_L1` 等 DDR 总线档位名），不是风扇 PWM。**本板纯被动散热**。

### 2.5 Android 用户态真正在用的执行器（`thermald-devices.conf`，21 块）

| 执行器 | 配置行 | 目标 |
|---|---|---|
| `gpu`（`cooling_name:gpu`） | `:3-9` | GPU 频率（Android kgsl） |
| `battery` | `:11-17` | 电池侧限流 |
| `backlight-clone`（`brightness0-clone`，def 200） | `:19-25` | 背光 |
| `temp_state` / `modem_limit` / `market_download_limit` / `poor_modem_limit` / `wifi_limit` | `:27-33`、`:75-81`、`:83-89`、`:123-129`、`:131-137` | 小米 `thermal_message` 的 sysfs 开关 |
| `thermal_hbm_disabled` | `:35-41` | 屏幕 HBM |
| `wireless_charge` | `:43-49` | 无线充限流 |
| `modem_ul` / `modem_dl` / `modem_pa_nr` / `modem_pa_lte` | `:51-57`、`:59-65`、`:107-113`、`:115-121` | modem PA/TJ（QMI） |
| `thermal_fcc_override`（`constant_charge_current`，def 22000000） | `:67-73` | 充电电流上限 |
| `lmh_cpu4` / `lmh_cpu7`（`cooling_name:cpu4` / `cpu7`） | `:91-97`、`:99-105` | 硬件 LMH（对应 DTS `0x19`/`0x1c`） |
| `hotplug_cpu7`（`cooling_name:pause-cpu7`） | `:139-145` | 对应 DTS 的 `pause-cpuN` 别名节点（`:16515` 起） |
| `thermal_max_brightness` / `thermal_reverse_limit` / `power_level`（def 100000000） | `:147-153`、`:155-161`、`:163-169` | 亮度上限 / 反向充电 / 省电档 |

这 21 项里，本移植现在有接口的只有"停核"一项（§2.6）；背光、HBM、充电电流、GPU/DDR 频率、QMI
全都要先有对应子系统。

### 2.6 本移植现有的"执行器"库存

| 能力 | 现状 | 证据 |
|---|---|---|
| 停核 | 有 `ArmCpu::haltCPU()`，但是**单向**：`quiesceCPU()` + `setCPUState(kIOCPUStateStopped)` + `daifset` + 死循环 `wfi` | `drivers/ArmCpu/ArmCpu.cpp:55`（声明）、`:489-495`（定义） |
| 重新上核 | 有 `startCPU()` → `psci_smp_start_cpu()` | `drivers/ArmCpu/ArmCpu.cpp:497-500` |
| CPU 频率/电压 | **没有**。XNU 只在 `IOCPU.cpp:369/:373` 把 `gPEClockFrequencyInfo.cpu_frequency_hz` 当属性发布，不设频率 | `iokit/Kernel/IOCPU.cpp:369-373` |
| GPU 频率 | 没有（Adreno 归档只做 MMU/固件探针，`CONFIG_XNU_NATIVE_ADRENO` 未启用） | 构建 manifest 的 skip 列表（`/mnt/e/k60-work/artifacts/thermal-20261114c/build-manifest.json`） |
| DDR 频率 | 没有 | 同上 |
| 充电电流 | 没有：`K60Battmgr` 只有 init/channel_up/channel_down/refresh/sent/receive/timeout/sample | `drivers/PongPower/K60Battmgr.h:55-68` |
| 电池属性发布 | 有，但只读：`K60Battery : IOPMPowerSource` | `drivers/PongPower/K60Battery.cpp:46`、`:85`、`:349` |
| 背光/HBM | 未见可用的设置接口 | — |

## 3. (c) 该不该注册 IOHWMControl / AppleSMC 风格执行器：不该，只上报

### 3.1 这两类东西在本树根本不存在

在 `.cache/xnu-work` 里 `grep -r IOHWMControl` 与 `grep -r AppleSMC` **零命中**；
`find -iname "*SMC*"` 在 fakeroot 的 `Kernel.framework/{Headers,PrivateHeaders}` 下也零命中。
也就是说没有"注册一个执行器"的基类可继承 —— 参考移植的 `AppleSMCSensorDispatcher` 是它自己仿写的
（本仓对应物是 `drivers/PongThermal/K60ThermalService.cpp`，见 `06-KEXT-SERVICE.md`），
并不是 Apple 提供的框架。

### 3.2 树里唯一导出的热事件通路，以及它的边界

| 事实 | 证据 |
|---|---|
| 发布入口是 `IOPMrootDomain::systemPowerEventOccurred` 的两个重载（`const OSSymbol*, uint32_t` 与 `const OSSymbol*, OSObject*`） | `iokit/Kernel/IOPMrootDomain.cpp:8098`、`:8139`；声明 `iokit/IOKit/pwr_mgt/RootDomain.h:177`、`:181`（`:169-175` 的注释写明「只有 Apple 自家 kext 该调用」） |
| 两个重载都在内核导出表里，本移植**可以调用** | `build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/all-kpi.exp:908`、`:909`；取 root domain 用 `IOService::getPMRootDomain()`（`all-kpi.exp:2396`、`iokit/IOKit/IOService.h:1285`） |
| 键名 `Thermal_Level_Warning`，取值 `Normal=0`/`Danger=5`/`Critical=10`/`Warning=100`/`Trap=110`/`Unknown=255` | `iokit/IOKit/pwr_mgt/IOPM.h:753`、`:763-772` |
| 只有 `Warning` 与 `Trap` 会把 `thermalWarningState` 置 1；发 `Danger(5)`/`Critical(10)` **什么也不会发生** | `IOPMrootDomain.cpp:8133` |
| `kIOPMThermalWarningLevelDanger` 是 `Warning`(100) 的别名，不是 5 —— 容易读错 | `IOPM.h:775` |
| 它影响的是睡眠策略（低电或热警告/紧急状态时总是睡眠），不是频率 | `IOPMrootDomain.cpp:7411-7412`、`:7485`、`:7514` |
| 事件同时被塞进 `thermalsDict` 并以 `Power Status` 属性发布，供用户态读 | `IOPMrootDomain.cpp:8143-8174`、`RootDomain.h:103` |
| 树内**没有任何生产者**调用它 —— 本移植要当第一个 | `grep systemPowerEventOccurred` 除 `IOPMrootDomain.cpp` 与头注释外零调用者 |
| `CPU_Power_Limits`/`CPU_Speed_Limit` 这组键确实存在，注释说"作为参数传给 systemPowerEventOccurred" | `IOPM.h:723-745` |
| 但本树没有任何代码消费 `CPU_Power_Limits`，而且即使消费也没有执行器（§2.6） | 同上 grep 零消费者；`IOCPU.cpp:369-373` |
| `kIOPMPerformanceWarningKey`（`Performance_Warning`）同样零消费者 | `IOPMPrivate.h:1051-1053`，全树无引用 |

### 3.3 为什么 cooling-map 不做成内核逻辑

1. **46 条里 20 条是 QMI 远端**（`0x75`/`0x7b`/`0x7c`/`0x7d`/`0x8a`），本移植没有 QMI 通路（§2.2）。
2. **9 条需要 GPU/DDR 频率框架**（`0x69` kgsl 2 条、`0x79` ddr-cdev 1 条、`0x19`/`0x1c` cpufreq 5 条），都没有（§2.6）。
3. **8 条是停核**（cpuX-pause）。`haltCPU()` 是单向的（`ArmCpu.cpp:489-495`），要"压到某一档再升回来"
   必须自己实现 pause/resume 状态机（`startCPU()` → `psci_smp_start_cpu`，`ArmCpu.cpp:497-500`），
   等于新写一个子系统，而且直接触碰 CPU 上电流程 —— 属于 `P-178` 要求单变量验证的高风险改动。
4. **语义不匹配**：DT 的 trip 是 Linux thermal framework 的触发点，配 `cooling-device = <phandle min max>`
   使用；本移植既没有 thermal zone 框架也没有 cooling device 框架，把这套表搬进内核只会得到一堆
   没有消费者的常量（`01-SAME-HARDWARE.md:271-273` 早已决定不复用这套策略，只把它当"板级设计意图"）。

### 3.4 参考移植与用户态现状

- SM8550 参考移植同样只上报：`ThermalLevel.cpp`/`ThermalProbe.cpp` 里 grep `systemPowerEventOccurred`、
  `IOPMrootDomain`、`setFrequency`、`voltage` **全部零命中**；它只通过 user client 提供 `mTPL`，
  `notify_post` 由 `thermalmonitord` 自己发（参考仓库 `UniXNU-sheng` 的 `ThermalLevel.h:14-15`）。
- 本仓启动器把 `thermalmonitord` 放在 DENY 列表里（`userland/mkjobs.py:217`），所以即使 kext 侧已经能
  发布 `mTPL`，现在也没有消费者在跑。**在它被放行之前，做执行器没有任何接收方。**

### 3.5 决策

**本阶段：只上报温度与压力等级，不注册任何执行器。** 具体是：

- in-tree 驱动只读 32 路 STATUS 并打印域温度（`drivers/PongThermal/pong_thermal.c:100-150`、`:152-188`）；
- 压力等级只做数据与算术（`drivers/PongThermal/K60ThermalLevel.c:87-123`），由 kext 侧 user client 发布
  （`drivers/PongThermal/K60ThermalService.cpp:253-261`、`:317`）；
- **不**调用 `systemPowerEventOccurred`：它只改睡眠策略，而在没有执行器、没有 `thermalmonitord` 的现状下，
  把机器往"热警告就睡眠"的方向推只会带来无关的睡眠行为变化，收益为零、风险非零。

**重新考虑的触发条件**（三条同时满足才做）：

1. 上机确认 32 路读数可信（task-2 的 `SROT_HW_VER`/`SROT_CTRL` + 原始 STATUS 字）；
2. `thermalmonitord` 被放行（`userland/mkjobs.py:217` 的 DENY 去掉）或另有消费者；
3. 出现真实的过热事件证据（日志里域温度逼近 95/110℃），而不是"理论上可能热"。

## 4. 若未来要做执行器：候选排序与前置条件

| 优先级 | 候选 | 为什么可行 | 前置条件 |
|---|---|---|---|
| 1 | 充电限流（`thermal_fcc_override`，`thermald-devices.conf:67-73`） | 影响最小、可逆、不碰 CPU/GPU | `K60Battmgr` 需要新增设置电流的通道（现在只有 `:55-68` 的采样/通道接口） |
| 2 | 背光/HBM 上限（`thermald-devices.conf:19-25`、`:147-153`） | 用户可见、可逆 | 显示栈需要提供亮度设置接口（当前未见） |
| 3 | `IOPM` 的 `Thermal_Level_Warning`（`IOPM.h:753`） | 调用面小、已导出（`all-kpi.exp:908-909`） | 需要 §3.5 的三条触发条件；且注意只有 `Warning`/`Trap` 有效（`:8133`） |
| 4 | CPU pause/resume | 唯一"本地物理动作" | 需要 pause/resume 状态机 + PSCI 上核路径验证（`ArmCpu.cpp:489-500`），按 `P-178` 单变量上机 |
| 5 | DVFS / GPU / DDR 频率 | — | 等于新写三个子系统，不建议在本项目范围内做 |

## 5. 复现命令

```bash
# 重建 DTS（UEFI 的 DTB 与 vendor_boot 的 DTB 实质相同，见 04 篇 §7）
dtc -I dtb -O dts \
  /mnt/e/hackios/uefi-mondrian/Platforms/Xiaomi/mondrianPkg/FdtBlob/sm8475-xiaomi-mondrian.dtb \
  -o /tmp/mondrian.dts

# trip 温度直方图（本文 §1.1 的数字）
sed -n '6643,8422p' /tmp/mondrian.dts | grep -o 'temperature = <0x[0-9a-f]*>' | sort | uniq -c

# trip 类型：146 passive / 8 active
sed -n '6643,8422p' /tmp/mondrian.dts | grep -c 'type = "passive"'
sed -n '6643,8422p' /tmp/mondrian.dts | grep -c 'type = "active"'

# cooling-map 条数：zone 内 46，全文 50（另外 4 处是 compatible 里的 cooling-device 字样）
sed -n '6643,8422p' /tmp/mondrian.dts | grep -c 'cooling-device'
grep -c 'cooling-device' /tmp/mondrian.dts

# 风扇：0 命中；pwm 唯一命中是 :9064 的 qcom,bus-vector-names 字符串
grep -ci fan /tmp/mondrian.dts
grep -ci pwm /tmp/mondrian.dts
```

## 6. 与其它文档的关系

- `01-SAME-HARDWARE.md:119-273`（§5-§7）是本文 §1、§2 的逐 zone 底表；本文只补三件它没做的事：
  trip 来源的排他性核查（§1.2）、未被引用的执行器节点清单（§2.3）、XNU 执行器决策（§3）。
- `05-PRESSURE-LEVEL.md:30-72`（§2-§3）记的是"五域三档 + 滞回"这套**算术**；本文 §1.3 给出它的 DTS 出处。
- `04-ANDROID-EVIDENCE.md:85-99`、`:199-266` 是本文 §1.2 的现场证据与标定负结论。
- `08-KERNEL-DRIVER.md:8-20`（§1）的 in-tree 驱动只做只读快照 + 轮询打印，与本决策一致。
