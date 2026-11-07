# K60 硬件 → 官方 UniXNU 组件映射与板级输入清单

> 调研快照：UniXNU 官方文档/组件目录 `E:/hackios/UniXNU` @ `75ae626a12764c706fc0b94c52a3eea09447dbaa`（2026-11-07）；K60 设备仓 `E:/hackios/UniXNU-mondrian` @ `9b4fec1d8708df7ed942ceab05bdef1963ad9e8f`。
>
> 引用约定：`docs/...` 指官方 `E:/hackios/UniXNU/docs/...`；`K60:docs/...` 指设备仓 `E:/hackios/UniXNU-mondrian/docs/...`；`components.toml` 指 `E:/hackios/UniXNU/components.toml`；`README.md`/`board.toml`/`porting.toml`/`dts/` 指设备仓根目录。`build-gop-legacy-display*.py` 等脚本位于 `E:/hackios/UniXNU-sheng/scripts/` 或 `E:/hackios/UniXNU/scripts/`，行号按本次读取的本地快照。

> 2026-11-08 LIVE 复核：本文件在本地快照（2026-10-29/11-07）基础上，按官网查询重抓「3. 适配驱动」16 项共 39 页；正文按 ①结论 → ②16 项覆盖率 → ③硬件映射/板级输入 → ④五个具体问题 → ⑤pong 对比 → ⑥未核实 排列，板级输入明细见附录 A、版本明细见附录 B、页面来源见附录 C。

## ① 结论摘要

1. **官方组件库是 SM8550/sheng 参考栈，不是通用 K60 栈。** 官方目录覆盖 A740（SM8550）、WCN7850、Novatek NT36532、KTZ8866 背光、CS35L43/WCD938x 音频；K60 的 SM8475/A730、QCA6490（ath11k）、Goodix 触摸、AW882xx 功放没有可直接替换的官方组件，只有通用平台层和 kit 层能对齐。
2. **可优先评估的官方组件（接口层低风险）：** `ArmDTPlatform`、`ArmCpu`、`ArmSmmu4K`（通用 ARM64 层）、`QcomGeniSpi`（GENI SPI 传输）；`ShengHidInput` 可复用结构但 IOHIDFamily ABI 需按 20G81 重对；`AppleKeyStoreState`/`RamBlock`/`XnuPrelink`/`DarwinBoot` 属 OS 支撑层，K60 当前另有 miniamfi/keybag 与本地 DarwinBoot22 路线，不能直接替换。`GopFramebuffer` 需要先补 16.6.1 的 ABI 构建器，属于中等风险，不能算“直接可用”。
3. **必须保留 pong 设备实现或以 pong 为蓝本新写的：** `PongUfs`（SM8475 UFS）、`PongAdreno`/`PongMetal`（A730/Metal）、Goodix 触摸协议层、`PongWifi`（QCA6490/ath11k）、`PongPower`（ADSP/AudioReach/平台电源）以及全新 AW882xx 功放、QCA6490 BT、K60 实体键驱动。官方同名组件在这些硬件上均不可直接替换。
4. **版本结论：官方 `drivers/`、`porting/`、`reference/` 全部文档 0 处提及 `16.6.1` 或 `20G81`。** 文档主要标注 iPadOS 17.7.11/21H461 与 iPadOS 27.0.1/24A446；对 K60 的 16.6.1 目标，所有组件级条目只能标“未说明”，不能把 17/27 的验证结果当作 16.6.1 资格。
5. **规范结论：** 官方是 format-2 设备仓 + `components.toml` 选择 + `scripts/package.sh` + `--os` 覆盖的单一构建流；pong ios16 是 54 行 `board.toml` + 自定义脚本 + 8 个 vendored driver 目录的社区先例。建议采用“**官方规范壳 + pong 设备驱动核**”：设备仓/记录/打包向官方靠拢，硬件驱动继续用 pong 分叉，等官方补齐 SM8475/A730/QCA6490/AW882xx 后再逐项上游化。

## ② 16 项官方文档覆盖率

### 2.1 阅读口径

- **已读**一列全部为 **是（LIVE 2026-11-08）**：16 项共 39 个页面由 `https://unixnu.com` 实时抓取后逐页通读；与本地 2026-11-04 存档相比，`porting/drivers.md` 等页面已有更新，本表以 LIVE 为准。
- **对 K60 适用性**按“官方组件/官方 ABI 是否能直接用”评级，不评价 K60 是否值得做该功能：
  - **✅ 直接适用**：方法论或通用组件无需改 ABI 即可用于 20G81。
  - **◐ 部分适用**：流程、架构、总线层可复用，但组件、板级常量或 OS ABI 必须重做/重对。
  - **✗ 不适用**：官方组件与 K60 硬件代际/OS 代际不匹配，只能当参考实现或流程模板。

### 2.2 覆盖率表

| # | 项目 | 文件（官方路径） | 是否已读 | 关键结论 | 对 K60 / 20G81 适用性 |
|---:|---|---|---|---|---|
| 1 | 适配顺序 | `docs/porting/drivers.md` | 是（LIVE） | 驱动边界必须写清 Hardware / Transport / Memory / OS / Build 五项；硬件顺序：CPU/中断/RAM/DMA → 存储 → 显示 → 输入 → GPU → Wi-Fi/蓝牙/USB → 基带 → DSP/音频/电源 → OS 服务；build 侧要接 `board.toml` 的 `[components] include`、`[kernel] archives`、`component:<ID>` 与初始化调用点。 | **✅ 方法论全适用**。K60 当前是 pong 式单脚本构建，迁官方 format-2 recipe 是后续重构项，不影响本条作为审查清单。 |
| 2 | 平台与内存 | `docs/porting/platform.md` | 是（LIVE） | CPU MPIDR/PSCI/GIC/计时器；sheng 用 `unixnu,cluster-type = "E"/"P"`（E=cpu0–2，P=cpu3–7）；内存要求 `/memory` 单节点单组 reg、**contiguous handoff RAM range**；DMA 要记录 SMMU instance/stream/context；DarwinBoot 只接收 Mach-O、ADT、sidecar；RamBlock/VerifiedRoot 是可选块/信任层。 | **✅ 流程适用，数值全换**。K60 的 MPIDR 是 flat `0x000..0x700`，不能套 sheng 的 E/P 分组；K60 内存是六段不连续，官方“contiguous”模型只支持单窗口，详见 `④c`。 |
| 3 | UFS 存储 | `docs/porting/ufs.md` + `docs/drivers/sheng-ufs.md`、`docs/drivers/verified-root.md`、`docs/drivers/ram-block.md` | 是（LIVE） | `ShengUfs` 是 SM8550 UFS 参考：host `0x01d84000/0x3000`、PHY `0x01d80000/0x2000`、apps-SMMU stream `0x60`、GCC `0x00100000`；流程是 firmware-state adoption（复用 bootloader 的 request list），再做 GPT/window/root publication；`VerifiedRoot` 做 owner-signed root policy，`RamBlock` 做 RAM-backed Data + `native_ufs_store` 回调。 | **◐ 流程适用，组件不适用**。K60 是 SM8475：host/PHY 同址但 SMMU stream `0xe0`、GCC UFS 页 `0x187000`、compatible `qcom,sm8475-ufshc`；`ShengUfs` 的 SM8550 常量不能直接选。K60 已有 `PongUfs`（`Emilelu/PongUfs@c959284`）逐项对上。`VerifiedRoot`/`RamBlock` 目前未启用。 |
| 4 | 显示与亮度 | `docs/porting/display.md` | 是（LIVE） | 先确认 firmware GOP（base/size/dimensions/stride/pixel format/reserved range），再走 `GopFramebuffer` / `NativeLegacyDisplay` / `NativeGOPPresenter`；`DisplayTimingProbe` 读 DPU/DSI 计数；direct scanout `sheng-dpu-scanout=2` 是实验；24A446 有专门默认 surface adapter。亮度是独立运输层（KTZ8866 I2C 示例）。 | **◐ GOP/软件 framebuffer 模型适用，DSI 真通路不适用**。K60 目前只有 GOP + 软件 framebuffer（1440×3200@60）；真 DSI 面板驱动缺失，官方 `DisplayTimingProbe` 是 SM8550 DPU，不是 K60 DSI0。24A446 adapter 不能用于 20G81。 |
| 5 | 亮度驱动 | `docs/drivers/sheng-backlight.md`、`docs/drivers/gop-framebuffer.md` | 是（LIVE） | `ShengBacklight` 驱动两颗 **KTZ8866 @ I2C 0x11**（QUP1 SE1 `0xa84000` / I2C hub `0x988000`），11-bit level 0–2047 写 `BL_BRT_LSB 0x04`/`BL_BRT_MSB 0x05`；GENI I2C 25 ms 超时；iPadOS 17 用 `IODisplayParameters.brightness`，iPadOS 27 还要 millinits/slider table/calibration/brightness-nits；`GopFramebuffer` 本身无亮度。 | **✗ 硬件不适用，◐ OS 属性模型可参考**。K60 无独立背光 IC：FDT 只有 `pm8350c gpio lcd_backlight_ctrl` 和面板 DCS 调光；上机笔记是 `0x11`(Sleep Out) → `0x29`(Display On) → `0x51`(brightness)。必须走 DSI DCS 传输，不能套 KTZ8866。20G81 只需 iPadOS 17 式属性，不需要 27 的 millinits 表。 |
| 6 | 触控与按键 | `docs/porting/input.md` + `docs/drivers/sheng-novatek-touch.md`、`docs/drivers/sheng-hid-input.md`、`docs/drivers/qcom-geni-spi.md`、`docs/drivers/community-nativefocaltechtouch.md` | 是（LIVE） | `nvt_bus` 只要求 `xfer`（全双工、CS 保持）和 `delay`；`QcomGeniSpi` 提供 GENI SPI 引擎；`ShengNovatekTouch` 是 NT36532E 协议 + 40×60 矩阵核心；`TouchBoard.h` 存板级地址/时钟/引脚；`ShengHidInput` 用 IOHIDFamily 2031.120.4 ABI 发布 digitizer；`ButtonProbe.cpp` 做 GPIO/PMIC 按键并报 report 2。FT8203 社区驱动说明“不同传感器要自己写协议”。 | **◐ 总线层适用、协议层不适用**。`QcomGeniSpi` 可复用（换 SE4 `0x990000`、IRQ GPIO21、RESET GPIO20、AVDD GPIO71、SPI 15 MHz）；Goodix 的识别/固件/report 必须新写；`ShengHidInput` 需按 20G81 IOHIDFamily 重对；`ShengNovatekTouch`/NvtTouchCore 不能用于 Goodix。详见 `④a`。 |
| 7 | GPU 与 Metal | `docs/porting/gpu.md` + `docs/drivers/adreno740.md`、`adreno-metal.md`、`adreno-firmware.md`、`adreno-pm4.md`、`arm-smmu4k.md`、`sm8550-platform.md`、`air-nir.md` | 是（LIVE） | `Adreno740` 只实现 **A740** 内核接口；`AdrenoMetal` 走 AIR→metal2vulkan→Turnip→NIR/IR3；`Sm8550Platform` 提供 GMU/GPU SMMU/RPMh command DB；`ArmSmmu4K` 是 4 KiB stage-1/2 表 kit；固件 `qcom/gmu_gen70200.bin`、`qcom/a740_sqe.fw`、`qcom/sm8550/sheng/a740_zap.mbn`；build 分 iOS 17 与 iOS 27 两套。 | **✗ A740 组件不适用**。K60 是 `qcom,kgsl-3d0@3d00000`、`qcom,gpu-model="Adreno730v3"`、chipid `0x7030002`、GMU `0x3d69000`；必须用 pong 的 `PongAdreno`/`PongMetal`（A730）+ `ArmSmmu4K` 思路。官方 GPU 流程（先 DMA/显示、后 GMU/firmware/ring）可当检查表。 |
| 8 | Wi-Fi | `docs/porting/network.md` + `docs/drivers/ath12k-wifi.md` | 是（LIVE） | 先 PCIe endpoint（controller/PHY/lanes/reset/WLAN_EN/PERST/refclk/rails/SMMU/MSI），再实现 `nw_abi.h` 的 `lx_platform`/`nw_board`，最后 `WifiNet` 接 Apple80211；官方实现只列 **ath12k 家族 QCC2072/QCN9274/WCN7850**（WCN7850 端点 `17cb:1107`，128 MiB DMA window）。 | **✗ 组件不适用，流程 ◐**。K60 是 **QCA6490 / WCN6855 hw2.x，ath11k，端点 `17cb:1103`**；`Ath12kWifi` 没有 ath11k 后端。K60 应走 `PongWifi`（`Chengdong-Yu/pong-wifi@d2e33ca`，ath11k v7.0.14）+ K60 板级 profile；官方 `nw_abi` 契约可复用。 |
| 9 | 蓝牙 | `docs/porting/bluetooth.md` | 是（LIVE） | `QcaBluetooth` 跑 Linux `btqca.c` 初始化，经 GENI UART + UART.SK 把 H4 字节送给 Apple `bluetoothd`；sheng 参数：UART QUP2 SE6 `0x898000`、IRQ 493、SMMU `0x423`、GPIO76–79、BT_EN81、3.2 Mbaud、固件 `hmtbtfw20.tlv`/`hmtnv20.bin`；用户态是 **iPadOS 27** BlueTool/bluetoothd/QcaBTType0.dylib。 | **✗ 对 20G81 不适用**。K60 是 QCA6490：UART QUPV3_2 SE20 `0x894000`、IRQ 587、GPIO76–79、BT_EN81、SW_CTRL82、XO204、wake byte `0xfd`；更关键的是 20G81 kernelcache **没有 IOBluetoothFamily/IOBluetoothHCI**，只有 `com.apple.driver.AppleBluetooth`（BTReset 电源字符设备），官方 iPadOS 27 路线无法照搬。 |
| 10 | 蓝牙驱动 | `docs/drivers/qca-bluetooth.md` | 是（LIVE） | QcaBluetooth 状态只写 sheng/iPadOS 27.0.1（24A446）：GENI 4×2048 RX + 1×4096 TX、IBS、UART.SK；adapter 锁定单个 `bluetoothd` hash；`audio_system_plugins = ["BTAudioHALPlugin.driver"]`。 | **✗ 同第 9 项**。K60 无 pong 蓝牙实现；20G81 用户态也没有对应 HCI 栈。只能把 `qbt_geni`/`qbt_transport` 当 GENI UART 协议参考，第一版建议自研 UART HCI + btstack，不追 Apple `bluetoothd`。 |
| 11 | USB | `docs/porting/usb.md` | 是（LIVE） | `QcomDwc3` 继承 `AppleUSBXDCI`/`AppleUSBXHCI`；sheng 参数：DWC3 `0x0a600000`、Apple window `+0xc000`、GIC 165、SMMU stream `0x40`、eUSB2 refclk 38.4 MHz；bringUp 9 步；UCSI over GLINK 角色切换；ABI 脚本 `gen-usb27-abi.py`/`gen-usb27-host-abi.py` 只针对 **24A446** kernelcache。 | **◐ 硬件流程参考，ABI 不适用**。K60 DWC3 `0xa600000`、eUSB2 PHY `0x88e3000`、QMP `0x88e8000`；DWC3 与 sheng 同址，但 PHY/IRQ/SMMU/rails 与 20G81 ABI 均未对位。官方 QcomDwc3 只能当方法参考。 |
| 12 | USB 驱动 | `docs/drivers/qcom-dwc3.md`、`docs/drivers/community-native-dwc3.md` | 是（LIVE） | QcomDwc3 状态是 sheng/iPadOS 27：10 Gbps 枚举、Trust/配对/lockdown 通过；host mode 部分；`fairplayd.A2`/`adid` 必须关；community NativeDwc3 是 SM8150 nabu，**无硬件结果**。 | **◐ QcomDwc3 仅 24A446；✗ community NativeDwc3 对本板无意义**。K60 现有 USB 日志路线是 sweet/pong 的 DWC3 设备端 + CDC-ACM，不是 Apple USB 栈；若走官方 QcomDwc3，需先为 20G81 生成 ABI。 |
| 13 | 基带与移动网络 | `docs/porting/baseband.md` + `docs/drivers/qcom-baseband.md` | 是（LIVE） | `QcomBaseband` 是 **SC7180 / IPA v4.2 / iOS 17** 参考：AppleBaseband/AppleBasebandPCIControl/AppleBasebandPCIInterface 类，QMUX/QRTR/QMI、SAHARA、IPA/GSI/QMAP，eSIM；Coachz 平台是 PCIe/MHI 风格。 | **✗ 不适用于 K60**。K60 是 SM8475 **集成 modem**：remoteproc@4080000（`qcom,sm8450-mpss-pas`）、GLINK→QRTR→QMI、IPA v5.1（mainline WIP），不是 SC7180 的 PCIe/MHI 架构。且 K60 伪装 iPad7,1（Wi-Fi 版）没有蜂窝身份，第一版应把 cellular 记为 `not-applicable`。 |
| 14 | DSP、音频与电源 | `docs/porting/power.md` | 是（LIVE） | `AdspProbe`：ADSP 固件/PAS/SMEM/SMP2P/GLINK/mailbox、`ShengAdspClient`、`sheng_adsp_channel`；`AudioProbe`：AudioReach/GPR 图、`ShengCs35l43.c`（sheng 的 6×CS35L43）、WCD938x SoundWire 麦克风、period buffer；`ShengBattery`/`ShengBattmgr`、`CpuFreqProbe`、`ShengPlatformPower`。SM8550 注意：DSP buffer <4 GiB、PRM clock `0x30c`、VA macro、19.2 MHz host clock。 | **◐ ADSP/AudioReach 架构可复用，功放层不适用**。K60 ADSP `0x03000000`、region `0x9fd00000/0x3100000`、SMEM `0x80900000/0x200000`、IPCC `0xed18000/IRQ261`、GPR `adsp_apps`、SID `0x1801` 与 sheng/pong 同构；但功放是 **2×AW882xx**，不是 CS35L43/TFA9873。`AudioProbe`/`AdspProbe` 对 AW882xx 覆盖为 0，详见 `④b`。 |
| 15 | 开发驱动 | `docs/drivers/overview.md`、`docs/drivers/xnu-drivers.md`、`docs/drivers/kexts.md`、`docs/drivers/device-tree-matching.md` | 是（LIVE） | 三层：UEFI driver / built-in XNU static archive / kext bundle。Built-in XNU 用 `IOService` + `KernelConfigTables.cpp` personality，编译必须复用 `.cpo.json` 的 flags，`-force_load` 链接；kext 需要 loader protocol revision 2，**shipped DarwinBoot 不接受 staged kexts**；DT matching 用 `IOClass/IOProviderClass/IONameMatch/IOProbeScore`。 | **✅ built-in 方法论适用**。K60 全部走 built-in（PongUfs/PongAdreno 均是）；`kexts.md` 的 bundle 路线对 K60 不适用（DarwinBoot22 不是 rev2 kext loader）。`device-tree-matching` 直接指导 PongUfs 的 `qcom,sm8475-ufshc` / `ufshc` 节点名修复。 |
| 16 | 修改 XNU | `docs/xnu/boot-arguments.md`、`docs/xnu/four-k-page-tables.md`、`docs/xnu/patch-reference.md`、`docs/xnu/source-and-patches.md` | 是（LIVE） | boot-args 合并规则/1000 bytes/1024 buffer；4K 页用 BCM2837 机器配置与一组 4K 补丁；patch 顺序按 `patch_series` 声明；17.7.11 用 `xnu-10063.141.1`，**iOS 16 与 iPadOS 17 共享 arm64 patch series**，iOS/iPadOS 27 用 arm64e series。 | **◐ 规则适用，源码/补丁要按 20G81 重排**。K60 用 `xnu-8796.141.3` / Darwin 22.6，不是 `xnu-10063.141.1`；4K、boot-args、patch order 三条必须遵守。当前 581 字符安全，详见 `④d`。 |

### 2.3 适用性统计

| 评级 | 项数 | 项目 |
|---|---:|---|
| ✅ 直接适用 | 3 | 1 适配顺序、2 平台与内存、15 开发驱动（方法论） |
| ◐ 部分适用 | 7 | 3 UFS、4 显示、6 触控、11 USB、12 USB 驱动、14 DSP/音频/电源、16 修改 XNU |
| ✗ 不适用（仅参考） | 6 | 5 亮度驱动、7 GPU、8 Wi-Fi、9 蓝牙、10 蓝牙驱动、13 基带 |
| **合计** | **16** | **16/16 已读** |

## ③ 硬件→组件映射大表

### 3.1 主映射表

| K60 硬件 | 官方组件/仓库 | 板级输入清单（完整字段见附录 A） | 与 pong 现方案的关系 |
| --- | --- | --- | --- |
| **CPU / 中断 / 内存** | `ArmDTPlatform`（platform expert）+ `ArmCpu`（CPU/GIC/timer）+ `ArmSmmu4K`（SMMUv2 4 KiB 表 kit）。仓库见 `docs/drivers/repositories.md:28-31`；页面 `docs/drivers/arm-dt-platform.md:5-17`、`docs/drivers/arm-cpu.md:5-17`、`docs/drivers/arm-smmu4k.md:3-19`；流程 `docs/porting/platform.md:18-20,24-26,71-74` | MPIDR/启动 CPU/启用核数、PSCI 方法、GIC revision/ distributor+redistributor 范围与 stride、timer 频率与中断 specifier（`docs/porting/platform.md:24-26`）；每个 CPU 节点 `unixnu,cluster-type="E"/"P"`（`:49-50`）；DRAM/secure carveout/framebuffer/DSP/GPU 固件/payload/kernel 的连续 handoff 范围与 `owned_memory_size`（`:66-69`）；每设备 DMA 地址宽度、物理→IOVA、SMMU instance/stream/context、cache 策略（`:71-74`）；ADT 必备 `/cpus`、`/psci`、`/arm-io`、`/chosen`、`/defaults`、`/options`（`docs/porting/device-tree.md:141-151`） | K60 当前 `drivers/ArmCpu`、`drivers/ArmDTPlatform` 与 pong ios16 字节一致（`K60:docs/audits/PONG16-DIFF-AUDIT.md:198-211`）；官方同名组件是上游版本，但 K60 的 Darwin22 first-boot 路径仍依赖 pong 修改（0247 等）。短期保留 pong CPU/平台代码，只把 DTS/ADT 契约对齐官方；`ArmSmmu4K` 可独立作为 kit 复用。 |
| **UFS** | `ShengUfs`（SM8550 UFS transport/root；`docs/drivers/repositories.md:13`、`docs/drivers/sheng-ufs.md:3-20`）。K60 现有 `PongUfs` 是设备组件（`components.toml:551-560`） | Controller compatible/revision/MMIO/capabilities/IRQ；PHY 范围/lane/参考时钟/tuning；clocks provider/ID/rate/parent/branch/interconnect；reset/power；SMMU instance/stream ID/mask/context bank/地址宽度；DMA 分配/IOVA/对齐/coherency/cache；HCE/HCS/link state/request-list 交接；LUN/块大小/容量/GPT/root 窗口/Data/log 保留；storage ABI/prelink/匹配（`docs/porting/ufs.md:37-47`）；`[userdata] first_lba/last_lba/lba_bytes`、`[payload.adt] root_match_volume_uuid`、`CONFIG_XNU_NATIVE_UFS=y`、`native-ufs-root=1`（`:94-118`） | K60 的 `PongUfs` 来自 pong `NativeUfs`，`dts/mondrian.dts:39-53` 已给出 `pong,ufs-*`/`pong,smmu-*` 全部常量（host `0x1d84000/0x3000`、GCC `0x187000`、SMMU `0x15000000/0x100000`、stream `0xe0`、SPI 265、context banks 78、match groups 120）。官方 `ShengUfs` 只覆盖 SM8550，不能直接替换；保留 PongUfs，后续可把 SM8475 常量做成 ShengUfs 的 SoC 后端。 |
| **显示 / 背光** | `GopFramebuffer`（UEFI GOP + MobileFramebuffer；`docs/drivers/repositories.md:16`、`docs/drivers/gop-framebuffer.md:3-25`、`docs/porting/display.md:16-63`）。背光**无 catalog 组件**，官方参考为 `UniXNU-sheng/package/AppleARMBacklight.cpp` + `GeniI2c.h`（KTZ8866）（`docs/drivers/sheng-backlight.md:3-69`、`docs/porting/display.md:101-145`） | GOP 的 base/size/width/height/stride/pixel format/reserved-memory（`docs/porting/display.md:3-5`）；`PE_current_console` 使用；`NativeGOPWire.h` 的 mode/geometry、present buffer 大小/stride、`NGPSwap.sequence`/`NGPComplete`（`:56-60`）；`CONFIG_XNU_NATIVE_LEGACY_DISPLAY=y`、`offline-legacy-*`（`:46-48`）；`sheng-dpu=1`、`sheng-vsync=120`、`sheng-dpu=2/3`、`sheng-dpu-scanout=2`、8-bit BGRA（`:78-99`）。背光：controller 数量、寄存器编码、亮度范围、I2C engine、slave 地址、pin、clock、IRQ、上电时序（`:106-110`）；`backlight-control`、`IODisplayParameters.brightness`（iPadOS17）、`BrightnessMilliNits`/`backlight-marketing-table`/`Lmax/Lmid/LminProduct`/`backlight-calibration-parameters`（iPadOS27）、`brightness-nits`/`brightness`/`FadePeriod`（`docs/drivers/sheng-backlight.md:29-44`） | K60 当前走 `MiniIOMobileFramebuffer` 补丁 + CPU 软件呈现（`README.md:73,91-93`；0210/0211/0213），不是官方 GopFramebuffer 路径。官方 `build-gop-legacy-display.py` 只接受 arm64 iOS17（`:10-12`），`build-gop-legacy-display-27.py` 只接受 arm64e iPadOS27（`:17-18`），16.6.1 无 recipe。背光：K60 无独立背光 IC，是面板 DCS `0x51` 调光（`K60:docs/reference/FEATURES-DRIVERS-RESEARCH-2026-10-31.md:106-108`）；官方 KTZ8866 I2C 示例只能复用 `AppleARMBacklight` 服务契约，传输层必须重写为 DSI-command。 |
| **触摸** | `QcomGeniSpi`（GENI SPI 控制器）+ `ShengNovatekTouch`（NT36532E 协议/处理）+ `ShengHidInput`（IOHIDDevice 上报）。`docs/drivers/qcom-geni-spi.md:3-19`、`docs/drivers/sheng-novatek-touch.md:3-154`、`docs/drivers/sheng-hid-input.md:3-21`、`docs/porting/input.md:16-79` | controller 窗口、bus mode/rate、GPIO、interrupt、SMMU stream（`docs/porting/input.md:43-44`）；power/reset 归属、engine firmware/pins/clocks；DMA 地址/cache；chip ID/固件/geometry；坐标到面板方向映射（`:44-50`）；Novatek 40×60 matrix、`scripts/gen-touch-firmware.py`（`:52-54`）；HID report descriptor、logical range、contact 上限（`:66-69`）；`sheng-touch=1..4`、`sheng-touch-hid=1`（`:56-58,71-73`） | K60 触摸是 **Goodix**（`xiaomi,m11a-spi`，GENI SPI SE4 `0x990000`，CS0），不是 Novatek NT36532。`QcomGeniSpi` 传输层可复用，`ShengHidInput` 可复用；`ShengNovatekTouch` 的 `NvtProtocol/NvtTouchCore` 不可用。需要 pong 的 `pong_goodix.c`/K60 `0242-k60-touch-goodix.patch` 作为协议层（`K60:docs/plans/K60-TOUCH-PARAMS.md:1,31-58,90`、`K60:docs/state/SESSION-DIRECTIVES-2026-11-07.md:67-84`）。 |
| **实体键** | **无 catalog 组件**；官方参考 `UniXNU-sheng/package/ButtonProbe.cpp` + `BootResetCore.h`（`docs/porting/input.md:84-97`） | GPIO 或 PMIC 输入、极性、ownership、interrupt routing、acknowledgement（`:89-90`）；`BootResetCore.h` helpers；HID report 2 的 Power/Volume Increment/Volume Decrement 位（`:92-94`）；`/buttons` ADT 的 `compatible="buttons"`、`device_type="buttons"`、`button-names`、`home-button-type`（`docs/porting/device-tree.md:233-235`）；`sheng-buttons=1` | pong `pong-physical-keys.patch` 是结构参考；K60 需按 UEFI `ButtonsDxe/SPMIDxe/PmicDxeLa` 的实测参数重写 XNU 驱动：PON peripheral `0x13`，音量加在 `pm8350@1/pinctrl@8800` GPIO6=`0x8d00`、ACTIVE_LOW（`K60:docs/state/SESSION-DIRECTIVES-2026-11-07.md:110-115`）。官方没有可复用代码。 |
| **GPU / Metal** | `Adreno740`（A740 kernel GPU）+ `AdrenoMetal`（Metal→metal2vulkan→Turnip frontend）+ `Sm8550Platform`（GMU/SMMU/RPMh kit）+ `AdrenoFirmware` + `AdrenoPM4` + `AirNir` + `ArmSmmu4K`。`docs/drivers/adreno740.md:1-38`、`docs/drivers/adreno-metal.md:1-58`、`docs/drivers/sm8550-platform.md:3-47`、`docs/porting/gpu.md:22-73,134-183`；catalog `components.toml:77-118,453-470` | GPU/GMU register 窗口、interrupt、SMMU context/stream ID、firmware、power domain、clock/voltage level、interconnect vote、RAM reservation、scanout layout（`docs/porting/gpu.md:30-32`）；固件 `qcom/gmu_gen70200.bin`、`qcom/a740_sqe.fw`、`qcom/sm8550/sheng/a740_zap.mbn`，`scripts/data/adreno-inputs.json` pin，`.cache/firmware/sheng-gpu/`，`proprietary-files.txt`（`:44-52`）；`build-turnip-darwin.py --target ios` 或 `--target ios27`、`build-adreno-metal-plugin.py`、`make-gpu-addon.py`、`--gpu-addon`/`--owner-trust-cache`、`sheng-gpu-addon=1`（`:136-152`）；`sheng-gpu-preempt=2`、`sheng-fb-bgra=1`、`TU_DEBUG=sysmem,nocb`（`:102,108-112`） | K60 是 **Adreno 730 v3**（chip `0x07030002`，2 MiB GMEM，HighestBankBit 16，64×32 tile；`K60:docs/plans/GPU-ENABLE-PLAN.md:238`），官方 `Adreno740` 的 hardware 字段明确 `["Adreno 740","SM8550"]`（`components.toml:86`），`Sm8550Platform` 也只支持 SM8550（`docs/drivers/sm8550-platform.md:15`）。K60 现用 `PongAdreno`/`PongMetal`（与 pong ios16 同码；`K60:docs/state/SESSION-DIRECTIVES-2026-11-07.md:97-100`）。保留 pong GPU 栈；`AdrenoFirmware`/`AdrenoPM4`/`AirNir`/`ArmSmmu4K` 可作 kit 级复用候选，但需按 A730 重新验证。 |
| **WiFi（QCA6490）** | `Ath12kWifi`（ath12k + MHI/QRTR/QMI；`docs/drivers/repositories.md:25`、`docs/drivers/ath12k-wifi.md:3-16`、`docs/porting/network.md:16-75`）。catalog hardware 只列 `qcc2072/qcn9274/wcn7850`（`components.toml:482`） | radio/PCI ID/firmware/board-data variant（`docs/porting/network.md:3-5`）；PCIe controller/PHY 窗口、lane、reset、WLAN enable、PERST、参考时钟、regulators、interconnect votes、SMMU streams、MSI routing（`:33-35`）；BAR/PCI capability/bus-master、DMA range/cache、MSI；`lx_platform`（time/sleep/poll/log/alloc/DMA alloc-map-sync/fw_get）与 `nw_board`（BAR/PCI identity/config space/MSI target）与 `nw_wifi_events`/`nw_wifi_start/step/stop`（`:53-75`）；MAC identity、channel/regulatory data、request layout（`:80-85`）；`build-ath12k-wifi.py` 由 `build-gop-legacy-display.py` 调用，`sheng-wifi=5`、`sheng-wifi-aj=0`（`:87-105`） | K60 是 **QCA6490/WCN6855，PCI `17cb:1103`，ath11k**（`K60:docs/plans/WIFI-PORT-PLAN.md:13,76-85`）；官方 `Ath12kWifi` 是 ath12k，只支持 WCN7850/QCC2072/QCN9274。**不可用**。pong main 的 `PongWifi` 才是正确先例，K60 计划已明确“直接移植 Pong 的 QCA6490 + ath11k 路线，不要沿用 Ath12kWifi 旧规划”（`K60:docs/plans/WIFI-PORT-PLAN.md:13`）。 |
| **蓝牙（QCA6490）** | `QcaBluetooth`（WCN7850 UART→Apple Bluetooth；`docs/drivers/qca-bluetooth.md:3-56`、`docs/porting/bluetooth.md:14-35`）。catalog hardware `["Qualcomm WCN7850 UART controller","Qualcomm GENI UART"]`（`components.toml:502`） | UART QUP2 SE6 `0x898000`/GIC INTID 493（sheng 示例）；DMA stream `0x423`；CTS/RTS/TX/RX GPIO 76/77/78/79；`BT_EN` GPIO81；wake GPIO79；51.2 MHz/16x/3.2 Mbaud；固件 `hmtbtfw20.tlv`/`hmtnv20.bin`（`docs/porting/bluetooth.md:24-35`）；powerOn 顺序（BT_EN 低 100 ms→serial clock→QUP version/protocol→engine→IRQ→BT_EN 高 60 ms→pull）；`sheng_wcn_power_get/put`（`:50-62`）；DTS 节点 `device_type="bluetooth"`、`compatible="qcom,wcn7850-bt"`、`unixnu,adt-name="bluetooth"`、`transport-encoding=<1>`、`transport-speed=<3200000>`、`status="okay"`；`local-mac-address` + `/chosen/mac-address-bluetooth0`；IOService `bluetooth`（`:75-89`）；`audio_system_plugins=["BTAudioHALPlugin.driver"]`、`bluetooth_tool`/`bluetooth_target`（`:93-99`）；AppleKeyStoreState key wrapping + `/chosen/unique-chip-id`（`:109-110`） | K60 QCA6490 BT 走 **GENI UART / HS-UART，QUPV3_2 SE20 `0x894000`，IRQ 587，GPIO76/77/78/79**（`K60:docs/plans/BT-AUDIO-PORT-PLAN.md:36,51-70,77`）；与 WCN7850 同族协议但固件/控制器不同（`htbtfw21.tlv`/`htnv21.bin`，未核实）。官方 QcaBluetooth 的 `qbt` 框架可借鉴，但 catalog hardware 不匹配；pong main/ios16 **都没有 BT 驱动**（`K60:docs/plans/BT-AUDIO-PORT-PLAN.md:36-41`），K60 BT 是零先例，需要新写 QCA6490 GENI UART 驱动。 |
| **音频（AW882xx）** | **无 catalog 组件**；官方参考为 `UniXNU-sheng/package/AudioProbe.cpp`、`ShengAudioReach.c/h`、`ShengGpr.c/h`、`ShengAudioService.cpp`、`ShengAudioPlugIn.c`、`ShengCs35l43.c`（CS35L43 功放 + WCD938x codec）。`docs/porting/power.md:13-17,53-141`、`docs/porting/drivers.md:48` | codec/amplifier ID、bus、clock、route、DSP topology、支持格式、OS audio ABI（`docs/porting/power.md:15`）；DSP firmware/PAS ID、memory reservation、mailbox IRQ、shared-memory layout、clock/power ownership（`:14`）；GPR domain/port/packet size/opcode、graph/subgraph/module instance ID、connections、codec port、amplifier setup、clock/channel map（`:70-104`）；period buffer <4 GiB、PRM vote、24 MHz host clock vs 19.2 MHz timebase（`:98-104`）；microphone route 的 codec/SoundWire/analog/digital 参数（`:114-137`） | K60 实测 **2×AW882xx**（`awinic,aw882xx_smartpa@34/@35`，I2C `0x34/0x35`，reset GPIO1/3，IRQ 88/63，spksw 52；`K60:docs/plans/BT-AUDIO-PORT-PLAN.md:38,207-222`）。官方 sheng 是 CS35L43 + WCD938x，pong main 是 TFA9873；三者功放都不同。`AudioReach/GPR` 图框架可从官方 sheng 或 pong `PongPower/PongAudio.cpp` 复用，但 AW882xx 功放驱动、寄存器表、awini 校准必须新写（`K60:docs/plans/BT-AUDIO-PORT-PLAN.md:414,499-500`）。 |
| **DSP / 电源 / 电池** | **无 catalog 组件**；官方参考 `AdspProbe.cpp`/`ShengAdsp.h`、`ShengBattmgr.c/h`、`ShengBattery.cpp`、`BatteryProbe.cpp`、`CpuFreqProbe.cpp`、`QcomRpmh.h`、`ShengPlatformPower.cpp`、`GpuPowerProbe.cpp`。`docs/porting/power.md:24-51,143-233` | DSP：firmware/PAS ID、memory reservation、mailbox IRQ、shared-memory layout、clock/power ownership（`:14`）；battery：gauge/firmware protocol、property ID、units、current sign、notification（`:16`）；power：clock domain、OPP table、regulator、firmware vote、thermal limit（`:17`）；battery 快照字段 presence/external power/charge state/capacity/voltage/current/temp/time remaining（`:157-176`）；SM8550 governor 输入（`:202-208`） | K60 的 ADSP carveout 是 `0x9fd00000/0x3100000`（49 MiB，`K60:docs/plans/BT-AUDIO-PORT-PLAN.md:219`），PMIC 为 `pmk8350/pm8350/pm8350c/pm8350b/pmr735a/pmr735b/pm8450`（`:224`）。pong main 的 `PongPower` 是最接近的 SM8475 实现（`PongPlatformResources`/`QcomRpmh`），pong ios16 没有 `PongPower`；K60 计划要求先移植 `PongPower` 再做 WiFi/BT/音频（`K60:docs/plans/WIFI-PORT-PLAN.md:17,308`、`K60:docs/plans/BT-AUDIO-PORT-PLAN.md:405-427`）。官方 sheng 参考是 SM8550，需按 K60 ADSP/PMIC 重对。 |
| **USB** | `QcomDwc3`（AppleUSBXDCI/AppleUSBXHCI on Qualcomm DWC3；`docs/drivers/qcom-dwc3.md:3-49`、`docs/porting/usb.md:14-118`、`docs/drivers/repositories.md:27`） | DWC3 base 与 Apple register window（base + `0xc000`）、GIC INTID、SMMU stream、eUSB2 参考时钟 38.4 MHz、eUSB2 PHY/PMIC repeater/QMP combo PHY/retimer/GDSC/RPMh rails（`docs/porting/usb.md:25-33`）；bringUp 9 阶段（`:44-57`）；stage 1 identity context write-back inner-shareable（`:59-60`）；AppleUSBXDCI/AppleUSBXHCI kext 加载顺序与 prelink roots（`:66-80`）；UCSI `qcom_dwc3_vbus`/`qcom_ucsi_start/receive/tick/polling`（`:90-105`）；pairing 的 `chip-id`/`board-id`/`security-domain`、`native-union-statfs-fsid`、lock state 3（`:108-118`） | 官方 `QcomDwc3` 只标 iPadOS 27.0.1（24A446）（`docs/drivers/qcom-dwc3.md:9`、`components.toml:523`），ABI JSON 也全部是 24A446（`docs/porting/usb.md:78-80`）。K60 DWC3 core 同在 `0xa600000`（+QSCRATCH `0xa6f8800`），但 eUSB2 PHY 是 `0x88e3000`、SMMU stream 实测为 `0x0`（`K60:docs/reference/USB-LOG-CHANNEL.md:150-152`、`K60:docs/reference/ISSUES.md:195`）。pong ios16 没有 USB 栈；K60 目前是自定义 DWC3/usblog 探针，不能直接换 QcomDwc3。 |
| **OS 支撑（钥匙串/加密/预链接/加载器/块）** | `AppleKeyStoreState`、`SoftwareAES`、`XnuPrelink`、`DarwinBoot`、`RamBlock`、`VerifiedRoot`（`docs/drivers/repositories.md:15,19-20,24,36-37`；`docs/reference/components.md:42-44`） | 钥匙串：`native_aks_device_id`、`sheng-aks-sls=3`、selectors/state callback（`docs/drivers/apple-key-store-state.md:9-13`）；加密：XNU AES/IOCryptoAcceleratorFamily ABI（`docs/porting/platform.md:87`）；prelink：kernelcache pin/roots/slide/ABI（`docs/drivers/xnu-prelink.md:9-14`）；loader：arm64/arm64e `MH_EXECUTE`、ADT/trust cache/ramdisk（`docs/drivers/darwin-boot.md:5-17`）；RamBlock：`native_ufs_store` 持久化回调（`docs/drivers/ram-block.md:5-9`）；VerifiedRoot：signed volume policy（`docs/porting/platform.md:86`） | K60 当前使用 `DarwinBoot22`、`kits/NativePrelink`、`NativeRamBlock`（pong 分叉），不是官方 `DarwinBoot`/`XnuPrelink`/`RamBlock`。16.6.1 ABI 未审计，建议保留现有；`AppleKeyStoreState`/`SoftwareAES` 可作为后续官方化候选，但 K60 现在有自己的 miniamfi/keybag 补丁路径（`K60:docs/state/SESSION-DIRECTIVES-2026-11-07.md:5-13`）。 |

### 3.2 官方组件资产、submodule pin 与 build integration

**Submodule 归属说明：** 框架仓 `UniXNU/.gitmodules` 只包含下表的“框架 submodule”组；`ShengUfs`、`ShengHidInput`、`ShengNovatekTouch`、`QcaBluetooth`、`QcomDwc3`、`Ath12kWifi`、`ShengPreflight` 是设备仓 `UniXNU-sheng/.gitmodules` 的 submodule；`Sm8550Platform` 是 `UniXNU-sm8550-common` 的 kit 目录，不是 submodule。

| 组件 ID | 仓库 URL | Submodule | 框架/设备仓 gitlink pin | `components.toml` revision | Build 脚本 → archive/output | 初始化调用点 |
| --- | --- | --- | --- | --- | --- | --- |
| `ArmCpu` | `https://github.com/UniXNU/ArmCpu.git` | 框架 | `9066b53bbc82e92a98ec44a11dd50fd13eaf1a1b` | `93a5030c5d983d0ef90f0fca93879d6e36ad1ba8` | `component:ArmCpu` → `build/armcpu/libArmCpu.a`（`docs/drivers/arm-cpu.md:17`） | `ArmCpu` personality / platform expert（`docs/porting/platform.md:19`） |
| `ArmDTPlatform` | `https://github.com/UniXNU/ArmDTPlatform.git` | 框架 | `417ff95d6a6e8607ddea9309ec45c3bfd4a67c60` | 同左 | `component:ArmDTPlatform` → `build/armdt-platform/libArmDTPlatform.a`（`docs/drivers/arm-dt-platform.md:17`） | `ArmDTPlatform::configure()` 发布 CPU nub 和每个 `arm-io` child（`docs/porting/device-tree.md:141-151`） |
| `ArmSmmu4K` | `https://github.com/UniXNU/ArmSmmu4K.git` | 框架 | `3ba92451bd44bb742d11758fbfcd3a446ecad685` | `83969cd874503e65997ff7639f7dcf3d0a92cd17` | 无独立 archive；由消费驱动 recipe 编译 `ArmSmmu4K*.c`（`docs/drivers/arm-smmu4k.md:19`） | GPU/UFS/display 的 SMMU context 编程点 |
| `ShengUfs` | `https://github.com/UniXNU/ShengUfs.git` | sheng 设备仓 | `af14068c329f4d8693d20a3ed38a435ade04bb75` | `99d8bcd3e43dd24fc3c8437c67b5d4cc71ab94d0` | `build-arm-driver.py ShengUfs` / `component:ShengUfs` → `build/sheng-ufs/libShengUfs.a`（`components.toml:137-138`）；`CONFIG_XNU_NATIVE_UFS=y`、`native-ufs-root=1`（`docs/porting/ufs.md:113-114`） | `NativeUfs` personality，`IONameMatch`=`qcom,sm8550-ufshc`（`docs/drivers/device-tree-matching.md:43-50`） |
| `GopFramebuffer` | `https://github.com/UniXNU/GopFramebuffer.git` | 框架 | `33e941a878dcf01b98dbd9160d798bd56e7551ea` | `e47c1b8de169cd2bd0b885c7d85e433010e3cdf2` | `build-gop-legacy-display.py`（iOS17）/ `build-gop-legacy-display-27.py`（iOS27）→ `build/native-legacy-display/libNativeLegacyDisplay.late.a`（`build-gop-legacy-display.py:13,316`，`-27.py:20,659`） | `native_legacy_display_probe()` 注册，`native_legacy_display_late_probe()` 后段启动（`LegacyDisplayProbe.cpp:470-512`；文档引 `docs/porting/drivers.md:63` 的 `:493` 为旧行号） |
| `ShengNovatekTouch` | `https://github.com/UniXNU/ShengNovatekTouch.git` | sheng 设备仓 | `3b44b1b7603eaadae942ea44ddc51bdcc48ad060` | 同左 | `build_stage="embedded"`，无独立 build；由 `build-gop-legacy-display.py:302-303` 编译 `NvtProtocol.c`/`NvtTouchCore.c` 进 `libNativeLegacyDisplay.late.a` | `native_touch_probe()`（`LegacyDisplayProbe.cpp:516`；`sheng-touch=1..4`） |
| `QcomGeniSpi` | `https://github.com/UniXNU/QcomGeniSpi.git` | 框架 | `eac47baefe6a5d2368a70351e6ad1b6361bedbe2` | 同左 | `build_stage="embedded"`；`GeniSpi.c` 编入 `libNativeLegacyDisplay.late.a`（`build-gop-legacy-display.py:302-303`） | 通过 `TouchProbe.cpp` 的 `nvt_bus.xfer` 回调初始化 |
| `ShengHidInput` | `https://github.com/UniXNU/ShengHidInput.git` | sheng 设备仓 | `71a40e76daeae1bb4127546f96ffa7339c7a06ff` | 同左 | `build-sheng-hid-input.py` → `build/sheng-hid-input/libShengHidInput.a` + `NativeHidInput.late.o`（`components.toml:159-160`） | `native_hid_input_probe()`（`LegacyDisplayProbe.cpp:526`） |
| `Adreno740` | `https://github.com/UniXNU/Adreno740.git` | 框架 | `5c8c1453c67d6ef6b10ec43ab1f8fc570a2f33e1` | `6fa7bae2a5b3b523e790eb3e0348af4d98969e4d` | `build-arm-driver.py Adreno740` / `component:Adreno740` → `build/adreno740/libAdreno740.a`；`build-adreno740-kits.py` 追加 kit objects；`build-adreno740-accelerator.py` 生成 accelerator（`docs/porting/gpu.md:67-70`、`docs/drivers/adreno740.md:26-32`） | `sheng-gpu-power=9`、`sheng-gpu-metal=1`、`sheng-gpu-addon=1`；GPU service 由 `NativeAdrenoService` 发布 |
| `AdrenoMetal` | `https://github.com/UniXNU/AdrenoMetal.git` | 框架 | `ce5e19e33e05e1873d38d818e23cabfe0ac708c3` | `6d7f73437087c57ee54a41adceb1735daaea405e` | `build-turnip-darwin.py --target ios` / `--target ios27` + `build-adreno-metal-plugin.py` 同 target + `make-gpu-addon.py` → `build/adreno-metal-plugin/NativeAdrenoMetal.bundle` / `gpuaddon.bin`（`docs/porting/gpu.md:136-152`） | `--gpu-addon`/`--owner-trust-cache` 装入 payload；router plugin `NativeAdrenoMetal`；`sheng-gpu-addon=1` |
| `AdrenoFirmware` | `https://github.com/UniXNU/AdrenoFirmware.git` | 框架 | `20ad3d7aca14bd46aecab6335c780f5413fa054b` | 同左 | kit，无独立 archive；由 `build-adreno740-kits.py` 编入 `libAdreno740.a`（`docs/porting/gpu.md:67-70`） | GMU/HFI 固件加载点（`ShengGmu.c`/`AdrenoHfi.c`） |
| `AdrenoPM4` | `https://github.com/UniXNU/AdrenoPM4.git` | 框架 | `282606b528b2595bc4274ea7490b62b323f35a5f` | 同左 | kit，无独立 archive；由 `build-adreno740-kits.py` 编入 `libAdreno740.a` | PM4 packet 编码，供 Adreno740 提交路径 |
| `AirNir` | `https://github.com/UniXNU/AirNir.git` | 框架 | `b356371a74cd158c2902f4886f373ebb0f833a36` | 同左 | kit，无独立 archive；Turnip/metal2vulkan 编译链使用（`docs/porting/gpu.md:159-160`） | AIR→SPIR-V→NIR→IR3 编译链 |
| `Sm8550Platform` | `https://github.com/UniXNU/UniXNU-sm8550-common.git`（`kits/Sm8550Platform`） | 否（SoC feed） | n/a | `a9f45dc60c035084b95463781538380f4c3606c9` | 无独立 archive；`build_stage="embedded"`，编入 board package（`docs/drivers/sm8550-platform.md:22-27`） | `ShengGmu.c`/`ShengGpuSmmu.c`/`ShengGmuCommandDb.c` 由 GPU 驱动调用 |
| `Ath12kWifi` | `https://github.com/UniXNU/Ath12kWifi.git` | sheng 设备仓 | `28de7b91d7a880682b777e0e3564245a99dbc3f5` | 同左 | `build-ath12k-wifi.py` 输出 `OBJ` 清单，对象并入 `libNativeLegacyDisplay.late.a`（`build-gop-legacy-display.py:315,327`）；用户态 `build-wifi-userspace.py`（`docs/porting/packaging.md:128-135`） | `sheng_wifi_probe()`（`LegacyDisplayProbe.cpp:517`）；`sheng-wifi=5` |
| `QcaBluetooth` | `https://github.com/UniXNU/QcaBluetooth.git` | sheng 设备仓 | `22ff97f93416452335bb61badb14c762da653487` | 同左 | `build-qca-bluetooth.py` 输出对象并入 `libNativeLegacyDisplay.late.a`（`build-gop-legacy-display-27.py:507-508`）；用户态 `build-bluetooth-userspace.py` | `sheng_bluetooth_probe()`（weak，`LegacyDisplayProbe.cpp:518`）；`sheng-bluetooth=1` |
| `QcomDwc3` | `https://github.com/UniXNU/QcomDwc3.git` | sheng 设备仓 | `e4efe95c903a737e0f5955e5b50a8fb4d2a7d718` | 同左 | `build-gop-legacy-display-27.py` 编译 `QcomDwc3.cpp`+`UsbProbe.cpp` 进 `libNativeLegacyDisplay.late.a`（`:597-656`） | `sheng_usb_probe()`（weak，`LegacyDisplayProbe.cpp:519`）；`sheng-usb=1` |
| `AppleKeyStoreState` | `https://github.com/UniXNU/AppleKeyStoreState.git` | 框架 | `42ff83e08b2265fe741d4adaf084bebe003452ba` | `8c70daf814aafdf4a3d35e40dde0322655fd0a83` | `component:AppleKeyStoreState` → `build/apple-key-store-state/libAppleKeyStoreState.a`（`components.toml:266-267`） | `native_keystore_probe()`（`LegacyDisplayProbe.cpp:513`）；`sheng-aks=1`/`sheng-aks-sls=3` |
| `RamBlock` | `https://github.com/UniXNU/RamBlock.git` | 框架 | `25c57e0e9b68bf452dd1986914525edc9d2320bc` | `4be2d7eb05ef5a98126c91e0302c149140c0e3e1` | `component:RamBlock` → `build/ram-block/libRamBlock.a`（`components.toml:288-289`） | `NativeRamBlock` personality / `native_ufs_store` 回调 |
| `VirtioMmioBlock` | `https://github.com/UniXNU/VirtioMmioBlock.git` | 框架 | `8ee3a5ab5a3726b0641990228346aec338246eaf` | `4e1013eb8c45077b57f8d38d61b389fe899ea1c3` | `component:VirtioMmioBlock` → `build/virtio-mmio-block/libVirtioMmioBlock.a`（`components.toml:310-311`） | VirtIO MMIO block 队列/中断初始化 |
| `VirtioMmioConsole` | `https://github.com/UniXNU/VirtioMmioConsole.git` | 框架 | `70253216890b2afcaa6333948726f896f84fc757` | 同左 | `component:VirtioMmioConsole` → `build/virtio-mmio-console/libVirtioMmioConsole.a`（`components.toml:332-333`） | VirtIO MMIO console 初始化 |
| `VerifiedRoot` | `https://github.com/UniXNU/VerifiedRoot.git` | 框架 | `def026642c6c6e71be0dea267d989df1d29ddc64` | `974f043d0c71ba2e60331483a41c6c6d35274ee3` | kit，由 storage recipe 编译；sheng 的 `[payload] root_policies` 指向 `build/sheng-source-storage/root-policies.bin`（`UniXNU-sheng/board.toml:60`） | storage policy 验证入口 |
| `XnuPrelink` | `https://github.com/UniXNU/XnuPrelink.git` | 框架 | `f876e3ee62e18fc06653dd75ed7dafcfb3950ac0` | `c645d76bb0ab8c506a76840ddf93a2276d419a0e` | `./unixnu build prelink`；工具 `kits/XnuPrelink/emit_prelink.py`（`docs/drivers/xnu-prelink.md:9-14`） | prelink 阶段，绑定 kernelcache roots/slide/ABI |
| `DarwinBoot` | `https://github.com/UniXNU/DarwinBoot.git` | 框架 | `3325e352d7df68a9f9ad74832ed94a6acbbd7390` | `3c75734014cdab0acd9541e88057b7606ee7ae08` | 固件 INF，`./unixnu build firmware`（`docs/drivers/darwin-boot.md:19-21`） | loader protocol，handoff kernel/ADT/trust cache/ramdisk |
| `SoftwareAES` | `https://github.com/UniXNU/SoftwareAES.git` | 框架 | `4a45326da5c2cd6fe6813d79ee43db20805628af` | 同左 | `component:SoftwareAES` + `build-software-aes-bindings.py` → `build/software-aes/libSoftwareAES.a`（`components.toml:244-245`） | `NativeAES` personality / IOAESAccelerator |
| `ShengPreflight` | `https://github.com/UniXNU/ShengPreflight.git` | sheng 设备仓 | `9cfc8d2c8d77f2008ba228fa6eff83d2c7ab7fd2` | 同左 | `build_stage="firmware"`；`docs/drivers/sheng-preflight.md:15-17`（无独立 archive） | UEFI preflight checks |

> **Pin 冲突警告：** 上表“框架/设备仓 gitlink pin”是 `.gitmodules` 的 `git ls-tree` 实值；“`components.toml` revision”是目录登记值。两者在 `ArmCpu`、`Adreno740`、`AdrenoMetal`、`GopFramebuffer`、`AppleKeyStoreState`、`RamBlock`、`DarwinBoot`、`ArmSmmu4K`、`XnuPrelink`、`VerifiedRoot`、`ShengUfs`、`VirtioMmioBlock` 等 12 个组件上不一致；发布前必须确认以哪个为准（见 ⑥）。

### 3.3 不在 component catalog 的官方参考实现

| 功能 | 官方参考文件/仓库 | 文档依据 | 说明 |
| --- | --- | --- | --- |
| 背光 | `UniXNU-sheng/package/AppleARMBacklight.cpp`、`GeniI2c.h` | `docs/drivers/sheng-backlight.md:5`、`docs/porting/display.md:20` | KTZ8866 I2C 示例；无 catalog ID |
| 实体键 | `UniXNU-sheng/package/ButtonProbe.cpp`、`BootResetCore.h` | `docs/porting/input.md:21,84-97` | 板级代码，无组件 |
| 音频/DSP | `UniXNU-sheng/package/AudioProbe.cpp`、`ShengAudioReach.c/h`、`ShengGpr.c/h`、`ShengAudioService.cpp`、`ShengAudioPlugIn.c`、`ShengCs35l43.c`、`AdspProbe.cpp`、`ShengAdsp.h` | `docs/porting/power.md:28-30,53-64` | 板级代码，无组件 |
| 电池/电源 | `UniXNU-sheng/package/ShengBattmgr.c/h`、`ShengBattery.cpp`、`BatteryProbe.cpp`、`CpuFreqProbe.cpp`、`QcomRpmh.h`、`ShengPlatformPower.cpp`、`GpuPowerProbe.cpp` | `docs/porting/power.md:143-151,183-188` | 板级代码，无组件 |
| 显示时序 | `UniXNU-sheng/package/DisplayTimingProbe.cpp` | `docs/porting/display.md:21,75-85` | DPU/DSI timing probe；无组件 |

**板级参考实现的 build integration（均无 catalog ID，由显示 recipe 编入同一个 late archive）：**

| 功能 | 编译脚本 | archive | 初始化调用点 / 参数 |
| --- | --- | --- | --- |
| 背光 | `build-gop-legacy-display.py`（iOS17）/ `build-gop-legacy-display-27.py`（iOS27） | `build/native-legacy-display/libNativeLegacyDisplay.late.a`（`build-gop-legacy-display.py:13,316`） | `sheng_backlight_probe()`（`LegacyDisplayProbe.cpp:524`）；`sheng-backlight=1` |
| 实体键 | 同上 | 同上（`build-gop-legacy-display.py:271,327`） | `sheng_buttons_probe()`（`LegacyDisplayProbe.cpp:523`）；`sheng-buttons=1` |
| 音频 | 同上；`build-sheng-audio-hal.py` 另编用户态 HAL | 同上（`build-gop-legacy-display.py:269-270,327`） | `sheng_audio_probe()`（`LegacyDisplayProbe.cpp:522`）；`sheng-adsp=2`、`sheng-audio=12` |
| DSP | 同上 | 同上（`build-gop-legacy-display.py:265-268,327`） | `sheng_adsp_probe()`（`LegacyDisplayProbe.cpp:520`）；`sheng-adsp=2` |
| 电池 | 同上 | 同上（`build-gop-legacy-display.py:278-281,327`） | `sheng_battery_probe()`（`LegacyDisplayProbe.cpp:521`） |
| CPU 频率/GPU 电源 | 同上 | 同上（`build-gop-legacy-display.py:256-257,327`）；`build-sheng-platform-power.py`（平台电源） | `sheng_cpufreq_probe()`/`sheng_gpu_power_probe()`（`LegacyDisplayProbe.cpp:514-515`）；`sheng-cpufreq=4`、`sheng-gpu-power=9` |
| 显示时序 | 同上 | 同上（`build-gop-legacy-display.py:273,327`） | `sheng_dpu_probe()`（`LegacyDisplayProbe.cpp:525`）；`sheng-dpu=1`、`sheng-vsync=120` |

## ④ 五个 K60 具体问题的回答

### ④a K60 Goodix 触摸：官方哪些总线层可复用、哪些协议层必须新写

**结论：总线和 HID 层可复用，协议和传感器层必须新写；Novatek 的 40×60 处理核心完全不能用于 Goodix。**

| 层 | 官方文件 | 对 K60 的处理 |
|---|---|---|
| GENI SPI 控制器 | `docs/drivers/qcom-geni-spi.md` → `QcomGeniSpi/GeniSpi.c` | **复用**。`GeniSpi.c` 只依赖调用方给的寄存器访问/平台回调；K60 换 SE4 `0x990000/0x4000`、SPI CS0、15 MHz（首次 4 MHz）、GPIO16/17/18/19 的 `qup4` mux。 |
| `nvt_bus` 接口形状 | `docs/drivers/sheng-novatek-touch.md`（`struct nvt_bus { xfer, delay }`） | **复用接口模式**，但把实现换成 Goodix：一次全双工 xfer、CS 保持、caller-owned buffer、超时/重试。 |
| 芯片识别 / 固件 / 帧协议 | `NvtProtocol.c`、`NvtProtocol.h` | **必须新写 Goodix 协议**。K60 DT 的 `goodix_firmware_m11a`/`goodix_cfg_group_m11a` 暗示 Berlin 系，但 0242 同时实现了 Berlin（`0xf1` 地址 + `0xff` 读）与 GT9xx（`0x8140/0x814e/0x8150`）两套；真机尚未回 ID。 |
| 触点处理核心 | `NvtTouchCore.c`（40×60 matrix → blob → tracking） | **不能复用**。Goodix 的 report 格式/矩阵/固件完全不同；需要按 Goodix Berlin/GT9xx 的 report 格式重写触点解析/跟踪，不能把 NVT 40×60 逻辑硬套。 |
| 板级常量 / 时钟 / 引脚 | `TouchBoard.h`、`TouchProbe.cpp` | **复用框架，换值**：`spi-base=0x990000`、`tlmm-base=0x0f000000`（+`gpio-offset=0x100000` = `0x0f100000`）、`gcc-base=0x100000`、`rsc-base=0x17a20000`（drv-2；但 K60 RSC 首读会死，见未核实）、`cmd-db-base=0x80860000`、pins `<16 17 18 19 21 20>`、max-x/max-y `14400/32000`（raw）。 |
| HID 发布 | `ShengHidInput/NativeHidInput.cpp`（IOHIDFamily 2031.120.4） | **可复用结构，ABI 需重对**：K60 20G81 的 IOHIDFamily 版本/selector 必须从本机 kernelcache 重新提取；`native_touch_seq` 快照协议可保留。 |
| 物理按键 | `ButtonProbe.cpp` + `BootResetCore.h` | **参考**：K60 的 Power/Vol +/- 走 PMIC/GPIO，需按 K60 FDT 重填 PON/GPIO；官方 sheng report 2 的位定义可复用。 |

**关键边界：**`porting/input.md` 第 22 行明确写“For a different sensor, implement its identification, firmware and report protocol. For a different bus controller, implement the transfer/delay callbacks used by `nvt_bus` when reusing the Novatek protocol.” 这句话反过来就是 K60 的答案：**传感器不同 → 协议全写；总线相同（GENI SPI）→ 只换板级回调**。

### ④b 音频功放：AudioProbe/AdspProbe 是否覆盖 AW882xx，还是只覆盖 TFA9873

**结论：两者都不覆盖 AW882xx；官方 `power.md` 的 AudioProbe 实际覆盖的是 sheng 的 WCD938x + 6×CS35L43，TFA9873 根本不是官方 16 项文档里的器件。**

| 层 | 官方 `porting/power.md` 实际内容 | 对 K60 AW882xx 的覆盖 |
|---|---|---|
| ADSP transport | `AdspProbe.cpp`：PAS 固件、SMEM、SMP2P、GLINK、mailbox、`ShengAdspClient`、`sheng_adsp_channel` | **可复用（约 80–90%）**：K60 ADSP `0x03000000`、region `0x9fd00000/0x3100000`、SMEM `0x80900000/0x200000`、IPCC `0xed18000/IRQ261`、GPR `adsp_apps` 与 sheng/pong 同构。 |
| AudioReach graph | `ShengGpr.h`、`ShengAudioReach.h`、`AudioProbe.cpp`：APM readiness、graph open/config、PRM votes、period buffer、`q6apm` 参考 | **可复用（约 70%）**：GPR 参数/图生命周期可抄；K60 需改 ADSP 固件路径、SM8475 图参数、TDM 1.536 MHz/双 data line。 |
| Codec | `AudioProbe.cpp` 参考 sheng 的 WCD938x（reset gpio108、ldob15、SoundWire TX master `0x6d30000`） | **K60 同为 WCD938x**：可高比例复用；K60 的 `va/tx/rx-macro` 正常、`wsa-macro`/`wsa2-macro` disabled（`wsa-max-devs=0`）。 |
| 功放 | `ShengCs35l43.c`：sheng 的 **6×CS35L43**，I2C | **0% 覆盖**。K60 是 **2×AW882xx @ I2C 0x34/0x35**（SE15 `0x880000`、GPIO56/57、reset GPIO1/3、IRQ GPIO88/63、spksw GPIO52、sound-channel 0/1、`aw-cali-mode="aw_none"`）。官方文档没有任何 AW882xx 寄存器/初始化/校准信息。 |
| TFA9873 | **官方 16 项文档全篇 0 命中**；TFA9873 只在 pong 的 `PongAudio.cpp` 中出现（I2C `0xa94000`、GPIO48/49、reset 1/89、revision `0x0b73`） | **0% 覆盖，且不能混用**。TFA9873 是 pong（Nothing Phone 2）器件；K60 FDT 全 compatible 扫描无 `tfa,tfa98xx`。不要因为两者都可能用 I2C 0x34/0x35 就按 TFA 写死；第一步必须读 chip ID/revision。 |
| 用户态 HAL | `ShengAudioService.cpp` / `ShengAudioPlugIn.c`（sheng 的 AudioServerPlugIn） | **可复用骨架**：`AudioServerPlugIn` API 在 iOS 16/17 稳定；K60 20G81 的 MediaExperience selector 需重定位（pong 的 22H374 地址不能直接抄）。 |

**因此 b) 的准确回答是：**`AudioProbe` 不是 AW882xx 驱动，也不是 TFA9873 驱动；它只是“ADSP AudioReach + WCD938x + CS35L43”的 sheng 示例。K60 要做的是 **保留 AdspProbe/AudioReach 的传输与图框架，新增 AW882xx 功放驱动（I2C 0x34/0x35）和 K60 TDM 1.536 MHz/双数据线配置**；TFA9873 只能作为 pong 参考，不能当 K60 硬件事实。

### ④c platform.md 对内存窗口/DarwinBoot 的约束，是否支持多区间 arena

**结论：官方 `porting/platform.md` 只支持“单一连续 handoff RAM range”，不支持多区间 arena；8 GiB 单窗口可以做，9.97 GiB 多区间不在官方 16 项文档的模型内。**

| 问题 | 官方原文/约束 | 对 K60 的含义 |
|---|---|---|
| DTS `/memory` | `porting/device-repository.md`：format 2 要求 `payload.dram_size` 与硬件 DTS 的 `/memory` 节点一致；`devicetree.py` 要求**恰好一个 memory 节点、恰好一组 reg**（本仓脚本行为，官方文档对应“single contiguous DRAM range”）。 | K60 若把 `dram_size` 写成 12 GiB（`0x300000000`），必须同时把 DTS 改成 `memory@80000000` 单组 reg；但这只是 ADT 元数据，不是 XNU 窗口。 |
| DarwinBoot 窗口 | `porting/platform.md` 只说“the loader's owned-memory request has its own size and alignment constraints. Keep both consistent with the actual UEFI memory map.” 官方页没有给 8 GiB 数字。 | K60 本地 `drivers/DarwinBoot22/DarwinBootPkg/Driver/WindowSize.h` 才定义 `size <= 0x200000000`（8 GiB）；`devicetree.py` 也只接受 256 MiB–8 GiB。8 GiB 单窗口是本地实现硬顶，不是官方文档承诺。 |
| 多区间 arena | 官方没有任何 `pmap_memory_regions` / 多段物理内存的说明；`four-k-page-tables.md` 只讨论 4K 页表与 bootstrap 表池（“Two roots plus up to seven L2 pages per 6 GiB mapping”）。 | K60 要让 XNU 管理低区 434.9 MiB + 高区 9774.5 MiB（约 9.97 GiB），必须给 arm64 加 pmap/vm_page 多区间支持；这是内核子系统改造，不是官方 16 项文档里的任何组件或配置能解决的。 |
| 8 GiB 单窗口 | 官方 `platform.md` 的“contiguous”模型 + 本地 `WindowSize.h` 8 GiB 上限 + K60 最长连续段 `[0x840000000,0xA69B78000)` 8.652 GiB（扣 DXE/内核基址偏移 0x20000 后对齐 8 GiB）。 | **可行**：`owned_memory_size = 0x200000000`（8 GiB），arena 至少 `0x200020000`；实际用 `0x840000000 + 0x229B78000` 的 8.652 GiB arena，并把顶部 `0xA69B78000..0xA80000000` 设为 MEM_RES。MEMORY-12G-PLAN 的阶梯（6/7/8 GiB）按此执行。 |
| 9.97 GiB 多区间 | 官方无支持；XNU arm64 当前只读一个 `{physBase, memSize}`。 | **不可直接做**：需要新增多区间 pmap/vm_page/physmap 补丁，并逐段挖掉 modem/ADSP/camera/HYP/UEFI/DXE 保留；不属于本 16 项文档范围。 |

**建议取舍：**先把 8 GiB 单窗口跑通（这是官方 contiguous 模型内、也是 DarwinBoot 硬顶），把 9.97 GiB 多区间列为独立的内核项目；不要为了“12 GiB 装机”把 12 GiB 写进 `owned_memory_size`（解析器和 `AllocateWindow()` 都会拒绝）。

### ④d boot-args 长度上限、4K 页表要求、patch 顺序要求

| 约束 | 官方规定 | K60 当前状态 / 结论 |
|---|---|---|
| boot-args 长度 | `docs/xnu/boot-arguments.md`：拼接后的命令行 **at most 1000 bytes**；DarwinBoot 复制进 **1024-byte buffer**。每个参数匹配 `[A-Za-z0-9_.-]+(=[A-Za-z0-9_.,-]+)?`。 | 你给的 **581 字符** < 1000，余量 **419 bytes**；格式上安全。注意 `board.toml` 的 `kernel_args` 单独只有 9 个 token、169 字符；581 应是 `[build] kernel_args` / local override 合并后的 effective line，最终以 `./unixnu payload` 打印的 `kernel args:` 与 payload.json 为准。 |
| 参数合并顺序 | `[payload] kernel_args`（board）→ `[build] kernel_args`（unixnu.local.toml）→ `--kernel-arg` 覆盖；同名后者替换前者。 | 新增 K60 驱动参数应写进 `[payload] kernel_args` 默认值，调试用 `--kernel-arg` 一次性覆盖；不要把临时参数写死在脚本。 |
| 4K 页表 | `docs/xnu/four-k-page-tables.md`：XNU 必须编译为 **BCM2837** machine config（`ARM_PGSHIFT=12`、`ARM_PGBYTES=4096`、`TCR_EL1_BOOT` TG0=0、TG1=2）；补丁至少 `native-4k-bootstrap-capacity`、`native-4k-user-abi`、`native-4k-signature-hash-cache`、`pgz-aligned-validation`、`zzx-pmap-sync-64bit-pa`；SMMU 用 `ArmSmmu4K` 4 KiB 表；新代码用 `PAGE_SIZE`/`ARM_PGSHIFT`，DMA 按 `PAGE_SIZE` 对齐。 | K60 profile 已是 `MACHINE_CONFIGS=PONG`（20G81 机器配置，4K 语义）；`CONFIG_XNU_NATIVE_CS_HASH_CACHE=y` 已在 `mondrian_defconfig`。8 GiB 窗口的 bootstrap 表池需满足“每 6 GiB 映射”预算；8.652 GiB arena 必须用 `native-4k-bootstrap-capacity` 的扩展池，不要用默认 16 KiB 假设。 |
| patch 顺序 | `docs/xnu/patch-reference.md`：format 2 按 `[kernel] patch_series` **声明顺序**应用；依赖补丁排在被依赖之后；碰 `zzy`/`zzz` 区域的补丁排在它们之前；`unixnu status --json` 打印 resolved sequence。format 1 按 `patches/xnu/*.patch` / `kits/XnuPrelink/patches/*.patch` 文件名字典序。 | K60 当前是 format 2 `patch_series = ["device:patches/xnu/series"]`（129 条），`status --json` 应报告 129 条有序补丁；不要用 pong 的 glob 字母序直接套（会先跑 0210 而目标文件还没被 UI foundation 创建）。新增 K60 补丁必须插在 `zzy`/`zzz` 之前。 |
| 源码 pin | `docs/xnu/source-and-patches.md`：17.7.11 用 `xnu-10063.141.1`，iOS 16 与 iPadOS 17 共享 arm64 patch series；27 用 arm64e series。 | K60 是 `xnu-8796.141.3`/Darwin22.6；不要拿 10063 的补丁直接套。`profiles/os/ipados-16.6.1-20G81/profile.toml` 已 pin `1b191cb58250d0705d8a51287127505aa4bc0789`。 |

### ④e 每一项对 iOS 16.6.1/20G81 的适用性汇总

| 项 | 20G81 适用性 | 理由（简） |
|---:|---|---|
| 1 适配顺序 | ✅ | 纯流程，无 OS ABI。 |
| 2 平台与内存 | ✅ | CPU/GIC/内存/DMA 流程与 OS 版本无关；K60 值需换。 |
| 3 UFS | ◐ | 流程适用；`ShengUfs` SM8550 组件不适用，K60 用 PongUfs。 |
| 4 显示与亮度 | ◐ | GOP/软件 framebuffer 模型适用；24A446 DSI adapter 不适用 20G81。 |
| 5 亮度驱动 | ✗ | K60 无 KTZ8866，背光走 DCS 0x51；官方驱动硬件不适用。 |
| 6 触控与按键 | ◐ | `QcomGeniSpi` 总线层可用；Goodix 协议新写，HID ABI 重对。 |
| 7 GPU 与 Metal | ✗ | 官方 A740 组件不适用 A730v3；用 PongAdreno。 |
| 8 Wi-Fi | ✗ | 官方 ath12k/WCN7850 不适用 QCA6490 ath11k；用 PongWifi。 |
| 9 蓝牙 | ✗ | 20G81 无 IOBluetoothFamily；官方 iPadOS27 BlueTool 路线不适用。 |
| 10 蓝牙驱动 | ✗ | 同 9；QcaBluetooth 只覆盖 WCN7850/iPadOS27。 |
| 11 USB | ◐ | DWC3/eUSB2 硬件流程参考；24A446 ABI 不适用 20G81。 |
| 12 USB 驱动 | ◐ | QcomDwc3 仅 24A446；community NativeDwc3 是 SM8150，无结果。 |
| 13 基带 | ✗ | 官方 SC7180/IPA4.2 与 K60 集成 SM8475 modem 不同类；iPad7,1 可 skip。 |
| 14 DSP/音频/电源 | ◐ | ADSP/AudioReach 框架可用；AW882xx 功放必须新写。 |
| 15 开发驱动 | ✅ | built-in XNU 方法完全适用；kext bundle 路线不适用 shipped DarwinBoot。 |
| 16 修改 XNU | ◐ | boot-args/4K/patch order 规则适用；源码 pin/补丁集按 20G81 重排。 |

> 逐组件版本明细见附录 B；该表保留官方 catalog 的 `os_abi` 与文档正文的对照，是 ④e 的证据底稿。

## ⑤ 与 pong 方案的差异与取舍

### 5.1 官方规范 vs pong ios16（流程层）

| 维度 | 官方 UniXNU 规范 | pong ios16 先例 | 对 K60 的含义 |
| --- | --- | --- | --- |
| 设备仓格式 | format 2：`schema_version=2`、`[components] include`、`[kernel] archives`、`[os_overrides]`（`docs/reference/configuration.md:3-5,44-59`；`docs/porting/packaging.md:3-24`） | 54 行 `board.toml`，无 `schema_version`/`[components]`/`[userdata]`/`windows`（`K60:docs/audits/PONG16-DIFF-AUDIT.md:10-16`；`git show FETCH_HEAD:board.toml`） | K60 已是 format 2，应继续用官方壳；不要退回 pong 的扁平 `board.toml` |
| 组件选择 | `components.toml` 目录 + `[components] include`，解析器按依赖排序（`docs/reference/components.md:3-13,46-57`） | drivers 以 git submodule/目录 vendored，无 catalog 选择（`K60:docs/audits/PONG16-DIFF-AUDIT.md:198-213`） | K60 目前只选 `ArmDTPlatform/ArmCpu/XnuPrelink/PongUfs`（`board.toml:14`）；其余 pong 驱动要逐步登记为组件或设备本地模块 |
| 补丁应用 | `[kernel] patch_series` 有序 series，`scripts/package.sh` 解析（`docs/porting/packaging.md:33-37`） | `patches/xnu/*.patch` 字母序 glob（`K60:docs/audits/PONG16-DIFF-AUDIT.md:12,32-40`） | K60 已用 series（129 条）；不要启用 pong 的 glob 路径 |
| 构建入口 | `scripts/package.sh --os 17` / `--os 27` / `--os PROFILE`，唯一脚本模板（`docs/porting/packaging.md:3-24,41-53`） | 自定义 `build-ios16-pong-macos.py` / `build-pong-prelinked-boot.py` / `build-userdata.py`（pong README「构建」节） | K60 可以保留自定义 16.6.1 预构建脚本作为过渡，但发布路径应接到 `scripts/package.sh` 的 `--os PROFILE` |
| OS profile | `profiles/os/ipados-17.7.11-21H461`、`ipados-27.0.1-24A446`；`[os_overrides]` 管理差异（`docs/porting/packaging.md:84-98`） | 自带 `os-profiles/`，iOS 16.6.1/20G81；无官方 16.6.1 profile 支持声明（`K60:docs/audits/PONG16-DIFF-AUDIT.md:5-8`；`UniXNU/profiles/os/ipados-16.6.1-20G81` 存在但文档未提） | K60 的 16.6.1 profile 是设备仓核心资产；官方组件迁移必须在此 profile 上重新验证 |
| 记录 | `porting.toml` 每个 area 有 inputs/configuration/procedure/findings/limits/next_action/evidence（`docs/porting/records.md:15-35,41-59`） | pong ios16 **没有 `porting.toml`**（`K60:docs/audits/PONG16-DIFF-AUDIT.md:15`） | K60 已有 13 个 area 的 `porting.toml`，继续按官方记录规范维护 |
| 输出 | `out/<device>/<os_profile>/<config>/`，manifest 记录 revision/大小/SHA-256（`docs/porting/packaging.md:100-117`） | 自定义输出目录（pong README 脚本参数） | K60 统一输出路径，便于与官方文档对齐 |

### 5.2 子系统取舍

| 子系统 | 官方推荐 | K60 现方案/最接近先例 | 取舍建议 |
| --- | --- | --- | --- |
| CPU/中断/内存 | ArmDTPlatform + ArmCpu + ArmSmmu4K | pong ArmCpu/ArmDTPlatform（同码）；K60 DTS/ADT 已有 | **保留 pong 驱动 + 官方 DTS/ADT 契约**；`ArmSmmu4K` 可直接引入做 GPU/display kit；16.6.1 first-boot 不换 ArmCpu |
| UFS | ShengUfs（SM8550） | PongUfs（SM8475，`components.toml:551-560`） | **保留 PongUfs**；把 SM8475 常量整理成 ShengUfs 的 SoC 后端是长期方向，不是本次切换 |
| 显示 | GopFramebuffer（iOS17/27） | MiniIOMobileFramebuffer + CPU 软件呈现（K60 0210/0211/0213） | **保留 K60 显示栈**；GopFramebuffer 仅在 K60 迁到 17/27 时替换；现在换会引入 ABI 断点 |
| 背光 | AppleARMBacklight 示例（KTZ8866 I2C） | K60 面板 DCS `0x51` 调光，无背光 IC | **复用 OS 服务契约，重写 DSI-command 传输**；不要照抄 KTZ8866 寄存器 |
| 触摸 | QcomGeniSpi + ShengNovatekTouch + ShengHidInput | K60 Goodix/xiaomi,m11a-spi；pong `pong_goodix.c` | **QcomGeniSpi + ShengHidInput 复用；ShengNovatekTouch 不用；Goodix 协议层用 pong/K60 0242** |
| 实体键 | ButtonProbe.cpp（板级参考） | pong `pong-physical-keys.patch`；K60 无 XNU 驱动 | **新写 K60 按钮驱动**（UEFI 参数为源）；无官方组件可换 |
| GPU/Metal | Adreno740 + AdrenoMetal + Sm8550Platform（A740/SM8550） | PongAdreno + PongMetal（A730/SM8475） | **保留 pong GPU 栈**；官方 A740 栈不适用；可复用 AdrenoFirmware/AdrenoPM4/AirNir/ArmSmmu4K kit |
| WiFi | Ath12kWifi（WCN7850） | PongWifi（QCA6490/ath11k，pong main） | **移植 PongWifi**；Ath12kWifi 不适用；K60 计划已如此选择（`K60:docs/plans/WIFI-PORT-PLAN.md:13`） |
| 蓝牙 | QcaBluetooth（WCN7850 UART） | pong 无 BT 驱动；K60 零先例 | **以 QcaBluetooth 的 qbt/GENI 框架为骨架新写 QCA6490 驱动**；不能直接选官方组件 |
| 音频 | AudioProbe/ShengAudioReach/ShengGpr（CS35L43/WCD938x） | pong main 的 PongAudio（TFA9873）；K60 AW882xx | **复用 AudioReach/GPR 框架；新写 AW882xx 功放与 K60 TDM 路由**；官方/ pong 功放都不能直接跑 |
| DSP/电源/电池 | AdspProbe/ShengBattmgr/ShengBattery/ShengPlatformPower（SM8550） | pong main 的 PongPower（SM8475）；pong ios16 无 | **从 pong main 移植 PongPower 并改 ADSP carveout/PMIC**；官方 sheng 只作参考 |
| USB | QcomDwc3（iOS27/24A446） | pong ios16 无 USB 栈；K60 自定义 DWC3/usblog | **16.6.1 继续自定义 DWC3/usblog**；QcomDwc3 等迁到 27 或完成 16.6.1 ABI 审计后再换 |

### 5.3 建议路线

1. **短期（16.6.1 主线）：** 保留 pong 设备驱动（PongUfs、PongAdreno/PongMetal、Goodix、PongWifi、PongPower、自定义 DWC3），把 `board.toml`/`porting.toml`/构建输出按官方 format 2 收紧；只引入无 ABI 风险的 `ArmSmmu4K`、`QcomGeniSpi`、`ShengHidInput` 接口层。
2. **中期（接口对齐）：** 把 K60 DTS/ADT 按 `docs/porting/device-tree.md` 和 `docs/porting/platform.md` 补齐（`/chosen` NVRAM、`/cpus` cluster-type、`/buttons`、`/arm-io` ranges、`dma-coherent`、`iommus`）；为 PongUfs/PongAdreno/PongWifi/PongPower 写 `porting.toml` 记录和 host check。
3. **长期（官方化）：** 官方补齐 SM8475/A730/QCA6490/AW882xx 后，按 `docs/reference/components.md` 的 catalog 流程注册为正式组件；在此之前不要为了“用官方组件”而替换任何已验证的 pong 驱动。

## ⑥ 未核实项

1. **`docs/reference/components` 目录不存在。** 任务书写的该目录没有 md；只有 `docs/reference/components.md`（85 行）。本清单以 `components.md` + `docs/drivers/repositories.md` + `components.toml` 为准。
2. **`components.toml` 与 `.gitmodules` 的 12 个 pin 不一致：** `ArmCpu`（catalog `93a5030…` vs gitlink `9066b53…`）、`Adreno740`（`6fa7bae…` vs `5c8c145…`）、`AdrenoMetal`（`6d7f734…` vs `ce5e19e…`）、`GopFramebuffer`（`e47c1b8…` vs `33e941a…`）、`AppleKeyStoreState`（`8c70daf…` vs `42ff83e…`）、`RamBlock`（`4be2d7e…` vs `25c57e0…`）、`DarwinBoot`（`3c75734…` vs `3325e35…`）、`ArmSmmu4K`（`83969cd…` vs `3ba9245…`）、`XnuPrelink`（`c645d76…` vs `f876e3e…`）、`VerifiedRoot`（`974f043…` vs `def0266…`）、`ShengUfs`（`99d8bcd…` vs `af14068…`）、`VirtioMmioBlock`（`4e1013e…` vs `8ee3a5a…`）。哪个是发布基线未核实；引用 pin 时要同时给出两套值。
3. **官方文档对 16.6.1/20G81 零声明：** `drivers/`、`porting/`、`reference/` 全文检索无命中；K60 的 16.6.1 profile 只证明配置层可选，不代表任何驱动/ABI 已在 20G81 上验证。
4. **K60 硬件值来源等级：** 本清单的 K60 地址/GPIO/固件名大多来自本地计划文档和 live FDT 记录，不是官方文档；其中 `QCA6490 BT` 固件 `htbtfw21.tlv`/`htnv21.bin`、AW882xx 寄存器表/awini 校准、Goodix 具体型号（Berlin vs GT9xx）均标为未核实（`K60:docs/plans/BT-AUDIO-PORT-PLAN.md:97-101,414,499-500`、`K60:docs/plans/K60-TOUCH-PARAMS.md:250-255`）。
5. **K60 USB 的 SMMU stream：** 本地记录为 `0x0`（`K60:docs/reference/ISSUES.md:195`），官方 QcomDwc3 sheng 参考为 `0x40`（`docs/porting/usb.md:31`）；K60 实际 stream/context 需以设备 DTS/实测为准，未核实。
6. **K60 背光：** “无独立背光 IC、DCS `0x51`”来自本地 FDT/上机笔记（`K60:docs/reference/FEATURES-DRIVERS-RESEARCH-2026-10-31.md:106-108`）；官方文档只描述 KTZ8866 I2C 示例。DCS 的亮度位宽/量程（0xFF vs 0..2047）需按 m11a panel 文档再核。
7. **pong main 与 pong ios16 的驱动范围不同：** pong ios16 只有 `ArmCpu/ArmDTPlatform/DarwinBoot22/NativeMetal/NativeRamBlock/NativeUfs/PongAdreno/PongMetal` 8 个 driver 目录（`git ls-tree FETCH_HEAD:drivers`）；`PongWifi/PongPower/PongUsb/PongBt` 只在 pong main（22H374）或未实现。K60 的 WiFi/音频/电源计划引用 pong main，不是 ios16；这些代码的 Darwin24 ABI 不能直接用于 16.6.1。
8. **官方 `Sm8550Platform` 无 SM8475 等价物：** catalog 只有 SM8550 kit（`components.toml:454-470`）；K60 A730 的 GMU/GPU SMMU/RPMh 命令库需要自建（或从 pong PongPlatform 移植），不能选 `Sm8550Platform`。
9. **`GopFramebuffer` 的 iOS 16.6.1 ABI 构建器不存在：** `build-gop-legacy-display.py` 在 `ARCH != 'arm64' or IOS_VERSION major != 17` 时直接 `SystemExit`（`:10-12`）；`-27.py` 只接受 arm64e iPadOS27（`:17-18`）。K60 若换 GopFramebuffer，必须先写 16.6.1 的 LegacyDisplay ABI JSON/构建器，未核实可行性。
10. **官方组件版本目录 vs 文档：** `Adreno740`/`AdrenoMetal` catalog `os_abi` 只写 17.7.11（`components.toml:87,109`），但文档给出 iOS27 构建命令（`adreno740.md:26`、`adreno-metal.md:40`、`gpu.md:144-150`）；`GopFramebuffer` catalog 写 17+27（`components.toml:215`），文档构建器只覆盖 17/27。catalog 元数据可能滞后于文档，选型时以文档 + 实测 ABI 为准。
11. **官方 `ShengUfs`/`ShengNovatekTouch`/`GopFramebuffer` 的 `verified_devices` 只有 sheng（`components.toml:132,175,217`），没有 K60/SM8475 记录；任何“可复用”判断都是接口层推断，不是硬件验证结论。**
12. **基带未列入本任务范围：** K60 是带 modem 的手机，但本任务清单未包含 cellular；官方 `QcomBaseband` 只提供 SC7180/IPA v4.2/iOS 17 的 Coachz 参考（`docs/porting/baseband.md:5`），K60 的 modem 型号、EFS/NV、QRTR/QMI、IPA 版本均未核实，后续需要单独评估。
13. **`ShengBacklight` 没有独立组件仓库：** 它是 `UniXNU-sheng/package/AppleARMBacklight.cpp` 的板级代码，不在 `components.toml` 的 `id` 列表中；引用它时只能按“官方参考实现”处理，不能当作可选择的 catalog 组件。

### 6.1 本次 LIVE 通读新增未核实项

| # | 项 | 现状 | 闭合方式 |
|---:|---|---|---|
| N1 | 官方页面 LIVE 与本地存档差异 | 本次 16 项 39 页全部用 LIVE；`porting/drivers.md` 等页面在 2026-11-08 已比 2026-11-04 存档新；本文件部分旧表引用的仍是本地 `E:/hackios/UniXNU/docs` 快照（2026-10-29） | 每次改动前用 `query.py --live` 重抓；引用行号以本地快照为准，结论以 LIVE 为准 |
| N2 | K60 Goodix 具体型号/ABI（Berlin vs GT9xx） | DT 只有 `xiaomi,m11a-spi` / `goodix_firmware_m11a`；0242 双 ABI 均未在真机读到 ID | stage 4 `k60touchstage=4 k60rpmhoff=1` 读 `0x10014`/`0x8140`，看 `abi berlin` 或 `abi gt9xx` |
| N3 | K60 RSC/TCS `0x17a00000/0x17a20000` 可达性 | 0240 称 drv-2 可读、0246 称首读 TCS 整机死；根因未定（XPU/电源域/互连） | 只用 0248 只读探针；先确认 XPU/电源域，不写 TCS |
| N4 | K60 IOVDD（pm8350c ldoc2）冷启动状态 | `k60rpmhoff=1` 时假设 bootloader/Android 已开 ldo2；冷启动是否成立未知 | Android 热重启进 fastboot 再 boot，对比冷启动 ID 结果 |
| N5 | K60 UFS 冷初始化/gear/PHY 状态 | PongUfs 走 firmware-state adoption；K60 冷启动时 PHY/clock 是否仍由 ABL 配置未逐项核实 | 第一轮 UFS 日志读 HCE/HCS、link state、request-list base；按 `porting/ufs.md` 的 inventory 记录 |
| N6 | K60 DSI 真通路（DSI0 `0xae94000`）与面板上电时序 | 当前只有 GOP 软件 framebuffer；120Hz 计划只确定 DSI0 基址和部分寄存器 | 先做 DSI host/PHY/PLL 驱动；`120HZ-PORT-PLAN.md` 的路径 B 需补全 m11a 的 52 字节 DCS payload |
| N7 | K60 背光 DCS 0x51 的完整序列/范围 | 上机笔记只写 `0x11`→`0x29`→`0x51`；亮度范围/斜率未测 | 在 DSI 通路打通后，逐级写 0x51 并读回/目测；记录到 display record |
| N8 | K60 GPU SID 路由 / GMU 固件 / ZAP | `PongAdreno` 只接受 exact 5/0x405 GMU 和 0/0x400/1/0x401 GPU 路由；K60 实际 SMR/S2CR 未核实 | 第一轮 `GPU SMMU actual IDs` + `SKIP ASID lease conflicts` 日志定标；ZAP 用 K60 签名镜像 |
| N9 | K60 WiFi 固件清单/分区路径/子系统 device ID | `amss.bin`/`m3.bin`/`firmware-2.bin`/`board-2.bin` 为 WCN6855 hw2.1 惯例；K60 `modem_a/b/image/qca6490` 未列；子系统 device 0x0108 未实读 | 只读挂载 `modem<slot>` 列目录；PCI config 读 subsystem ID；记录 `proprietary-files.txt` |
| N10 | Ath12kWifi 是否可加 ath11k 后端 | 官方组件只列 ath12k/QCC2072/QCN9274/WCN7850；K60 是 QCA6490/WCN6855 0x1103 | 拉取 Ath12kWifi 源码静态比对；若 WMI/QMI 差异大，直接用 PongWifi |
| N11 | K60 蓝牙固件文件名/波特率/BT_EN 极性 | `htbtfw21.tlv`/`htnv21.bin` 是 WCN6855 家族惯例；K60 分区未核实；初始 115200/运行 3.2M 未实测 | 列 `modem_a/b/image/qca6490`；上机 stage 2 读 GENI FW revision；示波器看 BT_EN |
| N12 | 20G81 是否有可用的 Apple 蓝牙栈 | kernelcache 字符串扫 `IOBluetoothFamily` 0 命中，只有 `AppleBluetooth`/BTReset；`IOSerialFamily` 存在 | 若要做 Apple `bluetoothd`，先补 IOBluetoothFamily 或证明其用户态可行；第一版走 btstack |
| N13 | K60 USB IRQ/SMMU stream/PHY rails | DWC3 `0xa600000`、eUSB2 `0x88e3000`、QMP `0x88e8000` 已定位；IRQ/stream/rail 未逐项核实 | 读 K60 FDT `usb` 节点 + GCC/GDSC；按 `porting/usb.md` inventory 填 |
| N14 | QcomDwc3 20G81 ABI | 官方脚本只生成 24A446 JSON；K60 20G81 类布局未提取 | 用 `scripts/gen-usb27-abi.py` 的同一方法从 20G81 kernelcache 生成；先验证 `AppleUSBXDCI` slot 179 |
| N15 | K60 集成 modem 的 IPA/GLINK 细节 | 官方 QcomBaseband 是 SC7180 IPA v4.2；K60 是 SM8475 IPA v5.1 WIP；EFS/FSG 分区未核实 | 若做 cellular，先按 `porting/baseband.md` 的 inventory 采集；第一版 `not-applicable` |
| N16 | AW882xx 寄存器表/awini 校准/reset 极性 | 本机无 AW882xx 源码/寄存器表/校准；DT 只给地址/GPIO/IRQ | 从 Xiaomi/LineageOS 内核拉 `aw882xx` 驱动与 `awini`；先读 chip ID/revision |
| N17 | 20G81 的 IOHIDFamily / GopFramebuffer / ShengHidInput ABI | 官方组件 `os_abi` 不列 20G81；`ShengHidInput` 记录 IOHIDFamily 2031.120.4 | 从 20G81 kernelcache 提取 IOHIDFamily 版本/selector；先在 QEMU/host 验证再上机 |
| N18 | 8 GiB 单窗口是否真能启动 | 7 GiB 曾被 loader 接受但 XNU 无输出（2026-11-02 的 7g 实验）；8 GiB 未测；4.75 GiB 已实测 `vm_page_bootstrap` 1,245,184 页 | 按 MEMORY-12G-PLAN 阶梯先 4.75→6→7→8 GiB，每轮只改 `owned_memory_size` 并保留回滚镜像 |
| N19 | 当前 boot-args 581 字符的构成 | `board.toml` 的 `kernel_args` 只有 9 token/169 字符；581 应是 `[build]`/local override 合并后的 effective line，未在本文件核对生成物 | 运行 `./unixnu payload` 看 `kernel args:` 与 `payload.json` 的实际 `kernel_args`；若超过 1000 按优先级删诊断参数 |
| N20 | 官方 `platform.md` 的 8 GiB 上限 | 官方页不写数字；8 GiB 来自 K60 本地 `DarwinBoot22/WindowSize.h` 和 `devicetree.py` 的 256 MiB–8 GiB 校验 | 以本地代码为准；若换官方 DarwinBoot 主线，重新核对 `WindowSize.h` |
| N21 | 官方 `TFA9873` 覆盖 | 官方 16 项 39 页全文 0 命中 TFA9873；只有 pong `PongAudio.cpp` 有该器件 | 不要把 TFA 寄存器写进 K60；K60 功放先读 I2C 0x34/0x35 chip ID |
| N22 | 官方 `AudioProbe` 的功放型号 | 官方 `power.md` 只列 `ShengCs35l43.c`（CS35L43）与 WCD938x；没有 AW882xx | 同上；AW882xx 驱动需从厂商源码另取 |

## 附录 A 各组件板级输入

### 3.1 CPU / 中断 / 内存

**DTS 字段：**
- `/cpus/cpu@N`：`device_type="cpu"`、`reg`（MPIDR affinity，boot CPU 为第一个 enabled CPU）、`compatible`（`arm,cortex-a510`/`a710`/`cortex-x2` 等）、`timebase-frequency`、`unixnu,cluster-type="E"|"P"`、`status`（`docs/porting/device-tree.md:79-82,199-212`；`docs/porting/platform.md:24-26,49-50`）。
- `/psci`：`compatible="arm,psci-1.0"`、`method="smc"|"hvc"`（`docs/porting/device-tree.md:212`）。
- `/arm-io`：`#address-cells=<2>`、`#size-cells=<2>`、`ranges`；每个 child 的 `reg`、`interrupts`、`interrupt-parent`、`iommus`、`clocks`、`unixnu,adt-name`（`docs/porting/device-tree.md:56-77,214-231`）。
- `/memory`：`device_type="memory"`、`reg`（一个连续 DRAM 范围；`docs/porting/device-tree.md:79-82`）。
- `/chosen`：`random-seed`（64 B）、`unique-chip-id`（u64）、`chip-id`（u32）、`osenvironment`、`dram-base`、`dram-size`、`crypto-hash-method`、`root-matching`、`ephemeral-storage`、`darwinboot-memory-size`、`amfi-only-platform-code`、`boot-manifest-hash`；NVRAM proxy 的 `nvram-bank-size`/`count`/`current-bank`/`proxy-data`（`docs/porting/device-tree.md:153-185`）。
- `/defaults`、`/options`：平台默认/选项（`docs/porting/device-tree.md:141-151`；`sleep-disabled` 等）。

**board.toml / config 字段：**
- `[board] soc`、`soc_source`；`[device_tree] source`、`include_dirs`；`[kernel] config_fragments`、`patch_series`（`docs/reference/configuration.md:44-59`）。
- `[payload] dram_size`；`[payload.adt] owned_memory_size`、`cpu_regs`、`psci_method`（`docs/reference/configuration.md:159-187`）；`[payload.adt] chip_id`/`unique_chip_id` 按需。
- `[components] include` 加 `ArmDTPlatform`、`ArmCpu`；`[kernel] archives` 加 `component:ArmDTPlatform`、`component:ArmCpu`（`docs/porting/drivers.md:87-92`）。

**K60 现值：** SM8475，8 核（4×A510 + 3×A710 + 1×X2），MPIDR 平铺 `0x000..0x700`，PSCI `smc`，GICv3，timer 19.2 MHz（`README.md:123`、`porting.toml:39-49`）；当前 `dts/mondrian.dts:29-32` 只有 arena `[0x900000000,0xa40000000)` 4 GiB，`board.toml:98` `dram_size=0x140000000`，`:162` `owned_memory_size=0x130000000`。官方要求双簇 `E/P` 标签；K60 是三簇，当前 SoC dtsi 全标 `P`（`README.md:123`），是否改成 A510=E、A710/X2=P 需按官方 Edge scheduler 验证——这是 K60 与官方平台模型的第一处结构差异。

### 3.2 UFS

**DTS 字段：**
- `ufs@1d84000`：`compatible`（SM8475 `qcom,sm8475-ufshc`）、`reg=<0x0 0x1d84000 0x0 0x3000>`、`unixnu,adt-name="ufshc"`、`interrupts`、`clocks`/`clock-names`、`iommus`（SMMU phandle + stream ID）、`status="okay"`。
- K60 扩展属性（当前 `dts/mondrian.dts:39-53`）：`pong,ufs-hc-base`、`pong,ufs-hc-size`、`pong,gcc-ufs-page`、`pong,smmu-base`、`pong,smmu-size`、`pong,smmu-stream-id`、`pong,ufs-spi`、`pong,smmu-context-banks`、`pong,smmu-match-groups`。
- PHY 节点：`reg`、`lanes`、`ref-clock`、tuning/init owner；官方 SM8550 参考为 PHY `0x1d80000/0x2000`（`docs/porting/ufs.md:55-59`），K60 DTS 未列 PHY 节点（未核实）。
- SMMU context：stream ID `0xe0`、context bank 78、match groups 120（K60 DTS）。
- Storage layout：`[userdata] first_lba=53342976`、`last_lba=61731583`、`lba_bytes=4096`、`windows=[{name="OS"...},{name="SystemOS"...}]`（`board.toml:31-35`）；`root_match_volume_uuid`（`board.toml:150`）。

**board.toml / config 字段：**
- `[components] include` 加 `ShengUfs`（或 K60 的 `PongUfs`）；`[kernel] archives` 加 `component:ShengUfs`（`docs/porting/ufs.md:100-103`）。
- `CONFIG_XNU_NATIVE_UFS=y`；kernel args 加 `native-ufs-root=1`（`docs/porting/ufs.md:113-114`）。K60 另有 `pong_ufs_readwrite=1`（`board.toml:125`）。
- `[payload.adt] root_match_volume_uuid` 设为选中 APFS 卷 UUID（`docs/porting/ufs.md:105-110`）。

**K60 现值：** host `0x1d84000/0x3000`、GCC `0x187000`、SMMU `0x15000000/0x100000`、stream `0xe0`、SPI 265、context banks 78、match groups 120（`dts/mondrian.dts:39-53`）；`[userdata]` 见上。官方 `ShengUfs` 用 SM8550 host `0x1d84000/0x3000`、PHY `0x1d80000/0x2000`、apps-SMMU stream `0x60`（`docs/porting/ufs.md:55-59`）；K60 stream `0xe0` 不同，说明不能只换组件名。

### 3.3 显示 / 背光

**DTS 字段：**
- 显示控制器节点：`compatible`、`reg`/`ranges`、`interrupts`、`clocks`、`power-domains`、`iommus`、`unixnu,adt-name`；`display-subsystem` 节点可由 `GopFramebuffer` 在 runtime 建 `gop-display`（`LegacyDisplayProbe.cpp:557-563`）。
- 面板节点（K60 真面板）：`compatible="qcom,mdss_dsi_m11a_42_02_0a_dsc_cmd"`，`reg`、`vdd*` supplies、`reset-gpio`、`pinctrl-*`、`mi,panel-id`；三档 `timing@0/1/2` 60/90/120 Hz（`K60:docs/plans/120HZ-PORT-PLAN.md:7-14,128-172`；`K60:docs/state/SESSION-DIRECTIVES-2026-11-07.md:87-93`）。
- 背光：K60 无独立背光 IC；面板 DCS `0x51` 调光，无 `backlight`/`ktz8866`/`lm3697` compatible（`K60:docs/reference/FEATURES-DRIVERS-RESEARCH-2026-10-31.md:106-108`）。若未来加独立控制器，按官方字段：controller count、register encoding、brightness range、I2C engine、slave address、pins、clocks、interrupts、power sequence（`docs/porting/display.md:106-110`）。

**board.toml / config 字段：**
- `[device_tree] source`/`include_dirs`；`/chosen/display-scale`、`/chosen/display-rotation` ADT 属性（K60 当前 `display-scale=3`，`README.md:83`；属性读取见 `LegacyDisplayProbe.cpp:444-458`）；`[bootimg.dtb_node]` 的 `/reserved-memory/splash_region`（`board.toml` 无该条时按官方模板补，`docs/porting/device-tree.md:283-292`）。
- `CONFIG_XNU_NATIVE_LEGACY_DISPLAY=y`；kernel args：`offline-legacy-register=1`、`offline-legacy-gop=1`、`offline-legacy-unit-scale=2`、`offline-legacy-pm=1`、`offline-legacy-validate=1`、`offline-legacy-transfer=1`、`offline-legacy-cpu-present=1`、`offline-legacy-phase=4`（`docs/porting/display.md:45-48`；`UniXNU-sheng/board.toml:66`）；`sheng-dpu=1`、`sheng-vsync=120`、`sheng-dpu=2/3`、`sheng-dpu-scanout=2`、`sheng-fb-bgra=1`、`sheng-fb-gpu=1`（`docs/porting/display.md:52-54,78-99`；`UniXNU-sheng/board.toml:66`）。
- 背光：`sheng-backlight=1`、`sheng-backlight-control=0`（`docs/drivers/sheng-backlight.md:58-62`）；OS props 见 ② 显示行。

**K60 现值：** 面板 `qcom,mdss_dsi_m11a_42_02_0a_dsc_cmd`，1440×3200，DSC video mode，60/90/120 Hz 三档，stride 5760（`K60:docs/plans/K60-120HZ-PLAN.md:71-72`、`K60:docs/plans/120HZ-PORT-PLAN.md:7-14`）；当前 GOP 软件呈现 1440×3200 BGRA（`README.md:73,91-93`），DSI host/PHY/PLL 驱动缺失（`K60:docs/state/SESSION-DIRECTIVES-2026-11-07.md:92`）。官方 `GopFramebuffer` 构建器只支持 iOS17/27，K60 的 16.6.1 需要另写 ABI builder 或继续用现有 MiniIOMobileFramebuffer 方案。

### 3.4 触摸

**DTS 字段（K60 Goodix）：**
- `soc/spi@990000/xiaomi_touch@0`：`compatible="xiaomi,m11a-spi"`、`reg=<0>`、`spi-max-frequency`（目标 15 MHz；首验 4 MHz）、`interrupt-parent`、`interrupts`、`pinctrl-0/1`、`status="okay"`。
- `goodix,avdd-gpio=<&tlmm 71 0>`、`goodix,iovdd-name="vdd"`、`vdd-supply=<&pm8350c_l2>`（1.8 V）、`goodix,irq-gpio=<&tlmm 21 0x2008>`、`goodix,reset-gpio=<&tlmm 20 0>`、`goodix,irq-flags=<2>`、`goodix,panel-max-x=<0x3840>`（14400）、`goodix,panel-max-y=<0x7d00>`（32000）、`goodix,panel-max-w=<0xff>`、`goodix,panel-max-p=<0x1000>`、`goodix,firmware-name="goodix_firmware_m11a"`、`goodix,config-name="goodix_cfg_group_m11a"`、`goodix,touch-expert-array=<2 3 2 2 4 3 3 2 3 3 4 2>`（`K60:docs/plans/K60-TOUCH-PARAMS.md:31-58,90`）。
- 若复用 pong `pong_goodix.c`，节点名要发成 `/arm-io/pong-touch`，`compatible="pong,goodix-berlin-d"`（`K60:docs/plans/K60-TOUCH-PARAMS.md:129-135`）。

**board.toml / config 字段：**
- `[components] include`：`QcomGeniSpi`、`ShengHidInput`（官方）；`ShengNovatekTouch` 只在 Novatek 传感器时选；K60 不选。
- `[kernel] archives`：显示 recipe（`build-gop-legacy-display.py` 或 K60 自有 touch 构建脚本）编译 `GeniSpi.c`/Goodix 协议/`NativeHidInput.late.o`。
- kernel args：`sheng-touch=1..4`、`sheng-touch-hid=1`（`docs/porting/input.md:56-58,71-73`）；K60 首验用 `k60touchstage=4 k60rpmhoff=1 k60touchdelay=8 k60touchhz=4000000`（`K60:docs/plans/K60-TOUCH-PARAMS.md:190`）。
- 固件提取：`scripts/gen-touch-firmware.py`（`docs/porting/input.md:52-54`）；K60 `proprietary-files.txt` 里登记 `goodix_firmware_m11a`。

**K60 现值：** GENI SPI SE4 `0x990000`、CS0、IRQ GPIO21（flags `0x2008`，下降沿）、RESET GPIO20、AVDD GPIO71/PM8350C LDO2 1.8 V；Goodix 型号未硬件确认（DT 只有 `xiaomi,m11a-spi`/`goodix_firmware_m11a`）；raw 上限 14400×32000 → 面板 1440×3200（`K60:docs/plans/K60-TOUCH-PARAMS.md:90,159-166`、`K60:docs/state/SESSION-DIRECTIVES-2026-11-07.md:67-84`）。RSC `0x17a00000` 首次读 TCS 会死机，首验必须 `k60rpmhoff=1`（`K60:docs/plans/K60-TOUCH-PARAMS.md:174-180,248-255`）。

### 3.5 实体键

**DTS / ADT 字段：**
- `/buttons`：`compatible="buttons"`、`device_type="buttons"`、`button-names=["hold","voldown","volup"]`、`home-button-type=<2>`（`docs/porting/device-tree.md:233-235`；`UniXNU-sheng/board.toml:150-163`）。
- PMIC/GPIO：PON peripheral `0x13`（K60），音量加 `pm8350@1/pinctrl@8800` GPIO6=`0x8d00`（ACTIVE_LOW）；音量减/电源键按 PUC 的 KPDPWR/RESIN 路由（`K60:docs/state/SESSION-DIRECTIVES-2026-11-07.md:110-115`）。
- 中断：GPIO/PMIC interrupt parent、polarity、ownership、acknowledgement（`docs/porting/input.md:89-91`）。

**board.toml / config 字段：**
- `[kernel] archives`：`ButtonProbe.cpp` 编入显示/输入 archive（`build-gop-legacy-display.py:271,327`）。
- kernel args：`sheng-buttons=1`（`docs/porting/input.md:92-94`）。
- HID：report 2 的 bit 0/1/2 = Power/Volume Increment/Volume Decrement（`:92-94`）。

**K60 现值：** UEFI 侧 `ButtonsDxe`/`SPMDxe→SPMIDxe`/`PmicDxeLa` 已存在（`K60:docs/state/SESSION-DIRECTIVES-2026-11-07.md:110-115`）；XNU 侧尚无驱动，需按 pong `pong-physical-keys.patch` 结构新写。

### 3.6 GPU / Metal

**DTS 字段：**
- GPU 节点：`compatible`（A730 `qcom,adreno-730`/`qcom,adreno` 按 SM8475 dtsi）、`reg`（GPU/GMU 窗口）、`interrupts`、`iommus`（GPU SMMU stream）、`power-domains`、`clocks`/`clock-names`、`opp-table`、`interconnects`、`qcom,gmu` child、`qcom,arc-level`/`qcom,gmu` 配置按目标。
- `reserved-memory`：GPU firmware/ZAP 区域（K60 `a730_zap` PAS 13 `0x8b91a000`，`docs/devices/mondrian-mzyxsl.md:396-398`）。
- Firmware 名称：A730 `gmu_gen70000.bin`、`a730_sqe.fw`、`a730_zap.mdt/.b01/.b02`；A740 `gmu_gen70200.bin`、`a740_sqe.fw`、`a740_zap.mbn`（`docs/porting/gpu.md:44-52`；`K60:docs/plans/GPU-ENABLE-PLAN.md:258-259`）。

**board.toml / config 字段：**
- `[components] include`：官方 A740 路线 `Adreno740`、`AdrenoMetal`、`Sm8550Platform`、`AdrenoFirmware`、`AdrenoPM4`、`AirNir`、`ArmSmmu4K`（`docs/drivers/sm8550-platform.md:20-25`）；K60 A730 路线用 `PongAdreno`/`PongMetal`（当前 `board.toml:14` 未选，需按 GPU-ENABLE-PLAN 添加）。
- `[kernel] archives`：`component:Adreno740`、`build-adreno740-kits.py`、`build-adreno740-accelerator.py`（`UniXNU-sheng/board.toml:20`）。
- kernel args：`sheng-gpu-power=9`、`sheng-gpu-metal=1`、`sheng-gpu-addon=1`、`sheng-gpu-preempt=2`、`sheng-fb-gpu=1`、`sheng-fb-bgra=1`（`UniXNU-sheng/board.toml:66`、`docs/porting/gpu.md:102,108-112`）。
- Payload：`--gpu-addon build/gpuaddon.bin`、`--owner-trust-cache`（`docs/porting/gpu.md:152`）。

**K60 现值：** Adreno 730 v3 `0x07030002`，2 MiB GMEM，HighestBankBit 16，64×32 tile，`gmu_gen70000.bin`/`a730_sqe.fw`/`a730_zap.*`（`K60:docs/plans/GPU-ENABLE-PLAN.md:238,258-259`；`docs/devices/mondrian-mzyxsl.md:396-398`）。官方 A740 固件/寄存器表不适用；pong `PongAdreno` 已按 A730 实现并已在 K60 编译（`README.md:91`）。

### 3.7 WiFi（QCA6490）

**DTS 字段：**
- `qcom,cnss-qca6490@b0000000`：`compatible="qcom,cnss-qca6490"`、`reg=<0xb0000000 0x10000>`（SMMU IPA window）、`reg-names="smmu_iova_ipa"`、`qcom,wlan-rc-num`、`qcom,wlan`、`qcom,wlan-cbc-enabled`、`use-pm-domain`、`cnss-enable-self-recovery`、`qcom,bus-bw-cfg`；`qcom,vreg_ipa="s3e"`（`K60:docs/plans/WIFI-PORT-PLAN.md:157-170,232-239`）。
- `qcom,pcie@1c00000`：`reg` 六个窗口、`reg-names`、`interrupts`/`interrupt-map`、`clocks`、`power-domains`、`resets`、`phys`、`#address-cells`/`#size-cells`、`ranges`；BAR0 `0x60200000/2 MiB`；MSI SPI140（`K60:docs/plans/WIFI-PORT-PLAN.md:157-170`）。
- 电源：`vdd-wlan-aon/dig/io/rfa1/rfa2/ant-switch` 六条 + `qcom,vreg_ipa`；K60 FDT 的 PMIC regulator 节点名（`K60:docs/plans/WIFI-PORT-PLAN.md:165-170,238-239`）。
- 控制 GPIO：GPIO80 WLAN_EN、81 BT_EN、82 SW_CTRL、94/95/96/204（XO/PERST/CLKREQ/WAKE，按 `K60:docs/plans/WIFI-PORT-PLAN.md:224` 与 `K60:docs/plans/BT-AUDIO-PORT-PLAN.md:59-66`）。

**board.toml / config 字段：**
- `[components] include`：官方 `Ath12kWifi`（**不适用于 K60**）；K60 应加 `PongWifi`（pong main 子模块，`K60:docs/plans/WIFI-PORT-PLAN.md:308`）。
- `[kernel] archives`：`build-ath12k-wifi.py`（官方）或 K60 `build-k60-wifi-resources.py` + PongWifi 构建（`K60:docs/plans/WIFI-PORT-PLAN.md:369`）。
- `[payload.runtime]`：`wifi_tool="scripts/build-wifi-userspace.py"`、`wifi_target="ios27"`/K60 16.6.1 需改 target、`wifi_launchd_cache=true`、`wifi_bin_prefix`（`UniXNU-sheng/board.toml:79-82`）。
- kernel args：`sheng-wifi=5`、`sheng-wifi-aj=0`、`log-wifi=1`（`docs/drivers/ath12k-wifi.md:64-67`）；K60 用 `pong_wifi` 系列（`K60:docs/plans/WIFI-PORT-PLAN.md:13,52`）。

**K60 现值：** QCA6490/WCN6855，PCI `17cb:1103`，PCIe0 `0x1c00000`，BAR0 `0x60200000/2 MiB`，SID `0x1c01`，IOVA `0xA0000000/256 MiB`，MSI SPI140，六条 WLAN rail + `qcom,vreg_ipa="s3e"`，GPIO80/81/82/94/95/96/204（`K60:docs/plans/WIFI-PORT-PLAN.md:13,76-85,157-170,224-239`）。官方 `Ath12kWifi` 的 WCN7850 六 PMU rail/PCIe0 Gen2 x1/17cb:1107/MSI SPI141 是 sheng 值（`docs/porting/network.md:102-116`），不能照抄。

### 3.8 蓝牙（QCA6490）

**DTS 字段：**
- `bt_qca6490`：`compatible="qcom,qca6490"`、`qcom,bt-reset-gpio`/`qcom,bt-en-gpio`/`qcom,sw-ctrl-gpio`、`qcom,wl-reset-gpio`、`qcom,xo-clk-gpio`、`vdd*` supplies（7 路：`pm8350 S10/S11/S12`、`pm8350c S1`、`pmr735a L7` 等；`K60:docs/plans/BT-AUDIO-PORT-PLAN.md:51-70`）。
- `qup_uart@894000`：`compatible="qcom,msm-geni-serial-hs"`、`reg=<0x894000 ...>`、`interrupts=<GIC_SPI 587>`、`pinctrl-0/1`、`qcom,wakeup-byte=0xfd`。
- 标准 `bluetooth` 节点（官方模板）：`device_type="bluetooth"`、`compatible="qcom,wcn7850-bt"`（K60 换成 `qcom,qca6490-bt`）、`unixnu,adt-name="bluetooth"`、`transport-encoding=<1>`、`transport-speed=<3200000>`、`status="okay"`；`local-mac-address` + `/chosen/mac-address-bluetooth0`（`docs/porting/bluetooth.md:75-89`）。
- 电源轨：`pm8350 S10`=1.8 V IO、`S11`=0.966–1.17 V（四路 AON/DIG/RFACMN/RFA-0P8）、`S12`=1.35–2.02 V RFA2、`pm8350c S1`=1.90–2.04 V RFA1、`pmr735a L7`=2.8 V ASD（`K60:docs/plans/BT-AUDIO-PORT-PLAN.md:60-64`）。

**board.toml / config 字段：**
- `[components] include`：`QcaBluetooth`（官方 WCN7850；K60 需新组件/分叉）。
- `[payload.runtime]`：`audio_system_plugins=["BTAudioHALPlugin.driver"]`、`bluetooth_tool="scripts/build-bluetooth-userspace.py"`、`bluetooth_target="ios27"`（K60 16.6.1 需改 target）（`docs/porting/bluetooth.md:93-99`、`UniXNU-sheng/board.toml:78,83-84`）。
- kernel args：`sheng-bluetooth=1`、`log-bluetooth=2`（`docs/drivers/qca-bluetooth.md:102-103`）。
- 固件：`hmtbtfw20.tlv`/`hmtnv20.bin`（WCN7850）；K60 预计 `htbtfw21.tlv`/`htnv21.bin`（未核实），`firmware/bluetooth/manifest.json` pin + `scripts/stage-bluetooth-firmware.py`（`docs/porting/bluetooth.md:36-40`）。

**K60 现值：** QCA6490 BT 独立 `bt_qca6490` 电源节点 + `qup_uart@894000`（QUPV3_2 SE20），IRQ 587，GPIO76/77/78/79，`qcom,wakeup-byte=0xfd`；WLAN 与 BT 共用 GPIO80/81/82/204 和 S5/S10/S11/S12/L7 电源轨（`K60:docs/plans/BT-AUDIO-PORT-PLAN.md:51-70,76-78`）。官方 QcaBluetooth 的 UART `0x898000`/IRQ493/GPIO76-79 是 sheng 值（`docs/porting/bluetooth.md:28-34`），K60 需改 SE20 `0x894000`/IRQ587。

### 3.9 音频（AW882xx）

**DTS 字段：**
- `i2c@880000/aw882xx_smartpa@34`、`@35`：`compatible="awinic,aw882xx_smartpa"`、`reg=<0x34>`/`<0x35>`、`reset-gpio=<&tlmm 1 0>`/`<&tlmm 3 0>`、`irq-gpio`（GPIO88/63）、`spk-sw-gpio`（GPIO52）、`vdd-supply`、`status="okay"`（`K60:docs/plans/BT-AUDIO-PORT-PLAN.md:207-222`）。
- ADSP：`remoteproc-adsp@03000000`：`compatible="qcom,cape-adsp-pas"`、`reg=<0x03000000 0x10000>`、`memory-region=<&adsp_region>`、`glink-edge`（`qcom,glink-channels="adsp_apps"`、`qcom,intents=<0x200 0x14>`、`reg=<2>`）、`status="okay"`（`K60:docs/plans/BT-AUDIO-PORT-PLAN.md:219-222`）。
- `reserved-memory/adsp_region@9fd00000`：`reg=<0x9fd00000 0x3100000>`（49 MiB）。
- IPCC：`qcom,ipcc@ed18000`、`reg=<0xed18000 0x1000>`、`interrupts=<GIC_SPI 261>`。
- 音频路由字段（官方）：graph/subgraph ID、module instance ID、connections、codec port、amplifier setup、clocks、channel map、period buffer 大小/对齐（`docs/porting/power.md:70-104`）；TDM 1.536 MHz、tx-lines=3（K60 计划，`K60:docs/plans/BT-AUDIO-PORT-PLAN.md:461`）。

**board.toml / config 字段：**
- `[components]`：无官方音频组件；`[kernel] archives` 用 `build-gop-legacy-display.py` 编 `AudioProbe.cpp`/`ShengGpr.c`/`ShengAudioReach.c`/`ShengCs35l43.c` 进 `libNativeLegacyDisplay.late.a`（`build-gop-legacy-display.py:265-314,327`）。
- `[payload.runtime]`：`audio_tool="scripts/build-sheng-audio-hal.py"`、`audio_target="arm64e-apple-ios27.0"`（K60 16.6.1 改）、`audio_system_plugins=["BTAudioHALPlugin.driver"]`（`UniXNU-sheng/board.toml:76-78`）。
- kernel args：`sheng-adsp=2`、`sheng-audio=12`（`UniXNU-sheng/board.toml:66`）。

**K60 现值：** 2×AW882xx I2C `0x880000`，地址 `0x34/0x35`，reset GPIO1/3，IRQ88/63，spksw52；ADSP carveout `0x9fd00000/0x3100000`；TDM 1.536 MHz、tx-lines=3（`K60:docs/plans/BT-AUDIO-PORT-PLAN.md:207-222,340-355,461`）。官方 sheng 是 CS35L43 ×2 + WCD938x，pong main 是 TFA9873 ×2；都不能直接用于 K60，必须新写 AW882xx 功放层。

### 3.10 DSP / 电源 / 电池

**DTS 字段：**
- ADSP 节点同 3.9；`qcom,smem`、`qcom,smp2p`、`qcom,glink` 由 `AdspProbe.cpp` 从 firmware/SMEM 发现（`docs/porting/power.md:28-30`）。
- PMIC：`pmk8350@0`、`pm8350@1`、`pm8350c@2`、`pm8350b@3`、`pmr735a@4`、`pmr735b@5`、`pm8450@7`（`K60:docs/plans/BT-AUDIO-PORT-PLAN.md:224`）。
- RSC：`rsc@17a00000`，`compatible="qcom,rpmh-rsc"`，`reg=<0x17a00000 0x10000 0x17a10000 0x10000 0x17a20000 0x10000 0x17a30000 0x10000>`，`qcom,drv-id=<2>`，`reg-names="drv-0"..."drv-3"`（`K60:docs/plans/K60-TOUCH-PARAMS.md:87`）。
- 电池：PMIC GLINK `qcom,battmgr` 协议（owner/message type/opcode/property ID/response length）；或直接 I2C gauge 的寄存器协议（`docs/porting/power.md:143-151`）。
- 电源域：clock domains、OPP/LUT、regulators、interconnect、thermal limits（`docs/porting/power.md:17`）。

**board.toml / config 字段：**
- `[kernel] archives`：`build-sheng-platform-power.py`（平台电源）、`build-gop-legacy-display.py` 编 `AdspProbe.cpp`/`QcomMdt.c`/`QcomSmem.c`/`QcomSmp2p.c`/`QcomGlink.c`/`QcomQmp.c`/`QcomRpmh.c`/`ShengBattmgr.c`/`ShengBattery.cpp`/`BatteryProbe.cpp`/`CpuFreqProbe.cpp`/`GpuPowerProbe.cpp`（`build-gop-legacy-display.py:265-314`；`UniXNU-sheng/board.toml:177`）。
- kernel args：`sheng-adsp=2`、`sheng-cpufreq=4`、`sheng-gpu-power=9`、`sheng-battery` 相关（`UniXNU-sheng/board.toml:66`）。
- `[payload.runtime]`：无专门电源字段；battery 服务通过内核启动。

**K60 现值：** ADSP carveout `0x9fd00000/0x3100000`；IPCC `0xed18000/0x1000` IRQ261；GPR `adsp_apps` intents `0x200/0x14`；PMIC 组见上（`K60:docs/plans/BT-AUDIO-PORT-PLAN.md:219-224`）；RSC `0x17a00000` 访问风险见触摸节（`K60:docs/plans/K60-TOUCH-PARAMS.md:174-180`）。官方 sheng 的 ADSP 是 `0x85700000/0x2800000`（pong 值），K60 必须改常量（`K60:docs/plans/BT-AUDIO-PORT-PLAN.md:348`）。

### 3.11 USB

**DTS 字段：**
- `ssusb@a600000`：`reg=<0xa600000 0x100000>`、`ranges`、`#address-cells`/`#size-cells`、`interrupts`、`iommus`、`power-domains`、`clocks`、`resets`。
- `dwc3@a600000`：`compatible="snps,dwc3"`、`reg=<0xa600000 0xd93c>`、`interrupts`、`dr_mode="otg"`、`maximum-speed="high-speed"`、`phys`/`phy-names`、`snps,dis_u2_susphy_quirk` 等按目标。
- `qcom,usb-snps-eusb2-phy@88e3000`、`qcom,usb-ssphy-qmp-dp-combo@88e8000`、`nxp,eusb2-repeater@4f`、`qcom,fsa4480-i2c`（K60 实测节点，`K60:docs/reference/FEATURES-DRIVERS-RESEARCH-2026-10-31.md:81`）。
- 电源/时钟：USB3 GDSC、core/iface/bus_aggr/utmi/sleep clocks、core reset、PHY rails（`K60:docs/reference/USB-LOGGING-PLAN.zh.md:45-51`）。

**board.toml / config 字段：**
- `[components] include`：`QcomDwc3`（官方 27 路线）；K60 16.6.1 计划用自定义 `PongUsb`/usblog，不选 QcomDwc3。
- `[kernel.prelink] roots`：`com.apple.driver.AppleUSBXDCI`、`com.apple.driver.AppleUSBDeviceMux`、`com.apple.iokit.IOUSBHostFamily`、`com.apple.driver.usb.AppleUSBXHCI`、`com.apple.driver.usb.AppleUSBHub`、`com.apple.driver.usb.AppleUSBHostCompositeDevice`、`com.apple.driver.usb.IOUSBHostHIDDevice`、`com.apple.iokit.IOUSBMassStorageDriver`、`com.apple.iokit.IOSCSIArchitectureModelFamily`、`com.apple.iokit.IOSCSIBlockCommandsDevice`，并排除 `AppleOnboardSerial`/`AppleSMC`（`UniXNU-sheng/board.toml:28`、`docs/porting/usb.md:75-80`）。
- kernel args：`sheng-usb=1`、`sheng-usb-host=<s>`、`sheng-usb-back=<s>`、`log-sys=1`（`docs/drivers/qcom-dwc3.md:33-40`）。
- `[payload.adt] chip_id`；`adt.chosen.u32` 的 `board-id`/`security-domain`（OS profile）；`native-union-statfs-fsid`；`sheng-aks-sls=3`（`docs/porting/usb.md:108-118`）。

**K60 现值：** DWC3 `0xa600000`（+QSCRATCH `0xa6f8800`）、eUSB2 PHY `0x88e3000`、QMP `0x88e8000`、USB3 GDSC、SMMU stream `0x0`（`K60:docs/reference/USB-LOG-CHANNEL.md:150-152`、`K60:docs/reference/ISSUES.md:195`）；官方 sheng 是 DWC3 同址、window `+0xc000`、IRQ 165、SMMU stream `0x40`、eUSB2 38.4 MHz（`docs/porting/usb.md:25-33`）。K60 的 stream 不同，是 USB 适配的最大风险之一。

## 附录 B iOS 版本适用性

**全局事实：** 对 `E:/hackios/UniXNU/docs/drivers`、`docs/porting`、`docs/reference` 三个目录做全文检索，`16.6.1` 与 `20G81` 命中数均为 **0**。官方文档只在通用 arm64 说明里承认 iOS 16 可作为 arm64 profile（`docs/porting/arm64e.md:6`：“Other devices use an arm64 profile (iOS 16 or iPadOS 17, for example `ipados-17.7.11-21H461`)”），但没有任何组件级 16.6.1 验证声明。K60 的 `profiles/os/ipados-16.6.1-20G81/profile.toml` 存在，只证明 OS 配置层可选。

| 组件 / 页面 | 文档明示版本（路径:行号） | 16.6.1 / 20G81 标注 |
| --- | --- | --- |
| `ArmCpu`（`arm-cpu.md`） | 无版本语句；catalog `os_abi=["ipados-17.7.11-21H461"]`（`components.toml:12`） | **未说明**（框架 arm64 档位可承载 iOS16，但组件未声明） |
| `ArmDTPlatform`（`arm-dt-platform.md`） | 无版本语句；catalog 17.7.11（`components.toml:30`） | **未说明** |
| `ArmSmmu4K`（`arm-smmu4k.md`） | 无版本语句；catalog 无 `os_abi`（`components.toml:397-413`） | **未说明** |
| `ShengUfs`（`sheng-ufs.md`） | 无版本语句；catalog 17.7.11（`components.toml:130`）；`sheng-ufs.md:32` 说“Historical iOS 17 device results do not qualify this path” | **未说明**（仅 17.x 参考） |
| `GopFramebuffer`（`gop-framebuffer.md` / `display.md`） | catalog 17.7.11 + 27.0.1（`components.toml:215`）；`build-gop-legacy-display.py:10-12` 只支持 arm64 iOS17；`-27.py:17-18` 只支持 arm64e iPadOS27；`display.md:65` 24A446 | **未说明**（文档覆盖 iOS17 + iPadOS27；16.6.1 无 recipe） |
| `ShengBacklight`（`sheng-backlight.md`） | iPadOS 17 working、iPadOS 27.0.1 (24A446) working/not verified（`:11-15`）；属性按 17/27 分（`:32-37`） | **未说明**（仅 17/27 有记录） |
| `ShengNovatekTouch`（`sheng-novatek-touch.md`） | 无版本语句；catalog 17.7.11（`components.toml:173`） | **未说明** |
| `QcomGeniSpi`（`qcom-geni-spi.md`） | 无版本语句；catalog 17.7.11（`components.toml:194`） | **未说明** |
| `ShengHidInput`（`sheng-hid-input.md`） | `IOHIDFamily 2031.120.4 ABI`（`:9`）；`sheng-hid-input.md:21` 说 historical iOS17 results do not qualify arm64e path | **未说明**（ABI 面向 17.x） |
| `Adreno740`（`adreno740.md` / `gpu.md`） | `adreno740.md:26` “resolved iOS 27 target tree”；`gpu.md:136-150` 同时给出 iOS17 和 iOS27 构建命令；catalog 17.7.11（`components.toml:87`） | **未说明**（文档覆盖 iOS17 + iOS27；16.6.1 无） |
| `AdrenoMetal`（`adreno-metal.md` / `gpu.md`） | `adreno-metal.md:40` “resolved iOS 27 target tree”；`gpu.md:136-150` iOS17/iOS27；catalog 17.7.11（`components.toml:109`） | **未说明**（同上） |
| `Sm8550Platform`（`sm8550-platform.md`） | 无版本语句；hardware 仅 SM8550（`:15`）；catalog 无 `os_abi`（`components.toml:462`） | **未说明**（硬件不适用 K60） |
| `Ath12kWifi`（`ath12k-wifi.md` / `network.md`） | `ath12k-wifi.md:36` “sheng on iPadOS 27”；`:40,53` 24A446；catalog 无版本（`components.toml:483`） | **仅 iOS 27（24A446）** |
| `QcaBluetooth`（`qca-bluetooth.md` / `bluetooth.md`） | `qca-bluetooth.md:10` iPadOS 27.0.1 (24A446)；`:58` iPadOS 27 adapter；catalog 27.0.1（`components.toml:503`） | **仅 iOS 27（24A446）** |
| `QcomDwc3`（`qcom-dwc3.md` / `usb.md`） | `qcom-dwc3.md:9` iPadOS 27.0.1 (24A446)；`usb.md:78-80` ABI JSON 24A446；catalog 27.0.1（`components.toml:523`） | **仅 iOS 27（24A446）** |
| 音频参考（`power.md`） | 无版本语句；示例是 sheng/SM8550；`baseband.md:5` iOS17 仅 baseband | **未说明** |
| DSP/电源/电池参考（`power.md`） | 无版本语句；SM8550 参考值（`:202-208`） | **未说明** |
| `AppleKeyStoreState`（`apple-key-store-state.md`） | 无版本语句；catalog 17.7.11 + 27.0.1（`components.toml:259`） | **未说明**（目录同时列 17/27） |
| `XnuPrelink`（`xnu-prelink.md`） | `:22` “iOS 27 reference build”；`:35,79` 24A446 fixture；catalog 无 os_abi | **仅 iOS 27 参考**（16.6.1 未说明） |
| `DarwinBoot`（`darwin-boot.md`） | 接受 arm64/arm64e `MH_EXECUTE`，无版本（`:15-17`）；`kexts.md:148` 提到 xnu-10063.141.1/iOS17 | **未说明** |
| `RamBlock`（`ram-block.md`） | 无版本语句；catalog 17.7.11（`components.toml:281`） | **未说明** |
| `SoftwareAES`（`software-aes.md`） | 无版本语句；catalog 17.7.11（`components.toml:237`） | **未说明** |
| `KeXt` bundle 路径（`kexts.md`） | `:148` executable 必须匹配 `xnu-10063.141.1` 和 iOS 17 deployment target | **未说明**（仅 iOS17 ABI 说明） |
| 打包/runtime（`packaging.md`） | `:128-161` “Runtime inputs for iOS 27”；`:168` 24A446；`:84-88` 17.7.11/27.0.1 defconfig 示例 | **仅 iOS 27 路径有 runtime 生成**（17 有示例；16.6.1 未说明） |
| 公开源驱动（`migration.md`） | `:468-474` `ipados-27.0.1-24A446` 的 `build-sheng-source-drivers.py`；`:516` “Existing iOS 17 ABI and device evidence…” | **仅 iOS 27 公开源路径**（16.6.1 未说明） |

**结论：** 没有一条官方组件文档写“也适用 16.6.1/20G81”。K60 的 16.6.1 只能作为 arm64 自定义 profile 继续维护；任何官方组件迁移都要先在 20G81 kernelcache/headers 上重新做 ABI 审计，不能以 17.7.11/21H461 或 27.0.1/24A446 的通过记录代替。

## 附录 C 官方页面来源

| 项 | URL |
|---:|---|
| 1 | `https://unixnu.com/porting/drivers` |
| 2 | `https://unixnu.com/porting/platform` |
| 3 | `https://unixnu.com/porting/ufs`、`https://unixnu.com/drivers/sheng-ufs`、`https://unixnu.com/drivers/verified-root`、`https://unixnu.com/drivers/ram-block` |
| 4 | `https://unixnu.com/porting/display` |
| 5 | `https://unixnu.com/drivers/sheng-backlight`、`https://unixnu.com/drivers/gop-framebuffer` |
| 6 | `https://unixnu.com/porting/input`、`https://unixnu.com/drivers/sheng-novatek-touch`、`https://unixnu.com/drivers/sheng-hid-input`、`https://unixnu.com/drivers/qcom-geni-spi`、`https://unixnu.com/drivers/community-nativefocaltechtouch` |
| 7 | `https://unixnu.com/porting/gpu`、`https://unixnu.com/drivers/adreno740`、`https://unixnu.com/drivers/adreno-metal`、`https://unixnu.com/drivers/adreno-firmware`、`https://unixnu.com/drivers/adreno-pm4`、`https://unixnu.com/drivers/arm-smmu4k`、`https://unixnu.com/drivers/sm8550-platform`、`https://unixnu.com/drivers/air-nir` |
| 8 | `https://unixnu.com/porting/network`、`https://unixnu.com/drivers/ath12k-wifi` |
| 9 | `https://unixnu.com/porting/bluetooth` |
| 10 | `https://unixnu.com/drivers/qca-bluetooth` |
| 11 | `https://unixnu.com/porting/usb` |
| 12 | `https://unixnu.com/drivers/qcom-dwc3`、`https://unixnu.com/drivers/community-native-dwc3` |
| 13 | `https://unixnu.com/porting/baseband`、`https://unixnu.com/drivers/qcom-baseband` |
| 14 | `https://unixnu.com/porting/power` |
| 15 | `https://unixnu.com/drivers/overview`、`https://unixnu.com/drivers/xnu-drivers`、`https://unixnu.com/drivers/kexts`、`https://unixnu.com/drivers/device-tree-matching` |
| 16 | `https://unixnu.com/xnu/boot-arguments`、`https://unixnu.com/xnu/four-k-page-tables`、`https://unixnu.com/xnu/patch-reference`、`https://unixnu.com/xnu/source-and-patches` |

> 交叉核对页：`https://unixnu.com/devices/sheng`（source record `460179565a018c741b93e0b1efa07c55d4de497a`）、`https://unixnu.com/devices/mondrian`（source record `c39ff292eee2726c0135f3ba3a98462c9c21d8de`）。
