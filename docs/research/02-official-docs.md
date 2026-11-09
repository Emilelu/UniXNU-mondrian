# 触摸 ② 官方驱动文档与配套文件

> 状态：◐ 部分完成。证据等级：文档。来源：`docs/plans/GOODIX-TOUCH-PORT.md §1`（2026-11-07 调研）。

## 已收集

| # | 文档/页面 | 内容 | 本地副本 | 抓取时间 |
|---|---|---|---|---|
| 1 | 小米官方 kernel 开源页（marble / fuxi） | Goodix 触摸驱动源码位置、板级 DTS | `docs/plans/DOCS-DRIVERS-ALL.md`、`DOCS-DEVICES-A-M.md`、`DOCS-DEVICES-N-Z.md` | 2026-11-08 01:04–01:19 |
| 2 | OFFICIAL-DRIVER-MAP 第 4 项（输入） | 触摸在 16 项覆盖表中的位置与要求 | `docs/plans/OFFICIAL-DRIVER-MAP.md` | 2026-11-07 |
| 3 | K60 live FDT（**事实上的官方硬件描述**） | `soc/spi@990000/xiaomi_touch@0` 全部属性 | `E:/k60-work/reports/live-6033dbec-fdt.dtb`（sha256 `95c02052…`） | 2026-11-02 从设备导出 |

## K60 原厂触摸参数（摘自 `K60-TOUCH-PARAMS.md`，逐项有来源）

| 属性 | 值 | 说明 |
|---|---|---|
| `compatible` | `xiaomi,m11a-spi` | 厂商触摸节点 |
| `spi-max-frequency` | `0x00e4e1c0` = **15 MHz** | 上电先用 4 MHz |
| `interrupts` | `<0x15 0x2008>` = **GPIO 21**，falling edge | INT |
| `goodix,reset-gpio` | `<&tlmm 0x14 0x0>` = **GPIO 20** | RESET |
| `goodix,avdd-gpio` | `<&tlmm 0x47 0x0>` = **GPIO 71** | 模拟电源（pong 原 schema 没有） |
| `vdd-supply` | `<&pm8350c_l2>` | LDO2 |
| `goodix,panel-max-x/y` | **14400 / 32000** | raw 坐标，不是 1440/3200 |
| `goodix,irq-flags` | `<0x2>` | falling |
| `firmware-name` | `goodix_firmware_m11a` | 固件名 |
| `config-name` | `goodix_cfg_group_m11a` | 配置组 |
| pinctrl | `pmx_ts_active` = gpio21+gpio20 | 上下电时序 |

## 缺口

- ❌ 没有 Goodix Berlin-D 的公开 datasheet（厂商 NDA）；只能以 Linux `drivers/input/touchscreen/goodix.c` 与 pong/renoir 实现作为协议依据。
- ◐ `goodix_firmware_m11a` / `goodix_cfg_group_m11a` 的实际二进制未提取（在 K60 Android 的 `/vendor/firmware` 或 `persist`）。
