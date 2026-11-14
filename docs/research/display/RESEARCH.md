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

### 1.1 厂商 panel XML：已找到，但是同族不同修订（2026-11-14）

`/mnt/e/hackios/Device-Binaries/marble/RawFiles/Panel_M11a_42_02_0a_amoled_dsc_cmd.xml`
（4,799 B / 203 行 / sha256 `65cd6826a2abcce28db60b7d82ab34aa9fa8ecd2aa82f5fc4f21f9853b4be482`，
引入提交 `a1501e0c`，2026-10-04）。**注意它没有 `references/` 软链**（`/mnt/e/k60-work/references/` 里
没有 `Device-Binaries`），只能按上面的绝对路径读。**它也不在仓库根，而在 `marble/` 子目录下**——先前「2,117 个
`Panel_*.xml` 无一匹配」是方法错误（只按根目录与命名猜，没跑 `git ls-files | grep -i m11a`）。
全仓 2,117 个里文件名含 `m11a` 的**恰好 1 个**。

**静态字段与 live FDT 逐项一致**（可放心用它读面板规格）：分辨率 1440x3200、porch
hfp/hbp/hsync = 8/8/12、vfp/vbp/vsync = 16/6/14、DSC Major1/Minor2、slice 720x32、slice-per-pkt 2、
bpp 8、bpc 10、`DSIBitClockFrequency=1200000000`（= `panel-clockrate=0x47868c00`）、`DSILanes=4`
（与 `lane-0..3-state` 四条一致；单 DSI 控制器仍可用 4 lane，与 `dsi-ctrl-num=0` 不矛盾）、
`mi,panel-id` 与文件名 `M11a_42_02_0a` 一致。XML 分四组：`Active Timing`、`Display Interface`、
`DSI Interface`、`Backlight Configuration`；`DisplayResetInfo = 5 1000 1000 10000 0`
（DTB 的 `reset-sequence=<1 11 0 1 1 11>` 是另一种编码，不能按字面换算）。

**但 init 序列不能直接烧。** XML `DSIInitSequence` 131 行里有 2 行 `FF <ms>` 延迟——DTB 把延迟放进
**前一个包的 wait 字节**（7 字节头 `<dtype> <last> <vc> <ack> <wait> <dlen_hi> <dlen_lo>`，wait 在 0 基索引 4），
合并后 XML = **129 包**；live FDT `timing@0` 是 **135 包**。LCS：**125 包相同，3 个编辑块**——
删 3 包（`39 f055aa520801`、`15 6f02`、`15 d22a`）、插 9 包（`39 f055aa520801`、`39 d20000000015`、
`15 6f05`、`39 d2010000`、`15 6f0e`、`39 d20000101332`、`39 e480030000000000000033`、`15 6f0a`、
`39 e4800300100053`）、改 1 包类型（`39 6f46` → `15 6f46`），外加 2 处只是「XML 的 `FF <ms>` 延迟并进
前一个包的 wait 字节」的编码差异（不是实质差异）。延迟语义的独立佐证：DTB `off-command`
`39 00 00 00 14 00 02 28 00` 解出 wait=20 ms 发 `0x28`、`... 64 00 02 10 00` wait=100 ms 发 `0x10`，
正好对应 XML `DSITermSequence` 的 `05 28 / FF 14 / 05 10 / FF 64`。

全仓 2,117 个 XML 用同一套 wait-aware LCS 打分（2026-11-14 复核）：第二名
`nuwa/RawFiles/Panel_M11_42_02_0a_dsc_cmd.xml`（136 行 → 合并延迟后 134 包）同样**相同 125 包、但 6 个编辑块**，其余全部
≤4 包相同 → **marble 这份与 nuwa 打平在 125 包，marble 编辑块更少**。两份都只匹配 60 Hz 档的
`2f02`/`8b00`/`df21`，即都是 **60 Hz 修订**。
结论：拿它们当"面板规格来源"可以，当"init 串"不行 —— **但已经不需要补差异，也不需要 `dispdcbx`**：
真串在 2026-11-02 从本机 dump 下来的 live FDT 里（见 4.1），三档 on-command 各 1,534 字节、
sha256 全部实测。marble/nuwa 的 XML 只用来核对规格，不用来烧。

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

**三档只差 6 个字节**（逐包比对，三档均 135 包 / 1534 B）：`#56 15 2f` = `02`/`01`/`00`（60/90/120）、
`#59 15 8b` = `00`/`10`/`00`、`#64 15 df` = `21`/`20`/`20`，外加 3 个**包头**字节（`#19`、`#27`、`#51`）。
timing-switch-command（10 包）与 flat-mode on/off（各 116 B）同样只差 `2f`/`8b`/`df` 三个值。
→ **90 Hz 在驱动侧没有额外工作量**：同一套 init，选 `timing@1` 即可。live FDT 实测的字节差异见 4.1。

### 4.1 三档 on-command 的真实字节差异（2026-11-14 实测，live FDT）

来源：`/mnt/e/k60-work/reports/live-6033dbec-fdt.dtb`（919,210 B，2026-11-02 从 `6033dbec` dump），
`dtc -I dtb -O dts` 后取 `qcom,mdss_dsi_m11a_42_02_0a_dsc_cmd` 节点下每个 `timing@N` 的
`qcom,mdss-dsi-on-command`。原始字节已落到 `E:/k60-work/artifacts/panel-init-live/`。

| timing | Hz | on-command | off-command | timing-switch | on-command sha256 |
|---|---|---|---|---|---|
| `timing@0` | 60 | 1534 B | 18 B | 98 B | `cadf02b1552bf39df4604f2b066ba965a855d001a8aefcb2210c8822ef1268ec` |
| `timing@1` | 90 | 1534 B | 18 B | 98 B | `480b8cfbb0260a8baf6ec1ee257adccc67dc5034332de8c9f187698d42bbb215` |
| `timing@2` | 120 | 1534 B | 18 B | 98 B | `24652fb5ba863540cd35eaebe471967ff9b4a1c21c59b9a75847366d7cb4c972` |

三档长度完全相同，逐字节差异：

- `timing@0` vs `timing@1`：**6 字节** —— offset 201 `00→40`、293 `40→00`、566 `40→00`、
  624 `02→01`、651 `00→10`、700 `21→20`
- `timing@0` vs `timing@2`：**4 字节** —— offset 293 `40→00`、566 `40→00`、624 `02→00`、700 `21→20`
- `timing@1` vs `timing@2`：**3 字节** —— offset 201 `40→00`、624 `01→00`、651 `10→00`

这与 XML 侧独立得出的「三档只差 6 个字节」**完全吻合**，但这次是烧进面板的真实字节，不是 XML 推断。
`off-command` 三档逐字节相同（`39 00 00 00 14 00 02 28 00 39 00 00 00 64 00 02 10 00`，
sha256 `fe90b4790e137ad4…`），即关屏序列与档位无关。

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
**阻塞点（2026-11-14 修正）**：3 条 RPMh LDO（ldoc12 / ldoc13 / ldod1）的阻塞**不是**「RSC 不可访问」—— drv-2（`0x17a20000`）已被实测证明可读可写（49 个 boot，`caps=0x800c8104`、ACTIVE TCS4 投票 48/49 成功，见 REFERENCE-INDEX 3.1 / 14.1）。真正缺的是这 3 条轨的 **cmd-db 资源地址与投票参数**（本板未取）；在那之前面板供电只能沿用 bootloader 已开状态。

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
2. **Pong 的面板库没有一个匹配 K60**：`uefi-mondrian/Include/RAW.inc:1-5` 原文说明约 72 个 `Panel_*.xml` 全是 pong 的——这条对 pong 那个库成立。但「`Device-Binaries` 里 2,117 个也无一匹配 m11a」**已于 2026-11-14 推翻**：m11a 的 XML 在 `marble/RawFiles/` 下，见 1.1。它的 init 序列仍是同族不同修订，**不能直接烧**（marble 3 个编辑块，见 1.1）。
3. **zizhan 的 framebuffer 分辨率不能套**（见第 2 节）。

## 8. 缺口与下一步

| 缺口 | 状态 |
|---|---|
| ~~K60 厂商 panel XML 未找到~~ **已找到（1.1）** | `/mnt/e/hackios/Device-Binaries/marble/RawFiles/Panel_M11a_42_02_0a_amoled_dsc_cmd.xml`（无 `references/` 软链）。静态规格可信，init 序列差 3 个编辑块（129 包 vs 135 包） |
| ~~**init 串的差异要不要补**~~ **已解决（4.1）** | 两个选项都不需要：真串已在 live FDT 里（三档 1,534 B，sha256 实测），已落到 `E:/k60-work/artifacts/panel-init-live/`。marble/nuwa XML 只用于核对规格，不用于烧写 |
| ~~XML 的 `DisplayResetInfo` 与 DTB `reset-sequence` 换算~~ **不需要换算** | 上电时序以 DTB 为准（`<1 11 0 1 1 11>`，见第 3 节），XML 那行只描述同一件事的另一种编码，不参与构建 |
| ~~`timing@1`（90 Hz）MIUI 侧是否使用~~ **已缩小** | 三档同一套 init 只差 6 字节（第 4 节），90 Hz 无额外驱动工作量。实机侧：492 个 boot 中 452 个打出面板行，只有 **60 Hz（180 次）/ 120 Hz（272 次）**，` 90 Hz` 字符串 0 命中 → 本线 bring-up 从未选过 `timing@1`。剩下是「要不要暴露」的产品决定 |
| 面板供电真上电验证 | 3 条 RPMh LDO 的 cmd-db 资源地址与投票参数未取（RSC drv-2 已实测可读写，不是 RSC 阻塞）；在此之前无法自证 |

## 9. 交叉引用

- 证据行：[`../REFERENCE-INDEX.md`](../REFERENCE-INDEX.md) 第 7 节（7.2 节点 / 7.3 timing / 7.4 供电 / 7.5 基址 / 7.6 背光 / **7.7 厂商 panel XML 逐包比对**）、14.6、14.7
- 本板 `Display Reserved 0xB8000000+0x2B00000` 与 `video_region 0x85700000+0x700000`：[`memory/RESEARCH.md`](../memory/RESEARCH.md)
- 门禁数据源：`docs/research/SOURCES.toml` 的 `[subsystem.display]`、`[subsystem.gpu]`
