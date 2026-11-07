# DOCS-DRIVERS-ALL — `docs/drivers/` 47 篇全量阅读纪要

> 阅读对象：`E:/hackios/UniXNU/docs/drivers/`，分支 `main`，HEAD `75ae626a12764c706fc0b94c52a3eea09447dbaa`。
> 规模：47 个 `.md`，106,686 字节，2,271 行（含空行）。
> 方法：`find docs/drivers -name '*.md' | sort` 生成清单，逐文件从第 1 行读到 EOF；47 篇全部返回 `complete=true`，无截断、无跳过。
> 口径：① 的摘要是对文档原文的压缩；`docs/porting/*` 的内容只在“K60 适配”判断中作为旁证。K60 = Redmi K60 / mondrian / SM8475，已知硬件锚点为 Adreno 730、QCA6490、Goodix、AW882xx；K60 具体地址/GPIO 标为「K60 现值」，来自设备仓与既有计划，标 `[未核]` 的需上机确认。

## 阅读结论（先给结论）

1. `docs/drivers/` 不是一本统一的驱动手册，而是 **“组件目录页 + 少量深指南”** 的混合体。47 篇里真正给出机制、代码结构或完整板级流程的约 14 篇：`overview`、`repositories`、`xnu-drivers`、`device-tree-matching`、`kexts`、`uefi-drivers`、`ath12k-wifi`、`qca-bluetooth`、`qcom-dwc3`、`sheng-novatek-touch`、`sheng-backlight`、`adreno740`、`adreno-metal`、`xnu-prelink`；其余 33 篇是 9–47 行的组件登记页。
2. **47 篇没有一篇记录 git commit pin。** 只有仓库 URL；唯一出现的具体 revision 是 `community-adreno830.md` 的“started from Adreno740 `5c8c145`”。`kexts.md` 另给出 ABI 锚点 `xnu-10063.141.1` / iOS 17 deployment target。真正的 pin 在 `components.toml` 的 `revision` 和 `.gitmodules` 的 gitlink 里，且两套值存在不一致——本文不复制未核 pin。
3. 官方组件清单共 **28 个条目**（`repositories.md` 的 Official drivers 表），社区驱动 **12 个**，另有 **9 个设备 fork**。官方组件的硬件验证集中在 sheng / SM8550 / iPadOS 17 与 27（通用平台/QEMU 组件除外）；**没有任何官方组件声明支持 SM8475 / K60 / 16.6.1**。
4. 对 K60 而言，**可复用的是接口层（部分需 ABI 审计）**：`ArmCpu`、`ArmDTPlatform`、`ArmSmmu4K`、`QcomGeniSpi`、`ShengHidInput`、`RamBlock`、`AppleKeyStoreState`、`SoftwareAES`、`VerifiedRoot`。**必须换 SoC/板级常量或重写的是**：A730 GPU 栈、SM8475 GMU/GPU SMMU/RPMh、QCA6490 Wi-Fi/BT、Goodix 触摸、AW882xx 音频、K60 DSI 显示/背光、实体键、USB。
5. 设备仓当前 `board.toml` 只选了 `ArmDTPlatform`、`ArmCpu`、`XnuPrelink`、`PongUfs`；`dts/mondrian.dts` 只有 `/memory` 和 `ufs@1d84000` 两个硬件节点。**其余子系统的 DTS 节点、personality 和板级常量都要新建**。

---

## ① 47 篇逐篇摘要

### 01. `adreno740.md` — A740 XNU GPU 驱动（38 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/Adreno740`；文档未给 pin，未列源文件清单。
- **定位**：SM8550 上实现 A740 内核 GPU 接口，拥有 GPU 内存映射、命令提交、fence、CP/GMU 初始化；板级提供固件、power vote 和显示集成。
- **板级输入**：GPU/GMU 寄存器与中断、GPU SMMU（4 KiB 页）、GMU 固件与 GPU microcode、power votes、scanout/display 集成；文档只给类型，不给地址表。
- **Build integration**：`scripts/build-arm-driver.py Adreno740`、`scripts/build-adreno740-kits.py`、`scripts/check-native-adreno-scheduling.py`；环境 `UNIXNU_XNU_ARCH=arm64e`、`UNIXNU_IOS_VERSION=27.0`；要求 resolved iOS 27 target tree。
- **K60 适配**：A730 ≠ A740，不能直接选。可复用其调度设计：mode 2 双 ring（高/正常高/实时 → ring 0；普通/低/后台/未指定 → ring 1）、ring 1 250 ms aging、2 ms service、1 s switch watchdog、`CP_SMMU_TABLE_UPDATE` 快照、GMEM 保存与 GMU keepalive；K60 用现有 `PongAdreno` 并换 A730 寄存器/固件。

### 02. `adreno-firmware.md` — GMU 固件/HFI kit（17 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/AdrenoFirmware`；pin 未记录。
- **定位**：Adreno GMU firmware 与 HFI kit，加载 GMU firmware 并说 HFI 协议；被 Adreno740 使用。
- **板级输入**：board GPU archive recipe 编译该 kit 并嵌入 **pinned local firmware images**；提取路径、board votes、startup checkpoints 见 GPU adaptation。
- **Build integration**：随 board GPU archive recipe 编译，无独立 archive。
- **K60 适配**：HFI 协议层可参考；A730 的固件集不同（`gmu_gen70000.bin`、`a730_sqe.fw`、`a730_zap.*`，见 K60 GPU 计划），必须重新 pin/打包，不能照抄 A740 的 blob。

### 03. `adreno-metal.md` — Metal 前端（58 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/AdrenoMetal`；pin 未记录。
- **定位**：通过 `MTLAddDevice` 发布 Metal device；AIR 经 metal2vulkan 翻译、Turnip 编译 SPIR-V，提交给 Adreno740；固件、power votes、显示集成由板级提供。
- **板级输入**：GPU 固件、power votes、display/scanout；缓存目录 `Library/Caches/org.unixnu.metal`（`NATIVE_METAL_SHARED_CACHE_DIR` 可改）；插件 staging/GPU addon。
- **Build integration**：`python3 scripts/build-turnip-darwin.py --target ios27`、`python3 scripts/build-adreno-metal-plugin.py --target ios27`、`python3 scripts/check-native-metal-frontend-host.py`。
- **K60 适配**：API 前端（MSAA 单采样、heap alias、swizzle、copy/raster、函数常量、内存统计 RAM/4 上限 2 GiB、队列容量）可复用；但提交后端绑定 Adreno740 ring/ABI，A730 需 `PongMetal`；`sheng-metal-flow=1`、`sheng-gpu-trace=1`、`sheng-wallpaper-freeze=1` 是 sheng 专用调试开关。

### 04. `adreno-pm4.md` — PM4 packet kit（17 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/AdrenoPM4`；pin 未记录。
- **定位**：Adreno PM4 packet 编码 kit，构造 Adreno740 提交的 command stream。
- **板级输入**：GPU 代际的 packet 支持、命令提交格式；具体寄存器/固件由使用它的 GPU 驱动提供。
- **Build integration**：board GPU archive recipe 把 `AdrenoPM4.c` 与所选 GPU driver 一起编译；先匹配 packet support 再启用前端。
- **K60 适配**：PM4 packet 表按 GPU 代际变化，A730 需逐项核对；可复用 packet builder 骨架，不能直接套 A740。

### 05. `air-nir.md` — 离线 AIR→NIR→IR3 编译器（17 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/AirNir`；pin 未记录。
- **定位**：离线 AIR→NIR→IR3 编译 kit，用于无 GPU 提交地验证 shader 路径。
- **板级输入**：无硬件输入；只吃 AIR/SPIR-V 输入与编译器配置。
- **Build integration**：按 kit README 构建；运行时 Metal 路径仍走 metal2vulkan + Turnip。
- **K60 适配**：与 GPU 代际无关的离线工具，可直接用来验证 K60 的 AIR/IR3 编译，不依赖 A730 上电。

### 06. `apple-key-store-state.md` — AppleKeyStore 状态（23 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/AppleKeyStoreState`；pin 未记录。
- **定位**：AppleKeyStore selector 与 state callback，适配所选 userland ABI；运行时服务和符号记录在 catalog。
- **板级输入**：`native_aks_device_id`（板级返回的 identity，用于派生 device key）；keybag 或 `sheng-aks-sls=3`（无 keybag 时报告无 passcode）。
- **Build integration**：`./unixnu build kernel -D /path/to/device`；catalog/profile 按依赖排序。
- **K60 适配**：keychain/配对（QcaBluetooth 也依赖）需要；当前 K60 用 pong software keybag 补丁，官方组件可作为后续官方化候选。注意文档明确：这是**软件 key wrapping，不是硬件 data protection**，reference key operations 与 device lock 不支持。

### 07. `arm-cpu.md` — ARM64 CPU/GIC/timer（17 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/ArmCpu`；pin 未记录。
- **定位**：ARM64 CPU、GICv3、ARM generic timer 驱动；发布 CPUs、interrupt controller、architectural timer。
- **板级输入**：`/cpus/cpu@N` 的 `reg`（MPIDR）、`compatible`、`timebase-frequency`、`/psci` method、GIC distributor/redistributor/CPU interface 资源；K60 现值：8 核 4×A510+3×A710+1×X2、MPIDR 0x000..0x700、PSCI `smc`、19.2 MHz。
- **Build integration**：`component:ArmCpu` → `build/armcpu/libArmCpu.a`；启用 kernel config 后按 platform adaptation 验 GIC/timer/PSCI。
- **K60 适配**：✅ 直接选；设备仓已在 `[components]` 与 `[kernel.archives]` 中包含。

### 08. `arm-dt-platform.md` — 设备树平台专家（17 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/ArmDTPlatform`；pin 未记录。
- **定位**：ARM device-tree platform expert；发布 CPU nub 和每个 `arm-io` child（来自 ADT）。
- **板级输入**：必须存在 `/cpus`、`/arm-io`、`/defaults`、`/options` 和 NVRAM proxy；ADT `reg`/`ranges` 需可解析。
- **Build integration**：`component:ArmDTPlatform` → `build/armdt-platform/libArmDTPlatform.a`；启用 personality 并供 ADT 节点。
- **K60 适配**：✅ 直接选；当前已包含。但 `dts/mondrian.dts` 只有 memory/UFS，`/arm-io` 子节点需要按外设补齐。

### 09. `arm-smmu4k.md` — SMMUv2 4 KiB 表 kit（19 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/ArmSmmu4K`；pin 未记录。
- **定位**：ARM SMMUv2 native 4 KiB table kit；构建并编程 stage-1/stage-2 context table；被 Adreno740 和存储驱动使用。
- **板级输入**：MMIO、context/stream 所有权、分配回调；具体 stream ID/context bank 由消费驱动提供。
- **Build integration**：无独立 archive；消费驱动 recipe 编译 `ArmSmmu4K*.c`，GPU archive 已包含。
- **K60 适配**：✅ kit 直接复用；K60 UFS 用 SMMU `0x15000000/0x100000`、stream `0xe0`、context 78；GPU/display 的 stream 需按 SM8475 补齐。批量 live map/unmap 语义（≤512 页 TLBIVAL，超过则 ASID invalidate）对 K60 同样适用。

### 10. `arm-virt-platform.md` — QEMU virt 平台（15 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/ArmVirtPlatform`；pin 未记录。
- **定位**：ARM virtual platform for QEMU，发布 QEMU virt 平台设备；用于 QEMU port。
- **板级输入**：QEMU virt 的 MMIO/中断/平台设备；无真实板级电源/时钟。
- **Build integration**：`build/armvirt-platform/libArmVirtPlatform.a`；按 QEMU testing 文档搭虚拟硬件和 entry fixture。
- **K60 适配**：❌ 不选；可作为无硬件时的 host/QEMU 回归夹具。

### 11. `ath12k-wifi.md` — Ath12k Wi-Fi（91 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/Ath12kWifi`；Sources 为 **pinned Linux v7.0.14**、匹配 headers、supplicant 2.12；具体 commit 未写。
- **定位**：在 XNU 上跑 Linux ath12k + mac80211 + cfg80211；MHI/QRTR/QMI 做设备启动，wpa_supplicant 2.12 做 userspace SME/WPA；普通数据包留在内核。
- **板级输入**：power、PCIe、BAR、MSI、DMA、firmware、网络接口；native interface `include/nw_abi.h`、`org.unixnu.wifi.control`；支持 Open 与 WPA2-PSK with PMF。
- **Build integration**：`build-ath12k-wifi.py` 输出对象清单；用户态 `build-wifi-userspace.py`；sheng 上 `sheng-wifi=5`、`sheng-wifi-aj=0`、`log-wifi=1`。固件经 VFS 从 `/private/var/ngpu/firmware/ath12k/WCN7850/hw2.0/` 加载；`package/WifiFirmware.h` 定义 loader/packer，`firmware/wcn7850/manifest.json` pin 大小与 SHA-256。
- **K60 适配**：❌ 官方组件只覆盖 WCN7850/QCC2072/QCN9274（ath12k）。K60 是 **QCA6490/WCN6855（PCI `17cb:1103`，ath11k）**，协议代际不同；只能参考其 mac80211/cfg80211/nw_abi 分层，实际走 `PongWifi`（ath11k）移植。

### 12. `community-adreno830.md` — Adreno 830 社区驱动（15 行）

- **仓库/源文件/pin**：`https://github.com/Shad0w23333/Adreno830`；板级仓库 `https://github.com/Shad0w23333/UniXNU-Pagani_SM8750`；明确 “started from Adreno740 `5c8c145`”。
- **定位**：OnePlus 13T（PKX110，SM8750）的 Adreno 830 (Gen8) 内核 GPU 驱动；bring-up GMU、CP、SMMU，服务 AdrenoMetal/metal2vulkan/Turnip。
- **板级输入**：A830 的 GPU/GMU 寄存器、SMMU、power/clock、firmware；具体值在 Pagani 设备仓。
- **Build integration**：文档未给命令；按 Adreno740 fork 体系构建。
- **K60 适配**：⚠️ A830 不是 A730，不能直接用；但它证明 **“Adreno740 fork 到新代际”** 的路径可行（桌面/系统 app/Widget/Control Center 已渲染，45 passed / 1 skipped，iPadOS 17.7.11 21H461），是 K60 `PongAdreno` 的最佳流程参照。

### 13. `community-native-adreno-fuxi.md` — Adreno fork（fuxi/SM8550）（15 行）

- **仓库/源文件/pin**：`https://github.com/ljhhkx529/NativeAdreno-fuxi`；pin 未记录。
- **定位**：Xiaomi 13（fuxi，SM8550）的 Adreno driver fork，跟踪官方 driver。
- **板级输入**：SM8550 GPU/GMU/SMMU/firmware；文档未列具体值。
- **Build integration**：文档未给；按官方 Adreno740 体系。
- **K60 适配**：SM8550 同代但 GPU 是 A740；只能作为 fork 维护方式参考，不能用于 A730。

### 14. `community-native-adreno-myron.md` — Adreno fork（myron/SM8850）（15 行）

- **仓库/源文件/pin**：`https://github.com/zg7681/NativeAdreno-myron`；pin 未记录。
- **定位**：Redmi K90 Pro Max / Poco F8 Ultra（myron，SM8850）的 Adreno fork；新增 A8XX register table、continuation thread、user-thread selection。
- **板级输入**：A8XX GPU/GMU 寄存器、用户线程选择参数；文档未给值。
- **Build integration**：文档未给。
- **K60 适配**：A8XX 不是 A730；可参考“新增 register table + 用户线程选择”的代码组织，不能直接跑。

### 15. `community-native-dwc3.md` — DWC3 USB3 DRD（nabu/SM8150）（15 行）

- **仓库/源文件/pin**：`https://github.com/Lux12138/NativeDwc3`；pin 未记录。
- **定位**：Xiaomi Pad 5（nabu，SM8150）的 native DWC3 USB3 DRD controller driver。
- **板级输入**：DWC3 寄存器、PHY、角色切换；文档未给具体值。
- **Build integration**：文档未给；repository present。
- **K60 适配**：DWC3 家族可参考，但 SM8150 的 PHY/角色线与 SM8475 不同；K60 现有自研 DWC3/usblog。

### 16. `community-native-emmc.md` — eMMC 驱动（merlinx）（15 行）

- **仓库/源文件/pin**：`https://github.com/Dracen-W/NativeEmmc`；pin 未记录。
- **定位**：Redmi Note 9（merlinx）的 native eMMC storage driver，向 XNU 发布设备存储。
- **板级输入**：eMMC 控制器/时钟/GPIO/分区；文档未给值。
- **Build integration**：文档未给。
- **K60 适配**：K60 是 UFS，不适用；只参考块设备发布结构。

### 17. `community-nativefocaltechtouch.md` — FT8203 GENI SPI 触摸（15 行）

- **仓库/源文件/pin**：`https://github.com/RigoLigoRLC/unixnu-nativefocaltechtouch`；pin 未记录。
- **定位**：Samsung Galaxy Tab S7 FE Wi-Fi（SM-T733）的 FT8203 touch controller，走 Qualcomm GENI SPI。
- **板级输入**：GENI SPI 控制器、FT8203 中断/复位/电源、firmware；文档未给具体值。
- **Build integration**：文档未给；社区仓库。
- **K60 适配**：K60 是 Goodix 不是 FT8203；但“QcomGeniSpi + 触摸协议 + HID”这条链路是 K60 的直接参照。该文档记录 basic tap/swipe，interrupt/suspend recovery 仍在进行。

### 18. `community-native-msdc.md` — MT8167 MSDC eMMC（15 行）

- **仓库/源文件/pin**：`https://github.com/mouseos/NativeMsdc`；pin 未记录。
- **定位**：Benesse TAB-A04-BR3（MT8167）的 MediaTek MSDC eMMC block driver；发布 root image windows 和 persistent Data store。
- **板级输入**：MSDC 寄存器、eMMC 分区、时钟/GPIO；文档未给值。
- **Build integration**：编译于 `xnu-10063.141.1` headers；寄存器序列沿用早期 a04br3 XNU port；**尚未 boot**。
- **K60 适配**：SoC 完全不同；只参考“root image windows + persistent Data”的块设备布局。

### 19. `community-native-ufs-alioth.md` — UFS fork（alioth）（15 行）

- **仓库/源文件/pin**：`https://github.com/FFT-infra/NativeUfs-alioth`；pin 未记录。
- **定位**：alioth（Redmi K40 / Poco F3 家族）的 UFS driver fork，跟踪官方 controller 和 root-read 路径。
- **板级输入**：UFS host/PHY/SMMU/分区；文档未给值。
- **Build integration**：文档未给。
- **K60 适配**：同类 UFS fork 的维护方式参考；SM8475 常量仍需自己填。

### 20. `community-native-ufs-myron.md` — UFS fork（myron）（15 行）

- **仓库/源文件/pin**：`https://github.com/zg7681/NativeUfs-myron`；pin 未记录。
- **定位**：myron 的 UFS driver fork，跟踪官方 NativeUfs controller/root-read 路径。
- **板级输入**：myron 的 UFS/SMMU/分区；文档未给值。
- **Build integration**：文档未给。
- **K60 适配**：fork 机制参考；不是 SM8475 实现。

### 21. `community-unixnu-nativemobiledisplay.md` — CPU/GPU 软件显示（15 行）

- **仓库/源文件/pin**：`https://github.com/RigoLigoRLC/unixnu-nativemobiledisplay`；pin 未记录。
- **定位**：Samsung Galaxy Tab S7 FE Wi-Fi（SM-T733）的 CPU software display、framebuffer copy 与 presentation。
- **板级输入**：GOP/framebuffer、面板分辨率/stride、vsync；文档未给值。
- **Build integration**：文档未给；社区仓库。
- **K60 适配**：⚠️ 重要参照：其 CPU 与 GPU scanout 路径可用；GOP scanout 无 vblank 中断，需 `sheng-vsync` 定时器补。K60 当前也是 GOP 软件呈现，可借这套“无 vblank 用 timer”的思路。

### 22. `community-unixnu-nativeramblock.md` — RAM-backed Data（15 行）

- **仓库/源文件/pin**：`https://github.com/RigoLigoRLC/unixnu-nativeramblock`；pin 未记录。
- **定位**：Tab S7 FE 的 persistent Data storage 与显式 reset 处理；用于 RAM-backed Data volume 和可选 persistent overlay。
- **板级输入**：Data 分区/窗口、reset 策略；文档未给值。
- **Build integration**：文档未给。
- **K60 适配**：K60 已有 `NativeRamBlock` fork，行为等价；可对照其 Data volume/reset 语义。

### 23. `community-unixnu-nativeufs.md` — SM7325 UFS/SMMU/root（15 行）

- **仓库/源文件/pin**：`https://github.com/RigoLigoRLC/unixnu-nativeufs`；pin 未记录。
- **定位**：Tab S7 FE 的 SM7325 UFS、SMMU 与 root storage 支持。
- **板级输入**：SM7325 UFS host、GCC、SMMU addressing、分区；文档未给值。
- **Build integration**：文档未给；controller selection、GCC diagnostics、可配置 SMMU addressing 已实现；firmware→XNU handoff 仍需设备执行。
- **K60 适配**：板级 UFS fork 的完整案例；SM7325 与 SM8475 不同，常量不可复用。

### 24. `darwin-boot.md` — UEFI bootloader（26 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/DarwinBoot`；pin 未记录。
- **定位**：UEFI bootloader；安装 loader protocol，把 kernel、ADT、trust cache、ramdisk 交给 XNU；不是 driver，但所有 XNU boot path 都用。
- **板级输入**：kernel/ADT/trust cache/ramdisk 的 payload 路径；`/chosen/memory-map/RootPolicies` 的 signed policy bundle（`kernel.macho.vroot`）。
- **Build integration**：把 DarwinBoot INF 加入目标 firmware 的 DSC/FDF，`./unixnu build firmware`；loader protocol 需先验证再选 XNU entry。
- **K60 适配**：K60 现用 `DarwinBoot22` fork（`board.toml` 的 `{tree}/drivers/DarwinBoot22`）；官方 DarwinBoot 只证明 arm64/arm64e `MH_EXECUTE`、PAuth/chained fixups、`MH_FILESET` 不支持；K60 16.6.1/18.x 的 boot_args ABI 仍以现有 fork 为准。

### 25. `device-tree-matching.md` — IOKit 匹配与 DT 规则（159 行）

- **仓库/源文件/pin**：无（指南）。
- **定位**：IOKit personality 匹配流程；`IOClass`、`IOProviderClass`、`IONameMatch`、`IOPropertyMatch`、`IOProbeScore`、`IOMatchCategory`、`IOResourceMatch`、`IOProviderMergeProperties` 的含义与优先级。
- **板级输入**：provider class（`IOPlatformExpertDevice`、`IOPlatformDevice`、`IOResources`、`IOMedia`、`IOBlockStorageDevice`）；ADT 的 `reg`/`interrupts`/`compatible`/`name`/`clock-frequency`；format 2 的 `reg` 是 little-endian u64 address/size 对。
- **Build integration**：personality 改则重编 kernel；ADT 改则重编 payload + boot image；overlay `[[overlay]] file = "board.dtbo"`；`[[dt_patch]] op = "set"`；Darwin path 读 `.adt` sidecar。
- **K60 适配**：每个新驱动都要有 personality + DTS compatible；示例 `NativeUfs` 匹配 `qcom,sm8550-ufshc`，K60 要写 `qcom,sm8475-ufshc`。K60 目前的 DTS 节点极少，这是所有外设 Bring-up 的前置工作。

### 26. `gop-framebuffer.md` — GOP framebuffer 呈现（25 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/GopFramebuffer`；pin 未记录。
- **定位**：用 firmware GOP handoff 做 framebuffer presentation；通过 `PE_current_console` 读 firmware framebuffer，接入 MobileFramebuffer ABI；board hooks 提供 display policy 和 GPU scanout 集成。
- **板级输入**：firmware framebuffer/PE console、display policy、GPU scanout；direct display 每个 swap 在首次成功 GPU fence query 时固定 target，busy 每 200 µs 重试，250 ms 记 slow frame，上一帧保持到完成/取消。
- **Build integration**：`./unixnu build kernel -D /path/to/device`。
- **K60 适配**：K60 当前是 MiniIOMobileFramebuffer 纯 CPU 缩放 + memcpy，1440×3200；GopFramebuffer 的 builder 只覆盖 iOS 17/27，16.6.1 需另写 legacy ABI builder。可先参考其 display policy/swap 等待语义，不急于替换现有显示栈。

### 27. `kexts.md` — Kext bundle staging（166 行）

- **仓库/源文件/pin**：无（指南）；ABI 锚点 `xnu-10063.141.1` / iOS 17 deployment target。
- **定位**：kext bundle 的 staging 流程，面向实现 revision 2 且接受 kext request 的 loader；**shipped DarwinBoot 使用 built-in drivers，会拒绝 staged kexts**。
- **板级输入**：bundle 目录、`Info.plist`（`CFBundleIdentifier`、`OSBundleLibraries`、`IOKitPersonalities`）、thin AArch64 `MH_KEXT_BUNDLE` 可执行文件。
- **Build integration**：entry kext `[[entry.kext]] bundle=...`；kit kext `[[kext]] bundle/entry/plist/executable/enabled`；`xcodebuild -target ... -sdk iphoneos`，`MODULE_TYPE=KEXT`、`MACH_O_TYPE=mh_kext_bundle`；AMFI 需要 trust cache 中的 CD hash。
- **K60 适配**：K60 的 `DarwinBoot22` 没有 revision 2 kext 注入路径；继续走 built-in XNU driver，不把希望放在 kext bundle 上。

### 28. `overview.md` — 驱动开发总览（80 行）

- **仓库/源文件/pin**：无（指南）。
- **定位**：三层驱动模型：UEFI driver（EDK II `.efi`，firmware dispatch / `[[driver]]` / kit）、built-in XNU driver（静态 archive 链入 kernel）、kext bundle（UEFI staging，loader 注入）。
- **板级输入**：按层选择；XNU 侧通过 `IOKitPersonalities` 匹配 provider；built-in personality 在 `iokit/KernelConfigTables.cpp`，kext 在 `Info.plist`。
- **Build integration**：`drivers/<Name>` 源码、`kits/<Name>` kernel library、`package/UniXNUPkg/Driver` UEFI driver、`package/UniXNUPkg/Test` 测试；设备 profile 选 catalog 组件，feed/local override 供源。
- **K60 适配**：K60 的平台/存储/GPU/显示/输入都应走 built-in XNU；UEFI 层只做 pre-XNU display/input/storage；kext 不作为主路径。

### 29. `qca-bluetooth.md` — QCA Bluetooth（110 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/QcaBluetooth`；pin 未记录；sources 为 Linux `btqca.c`、Debian sheng、Renoir UART.SK reference。
- **定位**：把 Qualcomm WCN7850 UART controller 接到 Apple Bluetooth stack；跑 locked Linux `btqca.c` 初始化、H4 framing、IBS；UART.SK/Skywalk 把 H4 送给 `bluetoothd`，Apple stack 管扫描/配对/密钥/BLE/音频 profile。
- **板级输入**：WCN power、clocks、pins、DMA mappings、IRQs、firmware；`WcnPower.h` 独立 Wi-Fi/BT vote，最后一个 owner 释放。sheng：`sheng-bluetooth=1`、GENI SE6 `0x898000`、IRQ 493、QUP2 DMA SID `0x423`、51.2 MHz → 3.2 Mbaud、DMA bypass bank 与 touch/audio 共享、GPIO79 wake、UART protocol-2 microcode。GENI 用 4×2048 B RX + 1×4096 B TX buffer；hard IRQ 屏蔽线路并唤醒 worker；RX backpressure 保留 buffer 并停 RFR；TX completion 检查 DMA 与 wire drain；IBS 控制字节只插在完整 H4 包之间；clock-off 要求 RX quiescent + armed wake source。板级要导出 `/arm-io/bluetooth` + IOService，带 H4 encoding、baud、stable private address。
- **Build integration**：`payload.runtime` 选 `build-bluetooth-userspace.py`，stage signed BlueTool、`bluetoothd`、`QcaBTType0.dylib` 和 pinned firmware；只读 union 暴露 `/usr/lib`、`/usr/sbin`；Wi-Fi/BT 共享 signed launchd cache。测试脚本 `tools/test-runtime.py`、`test-geni.py`、`build-bluetool.py`、`build-type0.py`、`check-kernel.py`，以及 sheng board checks。
- **K60 适配**：K60 QCA6490 BT 走 **GENI UART / HS-UART，QUPV3_2 SE20 `0x894000`，IRQ 587，GPIO76/77/78/79**；固件预计 `htbtfw21.tlv`/`htnv21.bin`（`[未核]`）。官方 `qbt`/GENI 框架可参考，但 WCN7850 与 QCA6490 的固件/控制器不同；K60 是零先例，需新写 QCA6490 驱动。

### 30. `qcom-baseband.md` — Qualcomm baseband bridge（13 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/QcomBaseband`；作者 HoshinoYumeka（@chiba233）；pin 未记录。
- **定位**：QMUX/QRTR + QMI CTL、SAHARA endpoint、AppleBaseband IOKit services、IPA/GSI/QMAP code；SC7180 IPA v4.2 data path。
- **板级输入**：modem boot、firmware、power、DMA、GLINK/QRTR、rmtfs；`baseband/QcomBaseband.h` 定义 transport hooks。
- **Build integration**：`scripts/build-qcom-baseband.py` 从 XNU compile records 构建 bridge archive；`--coachz` 加 SC7180 IPA adapter；输出 `build/qcom-baseband/libQcomBaseband.a`。
- **已验证行为（Coachz）**：IMEI/ICCID 显示、LTE roaming CS/PS attached、信号格与 data-port bindings；ABM RX queue 每 channel 1024 帧；carrier bundle PRI/GRI 被接受；IPv4 经 `pdp_ip0`–`pdp_ip3` + IPA 可上网；IPv6、APN 编辑、长会话与 eSIM provisioning 未完成；eSIM 在 Settings 显示不完整页面。
- **K60 适配**：K60 的 modem/蜂窝不在当前驱动范围；SC7180 IPA 与 SM8475 不同。除非后续做 cellular，否则不选。

### 31. `qcom-dwc3.md` — Qualcomm DWC3 USB（71 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/QcomDwc3`；pin 未记录。
- **定位**：在 Qualcomm DWC3 controller 上跑 Apple USB device/host stack；`QcomDwc3Xdci` 继承 `AppleUSBXDCI`，`QcomDwc3Xhci` 继承 `AppleUSBXHCI`。
- **板级输入**：eUSB2 repeater、QMP PHY、retimer、rails、SMMU context；sheng `sheng-usb=1`，eUSB2 reference 38.4 MHz，stream `0x40` 用独立 stage-1 context（write-back inner shareable，因为 `AppleUSBXDCI` 不做 cache maintenance）。
- **Build integration**：AppleUSBXDCI 没有 personality，驱动在注册 subclass 前先 load kext；prelink roots 加 device/host stacks，排除 `AppleOnboardSerial`、`AppleSMC`；boot args `sheng-usb=1/2/3`、`sheng-usb-host=<s>`、`sheng-usb-back=<s>`、`log-sys=1`；`scripts/gen-usb27-abi.py`、`gen-usb27-host-abi.py` 重生成 class layouts。
- **K60 适配**：K60 DWC3 core `0xa600000`（QSCRATCH `0xa6f8800`）、eUSB2 PHY `0x88e3000`、QMP `0x88e8000`，SMMU stream 实测 `0x0`（官方 sheng 为 `0x40`）；QcomDwc3 的 ABI 是 iPadOS 27/24A446，K60 16.6.1 不可直接用，保留自研 DWC3/usblog。

### 32. `qcom-geni-spi.md` — GENI SPI 控制器（19 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/QcomGeniSpi`；pin 未记录。
- **定位**：Qualcomm GENI serial-engine SPI controller operations；调用者提供 register access 与 platform callbacks。
- **板级输入**：QUP wrapper/SE base、SPI mode/max frequency、SMMU stream、GCC vote/halt/DFS、TLMM pinmux；参考 touch stack 与 `ShengNovatekTouch` 一起用。
- **Build integration**：`./unixnu build kernel -D /path/to/device`。
- **K60 适配**：✅ transport 直接复用；K60 Goodix 走 SE4 `0x990000`、CS0；具体 QUP/GCC/TLMM 常量按 K60 DTS 填。

### 33. `ram-block.md` — RAM-backed block storage（19 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/RamBlock`；pin 未记录。
- **定位**：sparse RAM-backed block storage，可选 persistent backing callbacks；把 Data image 发布为 block device。
- **板级输入**：`native_ufs_store` callbacks、Data image/窗口、reset policy。
- **Build integration**：`./unixnu build kernel -D /path/to/device`。
- **K60 适配**：K60 已有 `NativeRamBlock` fork；官方 RamBlock 可作为后续统一接口的候选，前提是 `native_ufs_store` 契约对齐。

### 34. `repositories.md` — 驱动仓库总表（81 行）

- **仓库/源文件/pin**：28 个官方 driver 仓库（列表见文档 7–38 行）、12 个社区驱动（40–57 行）、9 个设备 fork（59–73 行）；全部没有 commit pin。
- **定位**：官方仓库由 UniXNU 维护；社区仓库由 owner 维护，只从设备仓链接；设备 fork 跟踪官方 driver，不单列页面。
- **板级输入**：不涉及具体硬件；按 repository 的 layer（XNU GPU / Metal / storage / input / SPI / baseband / crypto / keystore / virtio / touch / prelink / Wi-Fi / Bluetooth / USB / CPU / platform / SMMU / firmware kit / loader / root trust / preflight）分类。
- **Build integration**：规则：一硬件一仓库；SoC/device profile 按 catalog ID 选组件；feed/submodule 供源；官方设备或 generic stack 可贡献到 UniXNU org；其他保持独立 submodule；所有 driver repo 带 `unixnu` topic。
- **K60 适配**：官方 28 个条目里没有 SM8475/K60；社区 12 个也没有 K60。K60 必须走“设备仓本地 fork + 新增 catalog 组件”的方式。

### 35. `sheng-backlight.md` — KTZ8866 背光（69 行）

- **仓库/源文件/pin**：源码 `https://github.com/UniXNU/UniXNU-sheng/blob/main/package/AppleARMBacklight.cpp`；无独立组件仓库、无 pin。
- **定位**：把 sheng 面板的两颗 KTZ8866 backlight controller 接到 CoreBrightness。
- **板级输入**：两颗都在 I2C `0x11`：一颗在 QUP wrap 1 SE1 `0xa84000`（SPI 354），一颗在 I2C hub engine 2 `0x988000`（SPI 466）；同一 11-bit level 0–2047，`BL_BRT_LSB`（0x04，bits 2:0）+ `BL_BRT_MSB`（0x05）；firmware/clock/SCL timing 保持 bootloader 状态，每步 25 ms deadline。
- **Build integration**：板级 `AppleARMBacklight` 类（`ShengBacklight` + `getMetaClass` 回答 `AppleARMBacklight`）；boot args `sheng-backlight=1`、`sheng-backlight-control=0`、`log-display=1`；iPadOS 27 需 `BacklightMode.m` 改 `backboardd` 的 `initBLControl:` 为 mode 1，并经 AppSync 替换 signed `backboardd`。
- **K60 适配**：❌ K60 没有独立背光 IC，面板走 DCS `0x51` 调光；KTZ8866 寄存器不能照搬。可复用其 CoreBrightness 属性契约（`backlight-control`、`IODisplayParameters.brightness`、`BrightnessMilliNits`、`backlight-marketing-table`、`Lmax/Lmid/LminProduct`、`backlight-calibration-parameters`），传输层要改成 DSI DCS。

### 36. `sheng-hid-input.md` — HID 输入集成（21 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/ShengHidInput`；pin 未记录。
- **定位**：触摸与按键接入 IOHIDFamily；使用 board touch state 和 `IOHIDFamily 2031.120.4` ABI。
- **板级输入**：board touch policy、touch 快照（`native_touch_seq` 等）、所选 OS ABI；archive builder 需要 qualified prelinked candidate 和 ABI records。
- **Build integration**：`./unixnu build kernel -D /path/to/device`；archive builder 读取 qualified prelinked candidate 与 ABI records（具体输出路径见组件目录）。
- **K60 适配**：⚠️ Goodix 触摸可以复用它的 HID 发布层和 sequence-counter 快照契约；`IOHIDFamily 2031.120.4` 是 iOS 17 口径，16.6.1/18.x 必须先做 ABI 审计。

### 37. `sheng-novatek-touch.md` — Novatek NT36532E 触摸（154 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/ShengNovatekTouch`（`NvtTouchCore.c`、`NvtProtocol.c/.h`）；`https://github.com/UniXNU/QcomGeniSpi`（`GeniSpi.c`）；`UniXNU-sheng/package/TouchBoard.h`、`TouchProbe.cpp`、`TouchBoardTests.c`；`ShengHidInput/NativeHidInput.cpp`；pin 未记录。
- **定位**：Novatek NT36532E 完整触摸驱动，也是新触摸驱动的教学样例；纯逻辑、协议、板级 probe、HID 四层分离。
- **板级输入**：`nvt_bus`（xfer/delay 回调）；40×60 16-bit matrix；72 startup frames 中位数 reference；THP 32-byte header；firmware ILM/DLM；QUP wrapper/SE base/size、SMMU stream/apps SMMU base、GCC vote/halt/DFS、TLMM GPIO/function/drive、SPI mode/max freq；`TouchBoard.h` 每个常量带来源。
- **Build integration**：`sheng-touch=1..4` 分阶段 probe（GCC/DFS/pins/SE identity → vote clocks/pins → GENI SPI/clock/chip id → firmware download/scan）；DMA buffer 物理连续、apps SMMU bypass、显式 clean/invalidate；HID globals `native_touch_seq/count/xs/ys/ids`；`sheng-tlog=1` + `decode-sheng-touchpath.py`。
- **K60 适配**：❌ Novatek core/protocol 不能用于 Goodix；但这是 K60 触摸驱动的最佳架构模板：纯 core + bus 接口 + 板级常量头 + 分阶段 boot arg + HID 快照。K60 Goodix 需要重写 `NvtProtocol` 对应层和 firmware download。

### 38. `sheng-preflight.md` — UEFI preflight（17 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/ShengPreflight`；pin 未记录。
- **定位**：板级 UEFI preflight 检查，构建前验证 firmware volume、memory map、boot inputs。
- **板级输入**：目标板 firmware volume/memory layout；`[firmware] preflight` 选择脚本。
- **Build integration**：`./unixnu build firmware` 在构建 FD 前调用。
- **K60 适配**：⚠️ 需写 K60 自己的 preflight（firmware volume、arena `[0x900000000,0xa40000000)`、UFS/内存窗口）；官方实现只针对 sheng。

### 39. `sheng-ufs.md` — ShengUfs（39 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/ShengUfs`；pin 未记录。
- **定位**：SM8550 UFS storage path；拥有 host controller、SMMU mappings、command queues、root reads；板级集成包括 clock 资源、persistent Data/log regions；按请求给 display bank（`sheng-dpu-scanout`）和 WiFi endpoint（`sheng-wifi=2+`）stage-1 windows，默认关。
- **板级输入**：SM8550 UFS host/PHY/clocks/SMMU；board power policy、storage layout；`CONFIG_XNU_NATIVE_UFS=y`；runtime class `NativeUfs`。
- **Build integration**：`./unixnu build kernel -D /path/to/device`；设备仓以 submodule 供 ShengUfs；Wi-Fi DMA window 128 MiB @ IOVA `0x10000000`，64 个 2 MiB block，独立 SMMU context bank；`scripts/check-wifi-dma.py`。
- **K60 适配**：⚠️ SM8475 UFS host 同为 `0x1d84000/0x3000`，但 PHY、GCC、SMMU stream `0xe0`、context 78 与 sheng 参考值不同（sheng 的 stream 见 `docs/porting/ufs.md`）；K60 现有 `PongUfs`，ShengUfs 只作为统一后端方向。

### 40. `sm8550-platform.md` — SM8550 GPU 平台 kit（47 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/UniXNU-sm8550-common`；pin 未记录。
- **定位**：SM8550 GPU platform operations：GMU、GPU SMMU、RPMh command database；不是 driver，是 board code。
- **板级输入**：SoC SM8550 寄存器映射/RPMh resource name、GPU firmware、`ArmSmmu4K`、`AdrenoFirmware`；`ShengGmu.c`（GMU start/halt/memory window/interrupt/keepalive）、`ShengGpuSmmu.c`（GPU stage-1/fault）、`ShengGmuCommandDb.c`（RPMh by name/level/vote）；`build_stage="embedded"`，无独立 archive。
- **Build integration**：board `[components] include = ["Sm8550Platform", "Adreno740", "AdrenoMetal", "AdrenoFirmware", "ArmSmmu4K"]`；`./unixnu build kernel`。
- **K60 适配**：❌ SM8550 专用；SM8475 没有等价 kit。K60 的 A730 GMU/GPU SMMU/RPMh command DB 必须从 `PongPlatform24`/`PongPower` 移植或新写。

### 41. `software-aes.md` — 软件 AES（19 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/SoftwareAES`；pin 未记录。
- **定位**：通过 XNU AES helpers 和 `IOAESAccelerator` ABI 提供软件 AES-CBC。
- **板级输入**：所选 XNU/IOCryptoAcceleratorFamily 接口；无硬件加速器要求。
- **Build integration**：`./unixnu build kernel -D /path/to/device`。
- **K60 适配**：⚠️ 可用于 K60 无硬件 AES 时的 keybag/crypto 路径；16.6.1 的 `IOAESAccelerator` ABI 需审计。

### 42. `uefi-drivers.md` — UEFI 驱动开发（221 行）

- **仓库/源文件/pin**：无（指南）。
- **定位**：UEFI driver = EDK II `.efi` module，跑 boot services，可发布 protocol、绑定设备、为下一阶段准备硬件。
- **板级输入**：DEC/protocol GUID、INF、DSC/FDF、`LoadOptions`、`[[driver]] path/args/connect/enabled`、`fv:<GUID>`；`UniXNURamDiskDxe` 可把 Mu-Silicium FDT initrd 暴露为只读 Block I/O。
- **Build integration**：`build -p MyPkg/MyPkg.dsc -a AARCH64 -b DEBUG -t CLANGPDB -n 8`；`package/UniXNUPkg/UniXNUPkg.dsc`；`package/build.sh` 复制到 `Build/Out/AARCH64-DEBUG`；driver model `EFI_DRIVER_BINDING_PROTOCOL`（Supported/Start/Stop）；日志格式 `UNIXNU: driver ... started/load failed/start failed`。
- **K60 适配**：✅ 方法直接可用；K60 的 uefi-mondrian 已有 ButtonsDxe/SPMDxe/PmicDxe/GOP，K60 preflight、UEFI 显示/输入可继续按此写。

### 43. `verified-root.md` — 根信任工具（17 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/VerifiedRoot`；pin 未记录。
- **定位**：Verified root trust tooling；构建并检查 owner-signed root policies。
- **板级输入**：owner policy、root image/trust inputs、storage archive。
- **Build integration**：board recipe 构建 owner policy + consuming storage archive；按 integrity/boot policy 检查。
- **K60 适配**：⚠️ 可选；若 K60 走 owner root chain，可复用；当前 boot chain 用 pong 自有信任路径。

### 44. `virtio-mmio-block.md` — VirtIO MMIO block（19 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/VirtioMmioBlock`；pin 未记录。
- **定位**：VirtIO 1.2 MMIO block transport，split queue。
- **板级输入**：兼容 MMIO device、中断路由、所选 storage ABI；owner-root path 还要 verified block policy archive。
- **Build integration**：`./unixnu build kernel -D /path/to/device`。
- **K60 适配**：❌ 仅 QEMU/virtual；K60 物理机不用。

### 45. `virtio-mmio-console.md` — VirtIO MMIO console（17 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/VirtioMmioConsole`；pin 未记录。
- **定位**：VirtIO 1.2 MMIO console transport，split queue；传 logs/diagnostic bytes。
- **板级输入**：MMIO range、interrupt route。
- **Build integration**：`./unixnu build kernel -D <device-repository>`。
- **K60 适配**：❌ 仅 QEMU/virtual；K60 用 UART/framebuffer console。

### 46. `xnu-drivers.md` — Built-in XNU driver 指南（270 行）

- **仓库/源文件/pin**：无（指南）；示例基于 XNU compile record `.cpo.json`。
- **定位**：UniXNU 的 XNU driver = C++ IOKit class，编译成 static archive，链入 kernel，经 `KernelConfigTables.cpp` personality 启动。
- **板级输入**：`drivers/MyDriver/{MyDriver.cpp,MyDriver.h,Info.plist}`；provider properties `reg`（format 2 LE u64 pairs）、`interrupts`、`compatible`、`name`、`clock-frequency`；DMA 必须过 device IOMMU/SMMU，`ArmSmmu4K` 提供 4 KiB 表。
- **Build integration**：读 `.cpo.json` 替换 source/output 编译；object ABI `0xfeedfacf`/CPU `0x0100000c`/filetype 1/subtype 0/build version platform 2 min `0x110000`；`xcrun ar rcs build/my-driver/libMyDriver.a`；`scripts/build-xnu-4k-baseline.sh` 加 `-force_load` + `KERNEL_ARCHIVE_DEPENDENCIES`；defconfig `CONFIG_XNU_MY_DRIVER=y`；personality 用 `-DXNU_MY_DRIVER=1` 注入 `KernelConfigTables.cpo_CFLAGS_ADD`；中断用 `IOInterruptEventSource`；测试 compile/ABI/host/QEMU/hardware。
- **K60 适配**：✅ K60 所有 built-in 驱动的标准施工图；K60 的 `build-xnu-4k-baseline.sh` 已按此模式改过（`KERNEL_EXTRA_ARCHIVES`/`force_load`）。

### 47. `xnu-prelink.md` — XnuPrelink（83 行）

- **仓库/源文件/pin**：`https://github.com/UniXNU/XnuPrelink`；pin 未记录。
- **定位**：kernel prelink emitter + ABI tooling；把 built XNU 与 selected original kexts 绑定并写 prelink plan；OS profile 供 kernelcache pin、roots、slide、ABI。
- **板级输入**：kernelcache pin/roots/slide/ABI、`--fileset-map`（匹配 input hash + matcher version）、`--fileset-reference`（带符号的参考 kernel）；24A446 fixture 的 23 个 import identity、13 个 vnode op descriptor、4 个 metaclass pointer slot、`gIODTPHandleKey`/`audio_active`。
- **Build integration**：`./unixnu build prelink -D /path/to/device`；iOS 27 reference 先 `build-fileset-release-reference.py --tree . --lto`，保持 LTO；`--allow-missing` 只产实验镜像并列 unresolved target；`unixnu kernel --skip-prelink` 把 native executable 当 `kernel.macho`，`unixnu prelink --skip-prelink` stage 现有 build。
- **K60 适配**：⚠️ 官方文档完全围绕 iOS 27 fileset/24A446；K60 当前用 `kits/NativePrelink` fork（darwin22/darwin24），16.6.1/20G81 没有官方通过记录。K60 是否切 XnuPrelink 取决于目标 OS 的 kernelcache/kext 集合，不能照抄 24A446 fixture。

---

## ② K60 组件选型表（硬件 → 组件 → 板级输入）

> 说明：`K60 现值` 来自设备仓 `board.toml`、`dts/mondrian.dts` 与 `docs/plans/` 既有记录；`[未核]` 表示需上机或读 DTS 确认。`文档依据` 是 `docs/drivers/` 中对应页面。

### 2.1 启动、平台、存储

| 硬件 / 子系统 | 组件（文档依据） | 板级输入（DTS / 寄存器 / GPIO / 时钟 / 固件） | K60 判定 |
|---|---|---|---|
| CPU / GIC / timer | `ArmCpu`（`arm-cpu.md`） | `/cpus/cpu@N` 的 `reg`（MPIDR）、`compatible`、`timebase-frequency`；`/psci method`；GICv3 distributor/redistributor/CPU interface。K60 现值：8 核 4×A510+3×A710+1×X2，MPIDR 0x000..0x700，PSCI `smc`，19.2 MHz | ✅ 直接选；设备仓已包含 |
| 平台设备树 | `ArmDTPlatform`（`arm-dt-platform.md`） | `/cpus`、`/arm-io`（`#address-cells=2`、`#size-cells=2`、identity `ranges`）、`/defaults`、`/options`、NVRAM proxy；每个 `arm-io` child 的 `reg`/`interrupts`/`compatible`/`unixnu,adt-name`。K60 现值：`dts/mondrian.dts` + `sm8475.dtsi`，当前仅有 `/memory`、`ufs@1d84000` | ✅ 直接选；DTS 需补全 |
| SMMU | `ArmSmmu4K`（`arm-smmu4k.md`） | MMIO base、stage-1/2 context/stream、分配回调。K60 现值：UFS SMMU `0x15000000/0x100000`、stream `0xe0`、context 78、match groups 120；GPU/display stream `[未核]` | ✅ kit 复用 |
| UFS | `ShengUfs`（`sheng-ufs.md`）/ `PongUfs`（K60 现用） | `ufs@1d84000`：`reg = <0 0x1d84000 0 0x3000>`、`compatible = "qcom,sm8475-ufshc"`、`unixnu,adt-name = "ufshc"`、PHY `0x1d80000/0x2000` `[未核]`、GCC `0x187000`、SPI 265、SMMU `0xe0`/ctx 78；分区 `first_lba=53342976`、`last_lba=61731583`、`lba_bytes=4096`；`CONFIG_XNU_NATIVE_UFS=y` | ⚠️ ShengUfs 需换 SM8475 常量；K60 保留 PongUfs |
| RAM block / Data | `RamBlock`（`ram-block.md`） | `native_ufs_store` 持久化回调、Data image 窗口、reset policy。K60 现值：`NativeRamBlock` + Data window | ✅ 接口可复用（K60 已有 fork） |
| 启动 loader | `DarwinBoot`（`darwin-boot.md`） | kernel/ADT/trust cache/ramdisk；arm64/arm64e `MH_EXECUTE`；`/chosen/memory-map/RootPolicies` 的 signed policy bundle。K60 现值：`DarwinBoot22` fork（`{tree}/drivers/DarwinBoot22`） | ⚠️ 官方是 27 口径；K60 用现有 fork |
| 预链接 | `XnuPrelink`（`xnu-prelink.md`） | kernelcache pin、roots、slide、ABI；fileset map/reference。K60 现值：`kits/NativePrelink`，darwin22/darwin24 迁移中 | ⚠️ 16.6.1/20G81 无官方证据；保留现有 |
| UEFI 驱动框架 | `uefi-drivers.md` | EDK2 DEC/INF/DSC/FDF、`[[driver]] path/args/connect/enabled`、`fv:<GUID>`；K60 现值：uefi-mondrian 已有 ButtonsDxe/SPMDxe/PmicDxe/GOP | ✅ 方法直接可用 |

### 2.2 显示、背光、输入

| 硬件 / 子系统 | 组件（文档依据） | 板级输入（DTS / 寄存器 / GPIO / 时钟 / 固件） | K60 判定 |
|---|---|---|---|
| 显示 scanout | `GopFramebuffer`（`gop-framebuffer.md`） | `PE_current_console` firmware framebuffer、MobileFramebuffer ABI、display policy/GPU scanout hooks、swap fence 200 µs/250 ms。K60 现值：MiniIOMobileFramebuffer 纯 CPU 1440×3200 BGRA，`display-scale=3`；DSI host/PHY/PLL `[未核]` | ⚠️ 官方 builder 仅 iOS 17/27；16.6.1 需自写 ABI；先保留现有软件栈 |
| 背光 | `ShengBacklight`（`sheng-backlight.md`，无 catalog） | KTZ8866×2 @ I2C 0x11：QUP SE `0xa84000`（SPI 354）/ `0x988000`（SPI 466）、11-bit 0..2047、`BL_BRT_LSB 0x04` / `BL_BRT_MSB 0x05`、25 ms/step；CoreBrightness 属性表。K60 现值：无独立背光 IC，面板 DCS `0x51` 调光 `[未核]` | ❌ 不能照搬；需 DSI DCS 调光 + CoreBrightness 契约 |
| 触摸传输 | `QcomGeniSpi`（`qcom-geni-spi.md`） | QUP wrapper/SE base、GENI SPI mode/max freq、SMMU stream、GCC vote/halt/DFS、TLMM pinmux。K60 现值：SE4 `0x990000`、CS0、IRQ GPIO21（flags `0x2008`）、reset GPIO20、AVDD GPIO71/PM8350C LDO2 1.8 V | ✅ transport 可复用 |
| 触摸控制器 | `ShengNovatekTouch`（`sheng-novatek-touch.md`，架构参考） | 40×60 matrix、72 startup frames、THP header、firmware ILM/DLM、`nvt_bus` xfer/delay。K60 现值：Goodix `xiaomi,m11a-spi`、`goodix_firmware_m11a`、`goodix_cfg_group_m11a`、panel max 14400×32000 | ❌ Novatek 核心不适用；新写 Goodix |
| HID / 触摸上报 | `ShengHidInput`（`sheng-hid-input.md`） | `native_touch_seq/count/xs/ys/ids` 快照、`IOHIDFamily 2031.120.4` ABI。K60 现值：Goodix 可复用该发布层 | ⚠️ 复用接口；16.6.1/18.x ABI 需审计 |
| 实体键 | 无官方组件（`ButtonProbe.cpp` 板级参考） | `/buttons compatible/device_type/button-names/home-button-type`、PMIC PON/GPIO、interrupt parent/polarity。K60 现值：UEFI `K60KeypadDeviceLib`/SPMDxe/PmicDxe 已有，XNU 侧无驱动 | ❌ 需新写 XNU 按键驱动 |

### 2.3 GPU / Metal

| 硬件 / 子系统 | 组件（文档依据） | 板级输入（DTS / 寄存器 / GPIO / 时钟 / 固件） | K60 判定 |
|---|---|---|---|
| GPU 内核 | `Adreno740`（`adreno740.md`）/ `PongAdreno`（K60 现用） | GPU/GMU 寄存器、interrupts、`iommus`、`power-domains`、`clocks`/`clock-names`、`opp-table`、`qcom,gmu` child；firmware。K60 现值：A730 v3 `0x07030002`、`gmu_gen70000.bin`、`a730_sqe.fw`、`a730_zap.*` `[未核]` | ❌ A740 ≠ A730；用 PongAdreno |
| GPU 平台（GMU/SMMU/RPMh） | `Sm8550Platform`（`sm8550-platform.md`） | `ShengGmu.c`：GMU start/halt/memory windows/interrupt/keepalive；`ShengGpuSmmu.c`：GPU stage-1/fault；`ShengGmuCommandDb.c`：RPMh resource by name/level/vote；`build_stage="embedded"`。SM8550 专用 | ❌ 需 SM8475 版（PongPlatform24/PongPower 移植） |
| Metal 前端 | `AdrenoMetal`（`adreno-metal.md`）/ `PongMetal`（K60 现用） | `MTLAddDevice`、metal2vulkan、Turnip、插件 staging、GPU addon、`Library/Caches/org.unixnu.metal`；K60 现值：PongMetal | ⚠️ 前端 API 可参考，A730 后端换 PongMetal |
| GPU 固件 / PM4 / 离线编译 | `AdrenoFirmware`（`adreno-firmware.md`）/ `AdrenoPM4`（`adreno-pm4.md`）/ `AirNir`（`air-nir.md`） | GMU firmware/HFI、PM4 packet 编码、AIR→NIR→IR3；K60 固件按 A730 重 pin（`gmu_gen70000.bin`/`a730_sqe.fw`） | ⚠️ HFI/PM4 按代际适配；AirNir 可离线复用 |

### 2.4 连接：Wi-Fi、蓝牙、USB

| 硬件 / 子系统 | 组件（文档依据） | 板级输入（DTS / 寄存器 / GPIO / 时钟 / 固件） | K60 判定 |
|---|---|---|---|
| Wi-Fi | `Ath12kWifi`（`ath12k-wifi.md`，WCN7850/ath12k）/ `PongWifi`（QCA6490/ath11k，K60 候选） | PCIe RC/BAR/MSI/DMA/rails/GPIO/firmware。K60 现值：QCA6490/WCN6855，PCI `17cb:1103`，PCIe0 `0x1c00000`，BAR0 `0x60200000/2 MiB`，SID `0x1c01`，IOVA `0xA0000000/256 MiB`，MSI SPI140，六路 WLAN rail + `qcom,vreg_ipa="s3e"`，GPIO80/81/82/94/95/96/204 | ❌ Ath12kWifi 不适用；移植 PongWifi |
| 蓝牙 | `QcaBluetooth`（`qca-bluetooth.md`，WCN7850） | GENI UART SE/IRQ/DMA SID/GPIO/clock/firmware；板级导出 `/arm-io/bluetooth` + IOService。K60 现值：SE20 `0x894000`、IRQ587、GPIO76/77/78/79、`qcom,wakeup-byte=0xfd`；固件 `htbtfw21.tlv`/`htnv21.bin` `[未核]` | ⚠️ qbt 框架参考；新写 QCA6490 驱动 |
| USB | `QcomDwc3`（`qcom-dwc3.md`） | DWC3 base + Apple window `+0xc000`、IRQ、SMMU stream、eUSB2 38.4 MHz、QMP/retimer/rails、UCSI GLINK。K60 现值：DWC3 `0xa600000`、QSCRATCH `0xa6f8800`、eUSB2 `0x88e3000`、QMP `0x88e8000`、SMMU stream `0x0`（实测） | ⚠️ QcomDwc3 是 24A446 ABI；K60 16.6.1 保留自研 DWC3/usblog |

### 2.5 音频、DSP、电源

| 硬件 / 子系统 | 组件（文档依据） | 板级输入（DTS / 寄存器 / GPIO / 时钟 / 固件） | K60 判定 |
|---|---|---|---|
| 音频功放 | 无 catalog；参考 `AudioProbe.cpp`、`ShengAudioReach.c/h`、`ShengGpr.c/h`、`ShengAudioService.cpp`、`ShengAudioPlugIn.c`、`ShengCs35l43.c`（`docs/porting/power.md`，非 drivers 页） | I2C/地址、reset GPIO、IRQ、spk-switch、TDM、ADSP carveout、AudioReach/GPR graph/subgraph/module/port。K60 现值：2×AW882xx @ I2C `0x880000`，`0x34/0x35`，reset GPIO1/3，IRQ88/63，spksw52，ADSP `0x9fd00000/0x3100000`，TDM 1.536 MHz，tx-lines=3 | ❌ 无官方组件；新写 AW882xx + K60 音频路由 |
| DSP / 电源 / 电池 | 无 catalog；参考 `AdspProbe.cpp`、`ShengBattmgr.c/h`、`ShengBattery.cpp`、`BatteryProbe.cpp`、`CpuFreqProbe.cpp`、`QcomRpmh.h`、`ShengPlatformPower.cpp`、`GpuPowerProbe.cpp` | ADSP firmware/PAS ID、memory reservation、mailbox IRQ、SMEM/GLINK、PMIC/RPMh/RSC、gauge/charger。K60 现值：ADSP `0x9fd00000/0x3100000`（29 MiB）、IPCC `0xed18000/0x1000` IRQ261、PMIC `pmk8350/pm8350/pm8350c/pm8350b/pmr735a/pmr735b/pm8450`、RSC `0x17a00000` | ❌ 无官方组件；移植 PongPower 并改 SM8475 |

### 2.6 OS 服务、调试与虚拟化

| 硬件 / 子系统 | 组件（文档依据） | 板级输入（DTS / 寄存器 / GPIO / 时钟 / 固件） | K60 判定 |
|---|---|---|---|
| Keystore | `AppleKeyStoreState`（`apple-key-store-state.md`） | `native_aks_device_id`、keybag/passcode 策略、`sheng-aks-sls=3`；K60 现值：pong software keybag 补丁 | ⚠️ 可作后续官方化候选 |
| 加密 | `SoftwareAES`（`software-aes.md`） | XNU AES helper、`IOAESAccelerator` ABI | ⚠️ 16.6.1 ABI 审计后可用 |
| 根信任 | `VerifiedRoot`（`verified-root.md`） | owner-signed root policy、trust inputs、storage archive | ⚠️ 可选；当前 pong 信任路径优先 |
| 虚拟化 | `VirtioMmioBlock` / `VirtioMmioConsole`（`virtio-mmio-*.md`） | 兼容 MMIO device、中断路由、storage ABI | ❌ QEMU/virtual only |
| Baseband | `QcomBaseband`（`qcom-baseband.md`） | modem boot/firmware/power/DMA/GLINK/QRTR/rmtfs；SC7180 IPA v4.2 | ❌ K60 当前不选（无蜂窝需求） |

---

## ③ 缺什么 / 要新写什么

### 3.1 `docs/drivers/` 自身的缺口

1. **pin 全部缺失**：47 篇没有 commit pin，只有仓库 URL。`repositories.md` 只是目录，不能作为可复现构建依据。发布前必须从 `components.toml` 的 `revision` 与 `.gitmodules` 的 gitlink 取 pin；两套值不一致的组件（ArmCpu、Adreno740、AdrenoMetal、GopFramebuffer、AppleKeyStoreState、RamBlock、DarwinBoot、ArmSmmu4K、XnuPrelink、VerifiedRoot、ShengUfs、VirtioMmioBlock 等 12 个）要单独裁决以哪套为准。
2. **组件页信息粒度不足**：33 篇是 13–47 行登记页，只给“scope 一句话 + build 命令”，没有 DTS 属性表、寄存器偏移、GPIO 表、时钟树、固件文件名/manifest。真正的板级细节在 `docs/porting/*`（本次未读，不属于 `docs/drivers`）。
3. **没有 K60 / SM8475 专属页**：所有官方组件的验证设备都是 sheng（Xiaomi Pad 6S Pro，SM8550，iPadOS 17/27）。`docs/drivers` 中不存在 `sm8475`、`mondrian`、`adreno730`、`qca6490`、`goodix`、`aw882xx` 任一页面。
4. **没有 build 初始化调用点总表**：`sheng-*` boot args、probe 函数、archive 名称散落在各页；K60 需要自己建立 `component → archive → probe → boot arg` 的映射。
5. **社区页证据弱**：12 篇社区文档中 6 篇明确 `No hardware result`（native-adreno-fuxi、native-adreno-myron、native-dwc3、native-emmc、native-ufs-alioth、native-ufs-myron），1 篇 `has not booted`（native-msdc），2 篇部分（nativefocaltechtouch、nativeufs），只有 Adreno830、nativemobiledisplay、nativeramblock 有可用结果。不能把社区页当“已验证可选”。

### 3.2 K60 必须新写 / 适配的组件（按优先级）

| 优先级 | 缺口 | 现状 | 要写的组件 / 文件 | 参考文档 |
|---|---|---|---|---|
| P0 | SM8475 平台电源 / PMIC / RPMh / RSC | K60 设备仓没有 `Sm8475Platform`；pong main 只有 `PongPower`，未进 K60 | `PongPlatform24`/`Sm8475Platform`（GMU、GPU SMMU、RPMh command DB、PMIC/regulator/RSC） | `sm8550-platform.md` 的结构 + K60 `BT-AUDIO-PORT-PLAN`/`PongPower` |
| P0 | UFS 板级常量 | `PongUfs` 已在 K60；ShengUfs 是 SM8550 | 保留 `PongUfs`；后续把 SM8475 host/PHY/GCC/SMMU `0xe0` 常量化进 `ShengUfs` 后端 | `sheng-ufs.md`、`device-tree-matching.md` |
| P0 | 原生 DSI 显示 / 面板 | K60 只有 GOP 软件呈现（1440×3200 CPU memcpy）；DSI host/PHY/PLL 驱动缺 | `K60DsiDisplay`：DSI host/PHY/PLL + panel init + DSC/60-120 Hz timing + scanout | `gop-framebuffer.md`、`community-unixnu-nativemobiledisplay.md`、`K60-120HZ-PLAN` |
| P0 | 实体键 XNU 驱动 | UEFI `K60KeypadDeviceLib`/SPMDxe/PmicDxe 已有；XNU 无 | `K60PhysicalKeys`：`/buttons` personality + PMIC PON/GPIO + HID report | `uefi-drivers.md`、`overview.md`、`xnu-drivers.md` |
| P1 | A730 GPU bring-up | `PongAdreno` 已编译/force_load，未上机；SM8475 GMU/GPU SMMU/RPMh 缺 | `PongAdreno` 上机 + `Sm8475Platform` GMU/SMMU/RPMh；A730 固件 `gmu_gen70000.bin`/`a730_sqe.fw`/`a730_zap.*` | `adreno740.md`、`adreno-metal.md`、`adreno-firmware.md`、`adreno-pm4.md`、`sm8550-platform.md` |
| P1 | Goodix 触摸 | K60 无 Goodix driver；只有 `xiaomi,m11a-spi` DTS/固件名 | `PongGoodix`：Goodix protocol core + firmware download + `QcomGeniSpi` bus + `ShengHidInput` 快照 | `sheng-novatek-touch.md` 架构 + `qcom-geni-spi.md` + `K60-TOUCH-PARAMS` |
| P2 | QCA6490 Wi-Fi | `PongWifi` 只在 pong main；K60 未接 | `PongWifi` 移植：ath11k + PCIe `17cb:1103` + BAR0/ MSI/IOVA/rails + firmware | `ath12k-wifi.md` 分层 + `WIFI-PORT-PLAN` |
| P2 | QCA6490 Bluetooth | 零先例；`QcaBluetooth` 是 WCN7850 | `PongQca6490Bt`：GENI UART SE20 `0x894000`/IRQ587/GPIO76-79/H4/IBS + `htbtfw21.tlv`/`htnv21.bin` | `qca-bluetooth.md` 框架 + `BT-AUDIO-PORT-PLAN` |
| P2 | AW882xx 音频 | 零先例；sheng 是 CS35L43+WCD938x，pong 是 TFA9873 | `PongAw882xx`：2×AW882xx I2C `0x34/0x35` + reset/IRQ/spksw + AudioReach/GPR 路由 + TDM 1.536 MHz | `docs/porting/power.md`（参考）；`BT-AUDIO-PORT-PLAN` |
| P2 | USB DWC3 | K60 自研 DWC3/usblog；`QcomDwc3` 是 24A446 | 先保自研；后续按 `QcomDwc3` 的 AppleUSBXDCI/XHCI 分层移植，K60 stream `0x0`、eUSB2 `0x88e3000`、QMP `0x88e8000` | `qcom-dwc3.md` |
| P3 | Prelink / loader ABI | K60 `DarwinBoot22` + `NativePrelink`；官方是 iOS27 | `K60Prelink`：按目标 OS（20G81/22H374）维护 kernelcache pin/roots/ABI；不要照抄 24A446 fixture | `xnu-prelink.md`、`darwin-boot.md` |
| P3 | UEFI preflight | `ShengPreflight` 只覆盖 sheng | `K60Preflight`：firmware volume、arena `[0x900000000,0xa40000000)`、UFS/内存窗口 | `sheng-preflight.md`、`uefi-drivers.md` |
| P3 | 根信任 | pong 自有路径 | `K60VerifiedRoot` 可选：owner-signed root policy + storage archive | `verified-root.md` |

### 3.3 复用分级（结论）

- **接口层直接复用**：`ArmCpu`、`ArmDTPlatform`、`ArmSmmu4K`、`QcomGeniSpi`、`ShengHidInput`、`RamBlock`、`AppleKeyStoreState`、`SoftwareAES`、`VerifiedRoot`。
- **必须换板级常量 / SoC 后端**：`ShengUfs`、`GopFramebuffer`、`Adreno740`、`AdrenoMetal`、`Sm8550Platform`、`Ath12kWifi`、`QcaBluetooth`、`QcomDwc3`、`XnuPrelink`、`DarwinBoot`。
- **只能抄架构，不能抄实现**：`ShengNovatekTouch`（换 Goodix）、`ShengBacklight`（换 DCS）、`community-*`（换 SoC/面板/控制器）。
- **不选**：`ArmVirtPlatform`、`VirtioMmioBlock`、`VirtioMmioConsole`（虚拟化）；`QcomBaseband`（K60 当前无蜂窝需求）。

### 3.4 证据缺口

- 28 个官方组件条目中没有一条声明 `ipados-16.6.1-20G81` 或 SM8475 验证；`GopFramebuffer`、`AppleKeyStoreState` 等只在 catalog 里同时列 17/27，不等于 16.6.1 通过。
- K60 设备仓当前 `[components] include = ["ArmDTPlatform", "ArmCpu", "XnuPrelink", "PongUfs"]`；`dts/mondrian.dts` 只有 `/memory` 与 `ufs@1d84000`。GPU、显示、触摸、WiFi、BT、音频、USB、按键的 DTS 节点都还没写——这比驱动代码更先卡住 bring-up。
- `board.toml` 与 `README.md` 存在路线差异：`board.toml` 写 `ipados-16.6.1-20G81`，README 写 darwin24（18.7.10/22H374）迁移。任何驱动 ABI 结论都必须先固定目标 OS，否则 16.6.1 的 IOHIDFamily/USB/Display ABI 与 18.x 不可混用。

---

## ④ 覆盖清单（47/47）

清单生成（与 `find docs/drivers -name '*.md' | sort` 同序）：

```sh
find docs/drivers -name '*.md' | sort
```

| # | 文档 | 行数 | 类型 | 覆盖 |
|---:|---|---:|---|---|
| 1 | `adreno740.md` | 38 | GPU | [x] |
| 2 | `adreno-firmware.md` | 17 | GPU 固件 kit | [x] |
| 3 | `adreno-metal.md` | 58 | GPU Metal | [x] |
| 4 | `adreno-pm4.md` | 17 | GPU packet kit | [x] |
| 5 | `air-nir.md` | 17 | 离线编译 | [x] |
| 6 | `apple-key-store-state.md` | 23 | keystore | [x] |
| 7 | `arm-cpu.md` | 17 | CPU/GIC | [x] |
| 8 | `arm-dt-platform.md` | 17 | 平台 | [x] |
| 9 | `arm-smmu4k.md` | 19 | SMMU | [x] |
| 10 | `arm-virt-platform.md` | 15 | QEMU 平台 | [x] |
| 11 | `ath12k-wifi.md` | 91 | Wi-Fi | [x] |
| 12 | `community-adreno830.md` | 15 | 社区 GPU | [x] |
| 13 | `community-native-adreno-fuxi.md` | 15 | 社区 GPU | [x] |
| 14 | `community-native-adreno-myron.md` | 15 | 社区 GPU | [x] |
| 15 | `community-native-dwc3.md` | 15 | 社区 USB | [x] |
| 16 | `community-native-emmc.md` | 15 | 社区存储 | [x] |
| 17 | `community-nativefocaltechtouch.md` | 15 | 社区触摸 | [x] |
| 18 | `community-native-msdc.md` | 15 | 社区存储 | [x] |
| 19 | `community-native-ufs-alioth.md` | 15 | 社区 UFS | [x] |
| 20 | `community-native-ufs-myron.md` | 15 | 社区 UFS | [x] |
| 21 | `community-unixnu-nativemobiledisplay.md` | 15 | 社区显示 | [x] |
| 22 | `community-unixnu-nativeramblock.md` | 15 | 社区存储 | [x] |
| 23 | `community-unixnu-nativeufs.md` | 15 | 社区 UFS | [x] |
| 24 | `darwin-boot.md` | 26 | UEFI loader | [x] |
| 25 | `device-tree-matching.md` | 159 | 指南 | [x] |
| 26 | `gop-framebuffer.md` | 25 | 显示 | [x] |
| 27 | `kexts.md` | 166 | 指南 | [x] |
| 28 | `overview.md` | 80 | 指南 | [x] |
| 29 | `qca-bluetooth.md` | 110 | 蓝牙 | [x] |
| 30 | `qcom-baseband.md` | 13 | baseband | [x] |
| 31 | `qcom-dwc3.md` | 71 | USB | [x] |
| 32 | `qcom-geni-spi.md` | 19 | SPI | [x] |
| 33 | `ram-block.md` | 19 | 存储 | [x] |
| 34 | `repositories.md` | 81 | 目录 | [x] |
| 35 | `sheng-backlight.md` | 69 | 背光 | [x] |
| 36 | `sheng-hid-input.md` | 21 | HID | [x] |
| 37 | `sheng-novatek-touch.md` | 154 | 触摸 | [x] |
| 38 | `sheng-preflight.md` | 17 | UEFI preflight | [x] |
| 39 | `sheng-ufs.md` | 39 | UFS | [x] |
| 40 | `sm8550-platform.md` | 47 | GPU 平台 kit | [x] |
| 41 | `software-aes.md` | 19 | crypto | [x] |
| 42 | `uefi-drivers.md` | 221 | 指南 | [x] |
| 43 | `verified-root.md` | 17 | 根信任 | [x] |
| 44 | `virtio-mmio-block.md` | 19 | 虚拟化 | [x] |
| 45 | `virtio-mmio-console.md` | 17 | 虚拟化 | [x] |
| 46 | `xnu-drivers.md` | 270 | 指南 | [x] |
| 47 | `xnu-prelink.md` | 83 | prelink | [x] |

**合计：47/47 篇，全部从第 1 行读到 EOF，无遗漏、无截断。**
