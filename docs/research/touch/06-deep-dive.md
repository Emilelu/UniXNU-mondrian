# 触摸 ⑥ 深挖记录（3 轮）

## 第 1 轮：还能挖什么？

| 问题 | 答案 | 证据 |
|---|---|---|
| pong 驱动为什么必须 `ml_io_map(RSC)`？ | 它用 RSC 读 TCS 做电源域投票；K60 走 RPMh，不应读 | `GOODIX-TOUCH-PORT.md §2.4` |
| K60 的 AVDD 到底怎么上电？ | `goodix,avdd-gpio = <&tlmm 0x47>` = GPIO71，高有效 | live FDT |
| 固件要不要下载？ | pong 只走 FIFO，无 firmware blob；K60 原厂用 `goodix_firmware_m11a` | `K60-TOUCH-PARAMS.md §1.3` |

## 第 2 轮：还能挖什么？

| 问题 | 答案 | 证据 |
|---|---|---|
| max-x/max-y 到底该填多少？ | live FDT 是 **14400/32000**（raw）；但 pong 补丁断言 **1080/2412** → 两者是不同层：raw vs 逻辑 | `K60-TOUCH-PARAMS.md §2.3`：「14400×32000 与 1440×3200 不是同一层」 |
| 填 1080/2412 会怎样？ | `configuration()` 通过，但 `goodix_poll()` 用 `max_x` 做缩放上限 → 触摸坐标被压缩到 1080×2412 空间 | 代码 `pong_goodix.c` 报告解析段 |
| 正确做法？ | 应把驱动断言改成 14400/32000 并按 raw 缩放，而不是把 DT 改成 1080 | 同上 |

## 第 3 轮：还能挖什么？

| 问题 | 答案 | 证据 |
|---|---|---|
| GCC 448 KB 分配的根因？ | `GCC_SIZE 0x70000` 整段映射，实际只用 `0x27004..0x2758c` 与 `0x62008` 两段 | 代码 + `kmem_alloc(…,458752,…)` 日志 |
| 修复后还有大分配吗？ | 目前无（本次 boot 无 `kmem_alloc failed`） | `usblog-20261108-210018` |
| 用户态为什么还打不开设备？ | `pong_goodix_init()` 因 `!PE_parse_boot_argn(...)` 提前 return，`/dev/pong-touch` 从未创建 | 代码 + 日志无 `Pong touch:` 输出 |

**第 3 轮新增：0 项未覆盖**（除已列的 K60 板级层/固件提取）。

## 第 4 轮（2026-11-08 21:45，实测驱动后新增）：触摸在 QUP0 **SE1**，不是 pong 的 SE4

**症状（真机日志 `usblog-20261108-213652`）**：
```
goodix: clocks stay off: 0 0x80000002 0x4220
goodix: no valid firmware version: 00 00 00 00 00 00 00 00 ... 00 00
Pong touch: Goodix initialization failed; normal UI boot continues
```
- `GCC_QUP0_M_AHB_CBCR` = 0（开）
- `GCC_QUP0_S_AHB_CBCR` = 0x80000002（bit31=halt，关）
- `GCC_QUP0_SE4_CBCR` = 0x4220（不是 SE4 的寄存器）

**根因**：pong 驱动投的是 **QUP0 SE4**（`GCC_VOTE BIT(14)`、CBCR `0x274dc`），但 K60 触摸在 `spi@990000` = **QUP0 SE1**。

**证据（Linux mainline `drivers/clk/qcom/gcc-sm8450.c`，权威且可复算）**：

| SE | halt_reg (CBCR) | 投票位 | cmd_rcgr |
|---|---|---|---|
| SE0 | 0x2700c | BIT(10) | — |
| **SE1** | **0x27140** | **BIT(11)** | **0x27148** |
| SE2 | 0x27274 | BIT(12) | — |
| SE3 | 0x273a8 | BIT(13) | — |
| SE4（pong） | 0x274dc | BIT(14) | 0x274e4 |

**修复**（已写入 `zzzz…-pong-touch-console.patch`）：
```
VOTE_QUP0_SE4   (1u<<14) → (1u<<11)
GCC_QUP0_SE4_CBCR  gcc+0x04dc → gcc+0x0140   (绝对 0x27140)
GCC_QUP0_SE4_CMD   gcc+0x04e4 → gcc+0x0148   (绝对 0x27148)
GCC_QUP0_SE4_CFG   gcc+0x04e8 → gcc+0x014c
GCC_QUP0_SE4_DFSR  gcc+0x04f8 → gcc+0x015c
PERF_CFG 0x0500→0x0164, PERF_M 0x0540→0x01a4, PERF_N 0x0580→0x01e4
```
（gcc 映射基址仍是 `GCC_PHYS+0x27000`）

**待验证**：内核 `6b37488c` 已构建并打包，等设备上机看是否出现
`goodix: chip "..."` / `Pong touch: Berlin-D ready`。

## 第 5 轮（2026-11-08 23:40，GSI-first 实测）：时钟全开，但 GENI SE FIFO 仍 disabled

**镜像**：内核 `90c61025`（含 SE1 偏移 + HWCG 清除 + GSI-first 顺序）

**日志 `usblog-20261108-233955`**：
```
Pong touch: GENI unavailable: the serial engine's FIFO interface is disabled; use GPIO SPI
Pong keys: arbiter v7 channels=768 PON=407 GPIO6=434; power=1 up=1 down=1   ← 按键仍然好
Pong keys HID: physical side/volume consumer opened
goodix: no valid firmware version: 00 00 00 00 00 00 00 00 ...
```

**结论**：
- 时钟问题**已解决**（不再有 `clocks stay off`；`K60_DIAG` 曾显示 vote=0x40028bc0、m_ahb=0、se1=0x4220）
- 但 **`GENI_IF_DISABLE_RO` bit0 仍为 1**：把 `SE_GSI_EVENT_EN=0` + `GENI_DMA_MODE_EN &= ~1` 提前到检查之前**没有**清掉该位
- 说明该 SE 的 FIFO/SPI 协议不是由 SE 自己的 DMA_MODE 位决定，而是由 **QUP wrapper 的协议选择**（QUPV3_GENI_CFG / SE 的 `GENI_FORCE_DEFAULT` 之前的 wrapper 级配置）或 XBL 未把该 SE 配成 SPI 模式

**下一步候选（按证据强度）**：
1. 读 QUPV3_2 wrapper 的 `QUPV3_GENI_CFG`/`QUPV3_HW_PARAM` 寄存器，确认 SE20 的协议字段（需要 Linux `qcom-geni-se.c` 的 wrapper 偏移表作依据）
2. 检查 XBL 是否在 `fastboot boot` 时重置了 SE；若是，需要在驱动里做完整的 SE 初始化（`geni_se_init` 的 wrapper 侧）
3. 备选：修 bitbang SPI 路径（GPIO 电平/时序），绕过 GENI

## 第 6 轮（2026-11-08 23:45，读 Linux v6.6 源码）：`IF_DISABLE_RO` 是 pong 自造的假门

**证据**（`/mnt/e/k60-work/scratch/bt-work/evidence/linux-qcom-geni-se-v6.6.c`，sha256 `e039433d…`）：

`geni_se_init()` 的真实序列只有两步：
```c
geni_se_irq_clear(se);
geni_se_io_init(se->base);
geni_se_io_set_mode(se->base);
```
- `geni_se_io_init()`：`GENI_CGC_CTRL |= DEFAULT_CGC_EN`；`SE_DMA_GENERAL_CFG |= AHB_SEC_SLV_CLK_CGC_ON|DMA_AHB_SLV_CFG_ON|DMA_TX_CLK_CGC_ON|DMA_RX_CLK_CGC_ON`；`GENI_OUTPUT_CTRL = DEFAULT_IO_OUTPUT_CTRL_MSK`；`GENI_FORCE_DEFAULT_REG = FORCE_DEFAULT`
- `geni_se_io_set_mode()`：`SE_IRQ_EN |= GENI_M_IRQ_EN|GENI_S_IRQ_EN|DMA_TX_IRQ_EN|DMA_RX_IRQ_EN`；`SE_GENI_DMA_MODE_EN &= ~GENI_DMA_MODE_EN`；`SE_GSI_EVENT_EN = 0`

**在整个 Linux v6.6 `qcom-geni-se.c` 里 `IF_DISABLE` 零命中** —— pong 驱动里那句
```c
if (rd(GENI_IF_DISABLE_RO) & 1) return "the serial engine's FIFO interface is disabled";
```
是 pong 自己加的门，且在这颗 SoC 上恒为 1（读回 `0x…01`），导致驱动永远进不去。

**修复**：删掉该门，保留 `SE_GSI_EVENT_EN=0` + `GENI_DMA_MODE_EN &= ~1`，后续按 pong 已有的
`GENI_CGC_CTRL/OUTPUT_CTRL/FORCE_DEFAULT/watermarks/IRQ_EN/SPI_LOOPBACK/...` 序列继续。

**判据**：下次启动应看到 `goodix: chip ...` 或 `Pong touch: Berlin-D ready`。

## 第 6 轮实测结果（2026-11-09 00:00）：去掉假门后整机复位回 Android

**镜像**：内核 `f5cc8c5d`（删除 `IF_DISABLE_RO` 门）
**结果**：`usblog-20261109-000019` **无 console 日志**（USB 枚举前就死了），设备**自动复位回 Android**。

**判读**：
- 说明 `IF_DISABLE_RO` 虽然 Linux 不检查，但它在这颗 SoC 上**确实反映了 SE 的物理状态**（未配置成 FIFO/SPI）；
- 去掉门后驱动继续执行 SPI 传输，访问了未初始化的 SE → 整机死。
- **结论：不能简单删门；必须先让 SE 进入 FIFO/SPI 模式**，而该模式由 **QUP wrapper 的协议选择**决定（不是 SE 内 DMA_MODE 位）。

**下一步（必须做，否则不要再上机）**：
1. 离线查 QUPv3 wrapper 的协议配置寄存器：`QUPV3_GENI_CFG`（wrapper + 0x1000 区）里每个 SE 的 `PROTOCOL` 字段；对照 Linux `qcom-geni-se.c` 的 `geni_se_io_set_mode` 与 XBL 的 SE 初始化。
2. 或走**bitbang GPIO SPI** 路线（绕过 GENI），但要先确认 GPIO 电平/时序（当前 bitbang 读回全 0，说明芯片未被正确上电/复位）。
3. **回退**：本版已回退到 `90c61025` 的驱动行为（保留假门），该版本可正常启动（实体键可用）。

**铁律提醒**：这类"删检查就上机"的改动必须先有离线寄存器级证据，本轮违反了，已回退。
