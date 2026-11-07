# DOCS-DEVICES-N-Z — UniXNU 设备页通读（N–Z）

- 范围：`E:/hackios/UniXNU/docs/devices/` 中文件名首字母 N–Z 的全部页面，共 **136 篇**（N–Z 段共 141 篇，已排除 `pong*` 5 篇；`mondrian*` 4 篇属 A–M 段，本就不在范围；全目录 266 篇）。
- 阅读方式：逐文件全文读取（共 3,381,792 bytes / 35,915 行），本文件为逐篇一行摘要 + K60 可复用清单 + 覆盖清单。
- 状态口径：页面 `Area | Status` 原样汇总；`implemented` 表示实现覆盖，`host-verified` / `device-verified` 表示证据等级，`planned` 表示未实现。无状态表的页面在摘要中直接描述。
- 关联：A–M 段见 `docs/plans/DOCS-DEVICES-A-M.md`；其中 `erhai-xingxing19035.md`（AW882xx 实机清单）、`asteroids.md`（双 TFA9873 实现）、`marble-milacy.md`/`fuxi-oddlylabs.md`（Goodix/触摸工程模板）是本段 K60 清单的跨段补充。

## 阅读结论（先给结论）

1. **N–Z 段的文档类型**：136 篇中 **46 篇**是 `This page is generated from the device record` 的 Format-2 记录页（有 `| Area | Status |` 表），其余 **90 篇**是设备简介/Record pending/单行仓库链接；后者没有域状态，只能给文字状态。
2. **K60 的最高价值页就在本段**：`rmx3551.md`（realme GT2 Master Explorer，SM8475，32/32 implemented）与 `zizhan.md`（MIX Fold 2，SM8475，PongPlatform24）是仅有的两篇 SM8475 完整实现页，且都基于 Pong；`udon.md` 提供 SM8475 + iPadOS 17.7.11 到 userland 的旁证，`unicorn.md` 仅占位。
3. **SM8550 sheng 系列高度同源**：17 篇 sheng 生成页共享同一套 13 域实现（ShengUfs/ShengHidInput/ShengNovatekTouch/Adreno740/CS35L43/ADSP/Ath12kWifi），差异主要是构建记录与少量 WiFi/GPU/日志修复；读 `sheng.md` 即可掌握主体，其余按本清单的“独有”行补差。
4. **QCA6490 在 N–Z 有真正落地页**：`zizhan.md` 给出从 PCIe/SID/64 MiB DMA 到 WPA2/DHCP/HTTPS/双频重连的完整链路；`rmx3551.md` 给出 Pong QCA6490 的 82 项 PHY 序列与 19 BSS 扫描；`negroni.md` 验证 PCIe 链路与 Metal 共存；`sm-t970.md` 则是“节点叫 qca6490、固件却是 qca6390”的反例。
5. **Goodix 只有组件边界与型号差异，没有协议实现**：`nx769j.md` 明确 ShengHidInput 可复用、ShengNovatekTouch 不可用于 Goodix 9916R；`rmx3551.md`（Berlin-D）、`raphael-guowenye.md`（GT9889）、`ruby.md`（GT9916R）、`rmx3823.md`（Goodix 节点被禁用、实际 Synaptics S3910）说明同系列多 SKU，K60 必须先读 chip ID。
6. **AW882xx 在 N–Z 全文 0 命中**；TFA9873 只在 `rmx3551.md`（双 TFA 完整服务链）、`zizhan.md`（Pong TFA 参数 vs 实际 CS35L41）、`oneplus13t-shad0w23333.md`（双 TFA 硬件）出现。K60 的 AW882xx 必须另找厂商源码，TFA 页只能复用 AudioReach/GPR/功放状态机框架。

## ① 逐篇一行摘要

### N（16 篇）

| # | 文件 | 设备 / SoC | 一行摘要 |
|---:|---|---|---|
| 1 | `nabu-3214791900-del.md` | （无标题） | 仅仓库链接：3214791900-del/unixnu-nabu-build（构建仓）；无设备与状态信息。 |
| 2 | `nabu-lee-kenneth.md` | （无标题） | 仅仓库链接：lee-kenneth/unixnu-nabu；无设备与状态信息。 |
| 3 | `nabu-xingjiaostudio.md` | （无标题） | 仅仓库链接：XingJiaoStudio/unixnu-nabu-sweet；无设备与状态信息。 |
| 4 | `nabu-zzc775.md` | （无标题） | 仅仓库链接：zzc775/unixnu-nabu；无设备与状态信息。 |
| 5 | `nabu-zzweiqing.md` | Xiaomi Pad 5 (zzweiqing) | Xiaomi Pad 5（SM8150）：8 核/SGI IPI、UFS root 窗口、NT36523 触摸、GOP + A640 Metal scanout 已上屏；首帧后有有界 scanout stall 待修，Data/网络/音频/电源未实现。 〔域：implemented: Configuration; device-verified×9; planned: Network, Audio, Power〕 |
| 6 | `nabu.md` | Xiaomi Pad 5 (nabu) | Xiaomi Pad 5（SM8150）：源内核到 load_init_program 尝试 /sbin/launchd，记录 errno 2（ENOENT）；12 GiB 机型内存布局需重测；无状态表。 |
| 7 | `nash.md` | Motorola Moto Z2 Force (nash) | Moto Z2 Force（MSM8998）：board/defconfig/早期 ARM 初始化与打包输入齐全，无目标机 boot 证据。 |
| 8 | `negroni.md` | OnePlus 10 Pro 5G (negroni) | OnePlus 10 Pro 5G（SM8450）：iOS 16.7.16 SpringBoard 触摸+CPU 渲染；iOSPlus10 记录 Metal 150 秒无崩溃、4.5–8 ms 命令缓冲、83 GPU presentations/s；QCA6490 PCIe 链路已验证，Wi-Fi/音频/充电待验。 |
| 9 | `nio.md` | MOTO Edge S (XT2125-4) / SM8250-AC UniXNU bring-up | MOTO Edge S XT2125-4（SM8250-AC）：仅仓库入口，porting.toml 待补全。 |
| 10 | `nuwa-alex-enix.md` | （无标题） | 仅仓库链接：Alex-Enix/nuwa-dev；无设备与状态信息。 |
| 11 | `nuwa-pubglite55.md` | （无标题） | 仅仓库链接：pubglite55/UniXNU-nuwa；无设备与状态信息。 |
| 12 | `nuwa-wuuuweiii.md` | （无标题） | 仅仓库链接：WuuuWeiii/UniXNU-nuwa；无设备与状态信息。 |
| 13 | `nuwa.md` | Xiaomi 13 Pro (nuwa) | Xiaomi 13 Pro（SM8550）：源内核可构建，临时硬件 boot 记录 AppleARMPlatform: IODTNVRAM，约 235 秒后重启原因未定；board 仍 example=true。 |
| 14 | `nx721j.md` | ZTE Nubia Z60 Ultra (nx721j) | Nubia Z60 Ultra（Pineapple）：board 选 Pineapple + nx721j_probe_defconfig，含 passive UFS probe 与 CI；firmware/payload/设备 boot 未完成。 |
| 15 | `nx729j.md` | Nubia RedMagic 8 Pro / 8 Pro+ (nx729j) | Nubia RedMagic 8 Pro/Pro+（SM8550）：固件经 SEC/PEI/DXE/BDS 并显示日志，NativeUfs/SMMU/verified-root 已集成；XNU/root/userland 待匹配内核与实机记录。 |
| 16 | `nx769j.md` | nubia RedMagic 9 Pro / 9 Pro+ / 9S Pro / 9S Pro+ (NX769J) | nubia RedMagic 9 Pro/9S Pro 系列（SM8650，复用 SM8550 寄存器图）：UFS/显示 GOP host-verified，Goodix 9916R 触摸与 Adreno 750 未实现（planned）；SM8550 与 SM8650 的 UFS/GPU/GMU/SMMU 地址完全一致，ShengHidInput 可复用但需 Goodix 事件源。 〔域：host-verified: Configuration, Firmware and boot, Image assembly; implemented×4; planned×6〕 |

### O（5 篇）

| # | 文件 | 设备 / SoC | 一行摘要 |
|---:|---|---|---|
| 17 | `odin.md` | Xiaomi Mi MIX 4 (odin, Snapdragon 888+ / SM8350) | Xiaomi Mi MIX 4（SM8350）：5 域 host-verified（Storage/Input/GPU/Power/Image），其余 planned；A660 GPU 仅 AdrenoFirmware 可复用；ShengUfs 的 SM8550 GCC/stream 0x60 不适用，UFS 需 SM8350 分叉。 〔域：planned×8; host-verified×5〕 |
| 18 | `odin3.md` | AYN Odin 3 (Dragonwing Q8, SM8750), 16 GiB | AYN Odin 3（Dragonwing Q8/SM8750，16 GiB）：10 域 implemented、GPU/Network/Audio planned；iPadOS 17.7.11 从 microSD ESP 启动到 SpringBoard 锁屏，8 核在线、只读 SD root + 独立 Data 分区。 〔域：implemented×10; planned: GPU, Network, Audio〕 |
| 19 | `oneplus13t-shad0w23333.md` | OnePlus 13T PKX110 with the native Adreno 830 GPU (Shad0w23333) | OnePlus 13T PKX110（SM8750）：8 域 device-verified；原生 Adreno830 + Metal 在实机跑 iPadOS 17.7.11 桌面（系统 App/Widget/控制中心），Wi-Fi/BT/音频/传感器已实现并 host 测试但未 boot，Data 为 RAM disk。 〔域：host-verified: Configuration, Storage and root, Power; device-verified×8; implemented×4〕 |
| 20 | `oneplus13t.md` | OnePlus 13T (oneplus13t) | OnePlus 13T（SM8750）：build 63 实机确认系统启动与触摸正常，CPU 8 核、RAM 4096 MiB，Clutch 单 pset、只读 UFS root；GPU host-verified，跨核压力/长期稳定性未验。 〔域：host-verified×4; device-verified×7; implemented: Network, Audio〕 |
| 21 | `orangepi5.md` | Orange Pi 5 (Rockchip RK3588S) | Orange Pi 5（RK3588S）：7 域 device-verified；U-Boot 从 NVMe ESP 启动固件，NVMe root/持久 Data 挂载，SpringBoard + Mali Metal 经 VOP2 直扫 HDMI0；网络/音频无驱动、DVFS 未接。 〔域：host-verified: Configuration; device-verified×7; implemented: CPU and interrupts, Input; planned: Network, Audio, Power〕 |

### P（25 篇）

| # | 文件 | 设备 / SoC | 一行摘要 |
|---:|---|---|---|
| 22 | `pandora.md` | Xiaomi 17 Pro (pandora) | Xiaomi 17 Pro（SM8850）：iOS 16.7 桌面/App/触摸/按键/亮度可用，8 核 DVFS/睡眠/热控有记录；Adreno 840 + Turnip + Metal 约 110 fps@120 Hz，音频 DSP 启动，扬声器/电池/Wi-Fi/蜂窝/相机待补。 |
| 23 | `pd2049.md` | （无标题） | 仅仓库链接：Kaurisss/UniXNU-PD2049；无设备与状态信息。 |
| 24 | `pdx203-shinyquagsire23.md` | （无标题） | 仅仓库链接：shinyquagsire23/UniXNU-pdx203；无设备与状态信息。 |
| 25 | `pdx203.md` | Sony Xperia 1 II (pdx203) | Sony Xperia 1 II（SM8250）：CI 可构建并 prelink（NativeUfs/NativeAES/PMGR），手机未 boot。 |
| 26 | `peridot-hoshikv.md` | Xiaomi Poco F6 / Redmi Turbo 3 (hoshikv) | Poco F6 / Redmi Turbo 3（hoshikv）：仅仓库入口，porting.toml 待补全。 |
| 27 | `peridot-wzy114514sb.md` | Poco F6 / Redmi Turbo 3 (wzy114514sb) | Poco F6 / Redmi Turbo 3（wzy114514sb）：仓库入口 + device.name 与 board.toml 不一致提示。 |
| 28 | `peridot.md` | Redmi Turbo 3 / Poco F6 (peridot) | Redmi Turbo 3 / Poco F6（SM8635）：多个 WIP 设备仓，均无硬件结果。 |
| 29 | `phy120.md` | OPPO Find X7 Ultra (PHY120) | OPPO Find X7 Ultra（SM8650）：UEFI 菜单可用、1440×3168 面板；vendor DXE 停在 EnvDxeEnhanced/SmemDxe/DALSYSDxe/RamManagerDxe，kernel 仅 stub display CI 构建。 |
| 30 | `piano-xiaomi-pad-8-pro-development.md` | Xiaomi Pad 8 Pro: first XNU boot from RAM (OnePlus 13T base) (xiaomi-pad-8-pro-development) | Xiaomi Pad 8 Pro（OnePlus 13T 基线）首个 RAM XNU boot：仅仓库入口 + 组件缺 area 的清单（BootProgress/Native*/Pagani*/Sm8750Platform 等）。 |
| 31 | `piano.md` | Xiaomi Pad 8 Pro (piano) | Xiaomi Pad 8 Pro（SM8750）：DT 生成器与 board 描述被 unixnu 接受，XNU 在 CI 构建/prelink（51,806,208 bytes，ARM64 MH_EXECUTE）；平板未运行，payload/bootimg/SunUEFI 集成待做。 |
| 32 | `picasso-ahu865.md` | （无标题） | 仅仓库链接：ahu865/UniXNU-picasso；无设备与状态信息。 |
| 33 | `picasso-huydre.md` | （无标题） | 仅仓库链接：huydre/UniXNU-picasso；无设备与状态信息。 |
| 34 | `picasso-minhtritt1996.md` | （无标题） | 仅仓库链接：minhtritt1996/UniXNU-picasso；无设备与状态信息。 |
| 35 | `picasso-silenzio111.md` | （无标题） | 仅仓库链接：silenzio111/UniXNU-picasso；无设备与状态信息。 |
| 36 | `picasso-suzukir1n.md` | Redmi K30 5G targeting iPhone X iOS 16; Darwin 22 ABI and firmware pending (SuzukiR1n) | Redmi K30 5G（SM7250）：9 域 planned、2 host-verified、2 implemented；iOS16/Darwin22 ABI 与固件未移植，明确不选 SM8550 存储/面板实现。 〔域：host-verified: Configuration, Diagnostics; planned×9; implemented: CPU and interrupts, Image assembly〕 |
| 37 | `picasso-tselongson.md` | （无标题） | 仅仓库链接：tselongson/UniXNU-picasso；无设备与状态信息。 |
| 38 | `picasso.md` | Redmi K30 5G (picasso) | Redmi K30 5G（SM7250）：UEFI 菜单/DarwinBoot 可走到 XNU，内核加载 AMFI/AppleImage4/pthread/MAC、初始化网络并注册 APFS；卡在 BSD root-device wait，UFS root 是下一步。 |
| 39 | `pipa-fft-infra.md` | （无标题） | 仅仓库链接：FFT-infra/UniXNU-alioth-ARCHIVE；无设备与状态信息。 |
| 40 | `pipa-xvanturing.md` | （无标题） | 仅仓库链接：xVanTuring/UniXNU-pipa；无设备与状态信息。 |
| 41 | `pipa.md` | Xiaomi Pad 6 (pipa) | Xiaomi Pad 6（SM8250）：UEFI/菜单/DarwinBoot/XNU 可跑，停在 Failed to mount root device @IOKitBSDInit.cpp:984；缺存储驱动。 |
| 42 | `pje110.md` | （无标题） | 仅仓库链接：ledgerliu/UniXNU-pje110；无设备与状态信息。 |
| 43 | `polaris-puszekreksio.md` | （无标题） | 仅仓库链接：PuszekReksio/UniXNU-judyln；无设备与状态信息。 |
| 44 | `polaris-sprmd.md` | （无标题） | 仅仓库链接：SPRMD/UniXNU-polaris；无设备与状态信息。 |
| 45 | `polaris.md` | Xiaomi Mi MIX 2S (polaris) | Xiaomi Mi MIX 2S（SDM845/A630）：平台级硬件验证完成（polaris ADT、GICv3、19.2 MHz、PSCI、6/8 GiB upper bank），XNU 跑到无 root 边界；无 userland/root/触摸/显示/GPU。 |
| 46 | `pudding.md` | Xiaomi 17 (pudding, qcom,canoe, SM8850) | Xiaomi 17（pudding，qcom,canoe/SM8850）：13 域全部 planned；SoC 值双源验证，userdata GPT/RAM size/PON APID 待测。 〔域：planned×13〕 |

### Q（2 篇）

| # | 文件 | 设备 / SoC | 一行摘要 |
|---:|---|---|---|
| 47 | `q2q.md` | Galaxy Z Fold3 (q2q) | Galaxy Z Fold3（SM8350）：仅源码构建 harness（XNU 10063.141.1 + 4 KiB 补丁），无 OS/IPSW/设备 dump，不启动 iPadOS userland。 |
| 48 | `qemu.md` | QEMU virt | QEMU virt：菜单/DarwinBoot/4 GiB/MMU/4 KiB 页/IOKit/VirtIO root/SystemOS/Data/ramfb 显示/触摸均可用；--metal 可把渲染服务 Metal 工作交给 Mac GPU。 |

### R（12 篇）

| # | 文件 | 设备 / SoC | 一行摘要 |
|---:|---|---|---|
| 49 | `r11.md` | OPPO R11 (r11) | OPPO R11（SDM660）：board/defconfig/硬件笔记存在，无硬件结果；记录 DRAM/CPU affinity/userdata/display 和 Synaptics I2C 触摸。 |
| 50 | `raphael-guowenye.md` | Independent Redmi K20 Pro port; compile-only default with separately gated native handset bring-up (guowenye) | Redmi K20 Pro：9 域 implemented、Input/GPU/Network/Audio planned；本地 APFS/SystemOS/launchd/显示服务有进展但桌面不完整；Goodix GT9889 仅有 binding，协议/固件/坐标未验。 〔域：implemented×9; planned×4〕 |
| 51 | `raphael-jackyhowh.md` | （无标题） | 仅仓库链接：jackyhowh/UniXNU-raphael；无设备与状态信息。 |
| 52 | `raphael-johnleeeeeee678.md` | （无标题） | 仅仓库链接：JohnLeeeeeee678/UniXNU-raphael；无设备与状态信息。 |
| 53 | `raphael.md` | Redmi K20 Pro / Mi 9T Pro (raphael) | Redmi K20 Pro / Mi 9T Pro：GitHub 仓库当前不可访问，状态待维护者确认。 |
| 54 | `rmx1971.md` | Realme 5 Pro | Realme 5 Pro：6 域 device-verified；boot chain/entry/MMU/timer/PSCI/console 在硬件跑通，XNU 在 bsd_init 等 root device；A616 GPU 未实现。 〔域：implemented: Configuration, Storage and root; device-verified×6; planned×5〕 |
| 55 | `rmx3551.md` | realme GT2 Master Explorer (RMX3551): UniXNU UEFI bring-up | realme GT2 Master Explorer（SM8475）：32 域全部 implemented，Pong main 的 iPadOS18/Darwin24 设备镜像；A730、QCA6490、TFA9873 双扬声器、Goodix Berlin-D、8 GiB 可写 UFS Data 均有专门章节，是 K60 最强同代蓝本。 〔域：implemented×32〕 |
| 56 | `rmx3823.md` | realme GT5 240W (RMX3823), kalama, 24 GiB, 1240x2772 AMOLED | realme GT5 240W（SM8550 kalama，24 GiB，1240×2772）：11 域 planned、2 implemented；复用 sm8550-common，UFS/GPU 节点已开，但面板/触摸未识别、boot.img 头 v4 的 base DT 在 vendor_boot 缺失。 〔域：implemented: Configuration, Memory and DMA; planned×11〕 |
| 57 | `ruby.md` | Xiaomi Redmi Note 12 Pro 5G (ruby, MediaTek Dimensity 1080 / MT6877) | Redmi Note 12 Pro 5G（MT6877）：5 implemented、3 device-verified；XNU 8796 + iPhone X iOS 16.7.16，Goodix GT9916R 走 bit-bang SPI3；不是 UniXNU 构建树。 〔域：host-verified: Configuration; not-applicable: Firmware and boot; implemented×5; device-verified: Input, Power, Diagnostics; planned: GPU, Network, Audio〕 |
| 58 | `ruyi-arnodorian123.md` | （无标题） | 仅仓库链接：ArnoDorian123/UniXNU-ruyi-min；无设备与状态信息。 |
| 59 | `ruyi-ehunshuaige.md` | （无标题） | 仅仓库链接：ehunshuaige/UniXNU-ruyi；无设备与状态信息。 |
| 60 | `ruyi.md` | Xiaomi MIX Flip (ruyi) | Xiaomi MIX Flip（SM8650）：board 配置/kernel defconfig 选用 iPad7,1 + iPadOS 17.7.11；TODO 值与实机 boot 未完成。 |

### S（41 篇）

| # | 文件 | 设备 / SoC | 一行摘要 |
|---:|---|---|---|
| 61 | `sagit.md` | Xiaomi Mi 6 (sagit) | Xiaomi Mi 6：GitHub 仓库当前不可访问，状态待维护者确认。 |
| 62 | `sheng-16crow.md` | （无标题） | 仅仓库链接：16Crow/UniXNU-sheng；无设备与状态信息。 |
| 63 | `sheng-ad1095445.md` | Xiaomi Pad 6S Pro (ad1095445) | Xiaomi Pad 6S Pro（SM8550）：完整 sheng 栈 13 域 implemented + arm64e-os planned；该副本独有 WifiNet/Ath12k 关联切换与设备验证细节。 〔域：implemented×13; planned: arm64e-os〕 |
| 64 | `sheng-airalex002.md` | Xiaomi Pad 6S Pro (airalex002) | Xiaomi Pad 6S Pro（SM8550）：完整 sheng 栈 13 implemented + arm64e planned；独有 A740 队列/16384 对象上限/512 页 unmap 与 alias 检查、162 库 shader priming 记录。 〔域：implemented×13; planned: arm64e-os〕 |
| 65 | `sheng-alghiffaryfa19.md` | （无标题） | 仅仓库链接：alghiffaryfa19/UniXNU-sheng；无设备与状态信息。 |
| 66 | `sheng-bai805.md` | Xiaomi Pad 6S Pro (bai805) | Xiaomi Pad 6S Pro（SM8550）：完整 sheng 栈 13 implemented + arm64e planned；独有 24A446 wifid `_LimitLoadToDeviceTree`/wlan 节点修复记录。 〔域：implemented×13; planned: arm64e-os〕 |
| 67 | `sheng-chenjin1494.md` | Xiaomi Pad 6S Pro (chenjin1494) | Xiaomi Pad 6S Pro（SM8550）：完整 sheng 栈 13 implemented + arm64e planned；独有 LAT1 524288 记录上限与 TouchProbe 触点坐标日志。 〔域：implemented×13; planned: arm64e-os〕 |
| 68 | `sheng-enlixk.md` | Xiaomi Pad 6S Pro (Enlixk) | Xiaomi Pad 6S Pro（SM8550）：完整 sheng 栈 13 implemented + arm64e planned（与 UniXNU-sheng 同 revision 4601795）。 〔域：implemented×13; planned: arm64e-os〕 |
| 69 | `sheng-fft-infra.md` | Xiaomi Pad 6S Pro (FFT-infra) | Xiaomi Pad 6S Pro（SM8550）：iPadOS 17.7.11/21H461 模板，13 域 implemented；DTS 禁用 cpu1/cpu2、root UUID 04769D26-...，是模板化最轻的一版。 〔域：implemented×13〕 |
| 70 | `sheng-gkxqh.md` | Xiaomi Pad 6S Pro (gkxqh) | Xiaomi Pad 6S Pro（SM8550）：完整 sheng 栈 13 implemented + arm64e planned；与 canonical 同源，差异仅构建记录。 〔域：implemented×13; planned: arm64e-os〕 |
| 71 | `sheng-ht94911.md` | Xiaomi Pad 6S Pro (ht94911) | Xiaomi Pad 6S Pro（SM8550）：完整 sheng 栈 13 implemented；board model J120AP、sheng-wifi=5、dpu-scanout=2。 〔域：implemented×13〕 |
| 72 | `sheng-hxzbaka.md` | Xiaomi Pad 6S Pro (hxzbaka) | Xiaomi Pad 6S Pro（SM8550）：完整 sheng 栈 13 implemented；独有 ADSP 从 modem_a image 加载、GLINK battery/IPCRTR 细节。 〔域：implemented×13〕 |
| 73 | `sheng-jn7163.md` | （无标题） | 仅仓库链接：jn7163/UniXNU-sheng；无设备与状态信息。 |
| 74 | `sheng-jsongmax.md` | Xiaomi Pad 6S Pro (jsongmax) | Xiaomi Pad 6S Pro（SM8550）：完整 sheng 栈 13 implemented + arm64e planned；与 canonical 同源。 〔域：implemented×13; planned: arm64e-os〕 |
| 75 | `sheng-kkkpc.md` | （无标题） | 仅仓库链接：kkkpc/UniXNU-fuxi-xiaomi13-forked-bypass-sheng；无设备与状态信息。 |
| 76 | `sheng-ks114514.md` | Xiaomi Pad 6S Pro (ks114514) | Xiaomi Pad 6S Pro（SM8550）：完整 sheng 栈 13 implemented + arm64e planned（与 UniXNU-sheng 同 revision 4601795）。 〔域：implemented×13; planned: arm64e-os〕 |
| 77 | `sheng-liangkam.md` | （无标题） | 仅仓库链接：LiangKam/UniXNU-sheng；无设备与状态信息。 |
| 78 | `sheng-lilinnan.md` | （无标题） | 仅仓库链接：lilinnan/UniXNU-sheng；无设备与状态信息。 |
| 79 | `sheng-lithosss.md` | Xiaomi Pad 6S Pro (Lithosss) | Xiaomi Pad 6S Pro（SM8550）：完整 sheng 栈 13 implemented + arm64e planned；与 canonical 同源。 〔域：implemented×13; planned: arm64e-os〕 |
| 80 | `sheng-macos.md` | macOS on sheng | sheng 上的 macOS 26.5/25F71：arm64e launchd 在 QEMU 与硬件运行，BaseSystem/ISC 挂载、临时 Data/模板复制、macoslog 持久化；WindowServer 在 HID/显示初始化反复退出，图形 Recovery 未达。 |
| 81 | `sheng-soneoylys.md` | Xiaomi Pad 6S Pro (Soneoylys) | Xiaomi Pad 6S Pro（SM8550）：完整 sheng 栈 13 implemented + arm64e planned；独有 16 位 unique-chip-id seed 与 bootimg v0 自检修复。 〔域：implemented×13; planned: arm64e-os〕 |
| 82 | `sheng-thearchitectengineer.md` | Xiaomi Pad 6S Pro (TheArchitectEngineer) | Xiaomi Pad 6S Pro（SM8550）：完整 sheng 栈 13 implemented；独有 CPU idle 补丁与 Domain 0 顶频说明。 〔域：implemented×13〕 |
| 83 | `sheng-tkings4chan.md` | Xiaomi Pad 6S Pro (tkings4chan) | Xiaomi Pad 6S Pro（SM8550）：完整 sheng 栈 13 implemented + arm64e planned；与 canonical 同源。 〔域：implemented×13; planned: arm64e-os〕 |
| 84 | `sheng-v1-727.md` | Xiaomi Pad 6S Pro (v1-727) | Xiaomi Pad 6S Pro（SM8550）：完整 sheng 栈 13 implemented + arm64e planned；与 canonical 同源。 〔域：implemented×13; planned: arm64e-os〕 |
| 85 | `sheng-yeyingjun-codes.md` | Xiaomi Pad 6S Pro (yeyingjun-codes) | Xiaomi Pad 6S Pro（yeyingjun-codes）：仓库入口 + device.os_profile 与 board.toml 不一致提示。 |
| 86 | `sheng-yuyaukong.md` | （无标题） | 仅仓库链接：yuyaukong/UniXNU-sheng；无设备与状态信息。 |
| 87 | `sheng.md` | Xiaomi Pad 6S Pro (sheng) | Xiaomi Pad 6S Pro（SM8550）canonical 记录：13 域 implemented + arm64e-os planned；ShengUfs/ShengHidInput/ShengNovatekTouch/Adreno740/CS35L43/ADSP/Ath12kWifi 全栈细节与脚本齐备，是理解官方 sheng 栈的主入口。 〔域：implemented×13; planned: arm64e-os〕 |
| 88 | `shennong-baihem.md` | Xiaomi 14 Pro 23116PN5BC (baihem) | Xiaomi 14 Pro 23116PN5BC（baihem）：仅仓库入口，porting.toml 待补全。 |
| 89 | `shennong.md` | Xiaomi 14 Pro 23116PN5BC | Xiaomi 14 Pro 23116PN5BC：仅仓库入口，porting.toml 待补全。 |
| 90 | `sirius-dddqmmx.md` | Xiaomi Mi 8 SE (dddqmmx) | Xiaomi Mi 8 SE（SDM710）：8 implemented、5 planned、1 device-verified；8 GiB APFS Data 内核内扩容零 ENOSPC，launchd/SpringBoard/backboardd ~19 fps CPU GOP，FTS521 + ShengHidInput 触摸可用，USB FASTBOOT 回 ABL 已验证。 〔域：implemented×8; device-verified: Storage and root; planned×5〕 |
| 91 | `sirius-huajifruit.md` | Xiaomi Mi 8 SE (HuajiFruit) | Xiaomi Mi 8 SE：8 implemented、4 planned、2 device-verified；IOKit 被 AppleARMCPU 抢 /cpus 阻塞；页内给出 A616 完整寄存器/GMU/SMMU/ZAP 与 Adreno6xx 分叉路线。 〔域：implemented×8; device-verified: Storage and root, Input; planned×4〕 |
| 92 | `sirius-yooglery.md` | Xiaomi Mi 8 SE (Yooglery) | Xiaomi Mi 8 SE：7 implemented、5 planned、1 device-verified；与同族页面相同，IOKit 卡在 AppleARMCPU /cpus。 〔域：implemented×7; device-verified: Storage and root; planned×5〕 |
| 93 | `sirius.md` | Xiaomi Mi 8 SE (sirius) | Xiaomi Mi 8 SE：8 implemented、5 planned、1 device-verified；同族页，boot-chain 已实现。 〔域：implemented×8; device-verified: Storage and root; planned×5〕 |
| 94 | `sm-t733.md` | Samsung Galaxy Tab S7 FE Wi-Fi (SM-T733) | Samsung Galaxy Tab S7 FE Wi-Fi：仓库入口；组件缺 area（Adreno740/AdrenoMetal/Sm8550Platform）。 |
| 95 | `sm-t970.md` | Samsung Galaxy Tab S7+ Wi-Fi (SM-T970, gts7xlwifi), single-core platform bootstrap | Samsung Galaxy Tab S7+ Wi-Fi（SM8250）：7 planned、4 implemented、2 host-verified；单核/8 核 BOOT 到 launchd/SpringBoard，512 MiB owned window + RAM Data，显示后端仍 disabled；UFS 遇 SM8250 SMMU 写锁，证明 ShengUfs SM8550 模型不适用。 〔域：host-verified: Configuration, Firmware and boot; implemented×4; planned×7〕 |
| 96 | `songyuan-aogg2023.md` | （无标题） | 仅仓库链接：aogg2023/songyuan-device；无设备与状态信息。 |
| 97 | `songyuan-wukawl.md` | （无标题） | 仅仓库链接：WUKAWL/songyuan-device；无设备与状态信息。 |
| 98 | `songyuan.md` | （无标题） | 仅仓库链接：WUKAWL/songyuan-unixnu；无设备与状态信息。 |
| 99 | `starlte.md` | Samsung Galaxy S9 (starlte, SM-G960F, Exynos 9810): HakiOS, iOS 16.5 on XNU; not built on the UniXNU tree | Samsung Galaxy S9（Exynos 9810，HakiOS/iOS 16.5，非 UniXNU）：13 域 device-verified；6 核、触摸、电池、振动、USB console、S6E3HA8 面板零拷贝 scanout、亮度、Mali-G72/Panfrost、DVFS/TMU、UFS root、RTC、Wi-Fi DHCP、前摄 30 fps。 〔域：implemented: Configuration; not-applicable: upstream; device-verified×13; planned: modem〕 |
| 100 | `sweet-zeroninevibedslop.md` | Xiaomi Redmi Note 10 Pro (zeroninevibedslop) | Redmi Note 10 Pro（zeroninevibedslop）：仅仓库入口，porting.toml 待补全。 |
| 101 | `sweet.md` | Redmi Note 10 Pro (sweet) | Redmi Note 10 Pro（SM7150）：两套 port；zeroninevibedslop 报 UFS root/launchd/SpringBoard/backboardd 与 USB CDC-ECM，A618 电源/GMU/HFI 有记录、GPU 提交与 Metal 仍在进行。 |

### T（8 篇）

| # | 文件 | 设备 / SoC | 一行摘要 |
|---:|---|---|---|
| 102 | `t610yp.md` | Unisoc UMS512 / T610YP | Unisoc UMS512 / T610YP：首 boot 设备仓，board/source-kernel/ADT 生成器 + 外部 edk2-sprd；无硬件结果。 |
| 103 | `tb128fu-riceneeder.md` | （无标题） | 仅仓库链接：Riceneeder/UniXNU-tb128fu；无设备与状态信息。 |
| 104 | `tb128fu.md` | Lenovo Xiaoxin Pad 2022 (tb128fu) | Lenovo Xiaoxin Pad 2022（SM6225）：iPadOS 17.7.11 桌面 + 触摸可用，Adreno 610 无 GMU、Metal 经 GPU hand-off；音频/Wi-Fi/电池/按键/睡眠未工作。 |
| 105 | `tb365fc.md` | Lenovo Xiaoxin Pad 12.1 (2025), Lenovo TB365FC (board cava_prc_consumer_wifi) | Lenovo Xiaoxin Pad 12.1 2025（TB365FC，MT6835/cava）：6 implemented、7 planned；UEFI 菜单/Advanced Logger 可用，XNU 未构建未 boot；8 GB/128 GB、BOE HX83122B 1600×2560@90、MT6631。 〔域：implemented×6; planned×7〕 |
| 106 | `thor.md` | Xiaomi 12S Ultra (thor): UniXNU UEFI bring-up | Xiaomi 12S Ultra：仓库入口 + device.name 与 board.toml 不一致提示。 |
| 107 | `thyme-coryyi.md` | （无标题） | 仅仓库链接：Coryyi/UniXNU-thyme；无设备与状态信息。 |
| 108 | `thyme.md` | Xiaomi Mi 10S (thyme) | Xiaomi Mi 10S（SM8250-AC）：Coryyi/tobyfox1640 两套 board/defconfig/ADT，无目标机 boot/userland 结果。 |
| 109 | `tundra.md` | （无标题） | 仅仓库链接：Meltemi-9264/unixnu-tundra；无设备与状态信息。 |

### U（14 篇）

| # | 文件 | 设备 / SoC | 一行摘要 |
|---:|---|---|---|
| 110 | `udon.md` | OnePlus Ace 2 / 11R (udon) | OnePlus Ace 2 / 11R（SM8475）：经 UEFI/DarwinBoot/native UFS 到 iPadOS 17.7.11 userland，OS/SystemOS/shared cache 加载、32 MiB 可写 APFS RAM Data；117 进程 176 秒后按诊断重启，止于 ReportCrash；UI/GPU/音频/Wi-Fi 待补。 |
| 111 | `uke-imposterissus13.md` | Xiaomi Pad 7 (IMPOSTERiSSUS13) | Xiaomi Pad 7（SM7675/cliffs）：9 device-verified、2 host-verified、2 n/a；format2 迁移经从零内核构建验证，73 patch 四层链，GPU mode 9 + 实屏 UI + 触摸扫描；A732。 〔域：host-verified: Configuration, Image assembly; device-verified×9; not-applicable: Network, Audio〕 |
| 112 | `uke-iosnjbrepo.md` | （无标题） | 仅仓库链接：iOSNJBrepo/UniXNU-uke；无设备与状态信息。 |
| 113 | `uke-tonghuaqwq.md` | Xiaomi Pad 7 (TongHuaQWQ) | Xiaomi Pad 7（SM7675/cliffs）：9 device-verified、2 host-verified、2 n/a；与 IMPOSTERiSSUS13 同源，format2/73 patch/GPU mode9/触摸扫描。 〔域：host-verified: Configuration, Image assembly; device-verified×9; not-applicable: Network, Audio〕 |
| 114 | `uke-wuhaoran956-cyber.md` | （无标题） | 仅仓库链接：wuhaoran956-cyber/UniXNU-uke；无设备与状态信息。 |
| 115 | `uke.md` | Xiaomi Pad 7 / POCO Pad X1 (uke) | Xiaomi Pad 7 / POCO Pad X1（SM7675）：9 device-verified、2 host-verified、2 n/a；iPadOS27/24A446 GPU 基线，A732 gen7-11-0，Adreno740 5c8c145 / ArmSmmu4K 3ba9245 / AdrenoMetal ce5e19e，uke-dpu-scanout=3 约 15 fps。 〔域：host-verified: Configuration, Image assembly; device-verified×9; not-applicable: Network, Audio〕 |
| 116 | `umi-agxmx666.md` | （无标题） | 仅仓库链接：AGXMX666/UniXNU-umi；无设备与状态信息。 |
| 117 | `umi-jopangjovan.md` | Xiaomi Mi 10 standalone UniXNU bring-up (JopangJovan) | Xiaomi Mi 10（SM8250）standalone：6 implemented、7 planned；早期 source-built XNU checkpoint，完整 kernel boot 未完成，无 standalone 硬件结果；UFS 不得复用他板 stream/SM8550 clock。 〔域：implemented×6; planned×7〕 |
| 118 | `umi-mouya-q.md` | （无标题） | 仅仓库链接：mouya-q/UniXNU-umi；无设备与状态信息。 |
| 119 | `umi-neowiseq.md` | （无标题） | 仅仓库链接：neowiseq/UniXNU-umi；无设备与状态信息。 |
| 120 | `umi.md` | Xiaomi Mi 10 (umi) | Xiaomi Mi 10（SM8250）：iPadOS 17.7.11 到 Hello/Setup Assistant，ST FTS 触摸实机可用（attempt 80）；UFS root/launchd 可用、持久 Data，GPU/Wi-Fi/BT/蜂窝/音频/相机未实现。 |
| 121 | `unicorn.md` | Xiaomi 12S Pro (unicorn, SM8475): UniXNU UEFI bring-up | Xiaomi 12S Pro（SM8475）：仓库入口 + components without area: XnuPrelink；无实际状态。 |
| 122 | `unisoc.md` | Unisoc devices | Unisoc 设备总览：UniXNU-Unisoc 核心分叉，未识别具体设备，无硬件结果。 |
| 123 | `unixnu-build.md` | unixnu-build | unixnu-build：仅构建产物与 workflow，不对应任何设备。 |

### V（7 篇）

| # | 文件 | 设备 / SoC | 一行摘要 |
|---:|---|---|---|
| 124 | `venus.md` | Xiaomi Mi 11 M2011K2C: single-CPU platform bring-up | Xiaomi Mi 11（SM8350）：6 host-verified、4 device-verified；WSL zeta XNU12377.121.6 过 QEMU UEFI/DarwinBoot/arm_vm_init（EL1/MMU/4 KiB），root/Data/userland 未定；早期 XNU10063 触摸正常、Metal 未激活；A660 参考实现，ZAP fuse 值 0。 〔域：host-verified×6; device-verified×4; planned: Network, Audio; implemented: Diagnostics〕 |
| 125 | `vermeer-ahzcpp.md` | Redmi K70 (ahzcpp) | Redmi K70（ahzcpp）：仓库入口，porting.toml 待补全。 |
| 126 | `vermeer-xyyyds0106.md` | （无标题） | 仅仓库链接：xyyyds0106/UniXNU-vermeer；无设备与状态信息。 |
| 127 | `vermeer-yyx2025.md` | （无标题） | 仅仓库链接：yyx2025/UniXNU-vermeer；无设备与状态信息。 |
| 128 | `vermeer.md` | Redmi K70 (vermeer) | Redmi K70（SM8550）：xyyyds0106 平台内核 CI 与 UEFI 菜单实机通过，XNU 执行待跑；其余仓库只提供源码基线。 |
| 129 | `vili.md` | Xiaomi 11T Pro (vili, 2107113SG), SM8350 / Snapdragon 888 | Xiaomi 11T Pro（SM8350）：仓库入口 + evidence 必须 HTTPS/仓库相对路径提示；无实际状态。 |
| 130 | `vince.md` | （无标题） | 仅仓库链接：zjh3215588/unixnu-vince；无设备与状态信息。 |

### W（1 篇）

| # | 文件 | 设备 / SoC | 一行摘要 |
|---:|---|---|---|
| 131 | `wayne.md` | Xiaomi Mi 6X (2018) | Xiaomi Mi 6X：仓库入口，porting.toml 待补全。 |

### X（1 篇）

| # | 文件 | 设备 / SoC | 一行摘要 |
|---:|---|---|---|
| 132 | `x9.md` | OPPO Find X9 (x9) | OPPO Find X9（MT6993）：LK 解压 kernel 并应用 DTB overlay 后撞 HWT，UEFI 未到；仓库自评 25–30%。 |

### Y（1 篇）

| # | 文件 | 设备 / SoC | 一行摘要 |
|---:|---|---|---|
| 133 | `yunluo.md` | Redmi Pad format-2 qualification candidate; boot Mu and cust UniXNU must remain separate | Redmi Pad（MT6789）：13 域全部 planned；format2 资格候选，Mu 在 boot、UniXNU 在 cust 必须分离，尚未 build/device 资格。 〔域：planned×13〕 |

### Z（3 篇）

| # | 文件 | 设备 / SoC | 一行摘要 |
|---:|---|---|---|
| 134 | `zeta.md` | Microsoft Surface Duo 2 (zeta) | Microsoft Surface Duo 2（SM8350）：native UFS 挂 APFS root，离线 arm64e→arm64 重写使 iOS 26.5.2 launchd/dyld 到 PID 1 并执行 shared cache；unslid pointer 执行 fault，pager/图形待做。 |
| 135 | `zizhan.md` | Xiaomi MIX Fold 2 (zizhan, SM8475): UniXNU bring-up derived from Pong | Xiaomi MIX Fold 2（SM8475）：9 implemented、2 host-verified、2 planned、1 device-verified；Pong 衍生 iPadOS 18.7.10 内屏/触摸/A730/电池，120 Hz、合成负载 95.3 fps，QCA6490 实验性 HTTPS 可用；CS35L41 音频关闭。 〔域：host-verified: Configuration, Image assembly; implemented×9; device-verified: Network; planned: cellular, Audio〕 |
| 136 | `zorn.md` | Redmi K80 (zorn) | Redmi K80（SM8650-AB）：10 implemented、GPU/网络/音频 planned；实机桌面/基本触摸/8 核/8 GiB Data 与 dim64，CPU1 窄 root 发布有界，GUI 间歇卡顿；A750v2/gen7-9-1 配置已缓存。 〔域：implemented×10; planned: GPU, Network, Audio〕 |

## ② K60 可复用清单

> K60 = Redmi K60 / mondrian，SM8475（4×A510 + 3×A710 + 1×X2），Adreno 730 v3（chip `0x07030002`，2 MiB GMEM），Goodix 触摸（`xiaomi,m11a-spi`），QCA6490/WCN6855（PCI `17cb:1103`，ath11k），2×AW882xx 功放。以下按“可直接复用 / 需改造 / 不可用”分类，均给出页面出处、commit 或参数。

### 2.1 同代 SM8475 设备页（最高优先级）

| 页面 | 设备 | 对 K60 的价值 | 关键 commit / 参数 |
|---|---|---|---|
| `rmx3551.md` | realme GT2 Master Explorer（SM8475） | **最强同代蓝本**：Pong main 的 iPadOS 18/Darwin24 完整设备镜像，32/32 域 implemented；A730、QCA6490、TFA9873 双扬声器、Goodix Berlin-D、8 GiB 可写 UFS Data 均有专章 | `porting.toml@45c829bf7479a132c9e989fa5ffd5fb6814e706a`；`drivers/` 拆 12 个 `Chengdong-Yu/pong-*` submodule 且路径不变；AdrenoMetal pin `c6d29ca`；Pong SM8475/A730 + 22H374 arm64/native 4 KiB；`board.toml` + `pong_ipados18_defconfig` |
| `zizhan.md` | Xiaomi MIX Fold 2（SM8475） | PongPlatform24 衍生，iPadOS 18.7.10/22H374；A730 + QCA6490 + 120 Hz/95.3 fps 的完整参数与修复记录 | `porting.toml@3b3c52fb5ba11b0a185703d7832fd567c94e770e`；`a730_sqe.fw` / `gmu_gen70000.bin` / `a730_zap.*`；`PONG_ADRENO_FIRMWARE`；`pong_gpu_level=9`（710 MHz 初始 GMU）；QCA6490 `17cb:1103`、SID `0x1c00/0x1c01`、GPIO 80/94/95/96/204、64 MiB arena；22H374 scan record 2264 B @ `0x8d0`、RSSI_BOUNDS type 106 |
| `udon.md` | OnePlus Ace 2 / 11R（SM8475） | 同 SoC 的 iPadOS 17.7.11 路线：UEFI/DarwinBoot/native UFS 到 userland，117 进程 176 秒；可作 16.6.1/17.x 启动链 sanity check | `takasugl/UniXNU-udon@ad550a97f612836181dd36c6c08b1d7e90fb7b14`（README 记录） |
| `unicorn.md` | Xiaomi 12S Pro（SM8475） | 仅仓库入口（components without area: `XnuPrelink`），暂无实现可抄 | — |

### 2.2 GPU / Adreno 730

**结论：K60 只能继续走 PongAdreno/PongMetal（A730/ABI1/22H374），不能选官方 Adreno740/Sm8550Platform。**

- 官方 `Adreno740` 明确只声明 A740/SM8550；`Sm8550Platform` 也是 SM8550 kit。`nx769j.md:461`、`sm-t970.md:1242`、`odin.md:366` 都给出同一结论；`rmx3551.md:865` 还明确“不把 A740 的 CP 双 ring 抢占、ABI2 地址空间切换与 Darwin26 offset 用于 SM8475/22H374”。
- **可复用实现**
  - `zizhan.md` GPU 段（350-420）：A730v3 + `a730_sqe.fw` / `gmu_gen70000.bin` / `a730_zap.*`；`PONG_ADRENO_FIRMWARE` 选本地固件目录；`pong_gpu_level=9`（710 MHz）；`pong_gpu_deny=-` 可恢复 MercuryPosterEx GPU；固定 900 MHz 不如 DCVS。
  - `zizhan.md:377` 的 BO 生命周期修复：`PongAdrenoClient::dropViews` 先 unmap/release 用户映射，`NativeAdrenoMemory::release` 逐页 `pmap_disconnect` 再还 VM，修复 `pmap_assert_free`。
  - `zizhan.md:381` UI 动画：匹配真实 `UIKit.InProcessAnimationManager` 类（不是旧 `UIViewInProcessAnimationManager`），合成 tail p50/p90 16.6/33.3 → 8.3/16.6 ms，移动 fps 56.7–58.4 → 95.3。
  - `rmx3551.md:386`：`NativeAdrenoUserClient` 按需分配稳定 128-entry chunks，保留 BO/queue/fence 所有权；`rmx3551.md:500-545` 的 512 MiB GPU 池与 fence 外等待可作 K60 内存预算参考。
  - `uke.md:543-547`：Adreno740 `5c8c145` + ArmSmmu4K `3ba9245` + AdrenoMetal `ce5e19e` 在 A732（gen7-11-0）上工作，`uke-dpu-scanout=3` 约 15 fps —— 证明同一 Adreno740 组件可通过 generation backend 适配不同 gen7 GPU；K60 的 A730 可照此把 A730 作为 generation 后端，而不是整体换 A740。
  - `oneplus13t-shad0w23333.md` / `oneplus13t.md`：新代 Adreno830 集成范式（独立 `Adreno830` 组件、`CONFIG_XNU_NATIVE_ADRENO_ARCHIVE`、AdrenoMetal 依赖替换、`IOGPUFamily` prelink root）；若 K60 从 Pong 栈迁到组件模型，可按此结构拆出 `Adreno730` 组件。
- **可用 commit 锚点**：`rmx3551.md` 记录 `core 6790e7c / Adreno740 a9a2cbb / AdrenoMetal a0f0287`（早期 c6d29ca）；`sheng.md` 记录 Adreno740 `a9a2cbb` + AdrenoMetal `831a9dc`；`oneplus13t.md` 记录 Adreno740 `a9a2cbb` / AdrenoMetal `831a9dc` / AdrenoFirmware `20ad3d7`（更早 403e69e/505d0a1）。K60 选 Pong 分叉时以 `pong-adreno`/`pong-metal`/`pong-adreno-metal` 三个 submodule 的 pin 为准，不要混用 A740 的 kit。

### 2.3 UFS / 存储

**结论：保留 PongUfs（SM8475），不要选 ShengUfs。**

- `sheng.md:248-251`：ShengUfs 的 host `0x01d84000/0x3000`、PHY `0x01d80000/0x2000`、GCC `0x00100000`、apps-SMMU stream `0x60`、LUN 0 4096 B、userdata LBAs 3094592–64007162 —— 全是 SM8550/sheng 值。
- `sm-t970.md:710-715` 直接判定：ShengUfs 声明 SM8550/sheng clock、SMMU、userdata 依赖，SM8250 不能选；并给出通用方法“firmware state takeover，不是 cold init：读 GCC gating/link state、从 SMR/S2CR readback 规划 stream、发布 per-device userdata window”。`sm-t970.md:725` 进一步证明 SM8250 apps SMMU 的 IDR0 bit30 与 SM8550 不同（写锁），必须按 SoC 重写 SMMU 模型。
- `odin.md:206,219`：SM8350 与 SM8550 的 UFS host/GDSC/SMMU 物理基址相同，但 PHY 窗口（0x1d80000/0x2000 vs 0x1d87000/0xe10）、stream（0x60 vs 0xE0）、SMMU compatible、GCC 每个 branch offset 不同；`GccUfs.h` 硬编码 SM8550 偏移，不能直接选。
- **K60 可复用**：`rmx3551.md:233-234` 使用 `drivers/NativeUfs` → `Chengdong-Yu/pong-ufs` submodule，RootLayout/SmmuTakeover 路径不变，8 GiB 可写 UFS Data 有启动记录；`zizhan.md:44-58` 用 `PongPlatform24` 默认启用 GPU+WiFi，UFS root 窗口独立。K60 现有 `PongUfs`（`Emilelu/PongUfs@c959284`）正是同一路线；把 SM8475 常量固化为 ShengUfs 的 SoC 后端只是长期方向。

### 2.4 触摸（Goodix）

**结论：复用 `QcomGeniSpi` + `ShengHidInput` 的接口层；Goodix 协议层必须用 pong `pong_goodix.c` / K60 `0242-k60-touch-goodix.patch`，不能用 `ShengNovatekTouch`。**

- `nx769j.md:398-416` 是最清晰的组件边界说明：Goodix 9916R 在 stock kernel 注册 `goodix_ts`/`goodix_fp`，固件 `goodix_firmware_9916r.bin`；`ShengHidInput` 只负责把 board touch event source 发布成 IOHIDDevice，HID 层可复用；`ShengNovatekTouch` 的 NvtProtocol 与 Goodix 不匹配，需要同时替换 transport 和 report parser。
- Goodix 型号差异警钟：`rmx3551.md:326` 是 Goodix Berlin-D + PM8350 实体键；`raphael-guowenye.md:292` 是 Goodix GT9889；`ruby.md:260` 是 GT9916R（bit-bang SPI3）；`rmx3823.md:316-319` 同 overlay 里 goodix 节点被禁用、实际 Synaptics S3910 —— 同一机型系列可能多触摸 SKU，K60 必须先读 chip ID，不能按型号名猜协议。
- 可复用参数：`zizhan.md:312-322` 的 ST FTS 走 bit-bang SPI、`pong_touch=1`、`touch_flip=2`；K60 Goodix 的 GENI SPI SE4 `0x990000`、CS0、IRQ GPIO21、RESET GPIO20、AVDD GPIO71（PM8350C LDO2 1.8 V）来自 K60 本地计划，不在 N–Z 页面；N–Z 提供的价值是 HID/transport 分层与 Goodix 家族差异清单。

### 2.5 WiFi QCA6490

**结论：走 PongWifi（ath11k），不要 Ath12kWifi。**

- `zizhan.md:421-462` 是最完整的 QCA6490 端到端记录：PCI `17cb:1103`、PCIe0、GPIO 80/94/95/96/204、SID `0x1c00/0x1c01`、64 MiB DMA arena、QMI `chip_id=0x12 board_id=0xff` 与 `bdwlang.elf`；WMI_INIT -11 → station ready/102 channel/42-channel scan → WPA2/DHCP/HTTPS 200 → 2.4/5 GHz 双向换频重连；22H374 scan record 2264 B @ `0x8d0`，RSSI_BOUNDS type 106，timer reentry 修复（256 callback budget）。
- `rmx3551.md:439-448`：Pong PCIe0/QCA6490，82 项 PHY 序列，GPIO80/94/95/96/204，RPMh；QCA6490 en0 用 Pong 固件扫描 19 BSS；`services103` 记录 64 MiB DMA 修复后扫 10 BSS；用户确认 `services112` Wi-Fi 连接正常。
- `negroni.md:15`：QCA6490 PCIe 链路与设备响应已验证（iOSPlus10，150 秒 Metal 运行、4.5–8 ms 命令缓冲、83 fps），说明同族 QCA6490 可以在 iOS 用户态跑通。
- 负面：`sm-t970.md:1272-1287` 的 WLAN 节点叫 `qcom,cnss-qca6490@b0000000`，但固件目录是 `qca6390`，且 `Ath12kWifi` 对 `17cb:1101` 兼容性未建立 —— 不要按节点名硬套。
- **K60 参数对照**：K60 是 QCA6490/WCN6855，`17cb:1103`，PCIe0 `0x1c00000`，BAR0 `0x60200000/2 MiB`，SID `0x1c01`，IOVA `0xA0000000/256 MiB`，MSI SPI140，GPIO80/81/82/94/95/96/204（现有 K60 WIFI-PORT-PLAN）；与 zizhan/rmx3551 的 GPIO/SID 族高度一致，优先移植 `PongWifi` 板级 profile。

### 2.6 音频（TFA9873 / AW882xx）

**结论：N–Z 全部 136 篇中 `AW882xx` 命中 0 次 —— K60 的 AW882xx 功放层没有任何现成文档可抄，必须新写；TFA9873 页面只提供 AudioReach/GPR 路由与功放状态机参考，不能直接改地址复用。A–M 段 `erhai-xingxing19035.md` 有 AW882xx 实机硬件清单（无驱动代码），`asteroids.md` 有双 TFA9873 完整实现，可作为跨段补充。**

- `rmx3551.md:500-545`（SM8475 + TFA9873 双扬声器）：`ADSP/GPR/APM`、MI2S `LPAIF0 tertiary` RX `SD1`/TX `SD0`、64 KiB UEFI audio DMA、PRM clock `0x104` @ 3.072 MHz、S16→Q31、TFA9873 `KEY2` volatile 配置、`TDMSPKE`、TFA status11 `8040`、原生 0..16 线性音量 + 分段 dB 元数据；`services141` 实测 peak 66496、volume4/gain1039/mute0，但 audible output 未确认。
- `zizhan.md:602-616`：zizhan 实际是两颗 CS35L41 @0x40/0x42（SE15 `0x880000`、GPIO56/57、IRQ88/118、shared GPIO1 reset）；Pong 的 TFA9873 是 SE13 `0xa94000`、GPIO48/49、地址 `0x34/0x35`；“改地址不能复用”，`GeniI2c` 支持多字节但 amplifier wrapper 仍是 TFA9873 专用。
- `oneplus13t-shad0w23333.md:848`：OnePlus 13T（SM8750）也是两颗 TFA9873 + PMIH010x 触觉 + `PaganiAudio` HAL 插件，可作为较新 SoC 的 TFA 参考，但同样不含 AW882xx。
- **可复用的 AudioReach 框架（不依赖功放型号）**：`sheng.md:511-544` 给出 ADSP image 从 `modem_a/image` 的 `adsp` + `adsp_dtb` 加载、24×128 B intents、4 KiB GLINK intent、period buffer 放在 <4 GiB 低 DRAM（write-combined）、PRM clock `0x30c`、CoreAudio host clock 24 MHz vs 19.2 MHz timebase 的补丁、65536-frame ring/480-frame period、`zzyd-sheng-audio-addon-mount.patch` 把 `hal/ShengAudio.driver` 覆盖到 `/System/Library/Audio/Plug-Ins/HAL`。K60 的 AW882xx 只需替换功放初始化/寄存器层，GPR/AudioReach/插件挂载可沿用这套结构。
- K60 本地实测（非本页）：ADSP carveout `0x9fd00000/0x3100000`、2×AW882xx I2C `0x34/0x35`、reset GPIO1/3、IRQ88/63、spksw52、TDM 1.536 MHz tx-lines=3（见现有 BT-AUDIO-PORT-PLAN）。

### 2.7 显示 / scanout

- `rmx3551.md:255-308`：Pong 1080×2412、stride 4320；120 Hz 是显示模式请求；DCS 背光 `00b4` 写后回读；`services83` 约 40–52 ms/帧；`services84` 线性纹理 + scanout 导入限制 3 帧；`services85-88` DBV/LP/锁存/字节序修复。K60 是 1440×3200，需重算 stride/clock，但 DCS 背光与 scanout 导入策略可沿用。
- `sheng.md:297-329`：GopFramebuffer + `CONFIG_XNU_NATIVE_LEGACY_DISPLAY=y`、`sheng-vsync=120`、`sheng-dpu-scanout=2`（display bank stage-1 window，TCR2 SEP 7）、8-bit BGRA；flip 等 GPU fence；`sheng-dpu=2/3` 的 DisplayTimingProbe；direct scanout 让内容变化 808→2 次/run。
- K60 的 16.6.1 GOP/Display ABI builder 不存在（官方 `build-gop-legacy-display.py` 只接受 arm64 iOS17，`-27.py` 只接受 arm64e iPadOS27）；K60 继续走现有 MiniIOMobileFramebuffer/CPU 呈现，除非另写 16.6.1 ABI。

### 2.8 电源 / 电池 / ADSP

- `rmx3551.md:557-604`：SM8475 ADSP/RPMh、PMIC battery、PongPower 策略；`services90` 把 0x04 通知订阅修正为 `TYPE_NOTIFY` 并向 IOPMPowerSource 发布真实状态；`services84` 用 `USB_ADAP_TYPE=7` 描述适配器；`services86` fresh 快照/真实 VBUS/两轮 source/5 秒刷新，充电控制仍归固件。`drivers/PongPower` 是 `pong-power` submodule。
- `sheng.md:568-621`：PMIC GLINK owner 32778 on `PMIC_RTR_ADSP_APPS`，opcode `0x50`，fuel gauge `0x8a/0x8b` 与 `0xa6/0xa7`；battery property 11 后整体移一位（charge current 12、temp 13、charge counter 15、cycles 16、design 17、full 18、time-to-full 20、time-to-empty 21）；charge=两 gauge 剩余/满容量，current 放电为正；USB property 6 SDP/7 adapter type。方法可复用，SM8550 数值需按 K60 PMIC 重对。
- K60 的 ADSP carveout `0x9fd00000/0x3100000`、PMIC 组（pmk8350/pm8350/pm8350c/pm8350b/pmr735a/pmr735b/pm8450）来自本地计划；PongPower 是最接近的 SM8475 实现。

### 2.9 构建 / 打包脚本（可照抄结构）

| 来源 | 脚本 / 做法 | 用途 |
|---|---|---|
| `sheng.md:639-699` | `scripts/package.sh`（模板在 UniXNU/templates）、`fetch-sheng-dts.py`、`check-sheng.py`、`build-sheng-source-storage.py --policy-dir`、`fetch-adreno-inputs.py`、`prepare-sheng-*`、`build-adreno740-kits.py`、`build-ath12k-wifi.py`、`build-gop-legacy-display.py`、`build-fileset-release-reference.py --lto` | format-2 板仓的完整打包/preflight/固件抽取/GPU kit/WiFi/显示 archive 流程；K60 可把 `sheng-*` 换成 `mondrian-*` 并保留阶段划分 |
| `zizhan.md:83-129` | `tools/gen_reserved.py`、`build_fw.sh`、`build_bootimg.py`、`ci_kernel.sh`、`ci_boot_ufs.sh`、`check-wifi-host.py`、`cycle.sh`、`cycle-resume.sh` | SM8475 Pong 衍生板的最小构建/临时 boot/回归脚本；`ci_boot_ufs.sh` 1020 字节 cmdline 限制、DarwinBoot24 <1024 字节要求 |
| `rmx3551.md:48-89` | `drivers/` 12 个 `pong-*` submodule；`migration/ipados18/services*.md` 逐轮记录 | 把 Pong 主线的 driver 拆分、逐服务编号追溯；K60 可直接建 `servicesNN` 记录体系 |
| `nx769j.md:75` | `scripts/extract-root-volume-uuid.py`（从 build 出的 userdata image 读 APFS volume UUID） | 无需设备/macOS 即可填 `payload.adt.root_match_volume_uuid` |
| `rmx3823.md:63` | `[boot_image]` 必须显式写全 `kernel_addr/pagesize/...`：SM8550 DDR 从 `0x80000000` 起，默认 `0x10008000/2048` 不是内存 | K60/SM8475 同样应显式写 boot image 五字段，避免 mkbootimg 默认值静默错误 |

### 2.10 明确不可直接复用 / 负面结论

| 项 | 结论 | 出处 |
|---|---|---|
| `ShengUfs` | SM8550/sheng 专用（PHY/GCC/stream 0x60/userdata LBAs），K60 SM8475 的 stream 0xe0、GCC 0x187000 不同；保留 PongUfs | `sheng.md:248-251`、`sm-t970.md:710-715`、`odin.md:206,219` |
| `ShengNovatekTouch` | 只适用于 Novatek NT36532E；K60 是 Goodix，协议/固件/report parser 全部不同 | `nx769j.md:415-416`、`sheng.md:352-375` |
| `Adreno740` / `Sm8550Platform` | 只声明 A740/SM8550；K60 A730 必须用 PongAdreno/PongMetal | `nx769j.md:461`、`sm-t970.md:1242`、`odin.md:366` |
| `Ath12kWifi` | 只覆盖 WCN7850/QCC2072/QCN9274（ath12k）；K60 QCA6490/WCN6855 是 ath11k，须走 PongWifi | `sm-t970.md:1287`、`zizhan.md:429` |
| `CS35L43`/sheng 音频 | 6×CS35L43 + WCD938x，SM8550 专用；K60 2×AW882xx，必须新写功放层 | `sheng.md:509-544` |
| `TFA9873` Pong 代码 | 双 TFA9873 的 SE13/GPIO48/49/0x34/0x35 与 zizhan CS35L41/SE15 完全不同，不能改地址复用；K60 是 AW882xx，更不适用 | `zizhan.md:602-616`、`rmx3551.md:500` |
| `AW882xx` | N–Z 136 篇 0 命中，无任何可复用实现/寄存器/校准 | 全量检索结果 |
| A740 ABI2 / Darwin26 offset | 不适用于 A730/22H374（K60 16.6.1 更不适用） | `rmx3551.md:865` |
| `GopFramebuffer` | 官方 builder 只覆盖 iOS17(arm64) / iPadOS27(arm64e)，K60 16.6.1 无 recipe | `sheng.md:639`、OFFICIAL-DRIVER-MAP 同结论 |
| SM8550 时钟偏移 | `sm-t970.md:65,703` 反复证明把 SM8550 clock/GDSC 偏移套到 SM8250 会读错分支；K60 的 SM8475 也必须逐项重对 | `sm-t970.md:65,703,1788` |


## ③ 覆盖清单（136/136）

### N（16/16）
- [x] `nabu-3214791900-del.md`
- [x] `nabu-lee-kenneth.md`
- [x] `nabu-xingjiaostudio.md`
- [x] `nabu-zzc775.md`
- [x] `nabu-zzweiqing.md`
- [x] `nabu.md`
- [x] `nash.md`
- [x] `negroni.md`
- [x] `nio.md`
- [x] `nuwa-alex-enix.md`
- [x] `nuwa-pubglite55.md`
- [x] `nuwa-wuuuweiii.md`
- [x] `nuwa.md`
- [x] `nx721j.md`
- [x] `nx729j.md`
- [x] `nx769j.md`

### O（5/5）
- [x] `odin.md`
- [x] `odin3.md`
- [x] `oneplus13t-shad0w23333.md`
- [x] `oneplus13t.md`
- [x] `orangepi5.md`

### P（25/25）
- [x] `pandora.md`
- [x] `pd2049.md`
- [x] `pdx203-shinyquagsire23.md`
- [x] `pdx203.md`
- [x] `peridot-hoshikv.md`
- [x] `peridot-wzy114514sb.md`
- [x] `peridot.md`
- [x] `phy120.md`
- [x] `piano-xiaomi-pad-8-pro-development.md`
- [x] `piano.md`
- [x] `picasso-ahu865.md`
- [x] `picasso-huydre.md`
- [x] `picasso-minhtritt1996.md`
- [x] `picasso-silenzio111.md`
- [x] `picasso-suzukir1n.md`
- [x] `picasso-tselongson.md`
- [x] `picasso.md`
- [x] `pipa-fft-infra.md`
- [x] `pipa-xvanturing.md`
- [x] `pipa.md`
- [x] `pje110.md`
- [x] `polaris-puszekreksio.md`
- [x] `polaris-sprmd.md`
- [x] `polaris.md`
- [x] `pudding.md`

### Q（2/2）
- [x] `q2q.md`
- [x] `qemu.md`

### R（12/12）
- [x] `r11.md`
- [x] `raphael-guowenye.md`
- [x] `raphael-jackyhowh.md`
- [x] `raphael-johnleeeeeee678.md`
- [x] `raphael.md`
- [x] `rmx1971.md`
- [x] `rmx3551.md`
- [x] `rmx3823.md`
- [x] `ruby.md`
- [x] `ruyi-arnodorian123.md`
- [x] `ruyi-ehunshuaige.md`
- [x] `ruyi.md`

### S（41/41）
- [x] `sagit.md`
- [x] `sheng-16crow.md`
- [x] `sheng-ad1095445.md`
- [x] `sheng-airalex002.md`
- [x] `sheng-alghiffaryfa19.md`
- [x] `sheng-bai805.md`
- [x] `sheng-chenjin1494.md`
- [x] `sheng-enlixk.md`
- [x] `sheng-fft-infra.md`
- [x] `sheng-gkxqh.md`
- [x] `sheng-ht94911.md`
- [x] `sheng-hxzbaka.md`
- [x] `sheng-jn7163.md`
- [x] `sheng-jsongmax.md`
- [x] `sheng-kkkpc.md`
- [x] `sheng-ks114514.md`
- [x] `sheng-liangkam.md`
- [x] `sheng-lilinnan.md`
- [x] `sheng-lithosss.md`
- [x] `sheng-macos.md`
- [x] `sheng-soneoylys.md`
- [x] `sheng-thearchitectengineer.md`
- [x] `sheng-tkings4chan.md`
- [x] `sheng-v1-727.md`
- [x] `sheng-yeyingjun-codes.md`
- [x] `sheng-yuyaukong.md`
- [x] `sheng.md`
- [x] `shennong-baihem.md`
- [x] `shennong.md`
- [x] `sirius-dddqmmx.md`
- [x] `sirius-huajifruit.md`
- [x] `sirius-yooglery.md`
- [x] `sirius.md`
- [x] `sm-t733.md`
- [x] `sm-t970.md`
- [x] `songyuan-aogg2023.md`
- [x] `songyuan-wukawl.md`
- [x] `songyuan.md`
- [x] `starlte.md`
- [x] `sweet-zeroninevibedslop.md`
- [x] `sweet.md`

### T（8/8）
- [x] `t610yp.md`
- [x] `tb128fu-riceneeder.md`
- [x] `tb128fu.md`
- [x] `tb365fc.md`
- [x] `thor.md`
- [x] `thyme-coryyi.md`
- [x] `thyme.md`
- [x] `tundra.md`

### U（14/14）
- [x] `udon.md`
- [x] `uke-imposterissus13.md`
- [x] `uke-iosnjbrepo.md`
- [x] `uke-tonghuaqwq.md`
- [x] `uke-wuhaoran956-cyber.md`
- [x] `uke.md`
- [x] `umi-agxmx666.md`
- [x] `umi-jopangjovan.md`
- [x] `umi-mouya-q.md`
- [x] `umi-neowiseq.md`
- [x] `umi.md`
- [x] `unicorn.md`
- [x] `unisoc.md`
- [x] `unixnu-build.md`

### V（7/7）
- [x] `venus.md`
- [x] `vermeer-ahzcpp.md`
- [x] `vermeer-xyyyds0106.md`
- [x] `vermeer-yyx2025.md`
- [x] `vermeer.md`
- [x] `vili.md`
- [x] `vince.md`

### W（1/1）
- [x] `wayne.md`

### X（1/1）
- [x] `x9.md`

### Y（1/1）
- [x] `yunluo.md`

### Z（3/3）
- [x] `zeta.md`
- [x] `zizhan.md`
- [x] `zorn.md`
