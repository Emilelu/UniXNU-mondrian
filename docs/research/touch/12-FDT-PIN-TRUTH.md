# K60 触摸 FDT 真值（2026-11-09 19:50）

> 来源：`/mnt/e/k60-work/reports/live-6033dbec-fdt.dtb`（919,210 B，
> sha256 `95c02052b773a1b8df8ec20f6368ba80c87717206ed40682046e2ad6f29fdac8`），
> 用 `dtc -I dtb -O dts` 反编译到 `/tmp/live.dts`（34,801 行）。

## 1. SPI 引脚（`/soc/pinctrl@f000000/qupv3_se4_spi_pins/qupv3_se4_spi_active`）

```
qupv3_se4_spi_pins {
    phandle = <0x2c7>;
    qupv3_se4_spi_active {
        phandle = <0xd8>;
        mux {
            pins = "gpio16\0gpio17\0gpio18\0gpio19";
            function = "qup4";
        };
        config {
            pins = "gpio16\0gpio17\0gpio18\0gpio19";
            drive-strength = <0x06>;
            bias-disable;
        };
    };
    qupv3_se4_spi_sleep {
        mux { pins = "gpio16\0gpio17\0gpio18\0gpio19"; function = "gpio"; };
        config { pins = "gpio16\0gpio17\0gpio18\0gpio19"; drive-strength = <0x06>; bias-disable; };
    };
};
```

**结论：SPI 引脚集合是 GPIO 16,17,18,19，功能 `qup4`（= QUP0 SE4）。**
我们的 `pins[0..3] = 16,17,18,19` **正确**。
**未确认**：这 4 个引脚中哪个是 MISO / MOSI / CLK / CS。

## 2. `spi@990000` 节点

```
spi@990000 {
    compatible = "qcom,spi-geni";
    reg = <0x990000 0x4000>;
    interrupts = <0x00 0x25d 0x04>;          /* GIC SPI 605 */
    clock-names = "se-clk\0m-ahb\0s-ahb";
    clocks = <0x24 0x5e 0x24 0x86 0x24 0x87>;
    pinctrl-names = "default\0sleep";
    pinctrl-0 = <0x581 0x582>;
    pinctrl-1 = <0x583 0x584>;
    dmas = <0xc7 0x00 0x04 0x01 0x40 0x02 0xc7 0x01 0x04 0x01 0x40 0x02>;
    dma-names = "tx\0rx";
    spi-max-frequency = <0x2faf080>;         /* 50 MHz */
    qcom,wrapper-core = <0xc4>;
    qcom,rt;
    ...
};
```

**注意**：`dmas` / `dma-names = "tx","rx"` 存在 —— 官方设计走 **SE DMA**，
这与 `QcomGeniSpi` 的 `use_dma` 路径一致。

## 3. 触摸子节点 `xiaomi_touch@0`（全部真值）

```
xiaomi_touch@0 {
    status = "ok";
    compatible = "xiaomi,m11a-spi";
    reg = <0x00>;
    spi-max-frequency = <0xe4e1c0>;          /* 15 MHz */
    interrupt-parent = <0x3c>;
    interrupts = <0x15 0x2008>;              /* GPIO 21, falling */
    pinctrl-names = "pmx_ts_active\0pmx_ts_suspend";
    pinctrl-0 = <0x585>;
    pinctrl-1 = <0x2f1 0x2f0>;
    goodix,avdd-gpio = <0x3c 0x47 0x00>;     /* GPIO 71 */
    goodix,iovdd-name = "vdd";
    vdd-supply = <0x301>;                    /* pm8350c_l2 */
    goodix,irq-gpio = <0x3c 0x15 0x2008>;    /* GPIO 21 */
    goodix,reset-gpio = <0x3c 0x14 0x00>;    /* GPIO 20 */
    goodix,irq-flags = <0x02>;               /* falling */
    goodix,panel-max-x = <0x3840>;           /* 14400 */
    goodix,panel-max-y = <0x7d00>;           /* 32000 */
    goodix,panel-max-w = <0xff>;
    goodix,panel-max-p = <0x1000>;
    goodix,firmware-name = "goodix_firmware_m11a";
    goodix,config-name = "goodix_cfg_group_m11a";
    goodix,touch-expert-array = <...>;
    panel = <0x6a3 0x697>;
};
```

## 4. 与我们实现的差异表

| 项 | FDT 真值 | 我们的实现 | 状态 |
|---|---|---|---|
| SPI 引脚集合 | gpio16-19, func qup4 | pins[0..3]=16,17,18,19 | ✅ 正确 |
| INT | GPIO 21, falling | pins[4]=21 | ✅ 正确 |
| RESET | GPIO 20 | pins[5]=20 | ✅ 正确 |
| **AVDD** | **GPIO 71** | 无 | ❌ 缺失 |
| **VDD** | **pm8350c_l2 (LDO2)** | `ldoc3` + `ldoc12` | ❌ 错误 |
| panel-max-x/y | 14400 / 32000 | 1080 / 2412 | ⚠️ 不一致 |
| spi-max-frequency | 15 MHz | 4 MHz (上电) | ⚠️ 可接受 |
| DMA | dmas present | 无 | ❌ 缺失（GENI 需要）|

## 5. 下一步

1. **确定 4 个引脚的角色**：24 种排列一次上机扫描（已实现 `K60_PIN_PERMUTE_BLOCK`）
2. 若排列都读 0 → 加 **RESET 脉冲**（拉低 10 ms → 拉高 100 ms）
3. 若仍不通 → 需要 **GPIO 71 (AVDD)** 上电 + **pm8350c_l2**
