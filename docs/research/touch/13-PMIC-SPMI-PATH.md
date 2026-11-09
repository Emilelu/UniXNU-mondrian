# 触摸供电：SPMI 直写方案（绕过 RSC）

> 2026-11-09 20:17。这是触摸修复当前**唯一可行的技术路径**。

## 1. 问题

FDT 明确：触摸 VDD = `pm8350c_l2`（PM8350C 的 LDO2，1.8 V），
由 `rpmh-regulator-ldoc2`（`qcom,rpmh-vrm-regulator`）管理。

**RPMh 稳压器只能通过 RPMh（RSC）写入**，而 `0x17a00000/0x17a20000`
首读整机死（PITFALLS P-49 / HARD-RULES HR-01）。

**后果**：XNU 侧无法给触摸 VDD 上电 → 芯片不应答任何 SPI 命令。

## 2. 合法替代：PMIC 仲裁器（SPMI）

FDT 提供独立的 SPMI 控制器：

```
qcom,spmi@c42d000 {
    compatible = "qcom,spmi-pmic-arb";
    reg = <0xc42d000 0x4000      /* cnfg   */
           0xc400000 0x3000      /* core   */
           0xc500000 0x400000    /* chnls  */
           0xc440000 0x80000     /* obsrvr */
           0xc4c0000 0x10000>;   /* intr   */
    reg-names = "cnfg\0core\0chnls\0obsrvr\0intr";
    qcom,ee = <0x00>;
    qcom,channel = <0x00>;
    cell-index = <0x00>;
};
```

**它与 RSC（0x17a00000）完全独立**，访问它不违反 HR-01。

## 3. 实现步骤

### 3.1 映射窗口（4 个，建议各 4 KiB）
```c
#define SPMI_CNFG_PHYS   0x0c42d000UL   /* 0x4000 */
#define SPMI_CHNLS_PHYS  0x0c500000UL   /* 0x400000，只需前 64 KiB */
#define SPMI_OBSRVR_PHYS 0x0c440000UL   /* 0x80000，只需前 4 KiB */
#define SPMI_CORE_PHYS   0x0c400000UL   /* 0x3000 */
```
注意 io_submap 预算（P-63）：每个窗口只映射实际用到的 4 KiB。

### 3.2 SPMI 写命令（PMIC arbiter 通道）
典型的 PMIC arbiter 写序列（参考 Linux `spmi-pmic-arb.c`）：
1. 选通道：`chnls + 0x0 + 0x1000*ch` 的 `CHAN_CMD` 寄存器
2. 写 `CHAN_CMD = (opcode << 27) | (priority << 8) | ...`
3. 写 `CHAN_DATA` 逐字节
4. 轮询 `CHAN_STATUS` 的 DONE 位
5. 读 `CHAN_STATUS` 的低 8 位拿错误码

### 3.3 PM8350C LDO2 的 SPMI 地址
**需要查**（不在公开 FDT 里，因为 FDT 把它建模为 RPMh VRM）：
- SPMI slave ID（PM8350C 在 K60 上通常是 SID 4 或 5）
- LDO2 的 base address（Linux `qcom_spmi-regulator.c` 的 `pm8350c` 表）
- 使能寄存器偏移（通常在 base + 0x46）

**来源建议**：
1. Xiaomi 内核 `arch/arm64/boot/dts/vendor/qcom/pm8350c-regulator.dtsi`
2. Linux `drivers/regulator/qcom_spmi-regulator.c` 的 `pm8350c_regulators[]`
3. 或读 Android 侧 `/sys/kernel/debug/regulator/` 看 LDO2 的 SPMI 地址

## 4. 替代方案（更简单，但可能不可行）

**直接读 SPMI**：PMIC arbiter 的 `obsrvr` 窗口可以做只读监听，
也许能看到 RPMh 之前写过的 LDO2 配置。如果能读到"已开启"，说明 ABL 已经上电，
那问题就回到 SPI 本身而不是供电。

## 5. 判据

| 步骤 | 成功标志 |
|---|---|
| SPMI 通道使能 | `CHAN_STATUS` bit0（DONE）= 1 |
| 写 LDO2 | 回读电压 ≈ 1.8 V，或 `INT` 线变化 |
| 触摸响应 | `goodix: chip "..." firmware "..."` |

## 6. 风险

- **写错 SPMI 通道/地址可能影响其它 PMIC 供电域**（如 CPU/内存/UFS），有整机死风险
- 建议**先只读**（obsrvr / 回读），确认安全后再写
- 严格遵守 HR-03：一次只加一个未知 MMIO 访问
