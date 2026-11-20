# 温控跳变点地图（AP 侧，纯模型）

状态：**纯跳变点/建议模型 + host 断言（125 项）；没有传感器读取、没有任何降温动作、没有寄存器写路径。**
分支 `feat/power-ios27-carry`，模块 `drivers/PongPower/K60ThermalMap.h` / `.c`。
编号说明：本分支只有 00–08；`feat/charge-auth` 分支占 09（充电认证移植），所以本文件用 10，合并后编号连续。

## 1. 为什么现在做这一层

温控线在 `feat/thermal-tsens` 上已经验收了**只读**部分：22 个传感器读数、5 个温区校准、
压力等级经 `IOPMrootDomain` 发布（2026-11-15 真机 `PongThermal: tsens0[3] cpuss-2 zone27 43.0 C`、
`level trapping (3) published as Thermal_Level_Warning=3`）。它不会降温，因为真正的冷却动作
（`cpufreq-cdev`）没有接线，pong 没有 thermal 动作、zizhan 的 `ZizhanTsensCore.h` 只读、
sheng 的 `CpuFreqProbe.cpp` 不接受温度输入、Linux 侧的 `cpufreq-cdev` 是 Linux thermal framework 绑定。
于是 2026-11-19 决定 **方案 1（park）**：只保留只读监控与等级上报，主动降温不做，
重访触发是 GPU 120 fps 飞行完成并做一次热预算实测（届时用默认关闭的 `pong_thermal_cap=1`）。

park 的是**动作**，不是**契约**。iOS 27 迁移要带走的是「多少度算过热、过热时禁止什么」，
这部分与 OS 版本无关，也不需要碰传感器：调用方（tsens、ADC、PMIC 告警）读温度，
模型只回答等级与后果。这与 `K60RailPlan` 的分工一致——顺序模型已经在那里，
`:108` 要求的「温控门」正好由本模块的 `allow_raise` 提供，两者在 host 套件里互相钉住。

## 2. 现场事实（`E:/k60-work/reports/live-6033dbec-fdt.dts`）

反编译自 `E:/k60-work/reports/live-6033dbec-fdt.dtb`（dtc），82 个 `thermal-zones`、
18 个 `cooling-devices`，全部带 trip。这些 trip 值不是从反编译文本里抄的，可以直接从这个 dump 读回来：
`python3 scripts/read-fdt-props.py E:/k60-work/reports/live-6033dbec-fdt.dtb --node /soc/thermal-zones/ddr/trips/ddr0-config --prop temperature --hex`
→ `00015f90`（90000）。同一个命令换成 `gpuss-0/trips/tj_cfg`、`cpu-1-0/trips/cpu4-emerg0-cfg`、
`aoss-0/trips/reset-mon-cfg`、`pa/trips/thermal-engine-config0` 就是阶梯剩下的四档；`--list --contains thermal-zones`
列出全部温区。`HW-CONTRACTS.toml` 的五条 `second` 字节区间用的就是这五组十六进制，门禁逐字节比对它们。

AP 侧可行动的温区与读温来源：

| 温区 | 读温来源 | 备注 |
| --- | --- | --- |
| `cpu-0-0..3` | tsens1 ids 1..4 | 小核簇 |
| `cpu-1-0..8` | tsens0 ids 5..13 | 大核簇 |
| `cpuss-0..3` | tsens0 ids 0..3 | 簇公共 |
| `gpuss-0/1` | tsens0 ids 14/15 | GPU |
| `ddr` | tsens0 id 9 | 内存控制器 |
| `aoss-0/1` | tsens0 | 常开子系统 |
| `pm8350_tz` / `pm8350c_tz` / `pm8450_tz` | PMIC temp-alarm | 板级供电 |

两个 tsens 提供者：`/soc/thermal-sensor@c263000`（compatible `qcom,tsens-v2`，
reg `0xc263000 0x1ff` + `0xc222000 0x1ff`，16 个传感器，中断 506/508，phandle `0x5d`）与
`/soc/thermal-sensor@c265000`（同构，`0xc265000`/`0xc223000`，中断 507/509，phandle `0x6b`）。
ADC 侧：`adc-tm7`（phandle `0x586`：`pm8350_msm_therm 0x144`、`flash 0x145`、`quiet 0x146`、
`charger 0x147`、`wireless 0x34b`、`pa0 0x44a`、`pa1 0x44b`、`wifi 0x44c`）与
`adc-tm7-iio`（`usb_conn 0x347`）。PMIC temp-alarm 节点：pm8350 `0x55e`、pm8350c `0x562`、
pm8350b `0x56a`、pmr735a `0x56c`、pmr735b `0x56d`、pm8450 `0x56e`；
BCL：pm8350c `0x563`、pm8350b `0x56b`。

跳变点（millidegC，FDT 原值）：`0x1e848`=125000（thermal-engine-config / thermal-hal-config /
active-config0）、`0x1c138`=115000（reset-mon-cfg）、`0x1adb0`=110000（每核 emerg）、
`0x17318`=95000（tj_cfg / junction / PMIC trip0）、`0x15f90`=90000（ddr0-config、pm8350b trip0）、
`0x18e70`=102000 与 `0x19a28`=105000（modem active，不在本模型内）。

冷却设备：`cpu@400 0x19`、`cpu@700 0x1c`（`qcom,cpufreq-cdev`）、逐核 pause
`0x5f/0x62/0x65/0x6d/0x6f/0x71/0x73`、`apc1-pause 0x420`、`cpu-6-7-pause 0x421`、
`qcom,kgsl-3d0@3d00000 0x69`（GPU）、`cdsp 0x75`/`cdsp_hw 0x8a`、`ddr 0x79`、
modem lte/nr `0x7b/0x7c/0x7d`。**大多数温区没有 cooling-map**：AP 侧真正可行动的只有
`cpu-1-*`、`cpu-0-*`、`gpuss-*`、`ddr` 与三个 PMIC 温区。

## 3. 等级阶梯与策略

| 等级 | 阈值 | 含义 |
| --- | --- | --- |
| `K60ThermalLevelNone` | < 90000 | 不触发 |
| `K60ThermalLevelWarm` | ≥ 90000 | 主动降温配置生效 |
| `K60ThermalLevelJunction` | ≥ 95000 | 结温：热点域上冷却设备 |
| `K60ThermalLevelEmergency` | ≥ 110000 | 禁止升档，两个域都降档 |
| `K60ThermalLevelReset` | ≥ 115000 | reset-monitor 区间 |
| `K60ThermalLevelShutdown` | ≥ 125000 | 关机区间 |

聚合规则（`k60_thermal_advise`）：**最坏读数胜出**——先比等级，再比温度，最后比更小的 zone index
（结果确定，不依赖输入顺序）。派生的三个门：

- `allow_raise = level < Emergency`：直接喂 `k60_rail_plan(state, target, thermal_ok, ...)` 的
  `thermal_ok`，即官网 `:108` 的温控门；`Emergency` 起的升档请求返回 `-2`；
- `throttle_cpu`：CPU 域（`cpu-0`/`cpu-1`/`cpuss`）`Junction` 及以上，或任意域 `Emergency` 及以上；
- `throttle_gpu`：`gpuss` 的 `Junction` 及以上，或任意域 `Emergency` 及以上。

刻意**不纳入**：modem、camera、NSP、video、QMI（modem/cdsp）与 mmWave 温区。它们的主人是对端处理器，
K60 内核驱动不应替它们降档；把它们放进 `allow_raise` 会在 CPU 并不热的时候冻结升档。

## 4. 接口

```c
enum k60_thermal_zone { K60ThermalZoneCpu0, K60ThermalZoneCpu1, K60ThermalZoneCpuss,
    K60ThermalZoneGpuss, K60ThermalZoneDdr, K60ThermalZoneAoss, K60ThermalZonePm8350,
    K60ThermalZonePm8350C, K60ThermalZonePm8450, K60ThermalZoneCount };
enum k60_thermal_level { K60ThermalLevelNone, K60ThermalLevelWarm, K60ThermalLevelJunction,
    K60ThermalLevelEmergency, K60ThermalLevelReset, K60ThermalLevelShutdown,
    K60ThermalLevelCount };

typedef struct { int zone; int32_t millideg; } K60ThermalReading;
typedef struct {
    int zone;                  /* 未过任何跳变点时 -1 */
    int32_t millideg;          /* 胜出读数，未过跳变点时 0 */
    enum k60_thermal_level level;
    int allow_raise;           /* Emergency 起为 0：喂 k60_rail_plan 的 thermal_ok */
    int throttle_cpu;
    int throttle_gpu;
} K60ThermalAdvisory;

const char *k60_thermal_zone_name(int zone);
const char *k60_thermal_level_name(enum k60_thermal_level level);
enum k60_thermal_level k60_thermal_level_at(int32_t millideg);
int k60_thermal_zone_level(int zone, int32_t millideg);   /* 未知 zone 返回 -1 */
int k60_thermal_advise(const K60ThermalReading *readings, unsigned count,
                       K60ThermalAdvisory *out);
```

`k60_thermal_advise` 返回 0 成功、`-1` 输出为空、`-2` count 非零但 readings 为空、
`-3` count 超过 `K60_THERMAL_MAX_READINGS`（16）、`-4` 出现未知 zone。
空输入是合法的 `None` 建议，便于「本轮没有读数」不制造假告警。

## 5. 它不做什么

- 不读传感器：不碰 tsens/ADC/PMIC 寄存器，不建 IOKit 服务，不写任何 MMIO；
- 不执行降温：没有 `cpufreq-cdev`，不下发任何 pause/限频/关机；
- 不声称跳变点已按 SM8475 手册核对：数值全部来自现场 FDT，是**厂商声明**，不是手册读数；
- 不覆盖远端处理器的温区（见 §3 最后一段）。

## 6. 验证

```
bash scripts/tests/run-k60-power-host.sh
```

十个套件共 **1915** 项（203/140/40/73/58/1038/134/125/99/5），其中 `thermal` 125 项
（`scripts/tests/test-k60-thermal-map.c`）：名字表、13 个阶梯边界、9 个温区 × 3 个等级、
错误码（空输出/空读数/超量/未知 zone）、每个等级的 `allow_raise` 与两个 throttle、
最坏读数胜出与平局规则（同等级同温度取更小 zone、同 zone 取更高温度）、
以及**与 `K60RailPlan` 的交叉断言**：`111000` 的读数让 `k60_rail_plan` 返回 `-2`（升档被拒），
`96000` 的读数让它返回 0。`K60_POWER_SANITIZE=1` 重跑同一套（ASan/UBSan）也是 1915。
`scripts/check-power-portability.py` 现在编译 7 个 freestanding C11 模块，本模块包含在内。

## 7. 下一步（都要求确认，不是本文件的结论）

1. 只读：把 tsens 读数喂进 `k60_thermal_advise` 并把 `level/allow_raise` 打进 console（仍不写 EPSS）；
2. 主动降温方案 2 的飞行（`pong_thermal_cap=1`）只在 GPU 120 fps 热预算实测之后；
3. iOS 27：模型原样搬走，只按 12377 的 tsens 节点名重接读数来源。

## 8. 参考

- 现场 FDT：`E:/k60-work/reports/live-6033dbec-fdt.dts`（82 温区 / 18 冷却设备）
- 解析脚本：`E:/k60-work/scratch/parse-thermal.py`
- 只读温控线：`feat/thermal-tsens`（22 传感器、等级发布；主动降温未接）
- `power/00-POWER-PAGE-CONFORMANCE.md` §5「温控与主动降温」、`power/07-RAIL-ORDERING.md`（`:108` 顺序）
- 官网：<https://unixnu.com/zh/porting/power>
