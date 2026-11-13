# WCD938x codec — K60 (mondrian / SM8475 / cape) 事实与判定

> 目标子系统：音频 codec 侧（WCD938x / LPASS macro / SoundWire）
> 日期：2026-11-14
> 状态：① 同型 ✅ ② 官方 ⚠️（无 K60 datasheet，用 Pong/phk110 源码 + 主线 DTS）③ 反编译 ✅（live FDT）④ 广域 ✅ ⑤ 方案 ✅ ⑥ 深挖 ✅ ⑦ 本机验证 ⏳ ⑧ 上机 ❌

## 1. 结论（先看这里）

1. **K60 的 codec 是 WCD938x，与 Pong（Nothing / SM8475 / cape）同型号，与 phk110（POCO X5 Pro / SM6375 / yupik）同型号。**
   三平台同一颗 codec → WCD938x 的寄存器序列、SoundWire 从设备 ID、micbias/供电拓扑可以复用；
   **不能复用**的是板级差异：供电 rail 名、reset GPIO、LPASS 宏基址、TX SoundWire master 归属、时钟树。
2. **K60 是 split-codec（`qcom,split-codec = 1`）**：codec 本体（`wcd938x-codec`）与两个 SoundWire slave
   （`wcd938x-tx-slave` / `wcd938x-rx-slave`）是三个独立节点，挂在不同 master 下。
3. **codec 复位脚 = GPIO43**（不是 phk110 的 GPIO83，也不是 Pong 的 GPIO108 之外的第三个值——Pong 也是 43）。
4. **codec 三路 1.8 V 供电来自 pm8350_s10（固定 1.8 V）**；mic bias boost 来自 pm8350c_bob（3.0–3.96 V）。
5. **TX core 时钟 id = 0x30c @ 19.2 MHz**（`tx_core_clk`），这是 `dts/mondrian.dts` 里 `tx-core-clock-id` 空占位缺的值。
6. **本文件不授权任何写操作。** 第 7 节列出必须先由 Lead 的 ADSP/PAS1 工作解锁的前置条件。

## 2. 同型判定依据（① 同型）

| 平台 | SoC | codec | 证据 |
|---|---|---|---|
| K60 (mondrian) | SM8475 / cape | WCD938x（split-codec） | `live-fdt.dts:23589-23616`：`compatible = "qcom,wcd938x-codec"`（:23615），`qcom,split-codec = 1`（:23614），phandle 0x5d8 |
| Pong (Nothing) | SM8475 / cape | WCD938x | `/mnt/e/k60-work/references/pong-power/PongWcd938.h:2`「Pong SM8475 WCD938x prerequisites」；同文件用 TX slave ID `0x000d01170223` |
| phk110 (POCO X5 Pro) | SM6375 / yupik | WCD938x | `/mnt/e/k60-work/references/phk110-port/drivers/audio/hakios.mic.c:579` `#define CODEC_TX_ID 0x000d01170223ull`；头注释自述源码来自 Xiaomi techpack `asoc/codecs/wcd938x/` |

**同一颗 codec 的强证据**：三个平台都要求 SoundWire 枚举出 **`0x000d01170223`**（8 字节设备 ID：`0x0d` = WCD938x 的
Manufacturer/Part ID 对，`0x1170223` = 设备唯一 ID）。Pong 的实现（`PongWcd938.h:105-115`）只接受这一个值，其他一律失败。

**不同点（必须按 K60 重算，不许照抄）**：

| 项目 | phk110 (SM6375) | Pong (SM8475) | K60 (SM8475/cape) |
|---|---|---|---|
| codec reset GPIO | 83（`hakios.mic.c:445-446`） | 43（`PongWcd938.h:59-120`） | **43**（`live-fdt.dts:2494-2507` pinctrl `wcd938x_reset_active`） |
| TX SWR master 基址 | 0x03230000（独立 tx_swr，`hakios.mic.c:394-400`） | 0x033b0000（va_swr_master） | **0x033b0000**（`live-fdt.dts:23349-23367` va_swr_master `swrm-io-base`） |
| TX macro 基址 | 0x03220000 | 0x03220000 | **0x03220000**（`live-fdt.dts:23421`） |
| VA macro 基址 | 0x03370000 | 0x033f0000 | **0x033f0000**（`live-fdt.dts:23336`） |
| split-codec | 未标注 | 未标注 | **1** |
| 供电 | L18B + BoB（boot 链保持） | pm8350_s10（`PongWcd938.h:29-38` 注释 "Actual DT: PM8350 S10B supplies WCD RXTX/buck/IO at 1.8V"） | pm8350_s10 + pm8350c_bob |

## 3. live FDT 逐条事实（③ 反编译）

### 3.1 `wcd938x-codec`（`live-fdt.dts:23589-23616`，phandle 0x5d8）

| 属性 | 值 | 行 |
|---|---|---|
| `compatible` | `"qcom,wcd938x-codec"` | :23615 |
| `qcom,split-codec` | 1 | :23614 |
| `qcom,cdc-static-supplies` | `cdc-vdd-rxtx` / `cdc-vddio` / `cdc-vdd-buck` / `cdc-vdd-mic-bias` | :23591 |
| `qcom,cdc-micbias1..4-mv` | 0xabe = **2750 mV** ×4 | :23592-23595 |
| `cdc-vdd-mic-bias-supply` | phandle **0x30c** | :23598 |
| `cdc-vdd-buck-supply` / `cdc-vddio-supply` / `cdc-vdd-rxtx-supply` | phandle **0x3d** ×3 | :23601 / :23604 / :23607 |
| 电压/电流 | vdd-buck 0x1b7740(1.8 V)/0x9eb10 µA；vddio 0x1b7740/0x7530；vdd-rxtx 0x1b7740/0x7530；vdd-mic-bias current 0x7530 | :23600-23608 |
| `qcom,tx-slave` / `qcom,rx-slave` | 0x5e3 / 0x5e2 | :23609-23610 |
| `qcom,wcd-rst-gpio-node` | 0x5e1 | :23610 附近 |
| `qcom,swr-tx-port-params`、`qcom,tx_swr_ch_map`、`qcom,rx_swr_ch_map` | 完整（32/… 个值） | :23611-23613 |

### 3.2 供电 phandle 落定（此前只是猜测，现证实）

- **0x3d = `pm8350_s10`**：`live-fdt.dts:5792-5804` `rpmh-regulator-smpb10` → `regulator-pm8350-s10`，
  `regulator-name = "pm8350_s10"`，`qcom,set = <0x03>`，min=max=init=`0x1b7740`（固定 1.8 V），phandle 在 :5802。
- **0x30c = `pm8350c_bob`**：`live-fdt.dts:6373-6389` `rpmh-regulator-bobc1`（`qcom,regulator-type = "pmic5-bob"`，
  `supported-modes = <0 3>`，`mode-threshold-currents = <0 0xf4240>`，`qcom,send-defaults`）→
  `regulator-pm8350c-bob`，name `"pm8350c_bob"`，min `0x2de600`(3.0 V) max `0x3c6cc0`(3.96 V)，
  `qcom,init-voltage` 原文为两字节字符串 `"\02K"`、`init-mode = <0>`，phandle 在 :6388。
- 邻接参考：0x30b = `pm8350c_l13`（:6362-6369）；0x43 = `pm8350_s5_level`（:5782-5788）。

> ⚠️ 未证实点：DT 只声明「这三路接 s10」，**没有**声明当前电压是 AP 投票出来的还是 boot 链残留。
> Pong 的实现是先投票再碰 codec（`PongWcd938.h:29-38`），touch 驱动的注释则明确写「Retained IOVDD is a prerequisite,
> NOT measured power」（`patches/xnu/…-pong-touch-console.patch:177-180`）。→ 上机必须**先读回** rail 状态再碰 codec。

### 3.2.1 供电 rail 表（任务第 4 步的交付物）

| rail（DT `regulator-name`） | 供谁 | 目标电压 | DT 电流上限 | 依据 | AP 投票通道 |
|---|---|---|---|---|---|
| `pm8350_s10`（SMPB10） | WCD938x 的 `cdc-vdd-buck` / `cdc-vddio` / `cdc-vdd-rxtx` | **1.8 V**（`0x1b7740`，min=max=init，固定不可调） | buck `0x9eb10` = 650 mA；io / rxtx 各 `0x7530` = 30 mA | `live-fdt.dts:5792-5804`（phandle 在 :5802，`qcom,set = <0x03>`）；三个 supply 属性全是 0x3d（:23601 / :23604 / :23607） | **有**，RPMh `smpb10`：Pong 的形状是 `pong_rpmh_vote(address+8, 7)`（mode）→ `pong_rpmh_vote(address, 1800)`（level，单位 mV）→ `pong_rpmh_vote(address+4, 1)`（enable），见 `PongWcd938.h:29-38`。需要 Lead 的 RPMh 投票基础设施（`drivers/PongPower/K60PmicRail.c`），本子任务不写 RPMh 寄存器 |
| `pm8350c_bob`（BOBC1） | WCD938x 的 `cdc-vdd-mic-bias`（mic bias boost） | 3.0–3.96 V（min `0x2de600` / max `0x3c6cc0`），`qcom,init-voltage` 原文是两字节字符串 `"\02K"`、`init-mode = <0>` | 无负载上限声明；`mode-threshold-currents = <0 0xf4240>` 的 1 A 是 bob 模式切换门限，不是负载 | `live-fdt.dts:6373-6389`（phandle :6388）；`cdc-vdd-mic-bias-supply = 0x30c`（:23598） | **有**，RPMh `bobc1`（同上基础设施） |
| 功放供电（**DT 里没有节点**） | 两颗 AW882xx（`aw882xx_smartpa@34/@35`） | **未知** | — | 两个节点都没有任何 `*-supply` 属性（`live-fdt.dts:13318-13341`）；`hakios.speaker.c` 也没有写功放供电（phk110 由 boot 链保持） | **无 AP 投票证据**。只能靠上机反推：读 `AW_SYSST` 的 `UVLS`（1<<14）与 `AW_PVBAT(0x21)`（×6025/1023 mV），若 ID 读不到先怀疑这一路没电 |

说明：
- codec 的 micbias 电压（`micbias1..4` 全为 `0xabe` = 2750 mV，`live-fdt.dts:23592-23595`）是 **codec 内部**的 bias 设定，不是 rail 电压；rail 只负责把 BoB 抬到 3.0–3.96 V。
- `pm8350_s10` 是 min=max=init 的固定档，所以「投票」只是 enable + mode，不存在选电压的自由度——但**仍要投**，因为 PMIC 上电默认不保证它开着。
- 若 Lead 的 `K60PmicRail.c` 暂不覆盖 `smpb10` / `bobc1`，codec 侧验证只能先读回 rail 状态（RPMh TCS 或 PmicGlink 的现成读路径），不要假设 Android 的档位还在。

### 3.3 reset GPIO 43（`live-fdt.dts:2494-2523`、:32560-32565）

| 节点 | phandle | 内容 |
|---|---|---|
| `wcd938x_reset_active` | **0x2b9** | mux pins `"gpio43"` function `"gpio"`；config：gpio43、`drive-strength = <0x10>`（16 mA）、output-high |
| `wcd938x_reset_sleep` | **0x2ba** | gpio43、16 mA、bias-disable、output-low |
| `msm-cdc-pinctrl`（`wcd-rst-gpio-node`，phandle 0x5e1） | — | `pinctrl-names = "aud_active", "aud_sleep"`；`pinctrl-0 = <0x2b9>`、`pinctrl-1 = <0x2ba>`（:32560-32565） |

→ `dts/mondrian.dts` 的 `codec-reset-gpio` 应填 **43**（与 GAP-ANALYSIS 的 43 一致，现由 pinctrl 节点独立证实）。
→ 复位极性：active = **高**（output-high 为 active 组）。Pong 的写法与此一致：
`pin(43,(1u<<9)|(7u<<6),0); IOSleep(20); pin(43,(1u<<9)|(7u<<6),1); IOSleep(20);`（`PongWcd938.h:59-120` 第 2 步）。

### 3.4 audio-ref-clk：`tx-core-clock-id` 的答案（`live-fdt.dts:32567-32646`）

| 节点 | phandle | `codec-lpass-clk-id` | `ext-clk-freq` | `ext-clk-src` |
|---|---|---|---|---|
| `va_core_clk` | 0x5d2 | 0x307 | 0x124f800 (19.2 MHz) | 0x02 |
| `wsa_core_clk` | 0x5d1 | 0x309 | 0x124f800 | 0x03 |
| `wsa2_core_clk` | 0x5d3 | 0x310 | 0x124f800 | 0x0c |
| `rx_core_clk` | 0x5d0 | 0x30e | **0x1588800 (22.5792 MHz)** | 0x05 |
| `rx_core_tx_clk` | 0x5d4 | 0x312 | 0x124f800 | 0x0d |
| **`tx_core_clk`** | **0x5cf** | **0x30c** | **0x124f800 (19.2 MHz)** | **0x07** |
| `wsa_core_tx_clk` | 0x5d5 | 0x314 | 0x124f800 | 0x0e |
| `wsa2_core_tx_clk` | 0x5d6 | 0x316 | 0x124f800 | 0x0f |
| `rx_mclk2_2x_clk` | 0x5da | 0x318 | 0x124f800 | 0x10 |

→ **`tx-core-clock-id = 0x30c`，频率 19.2 MHz**。三条独立证据吻合：
(a) 本表；(b) phk110 `hakios.mic.c:244-245` `CLOCK_TX_CORE 0x30c` / `CLOCK_TX_NPL 0x30d` @19.2 MHz；
(c) Pong `ShengAudioReach.h` `AR_CLK_TX_CORE_MCLK 0x30c`（注释原文：「PRM clock ids, not the device tree indices (57 was refused)」）
+ `PongWcd938.h:59-120` 第 5 步 `prmClock(AR_CLK_TX_CORE_MCLK, 19200000)`。

> 注意 `rx_core_clk` 是 22.5792 MHz 而不是 19.2 MHz——如果以后做 44.1 kHz 家族采样率，rx 侧要单独算，不要套 19.2 MHz。

### 3.5 codec 侧的 SoundWire slave 节点

| 节点 | `reg` | 挂在哪 | 行 |
|---|---|---|---|
| `wcd938x-tx-slave` | `<0x0d 0x1170223>` | `va_swr_master`（swrm-io-base 0x33b0000） | :23369-23373 |
| `wcd938x-rx-slave` | `<0x0d 0x1170224>` | `rx_swr_master`（swrm-io-base 0x3210000） | :23467-23471 |

→ 枚举期望值：TX `0x000d01170223`（Pong 与 phk110 都只接受这一个），RX `0x000d01170224`。

## 4. 与 `dts/mondrian.dts` 的对应（本文件授权的 DT 值）

`pong-audio` 节点当前 9 个 0 占位（`dts/mondrian.dts:54-81`）。本文件能定死的：

| 属性 | 应填 | 依据 |
|---|---|---|
| `codec-reset-gpio` | **43** | §3.3 |
| `tx-core-clock-id` | **0x30c** | §3.4 |
| `codec-supply-rail` | **`pm8350_s10`**（1.8 V；mic bias 另有 `pm8350c_bob`） | §3.2 |
| `mic-bias` | **2750**（mV，micbias1..4 同值） | :23592-23595 |
| `mic-adc` | **2**（ADC2，见 §5 路由） | RESEARCH.md 路由 + `hakios.mic.c` mic=3 路径 |
| `swr-device-index` | **1**（TX master 上 WCD 的枚举序号由运行时决定，此处填 master 内起始索引） | 待上机确认，见 §7 |

仍缺（**不许猜**）：
- `tx-master-base` = 0x33b0000 有 DT 依据（`swrm-io-base`），但**当前实现走的是宏寄存器路径还是 SWR 路径未定**，需在方案评审时定；
- `codec-i2c-address`：**WCD938x 在 K60 上不走 I2C**（split-codec + SoundWire），该属性对 codec 无意义 → 建议 Lead 从 DT 里删掉或改为 `0xffffffff` 表示 N/A；
- `amp-i2c-address`：见 `AMPS.md`（0x34 / 0x35）。

## 5. 路由（来自 RESEARCH.md，SM8550/SM8475 同族，待 K60 上机复核）

WCD938x 录音路径：AMIC3 / micbias3 / ADC2 → codec 数据端口 1 通道 2 → TX master 端口 2 →
TX decimator 0 读 `SWR_MIC1` → codec DMA `TX_CDC_DMA_TX_3`；单声道 48 kHz。
播放路径：RX master 端口 → `RX_CDC_DMA_RX_0` → WCD938x HPH/SPK（K60 走 TDM 到外部 AW882xx，见 `AMPS.md`）。

## 6. 本机已验证 / 未验证

已验证（⑦ 的部分）：
- 所有地址、phandle、GPIO、电压值均可回溯到 `live-fdt.dts` 行号（见上表），`uefi-mondrian.dts` 侧音频节点被裁剪
  （`:18214-18259` 只剩骨架，无 `reg`/`interrupts`/`swrm-io-base`）→ **寄存器地址只能取 Android live FDT**。
- codec 型号与 Pong/phk110 同型，三平台 SoundWire 枚举 ID 一致。
- `tx-core-clock-id` 三源交叉吻合。

未验证（⑦ 缺口，明确写出来）：
- **没有任何一次对 WCD938x 的实机寄存器读取**。原因见 §7。
- 供电 rail 当前是否已使能、电压是否 1.8 V，未实测。
- `qcom,swr-tx-port-params` / `tx_swr_ch_map` 的具体数值尚未解析成 K60 可用的端口映射表（下一步工作）。

## 7. 阻塞点（需要 Lead）

1. **LPASS 宏/SoundWire 的访问前置是 PRM 时钟投票，而 PRM 走 ADSP/GPR。**
   - Pong 的序列（`PongWcd938.h:59-120`）：先 `prmBlock(AR_HW_MACRO)`、`prmBlock(AR_HW_DCODEC)`、
     再 `prmClock(AR_CLK_TX_CORE_MCLK, 19200000)`，**之后才允许**映射/读写 `va_macro`/`tx_macro`/`swr`。
   - phk110 的注释更直白（`hakios.mic.c` 头注释）：「an access to a block without its clock may hang the bus」。
   - PRM 需要 ADSP 已启动 + GPR 通道可用 → **这是 Lead 的 PAS1/GLINK 工作**。
   - 在 ADSP 起来之前，唯一安全可做的 codec 侧工作是：**GPIO 状态读取**（纯 AP TLMM）与
     **不碰 LPASS 的 I2C 侧功放探测**（见 `AMPS.md`）。
2. **`adsp.mbn` 固件仍缺**（本机只有 `adsp.b00-b16` 分段，`/mnt/e/k60-work/firmware/adsp/`）→ PAS1 无法完成认证启动。
3. **本机没有 K60 vendor audio-kernel 源码**（`wcd938x`/`aw882xx` 驱动都不在盘上），所以 WCD938x 的寄存器级
   初始化序列只能取 Pong 的「用法级摘要」（`PongWcd938.h`，121 行）与 phk110 的 `hakios.mic.c`，
   **不是**完整的 vendor 序列。真要做全，需要 Lead 提供 K60 vendor 树的 `techpack/audio/asoc/codecs/wcd938x/`。

## 8. 下一步（按优先级）

1. 由 Lead 解锁 ADSP/PAS1 → 才有 PRM 投票 → 才能做 §7.1 的只读寄存器验证。
2. 在此之前，我这边交付 `AMPS.md` 的**纯 AP 路径**：GENI I2C 起来读功放 chip ID（不需要 ADSP）。
3. 解析 `qcom,swr-tx-port-params` 与 `tx_swr_ch_map`，把端口映射写成表（纯 DT 解析，不需要设备）。
