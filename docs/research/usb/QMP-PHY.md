# QMP USB3/DP Combo PHY（ssphy@88e8000）主机侧可验证部分

> 目标：K60（Redmi K60 / mondrian / SM8475）USB3 SuperSpeed PHY —— 在**不上机、不需要 ADSP 固件**的前提下，
> 把寄存器偏移、初始化表、上电时序、未决项全部钉到可核查的证据上。
> 日期：2026-11-14。分支 `feat/usb-console`。本文只读产出：未改驱动、未构建、未刷机。
> 路径约定：**仓库内**用相对路径；**仓库外**用绝对路径。WSL 侧构建树前缀 `/opt/k60/trees`。
>
> 上游/下游源码副本（本机已落地，供复核）：
> * 主线 v6.6：`/mnt/e/k60-work/scratch/usb/linux/phy-qcom-qmp-combo.c`（124459 B）、`phy-qcom-qmp.h`、
>   `phy-qcom-qmp-pcs-v5.h`、`phy-qcom-qmp-pcs-usb-v5.h`、`phy-qcom-qmp-qserdes-txrx-v6.h`
> * 下游 SM8450：`/mnt/e/k60-work/scratch/usb/linux/phy-msm-ssusb-qmp-sm8450.c`（32741 B）
> * 同 SoC 实机 DT 快照：`E:/k60-work/references/UniXNU-pong/configs/pong-usb-sm8475.json`
> * UEFI 侧 DT（固件树，**不是**随镜像走的 DT）：`E:/hackios/uefi-mondrian/Platforms/Xiaomi/mondrianPkg/FdtBlob/sm8475-xiaomi-mondrian.dtb`
> * 反编译文本：`E:/k60-work/scratch/usb/mondrian.dts`（21954 行）

---

## 0. 一句话结论

K60 的 SS PHY 在 **0x088e8000**（size 0x3000），DT 给的 13 项 `qcom,qmp-phy-reg-offset` 与下游 SM8450 驱动
`enum qmp_phy_rev_reg` **逐项 1:1 对应、无歧义**（`phy-msm-ssusb-qmp-sm8450.c:82-101`）；164 条
`qcom,qmp-phy-init-seq` 能按主线 `qmp_combo_offsets_v3` 的 block 基址完整分区（serdes 48 / txa 10 / rxa 39 /
txb 10 / rxb 39 / pcs 14 / pcs_usb 4），其中 **tx / rx / pcs / pcs_usb 与主线 sm8550 表一致，serdes 段 48 条里 24 条
不同**——那 24 条是手机 SM8475 自己的 PLL/SSC 参数，**主线平板（sheng, SM8550）的表不能套用**。
上机日志显示当前只走 HS（`connected, speed 0`，eUSB2），SS PHY 从未上电，所以 QMP 段至今是空白。

---

## 1. DT 真值（节点、电源、时钟、复位）

`E:/k60-work/scratch/usb/mondrian.dts:16899-16917`（`ssphy@88e8000`）：

| 项 | 值 | 证据 |
|---|---|---|
| compatible | `qcom,usb-ssphy-qmp-dp-combo` | mondrian.dts:16900 |
| reg | `<0x88e8000 0x3000>`，reg-names `qmp_phy_base` | :16901-16902 |
| status | **`disabled`** | :16903 |
| vdd-supply | `<0x234>` = `rpmh-regulator-ldob1` / pm8350_l1，830–920 mV，init **912 mV** | :5212-5219 |
| core-supply | `<0x233>` = `ldoc10` / pm8350c_l10，1.2 V | :5657-5664 |
| qcom,vdd-voltage-level | `<0 0xdea80 0xdea80>`（912000 µV） | :16904 |
| qcom,vdd-max-load-uA | `0xb798` = 47000 µA | :16905 |
| clocks | `<0x24 0xb0 0x24 0xb3 0x24 0xb4 0x24 0x07 0x20 0x00 0x24 0xb2 0x24 0xaf>` | :16906 |
| clock-names | aux_clk / pipe_clk / pipe_clk_mux / pipe_clk_ext_src / ref_clk_src / com_aux_clk / ref_clk | :16907 |
| resets | `<0x24 0x1b 0x24 0x1d>` = global_phy_reset / phy_reset | :16908-16909 |
| pinctrl-0 | `<0x235>`（gpio91 usb_phy） | :16910-16911 |

要点：
* `gcc` 是 `clock-controller@100000`（`#clock-cells=1`，无 `clock-output-names`），因此 clocks 只能按**序号**引用，
  名字来自 `clock-names`。驱动若硬编码时钟名，必须与这 7 个名字逐字一致。
* 只有 `USB3_AND_DP` 类型才取 `global_phy_reset`，否则取 `phy_phy_reset`
  （`phy-msm-ssusb-qmp-sm8450.c:1048-1058`）。K60 的 compatible 命中前者，所以**两个 reset 都要**。
* DT 里 `status = "disabled"`：UEFI 侧认为这块 PHY 没启用；随镜像走的 DT 里根本没有 ssphy 节点（见 §8）。

---

## 2. 13 项 reg-offset 的权威解码（无歧义）

解析代码：`phy-msm-ssusb-qmp-sm8450.c:1066-1086` —— 按 `size / 4` 计数，超过 `USB3_PHY_REG_MAX` 直接
`invalid reg offset count`（:1071-1072）。枚举 `enum qmp_phy_rev_reg` 在 :82-101，正好 13 个实项 + 哨兵
`USB3_PHY_REG_MAX`。

| # | DT 值（mondrian.dts:16914） | 枚举项（:82-101） | 语义 / 交叉验证 |
|---|---|---|---|
| 0 | 0x1c14 | USB3_PHY_PCS_STATUS | pcs 0x1c00 + 0x014 = `QPHY_V5_PCS_PCS_STATUS1`（`phy-qcom-qmp-pcs-v5.h:11`）✓ |
| 1 | 0x1f08 | USB3_PHY_AUTONOMOUS_MODE_CTRL | pcs_usb 0x1f00 + 0x008（`phy-qcom-qmp-pcs-usb-v5.h:12`）✓ |
| 2 | 0x1f14 | USB3_PHY_LFPS_RXTERM_IRQ_CLEAR | pcs_usb + 0x014（:15）✓ |
| 3 | 0x1c40 | USB3_PHY_POWER_DOWN_CONTROL | pcs + 0x040（`pcs-v5.h:12`）✓ |
| 4 | 0x1c00 | USB3_PHY_SW_RESET | pcs + 0x000（:10）✓ |
| 5 | 0x1c44 | USB3_PHY_START | pcs + 0x044（:13）✓ |
| 6 | 0xffff | USB3_PHY_PCS_MISC_TYPEC_CTRL | **哨兵**：本 PHY 无此寄存器（下游 :90 注释 "optional"） |
| 7 | 0x08 | USB3_DP_COM_POWER_DOWN_CTRL | com + 0x08（`phy-qcom-qmp.h:50`）✓ |
| 8 | 0x04 | USB3_DP_COM_SW_RESET | com + 0x04（:49）✓ |
| 9 | 0x1c | USB3_DP_COM_RESET_OVRD_CTRL | com + 0x1c（:54）✓ |
| 10 | 0x00 | USB3_DP_COM_PHY_MODE_CTRL | com + 0x00（:48）✓ |
| 11 | 0x10 | USB3_DP_COM_TYPEC_CTRL | com + 0x10（:52）✓ |
| 12 | 0x1e00 | USB3_PCS_MISC_CLAMP_ENABLE | **K60 与主线不同**：主线 pcs_misc 0x1a00 + 0x0c = 0x1a0c |

结论：前 6 项在 pcs / pcs_usb 域，后 6 项在 DP COM 域（com base = 0x0000，相对 ssphy 基址），
第 12 项 clamp 用 **DT 的 0x1e00**（K60 真值），不要套主线 0x1a0c。
`qmp_combo_offsets_v3`（`phy-qcom-qmp-combo.c:1476-1490`）给出的 block 基址是
com 0x0000 / serdes 0x1000 / txa 0x1200 / rxa 0x1400 / txb 0x1600 / rxb 0x1800 / pcs_misc 0x1a00 /
pcs 0x1c00 / pcs_usb 0x1f00（:1483 `usb3_pcs_misc = 0x1a00`）。

---

## 3. 164 条 init-seq：分区与逐条比对

工具：`docs/research/usb/qmp-phy-table.py`（可重跑，见 §9）。分区结果：

```
node base 0x088e8000 size 0x3000
reg offsets 13, init entries 164
per block: serdes 48, txa 10, rxa 39, txb 10, rxb 39, pcs 14, pcs_usb 4
RESULT: OK
```

对照对象：主线 `sm8550_usb3_serdes_tbl`（`phy-qcom-qmp-combo.c:733`）、`_tx_tbl`（:784）、
`_rx_tbl`（:798）、`_pcs_tbl`（:847）、`_pcs_usb_tbl`（:864）。

### 3.1 serdes 段（0x1000-0x11b4）：48 条里 **24 条不同**

全部集中在 PLL / SSC / LOCK_CMP / BIN_VCOCAL / DEC_START / CMN_CONFIG：

| offset | 主线符号 | 主线值 | K60 DT |
|---|---|---|---|
| 0x1000 | QSERDES_V6_COM_SSC_STEP_SIZE1_MODE1 | 0xc0 | 0x55 |
| 0x1004 | QSERDES_V6_COM_SSC_STEP_SIZE2_MODE1 | 0x01 | 0x0e |
| 0x1020 | QSERDES_V6_COM_LOCK_CMP1_MODE1 | 0x16 | 0x2e |
| 0x1024 | QSERDES_V6_COM_LOCK_CMP2_MODE1 | 0x41 | 0x82 |
| 0x1028 | QSERDES_V6_COM_DEC_START_MODE1 | 0x41 | 0x04 |
| 0x102c | QSERDES_V6_COM_DEC_START_MSB_MODE1 | 0x00 | 0x01 |
| 0x1034 | QSERDES_V6_COM_DIV_FRAC_START2_MODE1 | 0x75 | 0xd5 |
| 0x1038 | QSERDES_V6_COM_DIV_FRAC_START3_MODE1 | 0x01 | 0x05 |
| 0x1050 | QSERDES_V6_COM_BIN_VCOCAL_CMP_CODE1_MODE1 | 0x5c | 0xb7 |
| 0x1054 | QSERDES_V6_COM_BIN_VCOCAL_CMP_CODE2_MODE1 | 0x0f | 0x1e |
| 0x1058 | QSERDES_V6_COM_BIN_VCOCAL_CMP_CODE1_MODE0 | 0x5c | 0xb7 |
| 0x105c | QSERDES_V6_COM_BIN_VCOCAL_CMP_CODE2_MODE0 | 0x0f | 0x1e |
| 0x1060 | QSERDES_V6_COM_SSC_STEP_SIZE1_MODE0 | 0xc0 | 0x55 |
| 0x1064 | QSERDES_V6_COM_SSC_STEP_SIZE2_MODE0 | 0x01 | 0x0e |
| 0x1080 | QSERDES_V6_COM_LOCK_CMP1_MODE0 | 0x08 | 0x12 |
| 0x1084 | QSERDES_V6_COM_LOCK_CMP2_MODE0 | 0x1a | 0x34 |
| 0x1088 | QSERDES_V6_COM_DEC_START_MODE0 | 0x41 | 0x04 |
| 0x108c | QSERDES_V6_COM_DEC_START_MSB_MODE0 | 0x00 | 0x01 |
| 0x1094 | QSERDES_V6_COM_DIV_FRAC_START2_MODE0 | 0x75 | 0xd5 |
| 0x1098 | QSERDES_V6_COM_DIV_FRAC_START3_MODE0 | 0x01 | 0x05 |
| 0x10bc | QSERDES_V6_COM_BG_TIMER | 0x0a | 0x0e |
| 0x10cc | QSERDES_V6_COM_SSC_PER1 | 0x62 | 0x31 |
| 0x10d0 | QSERDES_V6_COM_SSC_PER2 | 0x02 | 0x01 |
| 0x1174 | QSERDES_V6_COM_CMN_CONFIG_1 | 0x16 | 0x04 |

判读：SSC（扩频）+ LOCK_CMP + DEC_START + BIN_VCOCAL 是一组互相耦合的 PLL 参数，随**参考时钟**变。
主线表是 SM8550（平板 sheng）配 38.4 MHz eUSB2 参考的产物；K60 是手机 SM8475。**serdes 段必须用 DT 原值，
不得引用主线表**——这是本文件最重要的一条结论，因为它决定"抄主线驱动"会在第一步就写错 24 个寄存器。

### 3.2 tx 段（0x1200 / 0x1600）：10 条全同

唯一"差异"是 `QSERDES_V6_TX_PI_QEC_CTRL`（`phy-qcom-qmp-qserdes-txrx-v6.h:33` = 0xe4）：
主线 lane1 = 0x21、lane2 = 0x05；DT 的 txa = 0x21、txb = 0x05 —— 完全一致，只是比对脚本按 lane 展开时重复计数。
tx 表在 `qmp_combo_usb_power_on` 里分两次写：`qmp_combo_configure_lane(tx, …, 1)` / `(tx2, …, 2)`
（`phy-qcom-qmp-combo.c:2572-2573`）。

### 3.3 rx 段（0x1400 / 0x1800）：差异只在 RX_MODE_00_* 与 UCDR_SB2_GAIN2

| 寄存器 | rel | 主线 | DT rxa | DT rxb |
|---|---|---|---|---|
| QSERDES_V6_RX_UCDR_SB2_GAIN2 | 0x058 | 0x0a | 0x08 | 0x08 |
| QSERDES_V6_RX_RX_MODE_00_LOW（`qserdes-txrx-v6.h:60`=0x15c） | 0x15c | 0xbf | 0x3f | 0x3f |
| QSERDES_V6_RX_RX_MODE_00_HIGH | 0x160 | 0xbf | 0xff | 0xff |
| QSERDES_V6_RX_RX_MODE_00_HIGH2 | 0x164 | 0xbf/0xff | 0xff | 0xff |
| QSERDES_V6_RX_RX_MODE_00_HIGH4 | 0x16c | 0xed/0xfd | 0xfe | 0xfe |

要点：DT 里 **rxa 与 rxb 除这些 lane 相关项外逐字节相同**，且把主线用 `QMP_PHY_INIT_CFG_LANE` 表达的
lane1/lane2 差异**已经展开成两份相同值**。⇒ 写入时必须按 rxa（0x1400）与 rxb（0x1800）**两块分别写**，
不能只写一份；照抄主线"一份表 + lane mask"的做法在 K60 上会漏写一半。

### 3.4 pcs 段（0x1c00）：14 条全同

对应 `QPHY_V5_PCS_LOCK_DETECT_CONFIG1`（0x0c4）… `QPHY_V5_PCS_EQ_CONFIG5`（0x1ec），与主线一致。

### 3.5 pcs_usb 段（0x1f00）：主线 5 条、DT 4 条

| 寄存器 | rel | 主线 | DT |
|---|---|---|---|
| QPHY_USB_V6_PCS_USB3_POWER_STATE_CONFIG1 | 0x000 | 0x68 | **缺** |
| QPHY_USB_V6_PCS_USB3_LFPS_DET_HIGH_COUNT_VAL | 0x018 | 0xf8 | 0xf8 |
| QPHY_USB_V6_PCS_USB3_RXEQTRAINING_DFE_TIME_S2 | 0x03c | 0x07 | 0x07 |
| QPHY_USB_V6_PCS_USB3_RCVR_DTCT_DLY_U3_L | 0x040 | 0x40 | 0x40 |
| QPHY_USB_V6_PCS_USB3_RCVR_DTCT_DLY_U3_H | 0x044 | 0x00 | 0x00 |

**0x1f00 是唯一"主线有、DT 无"的寄存器**，列为未决项（§7-1）。

---

## 4. 同 SoC 实机校正：Pong 的 override-seq

`E:/k60-work/references/UniXNU-pong/configs/pong-usb-sm8475.json` 的 ssphy 节点比 mondrian 多一条：

```
qcom,qmp-phy-override-seq = <0x1580 0x0d  0x1614 0x38  0x1980 0x0d>
```

解码（block base + rel）：
* `0x1580` = rxa + 0x180 = `QSERDES_V6_RX_RX_MODE_01_HIGH4`（`phy-qcom-qmp-qserdes-txrx-v6.h:69`），DT 现值 0x09 → Pong 改 0x0d；
* `0x1980` = rxb + 0x180 同寄存器，同样 0x09 → 0x0d；
* `0x1614` = txb + 0x014 = `QSERDES_V6_TX_TX_DRV_LVL`（:11），**DT 完全没有这个 offset**，Pong 补写 0x38。

下游把 override 拼在 init-seq 之后写（`phy-msm-ssusb-qmp-sm8450.c:1142-1166`，len = size + size1）。
⇒ K60 若 SS 眼图/链路训练不稳，**第一优先实验就是这三条覆写**（先按同 SoC 实机值，不改其它）。

---

## 5. 上电时序：主线 vs 下游（两套都要看）

### 5.1 主线（`phy-qcom-qmp-combo.c`）

`qmp_combo_usb_init`（:2629）→ `qmp_combo_com_init(false)`（:2388）→ `qmp_combo_usb_power_on`（:2548）：

1. 写 serdes 表（:733）；
2. 使能 pipe_clk；
3. tx 表按 lane1/lane2 写 txa/txb（:2572-2573）；
4. rx 表按 lane1/lane2 写 rxa/rxb（:2575-2576）；
5. 写 pcs 表（:847）→ 写 pcs_usb 表（:864）；
6. 可选 10–20 µs 延时；
7. `qphy_clrbits(pcs + SW_RESET, BIT(0))`（:35 SW_RESET BIT(0)）；
8. `qphy_setbits(pcs + START_CTRL, SERDES_START | PCS_START)`（:39/:40 = BIT(0)/BIT(1)）；
9. `readl_poll_timeout(pcs + PCS_STATUS, !(val & PHYSTATUS), 200, PHY_INIT_COMPLETE_TIMEOUT)`
   （:42 PHYSTATUS BIT(6)、:73 超时 10000 µs），失败打 `phy initialization timed-out`（:2596）。

com_init 的寄存器级顺序（:2388-2455）：`POWER_DOWN_CTRL |= SW_PWRDN`（:37）→
`RESET_OVRD_CTRL |= SW_DPPHY_RESET_MUX|SW_DPPHY_RESET|SW_USB3PHY_RESET_MUX|SW_USB3PHY_RESET`（:50/:52）
→ `TYPEC_CTRL = SW_PORTSELECT_MUX[|SW_PORTSELECT_VAL if reverse]`（:70/:71）
→ `PHY_MODE_CTRL = USB3_MODE|DP_MODE`（:55/:56）→ 清 RESET_OVRD → 清 SWI_CTRL 0x03 →
清 SW_RESET → `pcs POWER_DOWN_CONTROL |= SW_PWRDN`。
lane 写入统一走 `qmp_combo_configure_lane`（:1870），单表全 lane 时 mask 0xff（:1893）。

### 5.2 下游 SM8450（`phy-msm-ssusb-qmp-sm8450.c`）

`msm_ssphy_qmp_init`（:551-628）顺序：LDO 使能（:568）→ 时钟（:575）→
`dp_combo_reset`（`USB3_AND_DP` 分支，:577-579）→ `usb_qmp_update_portselect_phymode`（:581）→
`usb_qmp_powerup_phy`（:584）→ `configure_phy_regs`（:587）→
**`SW_RESET = 0x00`（:594）→ `START = 0x03`（:596）** → `mb()` →
轮询 `PCS_STATUS & PHYSTATUS(BIT(6))` 清零，最多 `INIT_MAX_TIME_USEC` = 1000 次（:27、:604-608），
超时打 `QMP PHY initialization timeout` + `USB3_PHY_PCS_STATUS:%x`（:611-614）。

两套的差别（实现时要选一套，不能混）：
* 主线用 `readl_poll_timeout(200 µs step, 10000 µs)`；下游用 1000 次循环、每次 `udelay(1)` 级别。
* 主线写 `START = SERDES_START|PCS_START = 0x03`，下游也是 `0x03` —— 一致。
* 下游多一步 `usb_qmp_powerup_phy` 显式写 `DP_COM_POWER_DOWN_CTRL = 0x01`（:524-525），并注明
  "**不要在这里写 DP_COM_SW_RESET = 0**，portselect/phymode 需要它是 1；由 init 在初始化 PHY 前写 0"
  （:527-532）。这是一条只有下游才写明的坑。
* clamp：`USB3_AND_DP` 时写 `!val` 到 `PCS_MISC_CLAMP_ENABLE`（:194-200）。

---

## 6. 上机证据：QMP 段至今未初始化

`E:/k60-work/evidence/usblog-20261114-usb-hb2/console.log`：
* :9 `DWC3 GSNPSID 0x33313130 GCTL 0x00102001 GSTS 0x7e800000 GUSB2PHYCFG 0x00102400`
* :12 `eUSB2[0x88e3000] +0x1a0 0 +0x210 0 +0x240 0 +0x254 0x0b0b0b0b`
* :257 起 QSCRATCH 全 0；:263 起心跳 `GDSC 0xf822f000 QSCRATCH HS 0x10100000 SS 0x01000000`
* :269 `connected, speed 0` —— DSTS bits[2:0]=0 = HIGHSPEED（`Dwc3.h:205-209`）

⇒ 设备只用 HS（eUSB2）枚举，SS PHY 从未上电。任何 SS 相关的判据都必须先有一次"PHY 上电 + PHYSTATUS 清零"的
上机证据，否则不能声称 SS 可用。

---

## 7. 未决项（必须显式标注，不得猜）

1. **0x1f00 POWER_STATE_CONFIG1 = 0x68 写不写**：主线有、K60 DT 无。写 = 引入一个无 DT 依据的值（违反铁则 3）；
   不写 = 与主线行为不同。当前决定：**先不写**，上机若 SS 起不来再作为单变量实验（附主线行号作依据）。
2. **clamp 用 0x1e00 还是 0x1a0c**：以 DT 为准（0x1e00）。主线值在本硅上无证据。
3. **serdes 表不可套主线**（§3.1）：任何"从主线搬表"的实现都算违反铁则 3。
4. **Pong override-seq 是否对 K60 必需**：同 SoC 但不同板（Pong 是平板），只能作为实验项，不能作为默认。
5. **PHY 参考时钟频率**：官方文档写 eUSB2 参考 38.4 MHz（`E:/k60-work/references/yibiya-unixnu-upstream/docs/drivers/qcom-dwc3.md`），
   但 K60 DT 的 `ref_clk_src` 只给了 phandle+序号，没有频率；serdes 表的 PLL 参数（§3.1）是间接证据。
   若要写死频率，需要 clock 驱动的 rate 表作依据 —— 本机没有该表。

---

## 8. 与"随镜像走的 DT"的关系（重要前提）

实际随镜像走的 DT 是 **4024 B** 的 `hardware.dtb`（sha256 `2d044eaa08b7e58c0510a33da795c960085e13d6943cd4c25e0e050e0bfa33cd`），
由 `dtc -I dts -O dtb … /opt/k60/trees/usb-device/dts/mondrian.dts` 生成（`usb-20261114g` 的 `logs/payload.log`），
反编译只有 210 行，**没有 ssphy / hsphy / dwc3 节点**。仓库 `dts/mondrian.dts`（198 行）同样没有。

⇒ 两条路：
* (a) **硬编码寄存器**（现有 0405-0409 的做法，grep `dt_prop`/`PE_parse_boot_argn` 无命中）；
* (b) **DT 驱动**：先在 `dts/mondrian.dts` 加 ssphy 节点 —— 但 `dts/` 不在本线写作用域，只能交 Lead 合并。
本文为 (a) 提供全部常量，为 (b) 提供节点内容（§1 即节点正文）。

---

## 9. 复现与自检

```bash
# 1) 反编译固件侧 DT（只读）
dtc -I dtb -O dts -o /mnt/e/k60-work/scratch/usb/mondrian.dts \
    /mnt/e/hackios/uefi-mondrian/Platforms/Xiaomi/mondrianPkg/FdtBlob/sm8475-xiaomi-mondrian.dtb

# 2) 表提取 + 五项一致性检查（RESULT: OK 才算通过）
python3 docs/research/usb/qmp-phy-table.py --dts /mnt/e/k60-work/scratch/usb/mondrian.dts --check

# 3) 生成 C 头并编译验证（enum kQmp* + 164 条 kK60QmpInit[]）
python3 docs/research/usb/qmp-phy-table.py --dts /mnt/e/k60-work/scratch/usb/mondrian.dts \
        --emit-c --out /mnt/e/k60-work/scratch/usb/kQmpPhyK60.h
printf '#include "kQmpPhyK60.h"\nint main(void){return (sizeof(kK60QmpInit)/sizeof(kK60QmpInit[0]))==164?0:1;}\n' > t.c
cc -std=c11 -Wall -Wextra -Werror -o t t.c && ./t   # rc=0
```

本轮自检结果（2026-11-14）：
* `--check` → `RESULT: OK`（13 项 reg-offset、164 条 init、block 分区全通过，唯一 note 是 clamp 0x1e00）。
* 生成头 `kQmpPhyK60.h` 186 行，sha256 `5e9b2e007a666a548eb2e06277375a49bbbe5ef49035900e47cd70f0528096c4`；
  `cc -std=c11 -Wall -Wextra -Werror` 编译 + 运行 rc=0（164 条断言成立）。
* init-seq 抽取副本 `ssphy-initseq.txt`（164 行）sha256 `e298d7bfa12bf1cf53df29bae21eff4d16d376f57b38271a533576cae11da8b2`。

---

## 10. 证据索引

| 事实 | 位置 |
|---|---|
| ssphy 节点全文 | `E:/k60-work/scratch/usb/mondrian.dts:16899-16917` |
| vdd / core 电源 | 同文件 :5212-5219、:5657-5664 |
| 13 项枚举 | `phy-msm-ssusb-qmp-sm8450.c:82-101` |
| 13 项解析 + 越界报错 | 同文件 :1066-1086（:1071-1072） |
| phy_type 判定 | 同文件 :1028-1035 |
| reset 获取 | 同文件 :1048-1058 |
| clamp | 同文件 :194-211 |
| portselect/phymode | 同文件 :439-517 |
| powerup（含 SW_RESET 注释） | 同文件 :519-538 |
| init 全序 + START/SW_RESET + 轮询 | 同文件 :551-628（:594/:596/:604-614） |
| 主线 block 基址 | `phy-qcom-qmp-combo.c:1476-1490`（:1483） |
| 主线五张表 | 同文件 :733 / :784 / :798 / :847 / :864 |
| 主线上电与超时 | 同文件 :2548-2596（:2594/:2596）、:2629、:2388 |
| 主线 typec 换向 | 同文件 :3136-3155 |
| 主线 sm8450 → sm8350 cfg | 同文件 :3551-3556 |
| DP COM 寄存器 | `phy-qcom-qmp.h:48-54` |
| PCS v5 寄存器 | `phy-qcom-qmp-pcs-v5.h:10-13` |
| PCS_USB v5 寄存器 | `phy-qcom-qmp-pcs-usb-v5.h:10,12,15,16` |
| QSERDES v6 tx/rx | `phy-qcom-qmp-qserdes-txrx-v6.h:11,33,60,69` |
| Pong override-seq | `E:/k60-work/references/UniXNU-pong/configs/pong-usb-sm8475.json` |
| 上机 PHY 真值 | `E:/k60-work/evidence/usblog-20261114-usb-hb2/console.log:9,12,257,263,269` |
| DSTS 速度编码 | `E:/k60-work/references/uefi-pong/Silicon/Samsung/SamsungPkg/Include/Device/Dwc3.h:205-209` |
