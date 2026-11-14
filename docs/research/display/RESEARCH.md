# display/RESEARCH.md —— 显示 / 背光（K60 mondrian / SM8475）

> **结论层。** 证据行（仓库 + `文件:行` + 可信度）在 [REFERENCE-INDEX.md 第 7 节](../REFERENCE-INDEX.md)；
> 本文只写两件事：**可以直接拿去做东西的值**，和**绝对不能抄的东西**。
> 所有 `fdt_dump.txt:NNNN` 都指 `E:/k60-work/scratch/refmine/fdt_dump.txt`，即 `E:/k60-work/reports/live-6033dbec-fdt.dtb`（设备 6033dbec，2026-11-02 导出，919,210 B）的解析结果。
> 八步进度与门禁以 `docs/research/EIGHT-STEPS.toml` 为准，**本文不声明进度**。

## 1. 面板身份（已定，不要再猜）

| 项 | 值 | 出处 |
|---|---|---|
| 实际启用的面板 | `qcom,mdss_dsi_m11a_42_02_0a_dsc_cmd`（phandle `0x6a3`） | bootargs `fdt_dump.txt:13` |
| 面板名 | `xiaomi 42 02 0a cmd mode dsc dsi panel` | `:27811` |
| MI panel-id | `<0x4d313141 0x420200>` = ASCII `M11AB` + `0x02` | `:27771` |
| 显示模式 | `dsi_cmd_mode`（command mode，**不是 video mode**） | `:27810` |
| 分辨率 | 1440 x 3200（未压缩；DSC slice 720 x 32、bpc 10） | `:27813` 起的 timing 节点 |
| DSI | 单 DSI：`dsi-ctrl-num=0` / `dsi-phy-num=0` | `:27802-27803` |

**会选错面板的陷阱**：`dsi-display-primary` 的 `qcom,dsi-default-panel=<0x697>`（`:28881`）指向
`qcom,mdss_dsi_visionox_r66451_fhd_plus_video`（`:22521`，1440x2340），**那不是本机在用的面板**。
判据只认 bootargs 的 `msm_drm.dsi_display0`。

## 2. 画布契约（WindowServer 会 assert，不是可选项）

`references/yibiya-upstream/patches/xnu/0210-k60-display-native-canvas.patch:12-16` 原文注释：面板是 1440 x 3200、DSC video mode、60 Hz；CoreAnimation 的画布取自显示发布的 mode，
画布若不是面板自身像素网格（1125x2436、1170x2532 这类 iPhone 形状），WindowServer 的 BoundingPathBitmap 会断言。
补丁里是 `K60_PANEL_WIDTH 1440` / `K60_PANEL_HEIGHT 3200`（`:22-23`），tunable `k60_panel` 默认 1，命中时打印
`K60 DISPLAY: fbwidth/fbheight/fbscale refused, the canvas is the panel`。

**不能套用**：`references/UniXNU-upstream/docs/devices/zizhan.md:104` 的 SimpleFbDxe 是 framebuffer `0xb8000000` + **2160x1916**（同 SoC 异板），分辨率不同。

## 3. 面板关键属性（live FDT）

| 属性 | 值 | 行 |
|---|---|---|
| `qcom,platform-reset-gpio` | `<&tlmm 0 0>` = **GPIO 0** | `:27738` |
| `mi,esd-err-irq-gpio` | `<&tlmm 0x74 0x2008>` = **GPIO 116**，下降沿 | `:27772` |
| TE | `te-using-te-pin` + `te-pin-select=1` + `wr-mem-start=0x2c` / `continue=0x3c`；TE 脚 `qcom,platform-te-gpio=<&tlmm 0x56 0>` = **GPIO 86** | `:27783-27788`、`:28884` |
| 复位序列 | `qcom,mdss-dsi-reset-sequence = <1 11 0 1 1 11>` | `:27791` |
| 背光控制类型 | `bl_ctrl_dcs`（**走 DCS 命令，没有独立背光 IC**） | `:27742` |
| 亮度上限 | `bl-max 0xfff` / `bl-min 0x1` / `mi,hbm-bl-max-level 0x7ff` / `normal-max-brightness-clone 0x1fff` / `max-brightness-clone 0x3fff` | `:27739-27770` |
| DBV | `bl-inverted-dbv`（反相）；`qcom,bl-update-flag=delay_until_first_frame` | `:27780`、`:27779` |
| 物理尺寸 | `pan-physical-height-dimension=0x609`、`width=0x2b7`（0.1 mm → 约 154.5 x 69.5 mm） | `:27789-27790` |
| bpp | `0x18` = 24 | `:27807` |

## 4. 三档 timing（60 / 90 / 120）

| timing | 行 | `panel-framerate` | 画布 | `display-topology` | `phy-timings`(14 B) | `mdp-transfer-time-us` |
|---|---|---|---|---|---|---|
| `timing@0` | `:27813` | 0x3c = **60** | 1440 x 3200 | <2 2 1> | `00270a0a1b250a0b0b0a0204200f` | 7300 |
| `timing@1` | `:27910` | 0x5a = **90** | 1440 x 3200 | <2 2 1> | 同上 | 7300 |
| `timing@2` | `:28007` | 0x78 = **120** | 1440 x 3200 | <2 2 1> | 同上 | 7300 |

三档共用（`timing@0` 的 `:27890-27907`）：`v-pulse-width=0xe`、`v-front-porch=0x10`、`v-back-porch=0x6`、
`h-pulse-width=0xc`、`h-back-porch=0x8`、`h-front-porch=0x8`、`h-sync-skew=0`、`panel-clockrate=0x47868c00`（**1.2 GHz**）、`panel-jitter=<5 1>`。

DSC（`:27871-27879`）：`bit-per-pixel=0x8`、`bit-per-component=0xa`、`slice-per-pkt=0x2`、`slice-width=0x2d0`、`slice-height=0x20`、`dsc-version=0x12`、`compression-mode=dsc`。

命令包：on-command **1534 B**（`:27889`）；off-command 18 B（`:27888`）；**timing-switch-command 98 B 且三档各不相同**（`:27885` / `:27982` / `:28079`）。
→ 做帧率切换必须用 m11a 自己的 98 B 命令，**不能用 sharp 节点的 68 B**（见第 7 节第 1 条）。

## 5. 面板供电：5 条轨，其中 3 条是 RPMh LDO

`qcom,panel-supply-entries = <0x6a2>`（`:27743`）→ `/soc/dsi_panel_pwr_supply_M11a`（`:28938`）；再叠加 `dsi-display-primary` 的 4 个 regulator（`:28874-28877`）与一个 GPIO 开关。

| 轨 | 电压 | 提供者 | 行 |
|---|---|---|---|
| `vddio` | 1.8 V | `pm8350c_l12` = rpmh-regulator-**ldoc12**（phandle 0x30a，`init-mode=4`） | supply-entry@0 `:28942-28951` |
| `vddd` | 1.07 V | `display_panel_vddd`，**GPIO 66** 高有效，`regulator-boot-on` | supply-entry@1 `:28952-28961` |
| `vci` | 3.0 V | `pm8350c_l13` = rpmh-regulator-**ldoc13**（phandle 0x30b，`init-mode=4`） | supply-entry@2 `:28962-28972` |
| `extvdd` | 1.2 V | `pm8350b_l1` = rpmh-regulator-**ldod1**（phandle 0x30e） | `:28875` |
| `avdd` | 5.5 V | `display_gpio_regulator@1`，**GPIO 186**，`ramp-delay=233 µs`，`proxy-consumer-enable` | `:28912-28925` |

时序：`vddio` post-on 20 ms / post-off 10 ms、enable-load 0x493e0；`vci` pre-on 10 ms / post-on 15 ms（`:28942-28972`）。
**阻塞点**：3 条 RPMh LDO（ldoc12 / ldoc13 / ldod1）在 RSC 可访问之前无法由 AP 侧投票，只能沿用 bootloader 已开状态（REFERENCE-INDEX 第 3 节与 14.1）。

## 6. DSI / PHY / MDP 基址

| 块 | 基址与长度 | 关键属性 | 行 |
|---|---|---|---|
| DSI ctrl0 | **`0xae94000+0x400`**、`0xaf0f000+0x4`、`0xae36000+0x300` | `qcom,dsi-ctrl-hw-v2.6`、`vdda-1p2-supply=0x233`、`interrupts=<4 0>` | `:28107-28120` |
| DSI phy0 | **`0xae94400+0xa00`**、`0xae94900+0x400`、`0xae94200+0xa0` | `qcom,dsi-phy-v4.3.2`、`pll-label=dsi_pll_5nm`、`vdda-0p9-supply=0x232`、`platform-lane-config=<0xa0a 0xa0a 0xa0a 0xa0a 0x8a8a>` | `:28161-28176` |
| MDP | `0xae00000+0x84000`、`0xaeb0000+0x2008`、`0xaeac000+0x800` | `/soc/qcom,mdss_mdp@ae00000` | `:21793`、`:21958` |

对照：Pong 的背光驱动用 `board.base == 0xae94000 && span == 0x400` 判控制器（`references/pong-power/PongBacklight.cpp:336`），**与 K60 的 DSI ctrl0 同基址**；
但 Pong 是 NT37705、K60 是 m11a，DCS 包常量（`0x80370002` / `0xa0060052` / `0xc0390003`，`:135/:141/:321`）**不能直接搬**——只能借结构（淡入淡出 `(latest & 0xffff)*1e6 ns`，`:238`）。

## 7. 绝不可抄（已经踩过的）

1. **yibiya 的 120Hz 文档数值不能搬**：`references/yibiya-upstream/docs/plans/K60-120HZ-PLAN.md` 的 timing 表读自 `qcom,mdss_dsi_sharp_qhd_cmd`（live FDT `:22033`）——720x3120 DSC 压缩、双 DSI、2 档、68 B timing-switch；本机是 1440x3200 未压缩、单 DSI、3 档、98 B。逐值对照见 REFERENCE-INDEX 14.7。
2. **Pong 的面板库没有一个匹配 K60**：`uefi-mondrian/Include/RAW.inc:1-5` 原文说明约 72 个 `Panel_*.xml` 全是 pong 的；`Device-Binaries` 里 2,117 个 `Panel_*.xml` 也无一匹配 m11a（REFERENCE-INDEX 14.6 / 15）。
3. **zizhan 的 framebuffer 分辨率不能套**（见第 2 节）。

## 8. 缺口与下一步

| 缺口 | 状态 |
|---|---|
| K60 厂商 panel XML（`dispdcbx` 分区或 Android 侧 `/vendor/etc/display`） | **2026-11-14 Lead 指派给 display/GPU 线（yibiya）**，本线不再跟踪。命名形状可参考 liuqin 的 `Panel_M81_42_02_0b_dualdsi_dsc_lcd_video.xml`（`references/UniXNU-liuqin/docs/liuqin-hardware.md:44`） |
| `timing@1`（90 Hz）MIUI 侧是否使用 | 未知；做 120Hz 时要决定是否同时暴露 90 |
| 面板供电真上电验证 | 卡在 RSC（3 条 RPMh LDO）；在此之前无法自证 |

## 9. 交叉引用

- 证据行：[`../REFERENCE-INDEX.md`](../REFERENCE-INDEX.md) 第 7 节（7.2 节点 / 7.3 timing / 7.4 供电 / 7.5 基址 / 7.6 背光）、14.6、14.7
- 本板 `Display Reserved 0xB8000000+0x2B00000` 与 `video_region 0x85700000+0x700000`：[`memory/RESEARCH.md`](../memory/RESEARCH.md)
- 门禁数据源：`docs/research/SOURCES.toml` 的 `[subsystem.display]`、`[subsystem.gpu]`
