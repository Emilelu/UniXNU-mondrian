# K60（Redmi K60 / mondrian / SM8475）→ iPadOS 16.6.1：外设与功能分层调研交付

日期：2026-10-31
素材来源：工作区 digest `unixnu-sheng-research-digest.md`（已核实，直接引用不重复调研）＋本轮三份调研报告（本地清点 / 大件调研 / 小件调研）＋本会话新增补丁树取证（§8.A，实跑命令照录）。
证据等级标记口径：【sweet 已验证】sweet 真机/宿主实跑；【sheng device】sheng porting.toml device 级证据；【sheng source】sheng 仅源码级；【DT 实证】K60 原厂 DTB 反编译文本；【用户仓】用户仓补丁/文档记录（含上机笔记）；【官网声称】unixnu.com 或厂商官网文字；【外部声称】第三方网页/帖子；【推测】无直接证据的推断，逐处标注。

---

## 0. 执行摘要

目标：Redmi K60（小米内部代号 mondrian，高通 SM8475＝`qcom,cape`；主 DTB `vendor_boot_a_fdt1.dtb` 480,692B、设备级 overlay `dtbo_a_fdt19.dtb`，共 59 个原厂 DTB 已全部反编译落 `/tmp/k60-dts/`——本地清点 A）跑 iPadOS 16.6.1（20G81），伪装身份 iPad7,1（iPad Pro 12.9 二代 Wi-Fi 版）。生态结论先行：**raphael（Redmi K20 Pro）不可借鉴**——官网 `unixnu.com/zh/devices/raphael` 为占位页（原文「当前 GitHub 公开访问无法读取该仓库，构建和设备状态待维护者确认」）、`api.github.com/repos/penYo22/UniXNU-raphael` HTTP 404、官方注册表 `devices.toml:1374-1382` 同口径（digest §1）；真正参照是 **sheng**（小米平板 6S Pro，SM8550，13/13 area `implemented`，GPU/网络/音频/电源有上机 device 证据，digest §2）的四条移植手法（IOKit 原生继承、Linux 源码+shim+单调度器、安卓固件 blob 直用、板级供电三板斧，digest §3），以及 **sweet 线**（xnu-8796 系 iOS 16 语义：0046/0071/0072-0077 补丁在本会话实测存于 `D:\Android\k60-ios\ios-sweet-k60\xnu\patches\` 与 refs 镜像）。分层结果：**T1** 十项可直接平移或已在进行（watchdog、IOMFB selector 15、HID 输入、触摸、音频、电池/充电、按键、USB、WiFi、GPU 结构）；**T2** 亮度、锁屏、激活/身份前置链（hactivation 模板）、闪光灯 torch 内核侧、温度读取——GNSS 经证据复核**降级 T4**；**T3** 四件大件（基带驱动路线、相机栈、NFC、SLPI 传感器——其中基带/相机/NFC 按证据同时带「无 iOS 消费端」属性，传感器为纯 T3）；**T4** IR、TouchID/指纹、震动马达、GNSS、真实 App Store/Apple ID 登录、相机整机消费端。最重的事实缺口：①显示真 DSI 通路（当前仅 UEFI GOP/软件 framebuffer 已过关）；②触摸 IOVDD（pm8350c ldoc2）的 RSC 安全路径仍在迭代（sweet 线 0244/0246/0248/0252）；③20G81 卷内 CommCenter/蜂窝 kext 存在性未验证（材料已在 `~/hackios/UniXNU/out/ipsw/20G81/`，需 `ipsw kernel kextlist`，本轮未执行）。

### 分层总览

| 层 | 功能 |
|---|---|
| T1 有先例·进行中/可直接平移 | watchdog、IOMFB sel15、HID 输入、触摸、音频、电池/充电、按键、USB、WiFi、GPU 结构 |
| T2 有模板·需适配 | 亮度、锁屏、激活/身份/网络前置（hactivation）、闪光灯 torch（内核侧）、温度读取 |
| T3 大件·无先例 | 基带（驱动路线）、相机栈、NFC、SLPI 传感器 |
| T4 无 iOS 消费端/不可用 | IR、TouchID/指纹、震动马达、GNSS（证据修正）、真实 App Store/Apple ID、相机整机（iOS 消费端）、torch iOS 消费端 |

---

## 1. T1【有先例·进行中/可直接平移】

> 每项格式：现状 | 参照 | 剩余步骤事实 | 证据等级。

### 1.1 watchdog（活仓 UniXNU-mondrian 0219/0221/0222）

- **现状**：活仓 `/home/emilelu/hackios/UniXNU-mondrian/patches/xnu/series` 共 118 行，`sed -n "112,118p"` 实测第 114-117 行依次为 `0219-k60-iowatchdog.patch` / `0220-k60-coredump-off.patch` / `0221-k60-watchdog-status.patch` / `0222-k60-disable-watchdogd.patch`——与 digest §7「series:114-117」吻合。语义（digest §7）：0219 全 selector 放行 + 0221 gK60WatchdogUp 门控 + 0222 launchd disabled-jobs 禁 watchdogd；**未上机**。原厂 DT 无 CPU watchdog 节点：fdt1 `grep wdt|watchdog|bark|bite` 仅命中 glink 中断名 4 处（本地清点 B），与我们的 IOWatchdog 工作不冲突。
- **参照**：K60 自研补丁组，无外部补丁参照；DT 侧互证（原厂也不含 watchdog 节点）。
- **剩余步骤**：上机验证（digest §7 原文「未上机」）。
- **证据等级**：【用户仓】补丁文件与 series 行号本会话实跑核对 +【DT 实证】grep 计数 + digest 实测语义。

### 1.2 IOMFB selector 15（sweet 0046 语义）

- **现状**：下一征兆 `MiniIOMobileFramebuffer: selector 15 is not implemented`（15=SetDebugFlags，backboardd 二进制导入实锤 @0x10a498；backboardd 已解包至 `/tmp/k60-forensics/backboardd`）——digest §7。我们当前回 unsupported。
- **参照**：sweet `0046-sweet-iosurface-iomfb.patch`（本会话实测文件名）语义＝**对未实现 selector 一律回 success 走完主屏**（digest §7）。
- **剩余步骤**：把未实现 selector 的返回从 unsupported 改为 success（0046 语义）。
- **证据等级**：【sweet 已验证】0046 语义 +【用户仓】backboardd 二进制 @0x10a498。

### 1.3 HID 输入（ShengHidInput 模板 + sweet 0071 语义 + K60 已 prelink 真 IOHIDFamily）

- **现状**：K60 已 prelink 真 IOHIDFamily，缺发布者（digest §7）。sweet 线触摸触点交给仓内已有 `SweetHIDTouch`（`0242` 补丁头：「交给仓库里已有的 SweetHIDTouch，不另造一套 IOHID 注入」；上报走 `sweet_hid_touch(finger, down, x, y)`＝`iokit/Kernel/arm/hid/SweetHID.cpp` 里 `SweetHIDTouch::touch` 的 C 入口——0242 补丁头原文）。
- **参照**：ShengHidInput＝IOHIDDevice 子类（`NativeHidInput.cpp:125`）；自造报告描述符 report1 键盘 / report2 Consumer 键含 Home/Power/音量（:21-35）/ report3 十指 digitizer（:36-50）；`setProperty("HIDDefaultBehavior",true)`(:288)；`DigitizerCollectionDispatch`(:296)；内核运行时补丁 vtable slot198 打 `kIOHIDDigitizerEventFromEdgeTip`(0x800)（:51-124，锁 IOHIDFamily-2031.120.4 ABI，＝sweet 0071 的对应物）；消失手指补 tip-up（:180-194）——digest §4。
- **剩余步骤**：K60 目标 iOS 16.6.1，IOHIDFamily 版本/vtable slot 必须按 16.6.1 的 kernelcache 重对（digest §4/§6 均标注【推测·重对】）。
- **证据等级**：【sheng source】（digest §2：触摸/HID 仅 source 级）＋【sweet 已验证】语义（sweet 真机触摸即 HID digitizer 事件，大件调研 §3 引 sweet）。

### 1.4 触摸（sweet 线 0240-0252 + 供电三板斧 + pong 同 SoC 模板）

- **现状**（两条线，勿混）：
  - **sweet 线**（`D:\Android\k60-ios\ios-sweet-k60\xnu\patches\`，本会话 `ls` 实测 0230-0252 共 13 个 k60 触摸补丁）：0230 periodic-scan、0235 irq-pullup、**0240** pins+rpmh（TLMM：AVDD GPIO71/复位 GPIO20/IRQ GPIO21；`bsd/dev/k60_touch_rpmh.c`＝**pm8350c ldoc2 的 RPMh 投票（command DB + RSC TCS）**；0240 头原文「把 pong（**Nothing Phone 2，同 SM8475**）那套 Goodix-over-GENI-SPI 搬到 mondrian」，拆自 `refs/UniXNU-pong/patches/xnu/zzzz…-pong-touch-console.patch` 的 `bsd/dev/pong_goodix.c`（899 行）；标题「默认只到这一步」）、**0241** GENI SPI（QUPv3 SE4 @0x00990000，reg 0x4000，GIC SPI 605，「K60 与 pong 的 SPI 控制器完全一致」；时钟对齐 `clkref/gcc-sm8450.c`——「SM8450 与 cape 是同一套 GCC」：`gcc_qupv3_wrap_0_m_ahb_clk` halt 0x27004/0x62008 bit6、`s_ahb` halt 0x27008/0x62008 bit7）、**0242** Goodix 协议（**Berlin 与 GT9xx 两套 ABI 都实现**，探针「谁回得出校验和正确的数据」定夺；0242 头：「型号没有在硬件上确认过（DT 只有 `xiaomi,m11a-spi` / `goodix_firmware_m11a`）」；Berlin＝「pong 用的那代，GT9916 一类」，读 0xf1+4 字节地址+3 字节 0xff、固件版本 0x10014、IC info 0x10070；老 GT9xx 产品 id 0x8140/状态 0x814E/触点 0x8150；坐标换算 IC 0.1mm→像素，DT `panel-max-x/y`＝14400/32000（live FDT `goodix,panel-max-x`=0x3840、`panel-max-y`=0x7d00），面板 1440x3200；成败行判据 `abi berlin selected, axes 14400 x 32000, panel 1440 x 3200`；镜像参数 k60touchflip）、0243 HID 线程（boot-arg 分级，默认最保守只到第 2 步）、0244 rpmh-slot-probe、0245 irq-pullup-pins、**0246** RSC 不安全时跳过 IOVDD 投票（`k60touchstage=2 adds the IOVDD vote`）、**0248** RSC 地址探测（`k60_touch_rsc_probe`）、0250 从 ADT `/k60-touch` 节点读接线（tools/mkadt.py 发的节点，板级事实见 `drivers/k60-goodix-touch/`；DT `spi-max-frequency` 只当上限）、**0251** `k60touchid=1` 机器可读 ID 读回（分级抬到 4「只验到 ID」；预期输出 `K60 TOUCH: ID: abi=berlin chip="911" …`、`raw 0x10014 = 39 31 31 00…`；顺带硬约束 k60rpmhoff=1 时拒绝 k60rscprobe=1）、**0252** 先 map RSC 再读 TCS（0244 在 `ml_io_map()` 之前读取导致首票访问未映射物理地址 0xd00；宿主冒烟台报 "no access outside the mapped windows"）。
  - **活仓 UniXNU-mondrian**：触摸未开始；RSC 0x17a00000 读即死机、ldo2 缺口（digest §7）。K60 DT 侧：反编译 fdt19 可见触摸节点供电经 vdd-supply phandle 引用、无独立触摸 LDO 节点；overlay 各 fragment `target=<0xffffffff>` 父总线 phandle 留空（本地清点 A/B）。
- **参照**：①sheng ShengNovatekTouch 四层（NvtTouchCore→NvtProtocol→TouchProbe GENI SPI/GCC/TLMM→NativeHidInput；常量取自 xiaomi-sheng-thp Apache-2.0 + 主线 nt36532e GPL 事实，digest §4；sheng 触摸路径无任何 LDO/regulator 代码——板上常供，grep 零命中）；②**供电三板斧**（digest §3.4 手法 4：cmd-db 解析 `QcomRpmh.c:13-43` → RSC/TCS active 直写 `QcomRpmh.c:55-89` → SPMI enable 0x46 bit7 自证 `:138-206`；上机件＝WifiProbe.cpp:290-360 六轨 + AudioProbe.cpp:772-797 micRail）；③**pong＝Nothing Phone 2，同 SM8475**，Goodix-over-GENI-SPI 已有成套实现（0240 头声称）。
- **剩余步骤**：①pm8350c ldoc2 投票的 RSC 安全路径（0244/0246/0248/0252 迭代中；真机 RSC 0x17a00000 读即死机＝digest §7；真机走到哪一步素材未记录）；②Berlin/GT9xx ABI 硬件判定（0242 双实现 + 0251 ID 读回判据）；③触点→HID 发布（0243 + SweetHIDTouch；UniXNU 侧对应物＝ShengHidInput，见 §1.3 的 16.6.1 vtable 重对）。
- **证据等级**：【用户仓】补丁头原文（本会话逐个实读）＋【sheng device】供电三板斧（WiFi/mic 轨上机）＋【DT 实证】xiaomi,m11a-spi/panel-max＋【推测】Berlin=GT9916 一类（0242 头自述「GT9916 一类」且「型号没有在硬件上确认过」）。

### 1.5 音频（sheng 全链，K60 同款 WCD938x）

- **现状**：K60 未开始（digest §7）。K60 器件（DT 实证）：`wcd938x-codec`（fdt19:6877-6941，split-codec=1，4×micbias 2750mV）＋ SWR slave wcd938x-rx-slave/wcd938x-tx-slave（fdt19:6758-6762,6660）；**功放＝2×`awinic,aw882xx_smartpa` @I2C 0x34/0x35**（fdt19:2405-2431，sound-channel 0/1，irq 0x58/0x3f，reset 0x01/0x03，小米树注释 "top and bottom speakers"）；va/tx/rx-macro 启用、**wsa-macro@3240000 与 wsa2-macro@31E0000 均 disabled**（fdt19:6763,6820）→ wsa883x×4 全禁用；4×swr-dmic 全 disabled（fdt19:6663-6700）；sound 卡 waipio-mtp-snd-card，wsa-max-devs=0（fdt19:6915-6955）。
- **参照**：sheng 全链（digest §4）：QcomSmem/Smp2p/Glink→QcomMdt（modem_a 的 adsp MDT）→ShengQrtr→ShengGpr→ShengAudioReach（0x08001001-0x08001015）→ShengAudioService 环形缓冲；功放 6×CS35L43 走 GeniI2c.c；WCD938x 走 TX SoundWire(0x6d30000)；用户态 `hal/ShengAudioPlugIn.c`（690 行 CoreAudio AudioServerPlugIn，union mount + CDHash trust cache）；时钟 hack（CoreAudio 把主机钟当 24MHz，插件改共享页 19.2MHz）。上机：六功放 PLL 锁定、WCD938x 枚举、0 late periods（porting.toml:216-227 device 证据）。
- **剩余步骤**：①功放换型 CS35L43→AW882xx（I2C 0x34/0x35 寄存器集）；②ADSP MDT 从 K60 modem_a 分区取（手法 3）；③WCD938x 路径照搬（digest §4 标「高可平移」）。
- **证据等级**：【sheng device】全链上机＋【DT 实证】K60 器件清单。

### 1.6 电池/充电（ShengBattery/ShengBattmgr 模板）

- **现状**：K60 未开始（digest §7）。K60 充电框架＝`qcom,battery-charger`（fdt1:8563）＋`qcom,battery-debug`（8584）＋`qcom,charger-ulog-glink`（8588）——ADSP 电池管理 GLINK 方案，与 sheng 同构，无独立 smb5 节点（grep smb=0，本地清点 B）。PMIC 全组（fdt19 SPMI SID 实测）：pmk8350/pm8350/pm8350c/pm8350b/pmr735a/pmr735b/pm8450（fdt19:153,650,748,1110,1488,1566,1643）。
- **参照**：`ShengBattery.cpp` 发布 IOPMPowerSource（powerd 直接读）＋`ShengBattmgr.c`（ADSP 电池管理器 PMIC GLINK owner 32778，opcode 表 :5-13）；上机 PPS 8.72V/1.3A（porting.toml:254-266）。充电由 ADSP 固件做（digest §4）。
- **剩余步骤**：opcode 表按 SM8475 重对（本地清点 B 定性原文）。
- **证据等级**：【sheng device】PPS 上机＋【DT 实证】K60 充电框架同构。

### 1.7 按键（ButtonProbe 模板）

- **现状**：K60 未开始（digest §7）。K60 DT＝`gpio_keys` vol_up GPIO6 code 0x73（fdt19:1985-1999）＋`qcom,pmk8350-pwrkey`/`resin`（fdt19:168,174）＋bark×2——与 sheng ButtonProbe 同构（本地清点 B）。
- **参照**：sheng `ButtonProbe.cpp`——电源=PON（SID0 外设 0x13/中断 7）、音量-=RESIN、音量+=PM8550 GPIO6，经 SPMI EE0+PDC 转 SPI 481（注释引 mainline spmi-pmic-arb v7/qcom-pdc v3.2）；按键并入 ShengHidInput report2（digest §4）。HID 语义 sweet 已验证：「power and volume keys as HID consumer keys; lock/wake works」（大件调研 §3 引 sweet）。
- **剩余步骤**：PMIC 外设/GPIO 编号按 K60 DT 重对（K60 pwrkey/resin 挂 PMK8350、vol_up 为 TLMM GPIO6）＋HID report 挂接。
- **证据等级**：【sheng source】（digest §2 device 级清单不含按键）＋【sweet 已验证】按键语义＋【DT 实证】K60 节点。

### 1.8 USB（sweet 0072-0077 模板）

- **现状**：K60 未开始（digest §7）。K60 DT＝`qcom,dwc-usb3-msm@0xa600000` 内含 `snps,dwc3@a600000`（dr_mode=otg，maximum-speed=high-speed）（fdt1:16829-16860）＋`qcom,usb-snps-eusb2-phy@88e3000`（16880）＋usb-nop-xceiv（16895）＋`qcom,usb-ssphy-qmp-dp-combo@88e8000`（16900）＋`qcom,fsa4480-i2c`（fdt1:10345，TypeC 模拟音频开关）＋overlay 补 `nxp,eusb2-repeater@4f`（fdt19:2123-2134）。
- **参照**：sweet 0072-0077 七补丁（本会话实测文件名：0072-sweet-usb-probe / 0073-sweet-usb-device-ep0 / 0074-sweet-usb-vbus-override / 0075-sweet-usb-ecm / 0076-sweet-usb-rx-mbuf / 0077-sweet-usb-live-log）＝DWC3 device mode→CDC-ECM→ue0→UDP 日志流（digest §4；本地清点 B 定性「DWC3 device mode 有 sweet 0072-0077 上机先例」）。sheng 无 USB device/net 驱动（digest §4）。
- **剩余步骤**：K60 侧 DWC3 探针/EP0/VBUS/ECM 平移＋eUSB2 PHY（`usb-snps-eusb2-phy`＋`nxp,eusb2-repeater`，较 sweet 目标更新的 PHY 件）适配。
- **证据等级**：【sweet 已验证】0072-0077（补丁树实测存在）＋【DT 实证】K60 USB 节点。注：本地清点 A 引 NOTES.md:17 作 USB 佐证，但该行原文为基带内容（见 §7 修正 8）。

### 1.9 WiFi（Ath12kWifi 框架换 ath11k）

- **现状**：K60 未开始（digest §7）。K60 器件（DT 实证）＝`qcom,cnss-qca6490@b0000000`（fdt1:10043-10075）：wlan-en/bt-en/sw-ctrl=GPIO 0x50/0x51/0x52，7 轨供电内嵌 config，mboxes=aop，vreg_ipa="s3e"。QCA6490（=WCN6855 家族）属 **ath11k** 家族；sheng 用 ath12k，源码不同（本地清点 B）。
- **参照**：Ath12kWifi 框架（digest §3/§4）：`tools/fetch-sources.sh:1-5` 抓 Linux v7.0.14 ath12k/MHI/QRTR/QMI＋FreeBSD releng/15.1 linuxkpi；clang -mkernel 编内核对象；`llvm-objcopy --redefine-syms` 加 `nwk_` 前缀；单线程调度器（shim/include/lx.h:1-3 "everything runs from one dispatcher (lx_pump)"）；`WifiProbe.cpp` 1504 行 PCIe0 全链上电（:290-360 六轨 kRails={smpg5,ldob15,smpg2,smpe4,smpg4,smpg6}，HPM→电压→enable，IOSleep(2) 轮询）＋`MhiBoot.c` BHI/BHIE 寄存器引导。上机：WPA2 5GHz 80MHz DHCP 成功、下行~12/上行~24 Mbit/s（porting.toml:183-188 device 证据）。
- **剩余步骤**：①换 ath11k 源码（WCN6855）——digest §4 原话「整套框架可复制【推测可行】」；②供电轨名按 K60 DT 内嵌 7 轨 config 重对（三板斧同法）；③MHI 固件来源：素材未给出具体文件（sheng GPU/ADSP 固件取自安卓分区＝手法 3；ath11k 固件对应 linux-firmware `qca6490` 或 K60 安卓分区，未核实——需要浅克隆 linux-firmware 或列 K60 modem/fsg 分区内容取证）。
- **证据等级**：【sheng device】框架全链上机＋【DT 实证】QCA6490 器件＋【推测】ath11k 平移可行性与固件来源。

### 1.10 GPU 结构（Adreno740 模板，K60 为 Adreno730v3 同代）

- **现状**：K60 真 GPU 未开始（当前显示为软件 framebuffer，digest §7）。K60 器件（DT 实证）＝`qcom,kgsl-3d0@3d00000`，compatible **`qcom,adreno-gpu-gen7-4-0\0qcom,kgsl-3d0`**，qcom,gpu-model=**"Adreno730v3"**，qcom,chipid=**0x7030002**，12 级 bus-table-ddr，zap-shader memory-region（fdt1:16171-16210）＋`qcom,gen7-gmu@3d69000`（fdt1:16421-16437）＋`qcom,qsmmu-v500\0qcom,adreno-smmu`（fdt1:15876）。
- **参照**：Adreno740/AdrenoMetal 链（digest §4）：QuartzCore→AdrenoMetal 插件→metal2vulkan→Turnip→NIR/IR3→内核 Adreno740→GMU/CP/SMMU/ring→A740→scanout；用户态走苹果原始发现路径（IOAcceleratorES→MetalPluginName→bundle principal class；故意命名 AGXAccelerator 使原 sandbox profile 接受）；`NativeAdrenoMetal.publish` 标记开启；shader cache 预热 162 个 Metal 库。上机：130 fps idle、1024 MiB pool 0 fallbacks（porting.toml:158-163 device 证据）；GPU commit 自述 "refusing render encoder"＝当前行为，**未完全跑通**。
- **剩余步骤**：SM8475 板级件（GMU/SMMU/cmd-db/签名 ZAP/保留内存）＋iOS 16.6.1 ABI 重对【推测——digest §4/§6 标注】；A730 与 A740 同 a7xx/IR3 代（digest §4）。
- **证据等级**：【sheng device】结构级上机＋【DT 实证】K60 GPU 器件＋【推测】平移与 ABI 重对。

---

## 2. T2【有模板·需适配】

### 2.1 亮度/背光（sheng display 指南 + mainline 背光 + 本地 NOTES selector 地图）

- **现状**：UniXNU `GopFramebuffer` 无亮度实现——`grep -rniE brightness|backlight|PowerChange` 对目录 8 文件 0 命中（本地清点 E2，目录清单实测）。K60 无独立背光 IC compatible（fdt19/fdt1 grep backlight|ktz8866|lm3697|ti,lm3|3514|3515 仅命中 pm8350c GPIO pinctrl `lcd_backlight_ctrl` fdt19:771-775 与 DC 调光特性 `mi,dc-feature-type`）→ **K60 背光＝面板 DSI 命令调光**；用户仓上机笔记 PORT-STATUS-K60.md:1069/1131/1195/1292：「disp_bring_up → `0x11`(Sleep Out) → `0x29`(Display On) → `0x51`(亮度 0xFF)」「然后发 `0x51`（亮度）→ 推我们自己的帧」（本地清点 E3）。
- **参照**：①sheng display 指南（https://unixnu.com/zh/porting/display ）：背光是设备仓独立驱动，`AppleARMBacklight.cpp`（KTZ8866）＋`GeniI2c.h` GENI 传输状态机；OS ABI＝`IODisplayParameters` 亮度范围＋`backlight-control`，服务接受 `brightness`/`FadePeriod` 属性；验证＝低/中/高回读＋可见变化；统计 `native_backlight_stats`；开关 `sheng-backlight=1`。模板实存 `/home/emilelu/hackios/UniXNU-sheng/package/AppleARMBacklight.cpp`（24085B；两颗 KTZ8866@I2C 0x11，BL_BRT_LSB 0x04/BL_BRT_MSB 0x05 11-bit；:13-14「CoreBrightness (backboardd) looks for a backlight service with **backlight-control = true**…sets {brightness, FadePeriod}」；:10-11 类名实为 ShengBacklight，因 AppleARMPlatform 已定义同名类——本地清点 E1 实读）。②selector 地图 `refs/ios-sweet-k60/NOTES.md:114`：`12 _kern_RequestPowerChange[ScalarMethod_stub]`、`50 _kern_SetBrightnessCorrection`、`66/67 _kern_SPLCSet/GetBrightness`（本地清点 E2）。③mainline 路径＝qcom-lpg→PWM→pwm-backlight（LCD 用；AMOLED 下游惯例 `bl_ctrl_dcs`——mdss-dsi-panel.txt 绑定文档，大件调研 §5）。
- **剩余步骤**：①K60 传输层＝DSI DCS 0x51（与官方 I2C KTZ8866 模板不同传输层，需在显示管线侧实现 DCS 传输——**依赖显示真通路，见 §6 显示条目**）；②按 iOS 16.6.1 重对 `OriginalMobileFramebufferABI.h`（digest §6 版本强绑定）；③selector 12 符号来源为本地 NOTES.md:114（大件调研：该符号在公开网页未找到原文，证据等级受限）。
- **证据等级**：【官网声称】sheng 指南＋【用户仓】sheng 模板文件实存与 K60 DCS 0x51 上机笔记＋【外部声称】mainline 绑定文档＋【推测】16.6.1 的 IOMFB 接入槽位。

### 2.2 锁屏（依赖链 + 无生物识别路径）

- **现状**：K60 已有关键件——显示点屏+内核首帧（MiniIOMobileFramebuffer 软件 framebuffer 1440×3200@60Hz）、keybag（ADT no-effaceable-storage＋内核写 systembag.kb，KeyBagKeys=base64("SWEET")）、UFS（digest §7）；缺 HID 发布者与触摸供电（digest §7）。K60 sweet 笔记：NOTES.md:140「AppleKeyStore registered (no passcode, unlocked)… MKB_INIT: FATAL KEYBAG ERROR: failed to load system bag」、:143 AKS selector 全表（5 set_system_with_passcode/7 get_lock_state）（本地清点 E3）。
- **依赖链**（sweet 实测集合，大件调研 §3）：内核侧 XNU＋UFS(root/data)＋IOMobileFramebuffer＋IOHIDFamily 触摸发布＋AppleKeyStore/keybag；用户态到「backboardd, SpringBoard, lock screen, home screen, Control Center, notification center, Settings」；触摸＝Goodix GT9896 I²C digitizer 事件；电源/音量键＝HID consumer keys；AppleKeyStore 为 stub。SpringBoard 角色：「essentially iOS's graphical user interface」「Starting in iOS 6, some of SpringBoard's former functions are now in backboardd」（theapplewiki SpringBoard）。
- **无生物识别路径**（三重行为证据）：①sweet＝iPhone X（FaceID 机型）身份，无 FaceID 硬件照常到锁屏、swipe up 解锁；②blueline Pixel 3（iPhone X 用户态）「Boot to iOS: lock screen, SpringBoard, Settings and the core apps」；③iPhone SE 2020 Touch ID 硬件坏后 passcode 仍正常（reddit r/applehelp，原帖反爬，引文为检索器转述——标注）。iPad7,1 真机带 Touch ID home 键，K60 无指纹硬件→iOS 应落 passcode-only【推测，由上述三条支持，无「无指纹传感器的 Touch ID 机型」直接行为学文档】。
- **参照**：sweet 在 iOS 16 系用户态（xnu-8796，与 K60 同代）的完整路径；K60 还差 HID 发布者（§1.3）与触摸供电（§1.4）。
- **证据等级**：【sweet 已验证】＋【外部声称】blueline/reddit＋【推测】passcode-only。

### 2.3 App Store / Apple ID（激活/身份/网络前置链）

- **前置链**（大件调研 §2）：激活（设备把 Activation Token 送 albert.apple.com/deviceservices/deviceActivation，服务器签 WildcardTicket，设备 AMDeviceActivate 验签——theapplewiki Activation；「the iPod touch has never been denied activation regardless of firmware, country etc.」）→ MobileGestalt 身份（`/usr/lib/libMobileGestalt.dylib` MGCopyAnswer 问答表，缓存 com.apple.MobileGestalt.plist——Timac 博文/theos 头文件）→ 网络（Wi-Fi＝§1.9）→ 沙箱/信任链（sweet 实测 permissive code signing/sandbox 下系统仍到主屏）。
- **sweet 实测路径**：激活走「Native 'Hactivation' path of mobileactivationd... **No Apple servers involved**」；身份＝「copying /product from the real iPhone X device tree」；结果「**No App Store, Apple ID, or sideloaded apps**」。
- **iPad7,1 版本窗**：iPad Pro 12.9 二代 iOS 16 分支末版=16.7.2（2023-10-25 停签）；终极版=iPadOS 17.7.11 (21H461)（＝sheng 的 OS profile，digest §2）；16.6.1=20G81 在支持范围内，IPSW 存在（5.59GB，unsigned，betaprofiles.dev）。**服务端对 iPad7,1+16.6.1 的 App Store/Apple ID 接受度：未找到任何直接证据**（只能上机）；blueline 被 Apple 服务器拒绝（「Apple's servers won't accept a device that isn't an iPhone」）但其**未做身份伪装**，不能直接外推。
- **待取证**：20G81 卷内 CommCenter/蜂窝 kext 存在性——材料已在 `/home/emilelu/hackios/UniXNU/out/ipsw/20G81/{096-57366-083.dmg(OS 卷), 096-56782-083.dmg(Cryptex), kernelcache.decompressed}`（digest §7），需 `ipsw kernel kextlist kernelcache.decompressed`＋卷内 ls；本轮未执行。
- **定性**：拆两半——**激活（hactivation 路线）＝T2**（sweet 有完整模板，但其为 17.7.11/16.7.16 ABI，需按 16.6.1 重对）；**真实 App Store/Apple ID 登录＝T4**（全生态零先例：sweet 绕开苹果服务器、blueline 被拒、UniXNU 官网/频道无相关报告）。
- **证据等级**：【sweet 已验证】hactivation＋【官网声称/外部声称】激活链与版本窗＋【推测】服务端行为。

### 2.4 GNSS（任务草案列 T2；证据复核定 T4）

- **事实**：①SM8475 定位清单 GPS L1/GLONASS G1/BDS B1I+B1c/GALILEO E1/QZSS L1（小米官网原文），GNSS 集成在 **modem**——fdt1 `grep -icE gnss`=0，无独立 DT 节点（本地清点 B）；②mainline `drivers/gnss/` 仅 mtk/serial/sirf/ubx/usb，无任何 qcom GNSS 驱动（小件调研 §6，目录页实测）；③Linux 侧唯一路径＝QMI LOC 经 ModemManager，且「GPS via ModemManager only works with a SIM inserted on Qualcomm modems」（pmaports issue #1284 原文）——即**无基带则无 GNSS 源**；④iPad7,1 Wi-Fi 身份官方定位能力原文＝「Digital compass · Wi‑Fi · iBeacon microlocation」，GPS/GLONASS 仅 Wi-Fi+Cellular 型号（Apple 规格页，经 archive.org 抓取）→ **iOS 16.6.1 在 iPad7,1 身份下 CoreLocation 只期待 Wi-Fi 定位库+iBeacon，不期待 GNSS 硬件**。
- **若坚持做**：最近参照＝pmOS QMI-LOC/ModemManager 路线，前置＝基带先通（§4.1）。
- **定性**：**T4（无 iOS 消费端）**——任务草案归 T2 的「有模板」理由不成立：模板依赖基带，且身份层已无 GNSS 期待（修正记录见 §7）。
- **证据等级**：【DT 实证】＋【外部声称】mainline 目录/规格页＋【官网声称】Apple 规格页。

### 2.5 其他有模板项（本轮发现）

- **闪光灯 torch（内核侧）**：K60 DT＝`qcom,pm8350c-flash-led@ee00` 四通道 flash_0..3（max-current 0x5dc=1500mA，ires 0x30d4=12.5mA）（fdt19:888-930）＋`qcom,camera-flash@1/@2/@3` 三头绑定（flash-source/torch-source=flash_0 复用，`__symbols__` led_flash_wide/ultra/macro）（fdt19:14838-14858）；小米树侧 `pm8350c_switch0/1/2` led-mask 9/6/15＋`pm8350c_flash` status ok（cupid-development android_kernel_xiaomi_sm8450-devicetrees xiaomi-sm8475-common.dtsi 原文）。mainline 模板＝`drivers/leds/flash/leds-qcom-flash.c`（v6.3 合入，compatible 仅 `"qcom,spmi-flash-led"`，运行时按 subtype 识别；源文件 subtype 宏仅 3CH_PM8150/3CH_PMI8998，**无 PM8350C 字样——覆盖未证实【推测：同 SPMI 接口，需上机读 subtype 寄存器】**）。**iOS 侧 torch 内核路径无公开资料→iOS 消费端 T4**。备选点亮路径＝sheng SPMI 直写三板斧（大件调研 §4）。
  - **定性**：内核侧 T2（模板+DT 硬证据）；iOS 消费端 T4。
- **温度读取**：`qcom,tsens-v2` ×2（fdt1:16439,16449，@c263000/@c222000）＋overlay 6×`qcom,spmi-temp-alarm@a00`＋2×`qcom,bcl-v5`＋`qcom,msm-bcl-soc`（1162，disabled）＋`qcom,qmi-sensors`（fdt1:16775）/`qcom,qmi-cooling-devices`（16630）（本地清点 B）。
  - **定性**：读温度 T2（有 mainline 模板，本地清点 B 定性）；做温控策略 T3。

---

## 3. T3【大件·无先例】

### 3.1 基带（驱动集成 modem 的路线）

- **为什么难（依赖链）**：①K60 为 SM8475 集成 modem：Android 侧固件经 remoteproc PAS（TrustZone）加载，驱动 `drivers/remoteproc/qcom_q6v5_pas.c`，sm8450.dtsi 节点 `remoteproc@4080000` compatible `"qcom,sm8450-mpss-pas"`——LKMDB 全表 96 项**无 sm8475/sm8480 专属 compatible**（cateee.net QCOM_Q6V5_PAS 页）；②host 接口不是 PCIe MHI 而是 GLINK→QRTR→QMI，数据面走 IPA——mainline IPA 无 `qcom,sm8450-ipa`（sm8350 5.13+/sm8550 6.8+），SM8450 IPA 补丁 2026-06 仍在评审且评审指出 SRAM 尺寸 SM8450≠SM8475（patchew/spinics）；③iOS 侧蜂窝栈＝CommCenter＋AppleBasebandPCIE kext；高通代 iPhone 基带为 **PCIe MHI 外挂**（iPhone 14=SDX65M，`pci_generic.c` 0x0308→qcom-sdx65m，固件 qcom/sdx65m/xbl.elf），与 K60 集成式 GLINK 架构不同类；Apple 主机侧协议无公开资料【推测】；④固件互换性：Android mpss=MDT/ELF+OEM 签名+QSEE PAS vs iOS 基带=BBFW 容器+FBPT+baseband_certificate_id 设备绑定（hack-different/apple-baseband 工作流+apple-knowledge baseband.yaml）——三重不同，**不可互换**【推测，基于三重证据链】。
- **最近参照**：pmOS/Nura wiki（SM8450/SM8475/SM7475 同页）per-SoC 表「Modem — Calls, SMS, Internet — **Works**」三行均 Works，设备表含「POCO F5 Pro/**Redmi K60 (xiaomi-mondrian)**」；mainline 表「Calls IPA v5.1 WIP」「SMS WIP」「Mobile data WIP」「GPS WIP」；「the mainline kernel fork currently only includes very basic support」——Linux 侧有成例，iOS 侧零（digest §5：13 个必需 area 不含基带）。
- **逃逸路线（事实）**：iPad7,1=Wi-Fi 版 A1670（iPad7,2 才是蜂窝版，AppleDB）→真机无基带、其 IPSW 不含基带固件；激活对无基带设备无要求（iPod touch 先例；蜂窝 iPad 基带坏也可 Wi-Fi 激活）；CommCenter 在 iPod touch 上也运行（theapplewiki）。
- **基带缺失的工程后果**（K60 sweet 笔记）：NOTES.md:22/24「CommCenter removed from launchd.plist」「Setup no longer killed… (it blocked in CoreTelephony getSubscriptionInfo -> CommCenter)」；NOTES.md:17「Black Phone app: main thread waits in -[VMVoicemailManager fetchAccounts] (sync XPC; **voicemail needs the modem**)」；blueline 不工作项含「cellular」。
- **定性**：双态——跳过路线＝**T1 成本 0**（Wi-Fi iPad/iPod touch 先例）；驱动集成基带＝**T3 大件无先例且 iOS 消费端为零（证据倾向 T4）**。本节按任务书以「驱动路线」入 T3。
- **证据等级**：【外部声称】LKMDB/Nura/mainline 源码＋【用户仓】NOTES.md 工程后果＋【推测】Apple 主机协议与固件不可互换。

### 3.2 相机栈

- **为什么难（依赖链）**：①mainline CAMSS 18 个 compatible 无 sm8450/sm8475（sm8550 6.15+/sm8650 6.19+/x1e80100 6.16+——LKMDB 全列）；SM8475 相机只在社区 fork（sm8450-mainline 组织；yzddmr6/linux-sm8450-liuqin＝小米平板 6 Pro SM8475）；Nura per-SoC：SM8450 相机 Works（fork 内）、SM8475 Untested、mainline 表 Camera WIP；②传感器型号不在 DT（DT 只给泛型 `qcom,cam-sensor0-3`，fdt19:15100-15237，MCLK0/1/2/5=广/超广/前/微距；CSIPHY compatible=`qcom,csiphy-v2.1.3-xiaomi-m11a` fdt19:14815,14823；ois_wide 整段注释掉），型号在用户态 sensor XML——规格页级＝主摄 OV64B40（无主线驱动；近亲 ov64a40 主线 6.8+）、超广 OV08D10（**主线有** drivers/media/i2c/ov08d10.c）、微距 OV02B10（无；近亲 ov02a10 Orphan）、前摄 OV16A1Q（无记录）（kimovil+kernelconfig 检索）；③小米 GPL 缺口：camera techpack 从未发布（MiCode/vendor_qcom_opensource_data-kernel#2：2023-08-01 提出「Missing 'Kernel: Xiaomi camera-kernel changes for Redmi K60 Android S'」，2025-07-14 被 not planned 关闭、小米零回应）；④iOS 侧：AppleISP kext **无任何公开逆向**（全世界上唯一 Apple ISP 逆向在 Asahi Linux M1，m1n1 hypervisor 跟踪法，硬件完全不同）；mediaserverd 为用户态相机枢纽（Google Project Zero 2019）；相机权限=tccd+mediaserverd 双闸。
- **DT 全量**（本地清点 B）：cam-isp/camss 链 20+ 节点（fdt1:19498 起，含 bps/ipe/icp、csid×3+lite×2、框架 5 件）＋供电 gpio-regulator@2-8（7 个）＋`xiaomi,wl2866d@28`（4 路相机 LDO，I2C 0x28）＋eeprom0-3＋actuator0（微距）。
- **闪光灯**：见 §2.5（内核侧 T2/iOS 消费端 T4，已拆出）。
- **定性**：整机**证据偏 T4**（无 iOS 消费端＋AppleISP 无逆向＋主摄无主线驱动）；任务书 T3 归类保留为「大件工程」。依据一句话：生态 devices.toml/必需 area 零相机先例（digest §5）＋sweet/blueline 明列 camera 为不工作项。
- **证据等级**：【DT 实证】＋【外部声称】LKMDB/规格页/GPL issue＋【外部声称】Asahi 方法学。

### 3.3 NFC（SEP 依赖）

- **为什么难（依赖链）**：①器件＝NXP SN 系 NFCC，**驱动注释点名 sn220**（小米树 `drivers/nfc/qti/nfc_i2c_drv.c` 错误路径注释「dwl gpio is a optional gpio for **sn220**」）；compatible `"qcom,sn-nci"` @I2C 0x28（qupv3_se9_i2c；irq=TLMM46/ven=34/firm=45/clkreq=35；vdd-1p8——小米树 xiaomi-sm8475-common.dtsi 原文＋fdt19:2094-2110）；eSE 无独立 DT 节点（fdt19 全 compatible grep ese|secure.element 零命中），但驱动栈有 `ese_cold_reset.c`（ESE_COLD_RESET_DO ioctl，NFCC 挂 eSE 小米公交场景）；②iOS 侧：CoreNFC 文档原文「it requires a device that supports Near Field Communication. To determine if support is available, check the `readingAvailable` class property」＋「NFC tag reading is only available on iPhone 7 and later models」→ **iPad（含伪装的 iPad7,1）CoreNFC 会话不可用**；Apple Pay/钱包路径需 SEPAL+SE（support.apple.com/guide/security/nfc-da20f3f41——两次 429 未取全文，仅 URL+搜索摘要，标注）；越狱事实 `/usr/libexec/nfcd` 持 UART `/dev/tty.stockholm`（r/jailbreak 2017）；Apple NFC kext 在 kernelcache 的确切类名无公开命名资料。
- **依赖链结论**：即使 NFCC 驱动成功（NCI over I2C 协议简单、小米 GPL 驱动在手），iPad7,1 身份下 readingAvailable=false → **无任何用户态消费者会话可挂接**；SEP 依赖是 Apple Pay 路径的额外墙，读卡路径已在身份层被堵。
- **最近参照**：小米树 `drivers/nfc/qti/`（GPL；CONFIG_NFC_QTI_I2C=m——mondrian_GKI.config 原文）；mainline 仅 `nxp-nci/`（compatible `"nxp,nxp-nci-i2c"`，与 `qcom,sn-nci` 不同名不同实现，**不能直接套**）。
- **定性**：驱动侧 T2 级模板；**iOS 消费端缺失 → T4**（任务书 T3 的「SEP 依赖」成立部分仅为 Apple Pay/钱包）。依据：readingAvailable 文档＋生态零先例（digest §5：13 area 不含 NFC、devices.toml grep=0）。
- **证据等级**：【DT 实证】＋【外部声称】Apple 文档/小米树源码＋【推测】无 SEP 时读卡模式能力边界。

### 3.4 SLPI 传感器（加速度计/陀螺仪/磁力计/光感/接近）

- **为什么难（依赖链）**：①K60 CPU 侧 DT **无任何 i2c 传感器设备节点**（fdt19 与 fdt1 无 st,/bosch,/akm,/lsm,/bmi,/apds compatible，grep 计 0）；实锤 `qcom,msm-ssc-sensors`（fdt1:9619-9623）`qcom,firmware-name = "slpi"; qcom,rproc-handle = <0xb4>`——传感器由 **SLPI DSP（SSC）固件**管理，CPU 侧经 fastrpc/glink（fdt1:9610 msm_fastrpc_rpmsg）；②小米树 `drivers/soc/qcom/sensors_ssc.c` 只做 SLPI boot（`/sys/kernel/boot_slpi`→rproc_boot）＋`/dev/sensors` 时钟换算（19.2MHz QTimer→32kHz），**无 QMI/SMEM/glink 传输**→数据路径在 SLPI 固件+用户态（LineageOS 设备仓 `sensors/hals.conf` 全文＝sensors.ssc.so/sensors.touch.detect.so/sensors.xiaomi.so 三行）；③IMU/光感/接近/SAR 丝印**未找到**（设备树全链/两份 config/eWiseTech 等三重查证空；BMI3xx/ICM-426xx/LSM6DSV 搜索候选全部作废）；④pmOS 路线＝libssc+iio-sensor-proxy（pmaports MR !5329：Pixel 3a/SDM670「the files are served to ADSP sensorspd」「Only the sensor registry is required for working sensors」）；SM8475 无 mainline 直连 IIO 传感器。
- **iOS 消费端存在**：motiond/CoreMotion（「Core Motion reports motion- and environment-related data from the available onboard hardware」）←IOHIDEventSystemClient（私有头 nanotech/iphoneheaders）；Apple Silicon 实证形态＝IMU 挂 `AppleSPUHIDDevice`/`AppleSPUHIDDriver`（Sensor Processing Unit，vendor usage page 0xFF00，BMI286 believed——olvvier/apple-silicon-accelerometer README）——iOS A 系同构**未单独验证【推测】**。
- **工程量**：SLPI 固件 blob 直用（手法 3 同构）＋QRTR/GLINK 通道（sheng 音频同构先例）＋自造 IOHIDFamily 传感器发布者（AppleSPUHIDDevice 式）＋iOS 16.6.1 ABI 重对；生态零先例（digest §5：13 area 不含 sensors、devices.toml grep sensor/haptic=0；全网无 UniXNU/sweet 传感器先例检索命中）。
- **定性**：**纯 T3**——iOS 有明确消费端（motiond/CoreMotion+IOHIDFamily）但大件无先例，SLPI 固件依赖+传输+发布者三件全要自建。
- **证据等级**：【DT 实证】＋【外部声称】小米树源码/pmOS＋【外部声称】CoreMotion 文档＋【推测】A 系 SPU 同构。

---

## 4. T4【无 iOS 消费端/不可用】

### 4.1 IR 遥控

- **事实**：K60 有 IR blaster（GSMArena「Infrared port: Yes」＋小米官网传感器清单含 "IR blaster"）；硬件＝`ir-spi@0`（fdt19:2022-2027，SPI 19.2MHz，status=ok；小米树挂 `&qupv3_se13_spi`）；小米树自带 `drivers/media/rc/ir-spi.c`（compatible `"ir-spi"`）＋CONFIG_IR_SPI=m；mainline 同名文件 compatible 已改 `"ir-spi-led"`（torvalds 原文）——小米保留旧版。
- **不可用原因**：iPhone/iPad **从未配 IR blaster**（iPad Pro 12.9 二代规格页全文无 IR 条目）；iOS 无任何面向消费红外发射的公开/私有 API 资料被检索到。
- **定性**：**T4 无 iOS 消费端**（协议层面 SPI 位膨胀波形法简单，做了无系统级收益）。
- **证据等级**：【DT 实证】＋【外部声称】mainline 源码/规格页。

### 4.2 TouchID / 指纹 / 生物识别

- **事实**：K60＝屏下光学 **Goodix G3S**（dts `fingerprint_goodix`，compatible `"goodix,fingerprint"`，gpio-reset=TLMM41/gpio-irq=TLMM40，`l1c_vdd-supply = <&L9C>` 3.2V——小米树 mondrian-sm8475.dtsi；CONFIG_FINGERPRINT_GOODIX_FOD_G3S=m＋驱动目录 `drivers/input/fingerprint/goodix_fod_G3S/`（gf_spi/netlink/platform，netlink `GF_NET_EVENT_IRQ`）；GSMArena「Fingerprint (under display, optical)」；侧边电容方案被否定——fpc/ 目录存在但无 CONFIG_FINGERPRINT_FPC 行）。Touch ID 架构＝传感器经 SPI（会话密钥加密）送 **SEP**，模板与匹配全在 Secure Enclave，OS 只拿 match/no-match（Apple 官方 support.apple.com/en-us/105095；Securosis；TechCrunch 2014 转述 Apple 白皮书）；私有框架 BiometricKit+biometrickitd（The Apple Wiki/SlideShare）。
- **不可用原因**：伪装设备 iPad7,1 带 Touch ID home 键→iOS 16.6.1 用户态存在 biometrickitd 并期待 SEP 管理的 Apple 传感器；K60 的 G3S 既无 Apple 私有传感器协议实现也无 SEP 匹配通路。K60 本地五文档 NFC/指纹 0 命中（本地清点 E3）。
- **定性**：**T4 无 iOS 消费端**（Linux 侧 goodix_fod_G3S 驱动可作 GPIO/IRQ/供电模板，供电轨 L9C 可套三板斧——仅此价值）。
- **证据等级**：【DT 实证】＋【外部声称】Apple 官方文档链。

### 4.3 震动马达（X 轴线性马达，PM8350B 内置 haptics）

- **事实**：`qcom,hv-haptics@f000`（PM8350B SID3 内，fdt19:1169-1200）：高压 LRA，vmax 0x4e2=1250mV，lra-period 0x16fa=5882µs(≈170Hz)，brake-pattern [ff 3f 1f]，nvmem hap_cl_brake＋pbs-client，effect_0..N 内嵌；另有 `swr_haptics@f0170220` compatible=`qcom,pm8350b-swr-haptics`（fdt19:6752-6757，status=ok，马达接 RX SoundWire）。马达本体=X 轴线性马达（ZOL K60 Pro 参数页列「X轴线性马达」）；「瑞声 AAC 0809」说法仅搜索摘要、无原文 URL，低置信存疑。驱动＝小米树 `drivers/input/misc/qcom-hv-haptics.c`（EN_CTL 0x46/SPMI_PLAY 0x4C/HBOOST，PBS+SDAM；CONFIG_INPUT_QCOM_HV_HAPTICS=m）；树内 Awinic 目录（aw8622x/aw86927/aw8697）无启用配置（`#CONFIG_INPUT_AW8697_HAPTIC=m` 被注释）→ **K60 未用 Awinic**。mainline 无 qcom-hv-haptics（有 pwm-vibra/gpio-vibra/drv260x/pm8xxx-vibrator/aw86927）。
- **不可用原因**：Taptic Engine 存在于 iPhone/Watch/MacBook/Trackpad，**无任何 iPad**（Wikipedia）；内核侧实证 ioreg `haptics-support-interface` 节点＝AppleARMIODevice（iPhone 8 Plus gist、robre/ioreg-archive iPhone12,1）；用户态入口 CoreHaptics/CHHapticEngine 但「Apple exposes no motors. It exposes haptic localities」；iPad7,1 身份下 iOS UI 震动反馈为无硬件 no-op。
- **定性**：**T4 无 iOS 消费端**（驱动侧为 T2 级模板——纯 SPMI 寄存器操作与三板斧同构，做出来只能供自研 kext/测试用）。
- **证据等级**：【DT 实证】＋【外部声称】Wikipedia/ioreg/文档＋低置信存疑（AAC 0809）。

### 4.4 GNSS

见 §2.4——证据复核定 **T4**（任务草案列 T2 的修正记录在 §7）。

---

## 5. 其他遗漏功能清点（DT/规格里容易被忘的）

| 项目 | 证据 | 定性/说明 |
|---|---|---|
| 显示真 DSI 通路 | 本地清点 B 定性原文「T3 大件无先例（sheng 仅 GopFramebuffer 原型+DPU 直扫可选件 sheng-dpu-scanout=2；K60 需真 DSI 通路，生态无上机显示先例）」；K60 面板=DSC command mode（sm8450-mainline/fdt mondrian.dts bootargs `msm_drm.dsi_display0=qcom,mdss_dsi_m11a_42_02_0a_dsc_cmd:`），DSI 控制器 `qcom,dsi-ctrl-hw-v2.6` ×2＋PHY `qcom,dsi-phy-v4.3.2` ×2（fdt1:20243,20273,20305,20336），fdt19 面板 31 条、framerate 0x78=120fps | **T3**（软件 framebuffer 已过关＝digest §7；真 DSI/DPU 通路未做，与 digest 的分歧记录在 §7） |
| 蓝牙（QCA6490） | `bt_qca6490` compatible=`qcom,qca6490`（fdt1:1271-1297，7 轨 vdd）＋btfmslim-driver `slim217,221`（fdt1:1264） | 素材未覆盖 BT 移植先例/模板（sheng network=WiFi；K60-IOS-STATUS.md:197 列「无…蓝牙」）——**分层未定（素材零覆盖），不强行下结论** |
| 双扬声器 | 2×AW882xx（fdt19:2405-2431，小米树注释 "top and bottom speakers"）；1012+1216 单元=中文参数站/发布报道，URL 未取到原文页——低置信 | 音频伴生件（§1.5 之内） |
| 无线充电 30W | 小米官网「30W wireless charging」＋GSMArena；机内 RX IC 未找到（公开拆解只标注充电器 TX 侧 NuVolta NU1708——chongdiantou MDY-14-ES 拆解） | 充电/ADSP 伴生；iOS 侧无独立消费接口（IOPMPowerSource 只读电量） |
| RGB 呼吸灯 | `qcom,tri-led@ef00`＋pwm-lpg@e800/@eb00（fdt19:851-871,801,842） | iOS 消费端素材未覆盖【推测：iPad 机型无 LED，no-op】 |
| RGB 呼吸灯之外的光效 | 无独立 torch 节点（三头 flash 绑定见 §2.5） | — |
| SD 控制器 | `qcom,sdhci-msm-v5@8804000`（fdt1:8983） | K60 是否引出卡槽素材未证；无先例记录 |
| 调试 UART | `qcom,msm-geni-console`（fdt1:10122） | log-capture 可用素材（官网 /zh/porting/log-capture 存在） |
| ramoops/pmsg | `ramoops@0xa7000000`（fdt19:2193）＋`mtdoops_pmsg`（2002） | 日志取证素材 |
| RTC | `qcom,pmk8350-rtc@6100`（fdt19:615） | iOS 需 RTC；素材未覆盖移植先例 |
| spmi-sdam ×10 | fdt19:521-599 | PMIC 非易失存储 |
| qpnp-pbs / amoled 供电 | `qcom,qpnp-pbs`（fdt19:1127）＋`qcom,qpnp-amoled-regulator`（1249）＋`qcom,amoled-ecm@f900`（1287） | 面板供电伴生 |
| reboot-reason / pon-log | fdt19:1715,1721 | 调试素材 |
| xiaomi,hardware-info | fdt19:2009 | 小米杂项 |
| IPA/rmnet/gsi | fdt1:9627-9646 | 基带数据面伴生（§3.1 之内） |
| cdsp-loader / adsp-loader | fdt19:9846,17875 | DSP 固件加载伴生（音频/传感器前置） |
| 五远程处理器 pas | cape-adsp/cdsp/modem/spss-pas＋waipio-slpi-pas＋pil-tz-generic（fdt1:8712,8791,8849,8893,9572,9639） | 音频(ADSP)/传感器(SLPI)/基带(modem) 共同前置 |
| GENI 总线基础设施 | qupv3-geni-se ×3 wrap（fdt1:10088,10410,10708）＋i2c/spi-geni 多实例（10137 起） | 所有 I2C/SPI 外设前置（0241 已在 sweet 线实现 SE4 SPI） |
| rpmh-rsc + arc/vrm regulators | fdt1:5121,5150-5224 | 供电基础设施（三板斧的 DT 侧对应物） |
| eUSB2 中继器 | `nxp,eusb2-repeater@4f`（fdt19:2123-2134） | USB 伴生（§1.8） |
| fsa4480 | fdt1:10345 | TypeC 模拟音频开关（K60 无 3.5mm——GSMArena） |
| 色温/光谱传感器 | GSMArena 相机特性栏 "Color spectrum sensor" | 相机白平衡器件，依赖相机子系统（§3.2） |
| 气压计/Hall/SAR | 官方清单未列＋dts 无节点（小件调研 §6） | **不存在**（两处清单均无） |
| eSE | fdt19 grep ese|secure.element 零命中；小米树有 ese_cold_reset.c（经 NFCC 的 eSE 冷复位 ioctl） | 无独立 DT 节点；iOS 侧随 NFC T4（§3.3） |
| 原厂 CPU watchdog | fdt1 grep wdt/watchdog/bark/bite 仅 glink 中断名 | DT 不含（§1.1 互证） |

---

## 6. 矛盾与修正汇总（digest ＋ 三份报告去重合并）

1. **音频功放口径**：任务书假设「WSA883x 功放」vs K60 DT 事实＝ADSP+WCD938x+**2×AW882xx I2C**（wsa-max-devs=0、wsa/wsa2-macro disabled）——ZCODE-RESEARCH-REPORT.md:284 同口径修正＋本地清点 B（fdt19:2405-2431,6763,6820,6915-6955）。已按 DT 定案。
2. **WiFi 芯片口径**：任务书 WCN6855/QCA6490＝ath11k 家族 vs sheng 用 ath12k——确认为同一结论的两半：器件确认（fdt1:10043 `qcom,cnss-qca6490`），源码需换【推测可行】。
3. **GNSS 分层**：任务草案 T2 vs 证据 T4——GNSS 集成在 modem（fdt1 grep=0）＋mainline 无 qcom gnss 驱动＋iPad7,1 Wi-Fi 身份 CoreLocation 只期待 Wi-Fi+compass+iBeacon（Apple 规格页）。**修正为 T4**（§2.4）。
4. **NFC 分层**：任务草案 T3（SEP 依赖）vs 小件报告 T4（iPad 身份 readingAvailable=false）——两者兼容：驱动侧 T2 级模板、消费端缺失定 T4；SEP 是 Apple Pay 路径的额外墙（§3.3）。
5. **相机分层**：任务草案 T3 vs 大件报告整机 T4（torch 内核侧 T2）——按证据整机偏 T4；T3 保留为「大件工程」归类（§3.2）。
6. **基带分层**：大件报告 T1（跳过路线）/T4（驱动路线）vs 任务草案 T3——修正为双态陈述（§3.1）。
7. **显示分层**：本地清点 B 显示定性 T3（真 DSI 通路无先例）vs digest §7 显示点屏+首帧已过关——修正：**软件 framebuffer（MiniIOMobileFramebuffer 1440×3200@60Hz）已过关；真 DSI/DPU 通路＝T3 未做**，两者不矛盾但必须分开表述。
8. **背光介质**：大件调研「K60 背光控制方式未从公开材料核实」vs 本地 PORT-STATUS-K60.md:1069/1131/1195/1292（DCS 0x51 上机笔记）＋本地清点 DT grep 无独立背光 IC——**修正：以本地实测笔记为准＝面板 DCS 0x51 命令调光**。
9. **触摸芯片命名**：digest §4「GT9916」vs ZCODE-RESEARCH-REPORT.md:351「Goodix Berlin chip ID 0x10014」vs sweet 线 0242 补丁头「Berlin（GT9916 一类，pong 用的那代）」「型号没有在硬件上确认过（DT 只有 xiaomi,m11a-spi / goodix_firmware_m11a）」——修正：**Berlin 家族确定、具体型号未硬确认**；0251 提供 `k60touchid=1` 机器可读 ID 判据（abi=berlin chip="911"）。
10. **NFC 家族命名**：本地清点 A 写「NXP SN 系 NCI（SN100T/QWC 家族）」vs 小件报告「SN100T 说法未找到任何证据；驱动注释点名 sn220」——**修正：采信 SN220（有驱动注释原文），SN100T 撤下**。
11. **指纹形态**：本地清点 A「光学/超声 DT 不可辨…K60 为侧边式【推断】」vs 小件报告「屏下光学 Goodix G3S（GSMArena under display optical＋CONFIG_FINGERPRINT_GOODIX_FOD_G3S＋驱动目录）」——**修正：屏下光学 G3S；「侧边式」推断撤下**。
12. **震动马达型号**：「瑞声 AAC 0809」仅搜索摘要无原文 URL vs DT 实证 PM8350B 内置 haptics（Awinic 被 config 注释否定）——**修正：PM8350B haptics 模块定案；AAC 0809 低置信存疑**。
13. **传感器丝印候选**：BMI3xx/ICM-426xx/LSM6DSV 搜索建议全部作废（无一条有证据）——留空待真机 `dumpsys sensors`/SLPI 固件逆向/拆解视频逐帧。
14. **USB 佐证行号**：本地清点 A 以 NOTES.md:17 佐证 sweet 0072-0077 USB 上机先例，但本地清点 E 节同行号原文为基带（「Black Phone app…voicemail needs the modem」）——**NOTES.md:17 的 USB 佐证疑为行号笔误**；0072-0077 模板本身已由本会话实测（补丁树文件存在，§8.A）。
15. **补丁号撞号（阅读陷阱）**：`0219/0221/0222` 在两棵树指**不同补丁**——活仓 `/home/emilelu/hackios/UniXNU-mondrian/patches/xnu/`（0219-k60-iowatchdog / 0221-k60-watchdog-status / 0222-k60-disable-watchdogd，series:114-117）vs `D:\Android\k60-ios\ios-sweet-k60\xnu\patches\`（0219-k60-touch-power / 0221-k60-touch-geni-fw / 0222-k60-touch-spi-loopback）。任务书的「watchdog（0219/0221/0222）」＝活仓、「触摸（0241/0242/0251）」＝sweet 线；引用时必须带树名。
16. **触摸供电口径**：digest §7「触摸 ldo2 供电未开始（RSC 0x17a00000 读即死机）」vs sweet 线 0240 头「0240 把电送上了（pm8350c ldoc2 的 RPMh 投票）」＋0246（RSC unsafe 时跳过 IOVDD）＋0252（修未映射访问 0xd00）——两线状态不同：活仓侧 RSC 直写死机；sweet 线走 command DB+RSC TCS 投票并在迭代安全性（0244/0246/0248/0252）；真机走到哪一步素材未记录。
17. **「flash」grep 语义**：NOTES.md 的 33 条 flash 全是 fastboot 烧录语义（:46「Flash a root image: fastboot flash…」），与相机闪光灯无关——防误读。
18. **多源一致的基准口径（非矛盾，列出防再查）**：SM8475＝`qcom,cape`（fdt1 model）＝「Mondrian based on Qualcomm Technologies, Inc SM8475」（fdt19 model＋小米树 mondrian-sm8475-pm8008-overlay.dts 同文）；Nura：「SM8450/SM8475/SM7475 only have very slight differences in pinctrl and clock controllers」。

---

## 7. 需要什么+为什么+怎么取（素材缺口清单，接依赖链）

1. **20G81 卷内 CommCenter/蜂窝 kext 存在性**：判据＝App Store/激活与「伪装 Wi-Fi iPad 是否需要基带件」的前置事实。材料已在 `/home/emilelu/hackios/UniXNU/out/ipsw/20G81/{096-57366-083.dmg, 096-56782-083.dmg, kernelcache.decompressed}`；取法＝`ipsw kernel kextlist kernelcache.decompressed`＋OS 卷内 ls（本轮未执行）。
2. **K60 背光 DCS 之外的确认**（面板 m11a dtsi 原文）：MiCode kernel_devicetree qcom/ 目录 listing 在 dsi-panel 段截断；取法＝浅克隆 `https://github.com/sm8450-mainline/fdt` 读 mondrian.dts 全文（面板节点在 raw 抓取 100KB 截断点之后），或反编译 K60 自身 dtbo_a.img（已在本地）。
3. **ath11k 固件文件**：WiFi 引导（MHI BHI/BHIE）需要固件；素材未给出具体文件；取法＝浅克隆 linux-firmware 查 `qca6490`/`ath11k/WCN6855` 目录，或列 K60 安卓 modem 分区。
4. **触摸 Berlin/GT9xx 硬件判定**：0251 `k60touchid=1` 已内置判据（分级 4＝只验到 ID）；真机执行结果素材未记录。
5. **NFC 机内丝印（SN220 确认）**：需拆解视频逐帧（B 站 BV1MY41117Hk 存在但无法取帧）或 fcc.report POCO F5 Pro internal photos（FCC ID 2AFZZ 系，未取得具体 ID）。
6. **K60 IMU/光感/接近丝印**：公开渠道全空；取法＝真机 `dumpsys sensors`/SLPI 固件逆向/拆解视频。
7. **iPad7,1+16.6.1 的 albert/App Store 服务端接受度**：无公开证据，只能上机验证。
8. **leds-qcom-flash 对 PM8350C subtype 的覆盖**：需上机读 subtype 寄存器（同 sheng SPMI 自证法）。

---

## 8. 证据索引

### 8.A 本会话实跑（新增取证，命令与输出要点）

1. `find /home/emilelu/hackios /mnt/d/Android/k60-ios -name "0241*" -o -name "0242*" -o -name "0251*"` → 命中 `/mnt/d/Android/k60-ios/ios-sweet-k60/xnu/patches/{0241-k60-touch-geni-spi,0242-k60-touch-goodix,0251-k60-touch-id-readback}.patch` 及 refs 镜像。
2. `ls /mnt/d/Android/k60-ios/ios-sweet-k60/xnu/patches/ | grep -E "^02(3|4|5)"` → 0230/0235/0240/0241/0242/0243/0244/0245/0246/0248/0250/0251/0252 共 13 个 k60 触摸补丁；`grep -E "^0219|^0221|^0222"` → 0219-k60-touch-power / 0221-k60-touch-geni-fw / 0222-k60-touch-spi-loopback（sweet 线编号）。
3. `sed -n "112,118p" /home/emilelu/hackios/UniXNU-mondrian/patches/xnu/series` → 0217/0218/**0219-k60-iowatchdog**/0220-k60-coredump-off/**0221-k60-watchdog-status**/**0222-k60-disable-watchdogd**/0230（即 series:114-117 为 watchdog 组）；`wc -l` series=118 行。
4. `head`/`sed` 实读补丁头：0240（pong=Nothing Phone 2 同 SM8475、AVDD GPIO71/复位 GPIO20/IRQ GPIO21、pm8350c ldoc2 RPMh 投票）、0241（SE4@0x00990000、GIC SPI 605、gcc-sm8450.c 时钟）、0242（Berlin/GT9xx 双 ABI、0x10014/0x10070、panel-max 14400/32000、sweet_hid_touch 入口、成败行判据）、0243（boot-arg 分级）、0246/0248/0252（RSC 安全迭代）、0250（ADT /k60-touch 接线）、0251（k60touchid=1 读回格式、k60rpmhoff=1 拒绝 k60rscprobe=1）。
5. `ls … | grep -E "^00(46|71|72|73|74|75|76|77)"` → `0046-sweet-iosurface-iomfb.patch`、`0071-sweet-touch-edge.patch`、`0072-sweet-usb-probe`~`0077-sweet-usb-live-log` 在 ios-sweet-k60 与 refs/ios-sweet-k60 双处命中。
6. 定位五文档：`ls /mnt/d/Android/k60-ios/*.md`（HANDOFF 系等在本会话输出可见；NOTES/PORT-STATUS 等行号引文沿用本地清点 E 节实测）。

### 8.B digest 内部引用（已核实，沿用）

- digest §1：`devices.toml:1374-1382`；digest §2：porting.toml 证据分级；digest §3：`tools/fetch-sources.sh:1-5`、`shim/include/lx.h:1-3`、`QcomRpmh.c:13-43/55-89/138-206`、`WifiProbe.cpp:290-360`；digest §4：`NativeHidInput.cpp:125/21-35/36-50/51-124/180-194/288/296`、`AudioProbe.cpp:772-797`、`ShengBattmgr.c:5-13`、`MhiBoot.c`；digest §2/§4 上机证据：porting.toml:158-163（GPU）、183-188（WiFi）、216-227（音频）、254-266（PPS）。

### 8.C 本地文件:行号（三份报告）

- 反编译 DT（/tmp/k60-dts/，fdt1=vendor_boot_a_fdt1.dts，fdt19=dtbo_a_fdt19.dts）：相机 fdt1:19498,19796-19858,18291-19491；fdt19:14815,14823,14980,15008-15237,14873-14965,2659-2681；闪光灯 fdt19:888-930,14838-14858,851-871,801,842；NFC fdt19:2094-2110；haptics fdt19:1169-1200,6752-6757；传感器 fdt1:9619-9623,9610；指纹（小米树 mondrian-sm8475.dtsi）；IR fdt19:2022-2027；充电 fdt1:8563,8584,8588；PMIC fdt19:153,650,748,1110,1488,1566,1643；WiFi/BT fdt1:10043-10075,1271-1297,1264；音频 fdt19:6877-6941,6758-6762,6660,6621,6763,6820,6790-6870,6663-6700,6915-6955,2405-2431；USB fdt1:16829-16860,16880,16895,16900,16920,10345；fdt19:2123-2134；tsens fdt1:16439,16449,16775,16630；GPU fdt1:16171-16210,16421-16437,15876；显示 fdt1:20243,20273,20305,20336,20410；fdt19:13862,13882,13912,9689-14027；按键 fdt19:1985-1999,168,174；UFS fdt1:9044-9075；fdt19:2052；pas 组 fdt1:8712,8791,8849,8893,9572,9639；IPC fdt1:9327,9526,9486,9839,6485；总线 fdt1:10088,10410,10708,10137,10122；杂项 fdt1:8983,5121,5150-5224；fdt19:521-599,615,1127,1249,1287,1715,1721,2193,2002,2009,9846,17875；IPA fdt1:9627-9646。
- 用户文档：`refs/ios-sweet-k60/NOTES.md:22/24/46/114/140/143/17`；`PORT-STATUS-K60.md:1069/1131/1195/1292/108`；`K60-IOS-STATUS.md:197`；`ZCODE-RESEARCH-REPORT.md:253/284/351`；`HANDOFF-2026-10-30-NIGHT.md`（106 行，九主题 0 命中）。
- 本地仓：`/home/emilelu/hackios/UniXNU/docs/porting/display.md:5,20,86-93,106-109`；`docs/zh/porting/display.md:18,70-81`；`/home/emilelu/hackios/UniXNU-sheng/package/AppleARMBacklight.cpp`（24085B，:10-14）；`uefi-mondrian/.../MemoryMapLib.c:40-52`；`/mnt/d/Android/k60-ios/deliverables/gamma/02-DT-FDT-CHAIN-K60.md §3.1`；GopFramebuffer 8 文件清单（grep 0 命中）。
- 本会话补丁树：`D:\Android\k60-ios\ios-sweet-k60\xnu\patches\{0046,0071,0072-0077,0240-0252}`（§8.A）。

### 8.D URL 全列（去重）

- 生态/官方：https://unixnu.com/zh 、https://unixnu.com/zh/porting/display 、https://t.me/s/unixnu 、https://github.com/dipa-studio/ios-sweet 、https://github.com/UniXNU/GopFramebuffer 、https://github.com/MiCode/vendor_qcom_opensource_data-kernel/issues/2 、https://api.github.com/repos/MiCode/Xiaomi_Kernel_OpenSource/branches/mondrian-s-oss
- Apple 文档/wiki：https://theapplewiki.com/wiki/Activation 、/wiki/CommCenter 、/wiki/SpringBoard 、/wiki/SDX65M 、/wiki/Touch_ID（词条）；https://developer.apple.com/tutorials/data/documentation/corenfc.json ；NFCNDEFReaderSession.ReadingAvailable（Apple 文档镜像）；https://support.apple.com/guide/security/nfc-da20f3f41 （429 未取全文）；https://support.apple.com/en-us/105095 ；https://support.apple.com/en-ie/111964 （经 archive.org）；https://blog.timac.org/2017/0124-mgcopyanswertable/ ；https://github.com/theos/headers/blob/master/MobileGestalt/MobileGestalt.h
- 设备/版本：https://appledb.dev/device/iPad-Pro-(12.9-inch)-(2nd-generation).html ；https://betaprofiles.dev/ipsw/ipados/16-6-1-20g81 ；https://www.gsmarena.com/xiaomi_redmi_k60-11975.php ；https://www.mi.com/ae-en/product/poco-f5-pro/specs ；https://www.kimovil.com/en/where-to-buy-xiaomi-redmi-k60 ；https://detail.zol.com.cn/1433/1432138/param.shtml
- Linux 内核：https://cateee.net/lkddb/web-lkddb/QCOM_Q6V5_PAS.html 、/QCOM_IPA.html 、/VIDEO_QCOM_CAMSS.html ；https://patchew.org/linux/20260622-sm8450-ipa-v1-0-532f0299f96e@proton.me ；https://www.spinics.net/lists/devicetree/msg944709.html ；https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/plain/drivers/bus/mhi/host/pci_generic.c ；https://raw.githubusercontent.com/torvalds/linux/master/drivers/leds/flash/leds-qcom-flash.c ；https://codebrowser.dev/linux/linux/drivers/leds/rgb （qcom-lpg.c）＋sc7180-trogdor.dtsi；https://www.kernelconfig.io/CONFIG_VIDEO_OV64A40 ；mainline drivers/media/i2c/ov08d10.c、drivers/gnss/ 目录页、drivers/input/misc/ 目录页
- 设备树源：https://raw.githubusercontent.com/someone5678/android_vendor_qcom_proprietary_camera-devicetree/diting/mondrian-sm8475-camera-sensor.dtsi ；https://raw.githubusercontent.com/cupid-development/android_kernel_xiaomi_sm8450-devicetrees/lineage-24.0/qcom/xiaomi-sm8475-common.dtsi ；https://github.com/sm8450-mainline/fdt ；MiCode/kernel_devicetree（mondrian-s-oss 分支：qcom/mondrian-sm8475.dtsi、xiaomi-sm8475-common.dtsi、mondrian-pinctrl.dtsi、cape-pmic-overlay.dtsi、pm8350b.dtsi）；PocoF5Pro/device_xiaomi_mondrian（aosp-14）sensors/hals.conf
- pmOS/Nura：https://wiki.nura.eco/wiki/Qualcomm_Snapdragon_8_Gen_1/8%2B_Gen_1/7%2B_Gen_2_(SM8450/SM8475/SM7475) ；pmaports MR !5329；pmaports issue #1284；https://docs.qualcomm.com （SSC/SLPI，搜索摘要级）
- 基带/逆向：https://github.com/hack-different/apple-baseband ；https://raw.githubusercontent.com/hack-different/apple-knowledge/main/_data/baseband.yaml ；TU Wien Sterz 2021（Intel 基带 PCIe/IPC）；TU Graz/SEEMOO ARIstoteles
- 社区：https://xdaforums.com/t/dev-experimental-blueline-native-ios-16-7-16-on-apples-xnu-kernel.4805973 ；https://www.reddit.com/r/applehelp/comments/1ebi9j6/iphone_se_2020_touch_id_stopped_working_no （检索器转述）；https://www.reddit.com/r/jailbreak/comments/5js3op （nfcd/tty.stockholm）；B 站 BV1MY41117Hk（微机分拆解，无法取帧）；chongdiantou.com MDY-14-ES 拆解
- 背光/显示：https://android.googlesource.com/kernel/msm/+/android-msm-hammerhead-3.4-kk-r1/Documentation/devicetree/bindings/fb/mdss-dsi-panel.txt ；https://wiki.sugarlabs.org/go/Student_Macbooks_hardware_details ；https://github.com/jschiefner/advanced-brightness-slider-tweak
- 相机方法学：https://asahilinux.org/docs/hw/peripherals/camera ；https://asahilinux.org/2021/08/progress-report-august-2021
- 传感器 iOS 形态：https://github.com/olvvier/apple-silicon-accelerometer ；nanotech/iphoneheaders `IOKit/hid/IOHIDEventSystemClient.h`；github.com/networkextension/4e54948…（iPhone 8 Plus ioreg）；robre/ioreg-archive（iPhone12,1 iOS14.3）；Wikipedia Taptic Engine；shinylib.net（CHHapticEngine localities）
- TouchID/SEP：Securosis「Investigating Touch ID and the Secure Enclave」；TechCrunch 2014；SlideShare「Demystifying Apple 'Pie' & TouchID」

---

*本文档由综合执笔人合并 digest 与三份调研报告生成；除 §8.A 本会话实跑取证外未新增无证据内容；所有【推测】处已逐条标注。*
