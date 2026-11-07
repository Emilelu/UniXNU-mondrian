# DOCS-DEVICES-A-M — `docs/devices/` A–M 全量阅读纪要

> 阅读对象：`E:/hackios/UniXNU/docs/devices/`，基线 `main` HEAD `75ae626a12764c706fc0b94c52a3eea09447dbaa`（2026-11-07 快照）。
> 规模：文件名首字母 A–M 的 `.md` 共 **121 篇**（A 10 / B 2 / C 14 / D 10 / E 13 / F 17 / G 9 / H 8 / I 6 / J 2 / K 3 / L 11 / M 16），合计 2,130,447 字节；不含 `mondrian*`（另有专人）与 `pong*`。
> 方法：`find docs/devices -name '*.md' | sort` 后按 basename 首字母过滤，逐文件从第 1 行读到 EOF；生成页按 `| Area | Status |` 表提取域状态，非生成页读 `## State` 或 Record-pending 错误行；最后用文件清单反向校验 121/121，无漏篇。
> 状态口径：`DV`=device-verified，`IM`=implemented，`HV`=host-verified，`PL`=planned，`NA`=not-applicable。`S/D/G/I/N/A/P` 分别代表 **Storage/Display/GPU/Input/Network/Audio/Power** 七个重点域；其余域（Cfg/Boot/CPU/Mem/Pack/Diag）只在有差异时补注。
> K60 基准：Redmi K60 / mondrian / SM8475，Adreno 730、QCA6490（WCN6855 同族）、Goodix（`xiaomi,m11a-spi`，GENI SPI `0x990000` CS0 15 MHz，IRQ GPIO21，reset GPIO20）、2×AW882xx smartpa。K60 具体地址/GPIO 以设备仓与既有计划为准，本文只标注“页面原文数值”。

## 阅读结论（先给结论）

1. **A–M 的设备页不是同一种文档。** 121 篇中只有 **27 篇**是 `This page is generated from the device record` 的 Format-2 记录页（有 status 表）；其余 94 篇是 Device notes（社区简介 + State）、Record pending（`porting.toml` 校验错误）或 Repository link（一行链接）。因此“status 摘要”只对 27 篇成立，其余只能给文字状态。
2. **A–M 内没有一篇实现 Adreno 730 或 QCA6490。** `Adreno 730`、`QCA6490` 在全部 121 篇正文中零命中；`WCN6855` 只在 `kebab-stevedang67889.md` 的 Network 硬件描述里出现一次，且明确 `No network work has been attempted`。K60 的 GPU/Wi-Fi/BT 只能继续用 pong 系 `PongAdreno`/`PongMetal`/`PongWifi`，A–M 无可替换实现。
3. **SM8475 同 SoC 页只有 `liuqin.md`（小米平板 6 Pro），而且只到 board file + defconfig + kernel USB debug port。** 它不能提供任何已验证驱动；K60 的 SM8475 参考仍以 pong/mondrian 自身为主。
4. **对 K60 最有价值的不是同 SoC 页，而是三组“同组件/同拓扑”页：** `marble-milacy.md`（SM7475，4×A510+3×A710+1×X2 同拓扑，UFS 0x1d84000/PHY 0x1d80000/SMMU 0x15000000/stream 0xE0，Goodix GT9916S 的 SPI/CS/15 MHz/IRQ GPIO21/reset GPIO20/GCC 0x100000 与 K60 已解析值一致，GPI `0x900000` 与 clock IDs 94/134/135 待上机复核）、`fuxi-oddlylabs.md`（完整 GENI SPI 触摸 + RPMh + HID 工程模板）、`asteroids.md`（双 TFA9873 完整音频链路）；音频侧 `erhai-xingxing19035.md` 是 A–M 唯一给出 AW882xx 实机硬件清单的页面。
5. **最完整的整机参考页是 `j716f.md`（SM8250，13 域中 11 域 device-verified）与 `evb10.md`（RK3588，除 Audio 外全 device-verified）。** 它们不提供 K60 可直接搬的驱动，但提供“逐域验收 + 真机证据 + 回滚/日志”的工程范式，以及大量可复制的脚本/boot arg 组织方式。
6. **高价值长页集中在 F 组：** `fuxi.md`（13 域全 implemented 的 SM8550 全栈）、`fuxi-oddlylabs.md`、`fuxi-mouse233.md`。`fuxi.md` 页内 intro 误写成 “Xiaomi Pad 6S Pro 12.4”，但标题、`board.toml` 与全部配置均为 Xiaomi 13（fuxi），这是复制痕迹，不是设备混淆。

## ① 逐篇一行摘要

### A — 10 篇

- `a04br3.md` — MT8167（4×A35/2 GiB/eMMC）Benesse TAB-A04-BR3；已到 iPadOS 主屏，eMMC DMA + CPU framebuffer，PowerVR Vulkan transfer/readback 可用；Metal UI 加速未完成。无 status 表（Device notes）。
- `ace6.md` — SM8750 OnePlus Ace 6；Record pending：firmware procedure 缺具体条目，未生成域记录。
- `alioth.md` — SM8250 Redmi K40；UFS root + launchd + 锁屏 + 触摸可用；GPU 已发布但 SpringBoard 在 client IOVA 窗口丢 Metal device；无 Wi-Fi。S=DV D=IM G=IM I=IM N=PL A=PL P=PL（Cfg/Boot/CPU/Mem=IM，Pack/Diag=DV）。
- `alioth-fjcx555.md` — SM8250 K40 fork；Record pending：AppleKeyStoreState/RamBlock/ShengUfs/VerifiedRoot/VirtioMmioBlock 五个组件无归属 area。
- `alioth-songchiyu.md` — SM8250 K40 fork；Record pending：与 fjcx555 相同的五个组件无 area。
- `alioth-taishang1024.md` — SM8250 K40 第二份完整记录（Taishang1024 fork），正文与 alioth 同文同状态：S=DV D=IM G=IM I=IM N=PL A=PL P=PL。
- `alioth-yang232138.md` — SM8250 K40 fork；Record pending：与 fjcx555 相同的五个组件无 area。
- `amethyst.md` — SM7635 Redmi Note 14 Pro+ 5G；Record pending，仅仓库链接与占位说明。
- `amethyst-bluedmc-amethyst.md` — SM7635 Redmi Note 14 Pro+ 5G（BluedMC fork）；Record pending，仅仓库链接与占位说明。
- `asteroids.md` — SM7635 Nothing Phone 3a；UFS userdata 直接跑 iPadOS 17.7.11；S=IM D=IM G=IM I=IM N=PL A=IM P=IM（其余 Cfg/Boot/CPU/Mem/Pack/Diag 全 IM，clock=DV）。双 TFA9873 音频、Adreno gen8、触摸均有上机记录；Network 未做。

### B — 2 篇

- `bbk-a2.md` — UMS512（T610/SharkL5Pro）BBK A2/X2/X2P 平板；Record pending：`porting.toml` 第 30 行第 317 列反斜杠未转义。
- `braveark.md` — SM8635 Brave Ark 平板；UEFI、UniXNU menu、payload、DarwinBoot 与 8 核 XNU BSD init 均可用；iPadOS root image 进行中。无 status 表（Device notes）。

### C — 14 篇

- `caihong.md` — SM8650 OnePlus Pad Pro；APFS restore RAM disk 挂为 `md0`，`/sbin/launchd` 可执行、文本 console 可用；IOFramebuffer/input/完整 root 进行中。无 status 表。
- `camellia.md` — MT6833 Redmi Note 10 5G；UEFI 经 LK→Linux initramfs→`drm_linear`→`uefi_jump` 真机验证，GOP/menu 可用；Cfg/CPU/Mem/Storage=IM、Display=DV；Input/GPU/Network/Audio/Power=PL。native UFS/XNU root 未完成。
- `cas.md` — SM8250 小米 10 Ultra；UEFI menu + CPU0 platform start 已验；Cfg/CPU=DV、Boot=DV、Mem=IM、Pack=IM；Storage/Display/Input/GPU/Network/Audio/Power/Diag 全 PL。
- `cas-pxl777806.md` — SM8250 Mi 10 Ultra（pxl777806）；仅仓库链接，无内容。
- `cepheus.md` — SDM855/SM8150 小米 9；device repo 与 boot chain 已备，无硬件结果。无 status 表（Device notes）。
- `cepheus-c0der88.md` — SM8150 小米 9（c0der88）；仅仓库链接。
- `cepheus-didazhiqian.md` — SM8150 小米 9（didazhiqian）；仅仓库链接。
- `cepheus-yangqi0408.md` — SM8150 小米 9（YangQi0408）；仅仓库链接。
- `cheeseburger.md` — MSM8998 OnePlus 5；Record pending：configuration 需 host evidence。
- `cheeseburger-lss717.md` — MSM8998 OnePlus 5（lss717）；仅仓库链接。
- `cheeseburger-maozedongae.md` — MSM8998 OnePlus 5（maozedongae）；仅仓库链接。
- `chiron.md` — MSM8998 小米 MIX 2；最小 4 KiB XNU 与自制 PID 1 heartbeat 已在真机跑起；完整 iOS userland 与存储路径未完成。无 status 表。
- `chiron-sbccc1888.md` — MSM8998 小米 MIX 2（sbccc1888）；仅仓库链接。
- `clover.md` — SDM660 小米平板 4 LTE；eMMC 上的 mockfs root 可跑静态 EL0 test init（fork/exec、Mach call、EL0 panic 有记录）；APFS publication/mount/file-readback 仅有 probe，缺设备记录。无 status 表。

### D — 10 篇

- `d2xq.md` — SM8150 三星 Note10+ 5G；Record pending：缺 audio/cpu/diagnostics/gpu/input/memory/network/packaging/power/storage 十个 area。
- `dada.md` — SM8750 小米 15；Record pending：RamBlock 组件无 area。
- `dada2.md` — SM8750 Redmi K80 Pro；Record pending：`device.name` 与 `board.toml` 不一致。
- `dali.md` — MT6991 Redmi K80 Ultra；目标仅单核 XNU early-boot checkpoint（经 UniXNU+DarwinBoot），storage/root/iOS userland 不在本阶段。无 status 表。
- `dandelion.md` — MT6765 Redmi 9A；Record pending：configuration 状态非法。
- `dipper.md` — SDM845 小米 8；UEFI/boot image/menu/payload FAT/synthetic DarwinBoot handoff 真机可用；fajita kernel 到 BSD init，但无 NativeUfs，root device wait 卡住。无 status 表。
- `dizi.md` — SM7435 Redmi Pad Pro（ruan unverified）；Record pending：`device.os_profile` 与 `board.toml` 不一致。
- `droidvm.md` — crosvm on Gunyah 的 DroidVM guest；kernel build、verified root、锁屏/主屏、virtio-input、virtio-net DHCP、AppleKeyStore keychain、NativeAdreno/Metal 均已工作（SM8650 为主）；完整 GPU app 未认证。无 status 表（Device notes，含逐 Stage 状态表）。
- `droidvm-lateautumn233.md` — DroidVM guest（lateautumn233）；仅仓库链接。
- `droidvm-neko17awa.md` — DroidVM guest（Neko17awa）；仅仓库链接。

### E — 13 篇

- `e5.md` — UMS9621 融悦 E5；Record pending：display findings 需具体条目。
- `elden.md` — SM8750P Lenovo Legion Y700 Gen 4；Phase 1 UEFI 已 device-verified，CPU/Mem=IM；Storage/Display/Input/GPU/Power=PL；Network/Audio=NA。Format-2 迁移中。
- `elish.md` — SM8250-AC 小米平板 5 Pro Wi-Fi；board data/staged defconfigs/ADT scripts 已备，`check-elish.py` 0 error/2 TODO；未 build。无 status 表。
- `enchilada.md` — SDM845 OnePlus 6；仓库有 board file/kernel config/device scripts，无硬件结果。无 status 表。
- `enchilada-keyfan.md` — SDM845 OnePlus 6（keyfan）；仅仓库链接。
- `enchilada-wangshaofan82-png.md` — SDM845 OnePlus 6（wangshaofan82-png）；仅仓库链接。
- `enuma.md` — SM8250 小米平板 5 Pro 5G；source 可组装 prelink/ADT/FAT/boot-v3 payload；EL1 有界 framebuffer 读取的计时观测；可见 GOP/menu、kernel/storage/userland 均待验证。无 status 表。
- `enuma-alghiffaryfa19.md` — SM8250 小米平板 5 Pro 5G（alghiffaryfa19）；仅仓库链接。
- `enuma-tlrenhb.md` — SM8250-AC 小米平板 5 Pro 5G（Tlrenhb）；仅仓库链接。
- `erhai.md` — SM8750 OnePlus Pad 2 Pro；XNU entry bring-up：已测 FD base `0xA7000000`/GIC/timebase/panel/touch/boot 分区，UEFI payload embed、S1–S6 屏幕 checkpoint 可用；root/UFS/GPU 未启用。无 status 表（Device notes，含 area 状态表）。
- `erhai-xingxing19035.md` — SM8750 OnePlus Pad 2 Pro（xingxing19035）Format-2；Cfg/Boot/Input/Pack=HV，Diag=DV；CPU/Mem/Storage/Display/GPU/Audio/Power=PL。音频硬件为 2×AW882xx smartpa + aw87xxx PA（详见②）；DSP carveout ADSP `0x9ed80000`/CDSP `0x9eb00000`/SoCCP `0x9ec00000`。
- `erhai-zczyh0922.md` — SM8750 OnePlus Pad 2 Pro（zczyh0922）；仅仓库链接。
- `evb10.md` — RK3588 EVB10 V10；除 Audio=IM 外全域 device-verified：iPadOS 17.7.11 userland、eMMC root+Data、VOP2 显示、Goodix GT1158 触摸、Mali-G610 ~50 fps、2.4 GHz Wi-Fi；GPU 调频/中断完成、5 GHz、音频听感、热限制未做。

### F — 17 篇

- `fairlady.md` — SM8850 OnePlus 15T；有早期 UEFI/ADT/S1–S6 屏幕诊断，无硬件结果。无 status 表。
- `fajita.md` — SDM845 OnePlus 6T；UEFI/menu 真机可用（`fastboot boot`+空 ramdisk），XNU 23.6.0 到 root mount；无 storage driver，root volume 停在 IOMedia/Apple_HFS wait。无 status 表（含逐 Stage 表）。
- `flashlm.md` — SM8150 LG V50 ThinQ；仅仓库链接。
- `fuxi.md` — SM8550 小米 13；13 域全部 implemented（arm64e-os=PL）：完整 SM8550 参考栈——ShengUfs（UFS `0x1d84000`/PHY `0x1d80000`/SMMU `0x15000000`/stream `0x60`）、GopFramebuffer、Adreno740/Metal、Ath12kWifi、CS35L43×6+WCD938x 音频、PMGR 电源、`scripts/package.sh`；页内 intro 误写“Xiaomi Pad 6S Pro 12.4”（复制痕迹），标题/board 为 Xiaomi 13。
- `fuxi-0721gpt.md` — SM8550 小米 13（0721GPT）；仅仓库链接。
- `fuxi-hanzi123-bilp.md` — SM8550 小米 13（hanzi123-bilp）；仅仓库链接。
- `fuxi-kerfand.md` — SM8550 小米 13（Kerfand）；仅仓库链接。
- `fuxi-kkkpc.md` — SM8550 小米 13（kkkpc）；Cfg/Boot=HV（host 侧 profile 解析通过），其余全域 PL；复用 mouse233 的 board data，未上机。
- `fuxi-ljhhkx529.md` — SM8550 小米 13（ljhhkx529）；仅仓库链接。
- `fuxi-minecraftvm.md` — SM8550 小米 13（MinecraftVM）；仅仓库链接。
- `fuxi-mouse233.md` — SM8550 小米 13（mouse233）；RAM boot：UEFI USB bulk receiver→DRAM→DarwinBoot→XNU 从 RAM block device 切到 APFS system volume。Mem/Storage=device-verified，Boot/Pack=host-verified，Cfg=IM，Diag=DV；CPU/Display/GPU/Input/Network/Audio/Power=PL。
- `fuxi-oddlylabs.md` — SM8550 小米 13（OddlyLabs）；CPU/Memory/Storage/Input/Power=IM，Boot/Pack=host-verified，Diag=IM；Display/GPU/Network/Audio=PL。FTM5 触摸完整链路（GENI SPI+RPMh+GPIO+FIFO+HID）已上机，见②。
- `fuxi-sohytrs.md` — SM8550 小米 13（Sohytrs）；仅仓库链接。
- `fuxi-star-mailaz.md` — SM8550 小米 13（Star-mailaz）；Record pending，仅占位说明。
- `fuxi-unixnu-fuxi.md` — SM8550 小米 13（UNIXNU-FUXI）；仅仓库链接。
- `fuxi-xyvern08371.md` — SM8550 小米 13（Xyvern08371）；仅仓库链接。
- `fuxi-yigezhong011-ops.md` — SM8550 小米 13（yigezhong011-ops）；仅仓库链接。

### G — 9 篇

- `gauguin.md` — SM7225 Moto G 5G；仓库有 board/build 步骤，无硬件结果。无 status 表。
- `giulia.md` — SM8650 OnePlus Ace 5；iOS 16/Darwin 22 到 Hello+Setup，1264×2780 全屏覆盖、触摸对齐；CPU0/native UFS/HFSX root/launchd/USB CDC 可用；Wi-Fi 到 PCIe/BHI/BHIE/AMSS/QMI，止于 QMP open；GPU/audio 仅准备代码。无 status 表。
- `giulia-349942669lh-art.md` — SM8650 OnePlus Ace 5（349942669lh-art）；仅仓库链接。
- `gta4l.md` — SM6115 三星 Tab A7 10.4；board/defconfig/fetch/tree 可跑，固件 3,145,728 bytes、ADT 13,180 bytes；kernel 未 build（需 macOS），硬件 boot 未演示。无 status 表（含 Layer 表）。
- `gta4l-gta4lunix.md` — SM6115 三星 Tab A7 10.4（gta4lunix）；Format-2 迁移记录：PMGR-linked host kernel、RAM-root/EL0 fixture、QEMU checkpoint 有主机结果，eMMC bring-up 未做；13 域全 PL。
- `gta4l-ilovemykedi.md` — SM6115 三星 Tab A7 10.4（ilovemykedi）；仅仓库链接。
- `gts9uwifi.md` — SM8550 三星 Tab S9 Ultra Wi-Fi；仓库存在，无硬件结果。无 status 表。
- `guacamole.md` — SM8150 OnePlus 7 Pro；UEFI/menu/payload FAT/DarwinBoot 可用，XNU r15 到 iOS userland；GPU/GMU 卡在 ios-sweet 树。无 status 表（含 Stage 表）。
- `guamp.md` — SM6115 Moto G9 Play；Mu-Silicium firmware 可 fastboot 启动并显示 UniXNU menu；kernel 未 build。无 status 表。

### H — 8 篇

- `haydn.md` — SM8350 Redmi K40 Pro；board/ADT/UEFI plan 就绪（preflight 0 error），firmware/payload/boot image 已 build 并 byte-check；kernel/userdata 需 macOS，硬件 boot 未跑。无 status 表（含 Layer 表）。
- `haydn-iamojz.md` — SM8350 K40 Pro（iamOJZ）；Record pending：configuration implemented 但缺 evidence。
- `haydn-xiaomi-haydn-dev.md` — SM8350 K40 Pro（xiaomi-haydn-dev）；仅仓库链接。
- `hero2lte.md` — Exynos 8890 三星 S7 Edge；Phase 1 UEFI/Display/Input 已 device-verified，CPU=IM；Memory/Storage/GPU/Network/Audio/Power=PL。XNU 走 ArmCpu GICv2，仍需原生 storage/display/input/power 驱动。
- `houji.md` — SM8650 小米 14；iOS 16.7.16 桌面在 8 核上经 native UFS/HFSX root 跑起；1200×2670 全屏、触摸对齐、recent-app cards 正常，显示走 CPU 合成；Adreno 750 仅 GMU/HFI/alloc/HWSCHED/power 诊断，命令提交/fence/Metal 未做。无 status 表。
- `houji-kizashi3.md` — SM8650 小米 14（Kizashi3）；仅仓库链接。
- `houji-sakayorilroha.md` — SM8650 小米 14（SAKAYORILROHA）；仅仓库链接。
- `hummer.md` — SM8750 OnePlus Ace 5 Pro；UEFI/XNU/6 核/physical root volume 到 Hello；160 MiB payload 含 OS/SystemOS 提取、UFS policy、RAM Data；持久 Data/GPU 加速/实体触摸待做。无 status 表。

### I — 6 篇

- `index.md` — `docs/devices/` 设备总索引：264 行设备表（Device/SoC/Format/Documentation/Repository），A–M 的 SoC 归属与文档类型以本页为准；不是设备记录。
- `instantnoodlep.md` — SM8250 OnePlus 8 Pro；Format-2 记录但 13 域全 planned，仅 board/仓库脚手架。
- `instantnoodlep-zhangp996.md` — SM8250 OnePlus 8 Pro（zhangp996 独立仓）；同样 13 域全 planned。
- `ishtar.md` — SM8550 小米 13 Ultra；Cfg/Boot/CPU/Mem/Pack/Diag=IM；Storage/Display/Input/GPU/Network/Audio/Power=PL。复用 sheng kit 与 `board.toml`/partition geometry 模式，未上机。
- `ishtar-markakash.md` — SM8550 小米 13 Ultra（markakash）；仅仓库链接。
- `ishtar-peter8889.md` — SM8550 小米 13 Ultra（peter8889）；仅仓库链接。

### J — 2 篇

- `j716f.md` — SM8250 Lenovo Xiaoxin Pad Pro 2021 TB-J716F；除 Network/Audio=PL 外全域 device-verified（Storage/Display/Input/GPU/Power/Diag 均有真机证据），含 Format-1→2 迁移、FAST/日志/reader、Goodix GT7386 I2C（SE4 `0x00990000`, addr `0x5D`, 10 点）与 PM8150 PON 键；超长记录（1336 行），是 A–M 中最完整的整机参考。
- `j716f-emptyghost.md` — SM8250 TB-J716F（EmptyGhost）；Cfg=HV、Boot/Mem/Display/Input/Diag=DV；CPU/Storage/GPU/Power=PL，Network/Audio=PL。

### K — 3 篇

- `kebab.md` — SM8250 OnePlus 8T；GFander 16 KiB-page iOS 16.7.16 port：UFS partition/HFS root/static EL0 init 有真机 log；console/full userland/多核/USB 未完；stevedang 分支 firmware/menu/按键/panel log 可用。无 status 表。
- `kebab-stevedang67889.md` — SM8250 OnePlus 8T（stevedang）；Cfg/Boot/CPU/Mem/Storage=IM/DV，Display/Input=DV，Pack/Diag=DV；GPU/Network/Audio/Power=PL。Network 仅列 WCN6855 combo，明确 “No network work has been attempted”。
- `komodo.md` — Tensor G4 Pixel 9 Pro XL；硬件测试到 firmware menu/test payload/entry probe（prebuilt uke XNU），post-MMU reset probe 有记录；native Tensor platform/root 未做。无 status 表。

### L — 11 篇

- `lafa.md` — SM8850 realme GT8 Pro；仅仓库链接。
- `lavender.md` — SDM660 Redmi Note 7；仅仓库链接。
- `lemonades.md` — SM8250-AC OnePlus 9R；board/defconfig/ADT/packaging 齐全，Linux LLVM19 产出 3 MiB FV 与 header-v2 boot image；硬件 firmware check/kernel/root 未做，Synaptics S3908 触摸待集成。无 status 表。
- `liuqin.md` — **SM8475 小米平板 6 Pro；A–M 中唯一 SM8475 设备页**：仅 board file、defconfig、kernel USB debug port，UEFI 集成是下一步；无硬件结果。无 status 表。
- `lmipro.md` — SM8250 Redmi K30 Pro Zoom；Record pending，仅占位。
- `lmipro-yang232138.md` — SM8250 K30 Pro Zoom（yang232138）；仅仓库链接。
- `lumia950.md` — MSM8992 Lumia 950；使用手机自带 UEFI/UniXNU menu/DarwinBoot，无 boot 记录。无 status 表。
- `lumia950-shrimpapplepro.md` — MSM8992 Lumia 950（shrimpapplepro）；仅仓库链接。
- `lumia950-twisstedtoast.md` — MSM8992 Lumia 950（TwisstedToast）；仅仓库链接。
- `luming.md` — SM8735 小米 Civi 5 Pro；记录 measured board inputs 与 source/ADT host checks 通过；kernel/prelink/UEFI build 未做。无 status 表。
- `luming-infinityex-rsxq.md` — SM8735 Civi 5 Pro（infinityEX-RSXQ）Format-2 skeleton；13 域全 PL，只有 measured SM8735 facts、AMFI+PMGR config、SHNGROOT/VerifiedRoot userdata recipe。

### M — 16 篇

- `m2381.md` — SM8550 魅族 20 Classic；m2381 分支有 device tree（`devices/m2381/unixnu-m2381`）与 firmware integration（`devices/m2381/uefi`）；kernel/prelink/payload 进行中。无 status 表。
- `m2381-riverkawa271828.md` — SM8550 魅族 20 Classic（RiverKawa271828）；Record pending：`device.os_profile` 与 `board.toml` 不一致。
- `malachite.md` — MT6878（Dimensity 7300-Ultra）POCO X7/Redmi Note 14 Pro 5G；UEFI 可用（直进 XNU loader，无 menu），UFS 可用（iOS 16.5 system image on userdata 为 `md0`）；XNU 单核启动、rootfs 加载、launchd/lsd 运行；iOS userland 启动异常；Display 仅 LK framebuffer 文本；USB/触摸/GPU/WiFi/BT/audio 全未实现。无 status 表（含 Stage 表）。
- `marble.md` — SM7475 Redmi Note 12 Turbo/POCO F5；legacy XNU 8796 源 port，历史短暂到 iOS Hello，touch/setup 未完成；非 Format-2，13 域全 PL。Goodix GT9916R 的 SPI/GPI 参数清单见②。
- `marble-milacy.md` — SM7475 Redmi Note 12 Turbo/POCO F5（MiLacy）Format-2；Cfg=IM、Boot/Storage/Pack=DV；CPU/Mem/Display/Input/GPU/Network/Audio/Power=PL（GPU/Network/Audio=NA）。UFS `0x1d84000`/PHY `0x1d80000`/SMMU `0x15000000`/stream `0xE0` 与 Goodix GT9916S 的 SPI `0x990000`/CS0/15 MHz/GPIO20/21/GPI `0x900000`/clocks 94/134/135 与 K60 高度一致，见②。
- `meizu21.md` — SM8650 魅族 21；13 域全 PL，SM8650 common repo 与 UEFI board port 尚未建立。
- `merlinx.md` — MT6768 Redmi Note 9；Record pending：GopFramebuffer 组件无 area。
- `merlinx-gytis283123.md` — MT6768 Redmi Note 9（Gytis283123）；Cfg/Boot/Storage/Diag=DV，Display/GPU/Power=IM，CPU/Mem/Pack=IM；Input/Network/Audio=PL。Mali-G52 M2/M3/M4/M6 内核路径完成、GPU_ID/MALI RC 0 有记录；GPU job/fence、NativeMali、PanVK、userland display 未完成。
- `mh2lm.md` — SM8150 LG G8X ThinQ；仅仓库链接。
- `miatoll.md` — SM7125 Redmi Note 9S/9 Pro/Note 10 Lite/POCO M2 Pro；iPadOS 17.7.11 profile，经 Mu-Silicium+DarwinBoot；first-console 阶段，13 域全 PL，无 device-verified。
- `munch.md` — SM8250 Redmi K40S；Record pending：gpu verification evidence 需 commit。
- `munch-erodenine.md` — SM8250-AC Redmi K40S（ErodeNine）；Cfg/Boot/Mem/Pack=PL，CPU=IM，Storage=DV，Display/Input/GPU/Network=IM，Diag=DV；硬件结果继承 alioth，未在 K40S 实测。
- `munch-upcry.md` — SM8250-AC Redmi K40S（Upcry）；Record pending：`device.name` 与 `board.toml` 不一致。
- `muyu.md` — SM8635 小米平板 7 Pro；仅仓库链接。
- `myron.md` — SM8850 Redmi K90 Pro Max/POCO F8 Ultra；仅有 core/driver forks（A8XX Adreno 寄存器表 + CPU affinity），无 device repo/board/defconfig/硬件结果。无 status 表。
- `myron-typeun.md` — SM8850 Redmi K90 Pro Max（Typeun）；仅仓库链接。

## ② K60 可复用清单

### 2.1 同 SoC / 同代平台：SM8475 与 SM8550

- **`liuqin.md`（SM8475，唯一同 SoC）**：可复用的只有 `board.toml` 的字段命名与 SM8475 平台身份写法（仓库 pin `907b8e91c88e71f698292abfd8db49ba90492dc4`）；页面自述只有 board file、defconfig、kernel USB debug port，UEFI 集成尚未开始，**没有任何已验证驱动可搬**。K60 的 SM8475 主体仍以 `PongUfs`/`PongAdreno`/pong 系为准。
- **`marble-milacy.md`（SM7475，4×A510+3×A710+1×X2 同拓扑）**：A–M 中对 K60 最有价值的整机页之一。可直接对照/复用的数值与做法：
  - CPU/GIC：GIC distributor `0x17100000`/`0x10000`，redistributors `0x17180000`/`0x200000`，stride `0x40000`，timer 19.2 MHz；`sm7475.dtsi` 声明 cpu0–7，board 标 cpu0–3 E、cpu4–7 P；SoC patch 加 `MAX_CPUS=8`、`MAX_CPU_CLUSTERS=2` + Edge scheduler。K60 是 4×A510 + 3×A710 + 1×X2 三簇，**不能照抄 4E/4P 的二分**，但 `zzyf-sheng-amp.patch`/`MAX_CPU_CLUSTERS` 这一课同样适用（`fuxi-oddlylabs` 也复现了 `MAX_CPU_CLUSTERS=1` 导致 `ml_parse_cpu_topology` panic）。
  - UFS：host `0x1d84000/0x3000`、PHY `0x1d80000/0x2000`、apps SMMU `0x15000000`、GCC `0x100000`、stream `0xE0`、4096-byte LBA——与 K60 的 `pong,ufs-hc-base 0x1d84000`、`pong,smmu-base 0x15000000`、`pong,smmu-stream-id 0xe0` 对齐。可复用的实现点：ShengUfs fork 的 `native-ufs-stream`（默认 0xE0）、`native-ufs-smmu-takeover`、`NATIVE_UFS_PROBE_ONLY` 守卫，以及“固件已占用 bank 2 的 exclusive SMR（slot=2 bank=74 smr=800000e0 s2cr=2）”的接管逻辑。
  - IOBlockStorageDevice ABI：`native-storage-original-bindings.S` 记录 vtable `0xfffffff005cb44c0`（+16，190 slots，14 pure virtual）、metaclass `0xfffffff006add1d0`、ctor `0xfffffff00496ed98`、D2 `0xfffffff00496edb8`、D1/D0 brk traps；由 `scripts/build-storage-bindings.py` 在 `XNU_NATIVE_UFS_FULL=1` 时归档。若 K60 也走 iPadOS 17.7.11 的 `IOStorageFamily`，这是最有价值的 ABI 锚点（但必须用 K60 自己的 kernel.macho 复核）。
  - Goodix：见 2.2。
- **`fuxi.md`（SM8550，13 域全 implemented 的参考栈）**：同代平台结构模板，可复用：
  - UFS host `0x01d84000/0x3000`、PHY `0x01d80000/0x2000`、GCC `0x00100000`、apps SMMU `0x15000000`、UFS stream `0x60`、LUN0 4096-byte、userdata LBA `3094592..64007162`；`payload.adt.owned_memory_size=0x130000000`、`dram_size=0x80000000`、splash `0xb8000000+0x2b00000`。
  - `board.toml` 的 `os_overrides` 多 profile 写法、`profiles.merge` **数组整体替换**（board 必须重复完整列表）、`scripts/package.sh`（无板值，board.toml `[package]` 指定 checkout/defconfig）、`scripts/check-sheng.py`/`scripts/read-sheng-log.py` 的验收入口。
  - 音频架构（CS35L43×6 + WCD938x）见 2.3；GPU（A740）不可直接用于 A730，见 2.5。
- **`fuxi-oddlylabs.md`（SM8550）的 CPU bring-up 教训**：`armcpu-spi-ipi=1` 必须开（SGI 在 fuxi 不达）、`armcpu-self-ipi=1` 才清 SIGPdisabled；`sheng-smp=1` 起 7 个 secondary；`MAX_CPU_CLUSTERS=1` + E/P 两簇会在 `ml_parse_cpu_topology` 断言 panic，修法是 `zzyf-sheng-amp.patch`（`__ARM_AMP__`, `MAX_CPU_CLUSTERS 2`, Edge scheduler）。K60 的四核 A510 + 三核 A710 + X2 三簇比这更复杂，必须按簇逐一验 `CPU_ON`/timer/IPI。
- **`fuxi-mouse233.md`（SM8550）的 RAM-root 方案**：UEFI USB bulk receiver 把 payload 收进 DRAM→DarwinBoot→XNU 以 RAM block device `md0` 起步→`pivot=OK old=md0 newroot=apfs` 切到 APFS system volume；`scripts/build-fuxi-usb-ram.py`、`scripts/test-usb-ram-full.py`、`scripts/check-usb-system-mount.py` 与 `--boot-profile usb-system` 可整套借用。关键参数：`dram_size=0x80000000`、KMEM headroom `662548480` bytes、handoff skew 与 kernel.macho 最低非空段 mod 2 MiB 对齐（记录值 skew `0x7c000`）。K60 若 UFS root 暂时卡住，可先用这条 RAM-root 链把 userland 跑起来。
- **`ishtar.md`（SM8550）**：只可复用 `board.toml` 的 partition geometry/`kit=sheng` 配置模式，驱动全部 planned，不能作为实现参考。

### 2.2 Goodix 触摸：A–M 的全部可用线索

| 页面 | 控制器/型号 | 页面给出的总线与参数 | 可复用价值 |
|---|---|---|---|
| `marble-milacy.md` | Goodix **GT9916S** | SPI `0x990000`，SPI 605，IRQ GPIO21，reset GPIO20，GPI `0x900000`，clocks 94/134/135；CS0，15 MHz child limit | **与 K60 已解析的 SPI/CS/15 MHz/IRQ GPIO21/reset GPIO20/GCC 0x100000 一致**；GPI `0x900000` 与 clock IDs 94/134/135 待上机复核。可直接抄 board 参数与 `QcomGeniSpi` 选择，但 Goodix 协议未实现 |
| `marble.md` | Goodix **GT9916R** | SPI `0x990000`，CS0，15 MHz，GPIO20 reset/GPIO21 IRQ；GCC IDs 94/134/135；GPI TX0/RX1/SEID4/protocol1/64TREs；GPI 与 wrapper 各自独立 SMMU context | 补充 GPI DMA 细节；明确“无 Goodix SPI transaction / 无物理触摸” |
| `j716f.md` | Goodix **GT7386**（I2C） | SE4 `0x00990000`，addr `0x5D`，10-point multi-touch；iPadOS 17.7.11 桌面已验证 | A–M 唯一 **device-verified 的 Goodix 触摸**；I2C 不是 K60 的 SPI，但产品 ID/固件/多点协议与 HID 适配可参考；页面自述坐标/HID 尚未适配 |
| `evb10.md` | Goodix **GT1158**（I2C5） | addr `0x14`，product id 1158，10 点，720×1280→1080×1920；400 kHz 扫描见 `0x14/0x5d`；352 HID reports | 完整的通用 Goodix probe/事件/HID 参考（轮询、坐标映射、产品 ID 读取） |
| `fuxi-oddlylabs.md` | ST FingerTip **FTM5**（不是 Goodix） | QUP1 SE4 `0xa90000`，wrapper `0xac0000`，SMMU stream `0xa3`，pins 44–47，IRQ GPIO25（active low，TLPI SPI 208），reset GPIO24；12 MHz SPI mode 0；rails ldob12 1.8 V（RPMh `0x40900`）/ldom6 3.2 V（RPMh `0x41b00`） | **不是同控制器，但这是 A–M 唯一完整跑通的 GENI SPI + RPMh + GPIO + FIFO + HID 触摸链路**，是 K60 Goodix 驱动的最佳工程模板 |

**从 `fuxi-oddlylabs` 可复制的四阶段流程（K60 把 FTM5 换成 Goodix 协议即可）：**
1. Stage 1：快照 QUP clocks、pins、两路 rail 到 command database。
2. Stage 2：RPMh 在 apps RSC DRV2（`tcs-offset 0xd00`）的 active TCS 2 先投 vdd 再投 avdd，等 3 ms，再投 QUP clocks、配 pins。**页面实测：`fuxi-touch-power=0` 时控制器三次 reset 都无响应、chip id `00 00`；恢复 rail vote 后每次都能读到 `36 40`——rail 必须投。**
3. Stage 3：GENI SPI 12 MHz；reset 拉低 10 ms；轮询事件 `03`（2 ms×100 ms×3 次，再走 ICR 4-wire fallback），读 chip id。
4. Stage 4：`A0 00 00` → 50 ms → `A0 00 01`，下降沿中断、drain FIFO，按 `ShengHidInput` ABI 发布触点。页面的 FTM5 事件字节 bit2-3 还带 major axis 高位，`0x13..0x1F` 全是 enter；K60 Goodix 需按 Goodix report packet 替换。

**可直接抄的构件/参数：**
- `scripts/build-fuxi-touch.py`、`scripts/build-fuxi-hid-input.py`；`package/NativeHidInput.cpp`（ShengHidInput `71a40e7` 的未改副本）；`package/FuxiHidProbe.cpp`；`patches/xnu/fuxi-touch-probe.patch`（在 `bsd_init` 的 `IOKitInitializeTime()` 后调 `native_touch_probe()`）。
- Boot args：`fuxi-touch=1..4`、`fuxi-touch-poll=1`、`fuxi-touch-hid=1`、`fuxi-touch-panic=1|2`、`fuxi-touch-power=0`、`fuxi-touch-hz`、`fuxi-touch-tcs`、`fuxi-touch-map`。
- HID 关键经验：`IOHIDDevice` 208 bytes；`IOHIDResource` 找到后注册 NativeHidInput 的 metaclass；**必须创建“keyboard collection 先、digitizer 第二”的默认设备**，否则 IOHIDEventDriver 不 attach（`sheng-touch-hid=1` 才给 digitizer）。
- 相关 commit：`e901139`（加 `CONFIG_XNU_DT_PANIC_REGION` 后到 `bsd_init`）、`484a650`（PMGR bridge，过 root device wait）、`22579b4`/`11db5c0`（HID 报告到 IOHIDFamily）。
- 页面的坑：GENI 没有 vendor 驱动所用的 10 µs CS hold（`SPI_DELAY_CS`）设置；一次 14 次 boot 中有一回在 touch 阶段自行 reset，原因未知。

### 2.3 音频：AW882xx 与 TFA9873

- **`erhai-xingxing19035.md`（SM8750）— A–M 唯一 AW882xx 实机清单**：该机音频硬件是 `aw882xx_smartpa` + `aw87xxx_pa` + `aw_haptic`，接近传感器 tmf8806/ams-tof；DSP 固件区在 live DT 保留为 ADSP `0x9ed80000`、CDSP `0x9eb00000`、SoCCP `0x9ec00000`。页面 Audio 仍是 `planned`，只可作为 K60 的硬件命名/固件区对照，**没有 AW882xx 驱动代码**。
- **`asteroids.md`（SM7635）— TFA9873 双功放完整实现（A–M 唯一跑通）**：两个 NXP TFA9873（P `0x34` slot 0、S `0x35` slot 1），QUPv3 wrapper 1 SE6（SE13，`0x898000`，gpio59/60），reset gpio141/142 active-high，primary MI2S gpio15–18 function 2，两个 32-bit slot @48 kHz。关键坑：**功放的数据在 SD1（gpio17）而不是 SD0**，`asteroids-audio-i2s=0x200200` 才出声；功放等 bit clock 才上电，必须在 DSP graph 启动后再上；TFA9873 `STATUS0` bits 1/2/4（DCOCPOK/OTDS/UVDS）是 ok flag 不是 alarm。可复用 `scripts/prepare-asteroids-tfa.py`（从 `tfa98xx.cnt` 生成 `AsteroidsTfaConfig.h`）与 `package/AsteroidsAudioProbe.cpp`（`AudioProbe.cpp` + `AsteroidsTfa9873.c` 替换 CS35L43）的结构。
- **`fuxi.md`（SM8550）— CS35L43×6 + WCD938x 完整音频架构**：六颗 CS35L43 挂在 QUP1 SE5 / QUP2 SE0（I2C `0x40..0x42`），共享 reset gpio90，secondary MI2S gpio121–124；麦克风 WCD938x 在 TX SoundWire master `0x6d30000`、reset gpio108、ldob15。重要经验：DSP 直通 ASP RX1（不走 DSP 图），16-bit I2S 48 kHz、SoC 为 clock master；**给音频流编 translating SMMU context 会重启板子，hypervisor 保留这些 context bank**；AudioReach/GPR、19.2 MHz host clock、plug-in/service 时间线可整套借鉴。K60 的 AW882xx 功放寄存器不同，但“I2S + I2C + reset + DSP graph + HAL plug-in”的分层可复用。

### 2.4 UFS / Storage / root

- **`marble-milacy.md`**：见 2.1，`native-ufs-stream=0xE0` + `native-ufs-smmu-takeover` + probe-only 是 K60 最接近的 UFS 诊断模板；它还记录了 `IOBlockStorageDevice` 的绝对符号/vtable 地址，可作为 K60 在 iPadOS 17.7.11 上链接 `NativeUfsBlock` 的 ABI 复核起点。
- **`fuxi.md`**：完整可用的 `ShengUfs` 板级输入：host/PHY/GCC/SMMU/stream/context bank/DMA 宽度/缓存维护；`payload.adt.root_match_volume_uuid=546DFF4A-4172-4026-9F1B-7FDAD45F3D2E`（23F84 示例）；`CONFIG_XNU_NATIVE_UFS=y`、`native-source-storage=1 native-ufs-root=1`。
- **`fuxi-mouse233.md`**：RAM-root 的完整 pivot 记录（`md0`→APFS，`pivot=OK`，`/sbin/launchd` SHA256 校验），以及 `scripts/test-usb-ram-full.py` / `scripts/check-usb-system-mount.py` 的 host+device 验收流程；K60 若需要“先跑 userland、后补 UFS”，这是现成模板。
- **`j716f.md`**：SM8250 上 Storage=DV 的整机记录，可参考它的分区/日志/reader 工具链与 `scripts/porting-record.py check` 的验收口径；具体 UFS 常量不适用于 SM8475。
- **`j716f-emptyghost.md`**：同机第二份迁移记录，Storage 仍 PL，价值低于主 j716f 页。

### 2.5 GPU / Network：A–M 的明确空白

- **GPU（Adreno 730）**：121 篇中没有 `Adreno 730`/A730 页面。可参考的只有 `fuxi.md`/`ishtar.md`/`asteroids.md` 的 Adreno740（SM8550，不同代）、`alioth.md` 的 Adreno650、`elden.md` 的 Adreno 830；`AdrenoMetal`/`AdrenoPM4`/`AirNir` 是通用前端/编译工具，但提交后端必须换 A730 寄存器/固件。K60 继续用 `PongAdreno`/`PongMetal`，A–M 不提供可替换实现。
- **Network（QCA6490/WCN6855）**：121 篇中 `QCA6490` 零命中；`WCN6855` 仅在 `kebab-stevedang67889.md` 的 Network 硬件依赖里一行“WCN6855 Wi-Fi and Bluetooth combo”，且该页 `Network=PL`、`No network work has been attempted`，firmware/校准/驱动全缺。`fuxi.md` 的 `Ath12kWifi` 是 WCN7850 路线，不是 QCA6490。K60 必须继续走 pong 的 `PongWifi`（ath11k/QCA6490）路线，A–M 无先例。
- **蓝牙**：A–M 无任何 QCA6490 BT 实现；`kebab.md`/`kebab-stevedang67889.md` 只有 WCN6855 combo 的硬件名。K60 的 QCA6490 GENI UART/HS-UART 方案只能按 `BT-AUDIO-PORT-PLAN.md` 自建。

### 2.6 构建/验收流程的可复用经验

- **`fuxi.md`**：`profiles.merge` 字典递归、**数组整体替换**——board.toml 必须重复 arch/SoC profile 的完整 `patch_series`/`archives`，否则会静默丢项；`os_overrides` 让一套分支服务 17/26/27 多 profile；`scripts/package.sh` 不含板值。
- **`j716f.md`**：Format-1→2 迁移的完整检查表：`scripts/porting-record.py check --device ../UniXNU-j716f`、FAST 日志、reader、`test-native-*`、CI artifact 反向审计；每个域都用“命令 + revision + 可复现证据”。K60 的 porting record 可直接借用这套验收粒度。
- **`alioth.md`**：记录了 `status` 的 catalog pin 与实际 build 的 `--local-module` 不一致（ShengUfs `e2b32cc4` vs `ab54059`，ShengHidInput `5f3a37ce` vs `f35c4ff1`），以及镜像来自未记录的 local module。K60 必须记录实际 build 源集，不能只信 `status`。
- **`camellia.md`**：当 LK 不执行内嵌 BootShim/UEFI FD（约 30 秒 reset）时，可走 “LK→Linux minimal initramfs→drm_linear→uefi_jump→UEFI→payload” 的 pre-Android 热跳；`build-camellia-hotjump.sh`、`build-boot-image.sh`、`fastboot flash boot_a/vendor_boot_a`。K60 的 boot chain 若遇 LK 限制，这是可复用的兜底路线。
- **`evb10.md`**：`tools/xnu-probe/run-kernel.sh` + `EXTRA_KERNEL_ARGS` 的逐项 boot 参数实验法（`evb10-wifi=2/3/5`、`evb10-touch=1`、`evb10-audio=2/4`、`rk3588-dvfs=4/7`），以及“每个 checkpoint 都留 host/device 证据”的完整范式；可作为 K60 后续逐域 bring-up 的脚本化模板。
- **`fuxi-oddlylabs.md`**：`scripts/audit-amfi-pmgr-contract.py`、`scripts/build-fuxi-platform-power.py`、`scripts/build-fuxi-ram-block.py` 以及 `sheng-pmgr=2` 的 PMGR bridge 是 K60 补 PMGR/电源时最接近的 SM8xxx 参考。

## ③ 覆盖清单

**覆盖：121/121（A 10 + B 2 + C 14 + D 10 + E 13 + F 17 + G 9 + H 8 + I 6 + J 2 + K 3 + L 11 + M 16）**

### A（10/10）

- [x] `a04br3.md`
- [x] `ace6.md`
- [x] `alioth.md`
- [x] `alioth-fjcx555.md`
- [x] `alioth-songchiyu.md`
- [x] `alioth-taishang1024.md`
- [x] `alioth-yang232138.md`
- [x] `amethyst.md`
- [x] `amethyst-bluedmc-amethyst.md`
- [x] `asteroids.md`

### B（2/2）

- [x] `bbk-a2.md`
- [x] `braveark.md`

### C（14/14）

- [x] `caihong.md`
- [x] `camellia.md`
- [x] `cas.md`
- [x] `cas-pxl777806.md`
- [x] `cepheus.md`
- [x] `cepheus-c0der88.md`
- [x] `cepheus-didazhiqian.md`
- [x] `cepheus-yangqi0408.md`
- [x] `cheeseburger.md`
- [x] `cheeseburger-lss717.md`
- [x] `cheeseburger-maozedongae.md`
- [x] `chiron.md`
- [x] `chiron-sbccc1888.md`
- [x] `clover.md`

### D（10/10）

- [x] `d2xq.md`
- [x] `dada.md`
- [x] `dada2.md`
- [x] `dali.md`
- [x] `dandelion.md`
- [x] `dipper.md`
- [x] `dizi.md`
- [x] `droidvm.md`
- [x] `droidvm-lateautumn233.md`
- [x] `droidvm-neko17awa.md`

### E（13/13）

- [x] `e5.md`
- [x] `elden.md`
- [x] `elish.md`
- [x] `enchilada.md`
- [x] `enchilada-keyfan.md`
- [x] `enchilada-wangshaofan82-png.md`
- [x] `enuma.md`
- [x] `enuma-alghiffaryfa19.md`
- [x] `enuma-tlrenhb.md`
- [x] `erhai.md`
- [x] `erhai-xingxing19035.md`
- [x] `erhai-zczyh0922.md`
- [x] `evb10.md`

### F（17/17）

- [x] `fairlady.md`
- [x] `fajita.md`
- [x] `flashlm.md`
- [x] `fuxi.md`
- [x] `fuxi-0721gpt.md`
- [x] `fuxi-hanzi123-bilp.md`
- [x] `fuxi-kerfand.md`
- [x] `fuxi-kkkpc.md`
- [x] `fuxi-ljhhkx529.md`
- [x] `fuxi-minecraftvm.md`
- [x] `fuxi-mouse233.md`
- [x] `fuxi-oddlylabs.md`
- [x] `fuxi-sohytrs.md`
- [x] `fuxi-star-mailaz.md`
- [x] `fuxi-unixnu-fuxi.md`
- [x] `fuxi-xyvern08371.md`
- [x] `fuxi-yigezhong011-ops.md`

### G（9/9）

- [x] `gauguin.md`
- [x] `giulia.md`
- [x] `giulia-349942669lh-art.md`
- [x] `gta4l.md`
- [x] `gta4l-gta4lunix.md`
- [x] `gta4l-ilovemykedi.md`
- [x] `gts9uwifi.md`
- [x] `guacamole.md`
- [x] `guamp.md`

### H（8/8）

- [x] `haydn.md`
- [x] `haydn-iamojz.md`
- [x] `haydn-xiaomi-haydn-dev.md`
- [x] `hero2lte.md`
- [x] `houji.md`
- [x] `houji-kizashi3.md`
- [x] `houji-sakayorilroha.md`
- [x] `hummer.md`

### I（6/6）

- [x] `index.md`
- [x] `instantnoodlep.md`
- [x] `instantnoodlep-zhangp996.md`
- [x] `ishtar.md`
- [x] `ishtar-markakash.md`
- [x] `ishtar-peter8889.md`

### J（2/2）

- [x] `j716f.md`
- [x] `j716f-emptyghost.md`

### K（3/3）

- [x] `kebab.md`
- [x] `kebab-stevedang67889.md`
- [x] `komodo.md`

### L（11/11）

- [x] `lafa.md`
- [x] `lavender.md`
- [x] `lemonades.md`
- [x] `liuqin.md`
- [x] `lmipro.md`
- [x] `lmipro-yang232138.md`
- [x] `lumia950.md`
- [x] `lumia950-shrimpapplepro.md`
- [x] `lumia950-twisstedtoast.md`
- [x] `luming.md`
- [x] `luming-infinityex-rsxq.md`

### M（16/16）

- [x] `m2381.md`
- [x] `m2381-riverkawa271828.md`
- [x] `malachite.md`
- [x] `marble.md`
- [x] `marble-milacy.md`
- [x] `meizu21.md`
- [x] `merlinx.md`
- [x] `merlinx-gytis283123.md`
- [x] `mh2lm.md`
- [x] `miatoll.md`
- [x] `munch.md`
- [x] `munch-erodenine.md`
- [x] `munch-upcry.md`
- [x] `muyu.md`
- [x] `myron.md`
- [x] `myron-typeun.md`

**总计：121/121 篇，全部 [x]。**
