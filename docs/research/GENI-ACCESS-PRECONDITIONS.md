# GENI 访问前置条件缺失 —— 跨驱动统一根因（2026-11-09 17:10）

> 本文是**触摸与音频两个挂死案例的统一分析**。P-59 的详细展开。

## 两个独立复现

### 案例 1：触摸 SPI
| 项 | 值 |
|---|---|
| 驱动 | `pong_goodix.c`（983 行，patch `zzzz...pong-touch-console.patch`）|
| boot-arg | `k60_touch_se=1` |
| 访问目标 | QUP0 **SPI SE4** `0x990000` |
| 结果 | **0 日志挂死**，自动复位回 fastboot |
| 触发点 | `bring_up()` → `clocks_on()` 通过 → `geni_spi_init()` → 访问 SE |
| 证据 | 内核 `8a5595f1` / `fb147b79` / `50f71363`，日志均 0 字节 |

### 案例 2：音频 I2C
| 项 | 值 |
|---|---|
| 驱动 | `aw882xx.c`（823 行，patch `0503-k60-audio-aw882xx.patch`）|
| boot-arg | `pong_audio=1 pong_aw882xx=1`（**两道门控都要**）|
| 访问目标 | **I2C `0x880000`** |
| 结果 | **0 日志挂死**，`Console never enumerated (kernel died before USB gadget init)` |
| 触发点 | `bsd_init` → `pong_audio_bootstrap()` → `aw882xx_bootstrap()` → `aw882xx_probe()` → `aw882xx_bus_init()` → 访问 GENI I2C |
| 证据 | 内核 `6419fe95`，日志 `usblog-20261109-170350` **0 字节** |

## 共同点

| 特征 | 说明 |
|---|---|
| **都是首次访问 GENI 控制器寄存器时整机死** | 不是驱动逻辑错误，是硬件访问前置条件不满足 |
| **都是 0 字节控制台输出** | 死在 USB gadget 初始化之前，连 `K60 USBLOG: running` 都没到 |
| **都不影响「不碰 GENI」的启动** | 不传对应 boot-arg 时系统正常启动到 SpringBoard |
| **都不是单点 bug** | 两个不同驱动、不同 GENI 实例（SPI vs I2C）、不同 wrapper 可能 |

## 高度可疑的缺失前置

### 嫌疑 1：**GDSC 电源域未使能**（最强嫌疑）
- Linux `gcc-sm8450.c` 里 QUPv3 wrapper 有独立 GDSC（`gcc_qupv3_wrap0_gdscr` / `wrap1_gdscr`）
- **我们代码里完全没有 GDSC 使能**
- sheng `TouchProbe.cpp` 的 `run()` 里是否有 GDSC 使能？**待 subagent `82ac7617` 确认**
- 如果 GDSC 没开，**读 CBCR 或 SE 寄存器本身就会挂死**（不只是写）

### 嫌疑 2：NoC 路径 / SMMU 未配置
- 官方 `GeniSpi.h:211-212`：「the SE clocks are already running (the caller must know that)」
- 但「时钟在跑」不等于「NoC 路径通」——`sm8450.dtsi:1301` 声明 `MASTER/SLAVE_QUP_CORE_0`

### 嫌疑 3：TLMM 引脚功能未切到 QUP
- 触摸和音频都需要先把 GPIO 切到 QUP function
- 我们的代码里 `gpio_configure(PIN_MISO, 1, ...)` 的 `1` 就是 function 1（QUP）
- 但**是否在访问 SE 之前配置完**？触摸后来改过顺序（`K60_PINORDER`），音频不确定

### 嫌疑 4：SE 时钟真未使能
- 我们的 `clocks_on()` 检查了 CBCR 但可能判定式错（已修一轮）
- agent `7df8bc42` 分析说缺 `CORE`/`CORE_2X` 检查，已补但真机仍挂

## 官方解法（待验证）

`QcomGeniSpi` 组件 + sheng `TouchProbe.cpp:399-424` 的完整前置序列：
1. **GPLL0 投票 + 等 lock**（`TouchProbe.cpp:399-401`）
2. **QUP 5 个分支投票**（`:403`）
3. **等分支时钟离 off 且判定式含 HWCG**（`:406` 的 `running()` lambda）
4. **配 SPI 四根脚的 TLMM 功能/驱动/上拉**（`:422-424`）
5. **映射 SE + wrapper 两个窗**（`:426`）
6. 若 `info.fifo_disabled`：备好 DMA + SMMU 直通（`:438-474`）

**注意 SoC 地址不能照抄 sheng**：sheng 是 SM8550 wrap1（`0x52008`/`0x184e4`），
Pong 是 SM8475 wrap0（`0x62008`/`0x274dc`/`0x33000`）。

## 最小安全验证方案（建议下次上机做）

**目标**：只读一个 SE 寄存器，验证 SE 可访问性。

```
1. 先只做 GDSC 使能（不碰 SE）
2. 然后读一个只读寄存器：GENI_FW_REVISION_RO (se+0x068)
3. 打印结果
4. 退出（不初始化、不传输）
```

**判据**：
- 打印出 `rev=0x...` → **SE 可访问**，问题在后续初始化
- 0 日志挂死 → **连只读都挂**，问题在 GDSC/NoC/时钟

**风险**：如果 GDSC 没开，只读也会挂。所以**必须先确认 GDSC 是否需要显式使能**。

## 待办

| 项 | 负责 |
|---|---|
| 确认 sheng 是否有 GDSC 使能 | subagent `82ac7617` |
| 确认 K60 QUP0/QUP1 的 GDSC 偏移 | 同上 |
| 最小只读验证补丁 | 同上 |
| 音频是否同样适用 | 待触摸解决后复用 |

## 相关文档

- PITFALLS **P-59**（本文的摘要版）
- PITFALLS **P-58**（音频两道门控）
- `docs/research/touch/09-CLOCK-FIX-PLAN.md`（第一版方案，已被本轮推翻部分）
- `docs/research/touch/10-SE-HANG-ROUND3.md`（第 3 轮，发现读 CORE 可能挂死）
- `docs/research/touch/11-KEY-EVIDENCE-RING.md`（历史日志证明 clocks_on 曾成功执行）
