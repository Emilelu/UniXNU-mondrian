# K60（mondrian / SM8475）蓝牙与音频移植实施方案

> 范围：**只读调研 + 本文件**。没有改 `patches/`、`series`、`drivers/`、`userland/`、`board.toml`、`dts/`、`uefi-mondrian` 或任何构建脚本。
> 目标机：Redmi K60（小米代号 `mondrian`，SM8475 / `qcom,cape`），目标系统 iPadOS 16.6.1 / 20G81（Darwin 22）。
> 参照：`UniXNU-pong` 的 **main 分支（iPadOS 18 / 22H374 / Darwin 24）** 的 `migration/ipados18/services*.md` 共 21 篇；pong 是同一颗 SM8475（Nothing Phone (2)），但 main 是 iPadOS 18，不是 K60 的 20G81。硬件事实可借，ABI 不能照抄。
> K60 硬件值的来源：`E:/k60-work/reports/live-6033dbec-fdt.dtb`（serial `6033dbec`，本文件写作时逐节点解析，以下简称 `FDT`）；其余引用见正文 `文件:行`。

## 阅读约定与证据标签

| 标签 | 含义 |
|---|---|
| **A = 有代码可抄** | 本机 workspace 内有可读、可编译/可移植的源码（含 PongPower 副本、Pong userland、Sheng AudioReach 等） |
| **B = 只有设计文档** | 只有 `services*.md`/方案描述/接口说明，没有可直接编译的实现 |
| **C = 完全未核实** | 无源码、无实测、无可靠公开资料；不得在实现中当成已知值 |
| **M = K60 实测** | `FDT` 节点或 K60 设备文档的实测底值；是硬件事实，不等于代码可复用 |

| 简称 | 完整路径 / 说明 |
|---|---|
| `FDT` | `E:/k60-work/reports/live-6033dbec-fdt.dtb` |
| `PongAudio.cpp` | `E:/hackios/UniXNU-zizhan/drivers/PongPower/PongAudio.cpp`（本机另一设备仓的 PongPower 副本，接口与 pong main 的 `drivers/PongPower` 子模块同套；本工作区未初始化 submodule，未逐字节比对） |
| `PongAudioService.cpp` | `E:/hackios/UniXNU-zizhan/drivers/PongPower/PongAudioService.cpp` |
| `PongAudioPlugIn.c` | `E:/hackios/UniXNU-pong/userland/PongAudioPlugIn.c`（41,210 B） |
| `PongAudioRoute.h` | `E:/hackios/UniXNU-pong/userland/PongAudioRoute.h`（17,861 B） |
| `ShengAudioReach.c` | `E:/hackios/UniXNU-sheng/package/ShengAudioReach.c`（17,119 B） |
| `ShengGpr.c` | `E:/hackios/UniXNU-sheng/package/ShengGpr.c`（4,165 B） |
| `AdspFirmware.c` | `E:/hackios/UniXNU-sheng/package/AdspFirmware.c`（7,165 B） |
| `FEATURES` | `docs/reference/FEATURES-DRIVERS-RESEARCH-2026-10-31.md`（本仓副本） |
| `K60PROFILE` | `E:/hackios/UniXNU/profiles/os/ipados-16.6.1-20G81/profile.toml`（K60 内核/prelink 配置；正文 `profile.toml:33` 指此文件） |
| `ZCODE` | `docs/reference/ZCODE-RESEARCH-REPORT.md` |
| `P18` | `UniXNU-pong:migration/ipados18/services*.md`（iPadOS18） |

---

## 0. 结论摘要

1. **蓝牙的 HCI 传输是 UART，不是 PCIe。** K60 的 QCA6490 WLAN 走 `qcom,pcie@1c00000`（PCIe0，RID 0x100 → SID 0x1c01）；蓝牙是独立 `bt_qca6490` 电源节点 + `qcom,msm-geni-serial-hs@894000`（QUPV3_2 SE20，IRQ 587，GPIO76/77/78/79，`qcom,wakeup-byte=0xfd`）。pong main **没有 `drivers/PongBt`**，21 篇 notes 中没有可执行的 BT UART/HCI 参数（仅 `services67` 有一处 BT/XO/WLAN 上电时序）；BT 硬件事实全部来自 K60 FDT 和 mainline `hci_qca` 结构。
2. **iOS 16.6.1 的 20G81 kernelcache 没有 `IOBluetoothFamily`。** 全字符串扫描 `IOBluetoothFamily`/`IOBluetoothHCI`/`IOBluetoothHostController` 均 0 命中；只有 `com.apple.driver.AppleBluetooth`（类 `BTReset`，personality `IONameMatch=bluetooth`，提供 `bt_reset`/`bt_wake`/`power_enable`/`bootstrap_lock` 的字符设备），不是 HCI 栈。iOS 16 的 `bluetoothd` 是用户态闭源；Pong 明确用 `_LimitLoadToDeviceTree=['bluetooth','marconi-bt']` 把它挡掉，原因写死为 “requires a real Pong Bluetooth transport; none implemented”（`userland/board_services18.py:84-89`）。
3. **音频的功放口径必须纠正：K60 实测是 2×AW882xx，不是 TFA9873。** `FDT` 中只有 `awinic,aw882xx_smartpa@34/@35`（I2C `0x34/0x35`），全 `compatible` 扫描无 `tfa,tfa98xx`。TFA9873 是 pong（Nothing Phone (2)）的器件；而且 TFA9873 的控制总线是 **I2C**，不是 SPMI。SPMI 在 K60 只用于 PMIC（PM8350/PM8350C/PMR735A 等），不接功放。
4. **音频代码的可复用性远高于蓝牙。** PongPower 的 `PongAudio.cpp`（ADSP AudioReach、SID1801 DMA、MI2S/TDM、TFA 配置）、`PongAudioService.cpp`（内核 `PongAudio` 服务 + user client）、`PongAudioPlugIn.c`（AudioServerPlugIn）、`PongAudioRoute.h`（VirtualAudio 路由）以及 Sheng 的 `ShengAudioReach.c`/`ShengGpr.c` 都在本机；K60 需要新写的是 **AW882xx 功放适配、K60 TDM 1.536 MHz/双数据线配置、20G81 的 HAL/路由 ABI 重新对位，以及 UEFI 的 64 KiB 音频 DMA lease**。
5. **依赖判断：** 内存窗口和 `apply()` 后的 launchd/OS 窗口是系统级前置；GPU、触摸**不是**音频/BT 的前置；WiFi 也不是硬前置，但 QCA6490 与 BT 共用 XO GPIO204 和 S5/S10/S11/S12/L7 等电源轨，必须共用/串行化 PMIC 电源路径。
6. **工作量粗估：** 音频 L（约 10–16 人周，主体可抄 Pong，但 AW882xx 与 20G81 ABI 是新增）；蓝牙基础 BR/LE L（约 10–16 人周，零先例）；“让 Apple `bluetoothd`/CoreBluetooth 直接可用” XL/未核实，不作为第一版目标。

---

## 1. 蓝牙：QCA6490

### 1.1 K60 实测硬件事实（FDT）

| 项目 | K60 实测值 | 说明 |
|---|---|---|
| 芯片节点 | `/soc/bt_qca6490`，`compatible = "qcom,qca6490"` | 独立 BT 电源/复位节点，不是 HCI 节点 |
| BT UART | `/soc/qcom,qup_uart@894000`，`compatible = "qcom,msm-geni-serial-hs"`，`reg = <0x894000 0x4000>`，`status = "ok"` | QUPV3_2（wrapper `qcom,qupv3_2_geni_se@8c0000`）SE20 |
| UART 中断 | `interrupts-extended` 第一项 GIC SPI `0x24b` = **587**，type 4（level high）；第二项 TLMM GPIO `0x4f` = 79（RX wake） | FDT |
| UART 引脚 | GPIO76=CTS、GPIO77=RTS、GPIO78=TX、GPIO79=RX；pinctrl 节点 `qupv3_se20_4uart_pins`，function `qup20` | FDT |
| Wake byte | `qcom,wakeup-byte = <0xfd>` | hci_qca 的 wake 机制 |
| BT_EN | `qcom,bt-reset-gpio = <&tlmm 81 0>`；默认 pinctrl `bt_en_sleep`：GPIO81、function gpio、output-low、bias-pull-down、2 mA | FDT：`/soc/pinctrl@f000000/bt_en_sleep` |
| SW_CTRL | `qcom,bt-sw-ctrl-gpio = <&tlmm 82 0>` | FDT |
| XO clock latch | `qcom,xo-clk-gpio = <&tlmm 204 0>` | 与 WLAN 共用 |
| WLAN_EN | `qcom,wl-reset-gpio = <&tlmm 80 0>`（`bt_qca6490` 节点内） | 同芯片 WLAN 侧 |
| BT VDD IO | `qcom,bt-vdd-io-supply` → PM8350 S10（`pm8350-s10`），`0x1b7740` = 1.8 V 固定 | FDT 供电 phandle 解析 |
| BT VDD AON/DIG/RFACMN/RFA-0P8 | 四个属性都指向 PM8350 S11（`pm8350-s11`），配置范围 `0xebd70..0x11da50`（约 0.966–1.17 V） | 同一个 buck 给四路 |
| BT VDD RFA1 | PM8350C S1（`pm8350c-s1`），`0x1cfde0..0x1f20c0`（1.90–2.04 V） | FDT |
| BT VDD RFA2 | PM8350 S12（`pm8350-s12`），`0x149970..0x1ee240`（约 1.35–2.02 V） | FDT |
| BT VDD ASD | PMR735A L7（`pmr735a-l7`），`0x2ab980` = 2.8 V | FDT |
| WLAN 侧 PCIe0 | `/soc/qcom,pcie@1c00000`：parf `0x1c00000/0x3000`、phy `0x1c06000/0x2000`、dbi `0x60000000`、elbi `0x60000f20`、atu `0x60001000`、config `0x60100000`；`perst-gpio=<&tlmm 94 0>`、`wake-gpio=<&tlmm 96 0>`、clkreq=GPIO95；`qcom,smmu-sid-base=<0x1c00>`，iommu-map RID0→0x1c00 / RID0x100→0x1c01 | 这是 **WLAN**，不是 BT |
| CNSS 节点 | `/soc/qcom,cnss-qca6490@b0000000`，`reg=<0xb0000000 0x10000>`（`smmu_iova_ipa`），`qcom,vreg_ipa="s3e"`；`wlan-en=GPIO80`、`qcom,bt-en-gpio=GPIO81`、`qcom,sw-ctrl-gpio=GPIO82`、`qcom,xo-clk-gpio=GPIO204` | WLAN 与 BT 共用板级控制 |
| SLIMbus 伴生 | `/soc/slim@3340000/ngd@1/btfmslim-driver`，`compatible="slim217,221"`，reg `<1 0>`；`slim@3340000` controller 正常 `status=ok` | 这是 FM/SLIM 音频/控制路径，不是 HCI；第一版可忽略 |
| Sound 中的 WCN BT | `/soc/spf_core_platform/sound`：`qcom,wcn-bt = <1>`、`qcom,tdm-audio-intf = <1>`、`qcom,mi2s-audio-intf = <1>` | 表示 AudioReach 侧存在 BT SCO 音频路径；与 HCI 无关，后续做 HFP 才用 |

> 关键结论：`bt_qca6490` 节点没有 child `bluetooth`，也没有 `qcom,wcn6855-bt` compatible；真正的 UART 是 `qup_uart@894000`。Android 侧 `bt_qca6490` 只负责上电/复位，HCI 由 `hci_qca` 通过该 UART 传输。注意 `bt-reset-gpio` 虽名为 reset，FDT 默认 pinctrl 是 `bt_en_sleep`/output-low；**有效电平和“先拉高还是先拉低”必须按 QCA6490 数据手册与实测确认（C）**，不要凭名字写死。

### 1.2 HCI 传输方式判定：UART/HS，不是 PCIe

| 问题 | 结论 | 依据 |
|---|---|---|
| QCA6490 WLAN 走什么 | PCIe0，`qcom,pcie@1c00000`，端点 ID 期望 `17cb:1103`（ath11k WCN6855 hw2.x） | `FDT`；`ZCODE:298` U9-C2 |
| QCA6490 BT 走什么 | **GENI UART / HS-UART**，QUPV3_2 SE20 `0x894000`，IRQ 587 | `FDT`；`ZCODE:308` U9-C12 |
| 是否 PCIe 复用 | 否。BT 节点没有 PCIe reg/msi；`qcom,cnss-qca6490` 的 `reg=0xb0000000` 是 WLAN 的 SMMU IPA 窗口 | `FDT` |
| UART 协议 | `qcom,msm-geni-serial-hs`；mainline 同硅先例是 `&uart20 { bluetooth { compatible = "qcom,wcn6855-bt" } }`，K60 的 SE20/GPIO 映射与其一致 | `ZCODE:308` |
| HCI 上层 | `hci_qca`（QCA vendor TLV 下载 → 标准 HCI）；不是裸 H4 一开始就能通 | mainline `drivers/bluetooth/hci_qca.c` 结构；C 级（本机无源码） |
| 初始/运行波特率 | DTS 未给；`hci_qca` 惯用 115200 初始化、运行 3.2 Mbps（WCN6855 家族）；**需上机实测** | C |
| 流控 | CTS/RTS 使用 GPIO76/77；`qcom,wakeup-byte=0xfd` | `FDT` |

Android 侧对应驱动名（用于对照，不是 iOS 可执行代码）：

| Android 驱动/节点 | 作用 | 证据等级 |
|---|---|---|
| `bt_qca6490`（`compatible="qcom,qca6490"`） | BT 电源、BT_EN/SW_CTRL、XO、7 路 vdd 配置 | 事实·高（`ZCODE:308`；`FDT`）；源码不在本机，C |
| `hci_qca`（`compatible="qcom,wcn6855-bt"` / `qcom,msm-geni-serial-hs`） | UART HCI 传输、QCA TLV/NVM 下载、HCI 初始化 | 事实·高（mainline 同硅）；源码不在本机，C |
| `btfmslim-driver`（`slim217,221`） | SLIMbus FM/音频伴生 | `FDT`；与 HCI 无关，第一版忽略 |
| `qcom,cnss-qca6490` / `cnss2` | WLAN 主机驱动（PCIe/MHI），不是 BT | `FDT`；`ZCODE:298` |

### 1.3 需要的固件（`qca/*.bin`）

| 用途 | 预期文件 | 来源/取法 | 等级 |
|---|---|---|---|
| QCA6490/WCN6855 BT rampatch | `qca/htbtfw21.tlv` | linux-firmware `qca/`；或 K60 `modem_a/image/qca6490/` 下同名文件 | **C（文件名为 WCN6855 家族惯例，K60 分区实际清单未核实）** |
| QCA6490/WCN6855 BT NVM | `qca/htnv21.bin` | 同上 | **C** |
| QCA6390 系 BT NVM（不要混用） | `qca/hpnv21.bin` | QCA6390 使用 `hp*` 前缀，QCA6490/WCN6855 应使用 `ht*`；不要误拷 | **C（用于排除错误来源）** |
| WLAN 固件（独立，不属于 BT） | `ath11k/WCN6855/hw2.1/amss.bin`、`m3.bin`、`firmware-2.bin`、`board-2.bin` | pong 从 `modem_b/image/qca6490` 提取了 200 个文件；K60 侧未列清单 | **C（WLAN 用；不要与 BT 固件混放）** |
| K60 分区实际路径 | 预计 `modem_a/image/qca6490/` 或 `modem_b/image/qca6490/` | 用 `adb shell ls -l /dev/block/by-name/modem_a` 挂载/读取，或按 `AdspFirmware.c` 的 FAT `image/` 方式读取 | **C** |

注意：pong 的 `configs/pong-power-sm8475.json` 只列 TFA 音频容器 `tfa98xx.cnt`，**没有 BT 固件**；pong 的 `PongPlatform24` 组件也没有 BT。不要从 pong 仓库找 `PongBt` 的固件清单，找不到是正常的。

### 1.4 iOS 16 侧可复用框架（IOBluetoothFamily/HCI）

**实测扫描方法**：对 `E:/hackios/UniXNU/out/ipsw/20G81/kernelcache.decompressed`（48,644,096 B，iPadOS 16.6.1 的 kernelcache）做 ASCII 字符串扫描；同样扫描 `21H461` 作为对照。

| 符号/类 | 20G81 结果 | 说明 |
|---|---|---|
| `IOBluetoothFamily` | **0 命中** | 不存在，不能 prelink/复用 |
| `IOBluetoothHCI` / `IOBluetoothHCIController` / `IOBluetoothHostController` | **0 命中** | 没有 Apple HCI 传输基类 |
| `com.apple.driver.AppleBluetooth` | 存在（`1.0.0d1`）；`CFBundleExecutable=AppleBluetooth`；personality `IONameMatch=bluetooth`、`IOClass=BTReset` | 只有电源/复位字符设备；**K60 `profile.toml:33` prelink roots 未包含 `com.apple.driver.AppleBluetooth`，复用前需加入 roots** |
| `BTReset` 函数 | `bt_reset`、`bt_wake`、`power_enable`、`bootstrap_lock`、`bootstrap-delay`、`btreset-verbose`；字符设备 `btreset` | 可作电源驱动参考，不是 HCI |
| `IOSerialFamily` | 存在：`com.apple.iokit.IOSerialFamily 9.1`，`IOSerialStreamSync`、`IOSerialBSDClient` | 可复用的串口 provider 框架；**当前 K60 `profile.toml:33` 的 prelink roots 不含 `IOSerialFamily`，需先加入 roots 或自行编译链接** |
| `AppleEmbeddedBluetoothForce` | 存在 | Apple Pencil/HID 相关，不是 HCI |
| `AppleBluetoothVoice` | 存在（`AppleSecondaryAudio` personality，provider `AppleARMIISDevice`，`IONameMatch=audio-data,bluetooth-voice`） | 只是音频路由 personality，不是 HCI |
| `bluetoothd` | 用户态进程；Pong 用 `_LimitLoadToDeviceTree=['bluetooth','marconi-bt']` 阻止启动 | `userland/board_services18.py:84-89` |

**结论**：

- **`IOBluetoothFamily`/Apple HCI 复用路线不成立（对 20G81 是负面证据）**。如果后续有人提出“把 IOBluetoothFamily 像 IOHIDFamily 一样 prelink 进 K60 内核”，先拿本表反驳：20G81 kernelcache 没有这个 kext。
- `AppleBluetooth` 只能提供 BT 电源/复位控制；其 `BTReset` 字符设备的 `function-*` 属性契约未在二进制中逐项核实（C）。自写 `PongBtPower` 比逆向它更可控。
- `IOSerialFamily` 是唯一可直接复用的内核框架：写一个 GENI UART provider 发布 `IOSerialStreamSync`，由 `IOSerialBSDClient` 暴露 `/dev/tty.*`，用户态 HCI 栈可读写该设备。
- **第一版不建议追求 Apple `bluetoothd`/CoreBluetooth**：`bluetoothd` 是用户态闭源，且没有可用的 Apple HCI 传输类；让 `CoreBluetooth` 应用直接可用属于 XL/未核实。第一版目标应是“自研 UART HCI + 用户态 btstack 做 BR/LE 扫描/连接/GATT/RFCOMM”。

### 1.5 需要新写的模块清单

| 模块 | 角色 | 语言/形态 | 复用等级 | 备注 |
|---|---|---|---|---|
| `PongBtPower` | BT 上电/复位：BT_EN GPIO81、SW_CTRL GPIO82、XO GPIO204、S5/S10/S11/S12/L7 轨；按顺序上电、释放复位 | C++ IOKit platform driver | **C**（无 PongBt 代码；仅 FDT 事实） | 也可先做一个用户态测试工具直接写 GPIO/PMIC 验证，再内核化 |
| `PongBtUart` | GENI UART SE20 初始化：`0x894000`、IRQ587、GPIO76-79、FIFO/波特率/流控；发布 `IOSerialStreamSync` 或字符设备 | C++ IOKit + `IOSerialFamily` | **B**（UART 初始化无现成 K60 代码；`IOSerialFamily` 本身 A） | 第一版可用 PIO/FIFO，不启用 DMA |
| `PongBtFirmware` | QCA `htbtfw21.tlv`/`htnv21.bin` 下载、TLV 解析、校验、版本读回 | C++/C | **C** | 需先列 K60 分区实际文件清单 |
| `PongBtHCI` | HCI H4 framing、command/event/ACL/SCO 队列、flow control、wake byte 0xFD | C++/C | **C** | 可与 `PongBtUart` 合并为第一阶段 |
| `PongBtUserClient` | 内核到用户态的 read/write/ioctl 通道；sandbox 授权 | C++ IOKit | **B** | 若用 `IOSerialFamily` 可直接走 BSD 设备，未必需要 |
| `pong-btstack` | 用户态双模栈：HCI transport plugin、L2CAP、SDP、RFCOMM、GATT；btstack 为纯 C 可移植实现 | 用户态 C | **B**（btstack 外部源码不在本机） | 先做 HCI/扫描，再做 GATT/RFCOMM；不要先碰 CoreBluetooth |
| `PongBtAudio` | HFP/SCO 音频路径（`qcom,wcn-bt=1` → AudioReach） | 内核/用户态 | **C** | 依赖音频先打通；第二阶段 |

### 1.6 ADT 节点与 boot args

**推荐自定义节点（第一版）**：在 `dts/mondrian.dts` 增加（或通过核心 `devicetree.py` 的 ADT 表生成）一个 `/arm-io/pong-bt`，用绝对地址属性避免不完整的 interrupt/reg 映射（与 `pong-touch`/`ufs` 的写法同一模式）：

```dts
pong-bt {
    compatible = "pong,sm8475-bt";
    pong,uart-base = <0x894000 0x4000>;
    pong,uart-irq = <587>;
    pong,uart-pins = <76 77 78 79>;
    pong,bt-en-gpio = <&tlmm 81 0>;
    pong,bt-sw-ctrl-gpio = <&tlmm 82 0>;
    pong,bt-xo-gpio = <&tlmm 204 0>;
    pong,baud-init = <115200>;
    pong,baud-run = <3200000>;   /* 待实测，先按 3.2M 候选 */
};
```

**给 AppleBluetooth 兼容路径**（仅研究，不建议第一版）：ADT 节点名必须是 `bluetooth`（`IONameMatch` 是 `bluetooth`），并尝试提供 `function-bt_reset`/`function-bt_wake`/`function-power_enable`/`bootstrap-delay` 属性；其属性类型和 GPIO specifier 格式 **C**，没有 iOS16 反汇编证据不要写死。

**boot args**：

| 参数 | 作用 | 建议 |
|---|---|---|
| `pong_bt=1` | 启用 BT 驱动/探测 | 第一版 |
| `pong_bt_stage=1` | 只上电/打印 PMIC 读数，不碰 UART | 分级 bring-up |
| `pong_bt_stage=2` | 初始化 UART、读 `GENI_FW_REVISION_RO` | 分级 |
| `pong_bt_stage=3` | 下载 QCA 固件 + HCI Reset | 分级 |
| `pong_bt_stage=4` | 启动 btstack 扫描/连接 | 分级 |
| `pong_bt_baud=...` | 覆盖运行波特率 | 调试用 |

**日志**：K60 没有外部可用的 SoC UART 调试口；PITFALLS P-10 明确记录“串口 COM3/COM4 是蓝牙虚拟口读不到内核输出”（`docs/reference/PITFALLS.md:97-104`）。BT 调试必须走屏幕/Advanced Logger/QR 或内核日志通道，不能假设能接主机 COM 口。

### 1.7 蓝牙验证阶梯

| 阶段 | 成功判据 | 证据 |
|---|---|---|
| S0 | `ioreg`/日志出现 `PongBtPower`，ADT 有 `pong-bt`，UART 寄存器可读 | 屏摄/内核日志 |
| S1 | BT_EN（GPIO81）= 高；SW_CTRL 时序正确；S10≈1.8 V、S11≈0.97–1.17 V、S1≈1.9–2.04 V、S12≈1.35–2.02 V、L7≈2.8 V；XO GPIO204 有 19.2 MHz latch | 万用表/示波器；PMIC 读数 |
| S2 | `GENI_FW_REVISION_RO(0x68)` 高 8 位 = UART 协议；`GENI_STATUS(0x40)` bit0=0；FIFO 深度 > 0；写 0xFD 能唤醒 | 内核日志 |
| S3 | QCA TLV 下载完成；HCI Reset 返回 Command Complete（0x0E）；Read Local Version 有合理值；Read BD_ADDR 非全 0/全 F | HCI 日志 |
| S4 | Inquiry/LE Scan 返回设备；可建立 ACL；btstack 能读 GATT | btstack 日志 |
| S5 | RFCOMM/SPP 或 GATT 读写稳定；断线重连 | btstack/设备 |
| S6（可选） | HFP/SCO 音频：`qcom,wcn-bt=1` 的 AudioReach 路径出 PCM | 需音频先打通；C |

---

## 2. 音频：K60 的 TFA9873/AW882xx

### 2.1 口径纠偏（必须先看）

| 任务书/旧文档口径 | K60 实测 | 处理 |
|---|---|---|
| “TFA9873 双功放” | `FDT` 只有 `awinic,aw882xx_smartpa@34/@35`；全 compatible 扫描无 `tfa,tfa98xx` | **按 AW882xx 设计**；TFA9873 只作 Pong 参考 |
| “TFA9873 的 I2S + SPMI 接线” | TFA9873 控制总线是 **I2C**（0x34/0x35），不是 SPMI；K60 的 SPMI 只挂 PMIC | 功放控制用 I2C（QUPV3_2 SE15）；SPMI 只用于 PMIC 轨 |
| “K60 全部同款 TFA9873”（`PONG-FEASIBILITY.md:31`/`ROUTE-A-18-HANDOFF:34`） | 该说法是 Pong 板级粗口径；K60 live FDT 与 `ZCODE:305` U9-C9 明确为 AW882xx | 以 `ZCODE:305`/`FDT` 为准；旧文档不用于实现 |
| “WSA883x 功放” | `wsa-macro@3240000`/`wsa2-macro@31E0000` 均 `status="disabled"`；`qcom,wsa-max-devs=<0>` | 不按 WSA883x/SoundWire 设计 |

> 如果实际目标机的硬件变体和 serial `6033dbec` 不是同一块板：TFA9873 与 AW882xx 都可能使用 I2C `0x34/0x35`，**不能靠地址区分**；第一步必须读 chip ID/revision，再决定走 TFA 参考代码还是 AW882xx 新代码。
>
> 关于“pong main 无 audio 驱动目录”：main 树里确实没有展开的 `drivers/PongPower` 目录；`drivers/PongPower` 是 git submodule 指针（`git -C E:/hackios/UniXNU-pong submodule status` 显示 `-c37179e...`，本工作区未初始化）。音频内核实现要到 `pong-power` 子模块看；`userland/PongAudioPlugIn.c`、`PongAudioRoute.h`、`audio_clock18.h` 等用户态代码仍在 main 树，是本方案的主要可抄来源。
>
> 注：`AGENT-COORDINATION.md`（371,564 B）全文 grep `TFA9873`/`QCA6490` **0 命中**；只有第 484 行状态表把音频/蓝牙列为不可用、第 3253 行提到 pong 专属 DT 契约缺失。故本文 K60 硬件值以 live `FDT` 和 `ZCODE`/`FEATURES` 为准，不把该文件当 TFA/QCA 数据源。

### 2.2 K60 实测音频接线

| 项目 | K60 实测值 | 说明 |
|---|---|---|
| 功放 | `awinic,aw882xx_smartpa` ×2，`/soc/i2c@880000/aw882xx_smartpa@34`、`@35` | `FDT`；不是 TFA |
| 功放 I2C 控制器 | `/soc/i2c@880000`（`qcom,i2c-geni`），`reg=<0x880000 0x4000>`；wrapper `/soc/qcom,qupv3_2_geni_se@8c0000`；pinctrl `qupv3_se15_i2c_active`，function `qup15`，GPIO56/57，2 mA pull-up | `FDT`；`iomem` 也显示 `880000-883fff : 880000.i2c` |
| 功放地址 | `@34` = TOP，`@35` = BOT（`reg=<0x34>`/`<0x35>`） | `FDT`；与 `ZCODE:305` 一致 |
| 复位 | `reset-gpio=<&tlmm 1 0>`（@34）、`<&tlmm 3 0>`（@35）；flag 0，极性需按 AW882xx 驱动核对 | `FDT`；**C 极性/时序** |
| IRQ | `irq-gpio=<&tlmm 88 0x2008>`（@34）、`<&tlmm 63 0x2008>`（@35） | `FDT`；0x2008 原始 flags 保留 |
| Speaker switch | `spksw-gpio=<&tlmm 52 0>` 仅 @34 节点 | `FDT` |
| 声道/同步 | `sound-channel` @34 = 0（空），@35 = 1；`sync-flag=<1>`；`dc-flag=0`；`aw-cali-mode="aw_none"` | `FDT`；无校准文件，需厂商默认寄存器表 |
| TDM 引脚 | GPIO121=SCK（`mi2s2_sck`）、GPIO123=WS（`mi2s2_ws`）、GPIO122=DIN（`mi2s2_data0`）、GPIO124=DOUT（`mi2s2_data1`）；drive-strength=8 mA；SCK/WS/DIN bias-disable，DOUT bias-pull-down | `FDT`；`/soc/pinctrl@f000000/tert_tdm*` |
| TDM 时钟 | `qcom,msm-cpudai-tdm-clk-rate = <0x177000>` = **1,536,000 Hz**（48 kHz × 32 bit × 1 slot/line）；`qcom,msm-mi2s-tx-lines=<0x3>`（2 条 TX data line）、`rx-lines=0`、`dev-id=2` | `FDT`；与 pong 的 3.072 MHz/单 SD1 不同，**不能直接抄 Pong 时钟** |
| Sound 卡 | `/soc/spf_core_platform/sound`：`compatible="qcom,waipio-asoc-snd"`、`qcom,model="waipio-mtp-snd-card"`、`qcom,tdm-audio-intf=1`、`qcom,mi2s-audio-intf=1`、`qcom,wcn-bt=1`、`qcom,wsa-max-devs=0`、`qcom,tdm-max-slots=8` | `FDT` |
| Codec | `wcd938x-codec`，`split-codec=1`，4×micbias 2750 mV；`va-macro@33F0000`/`tx-macro@3220000`/`rx-macro@3200000` 正常；`wsa-macro@3240000`/`wsa2-macro@31E0000` disabled | `FDT` |
| Audio SMMU | `qcom,msm-audio-ion`：`iommus=<&apps_smmu 0x1801 0>`、`qcom,smmu-enabled`、`qcom,smmu-version=2`；`apps-smmu@15000000/lpass_tbu@151e9000` 的 `qcom,stream-id-range=<0x1800 0x400>` | `FDT`；**SID 0x1801 与 Pong 相同** |
| ADSP | `/soc/remoteproc-adsp@03000000`，`compatible="qcom,cape-adsp-pas"`，reg `0x03000000/0x10000`，`status=ok`；memory-region → `/reserved-memory/adsp_region@9fd00000`，`reg=<0x9fd00000 0x3100000>`（49 MiB） | `FDT`；pong 是 `0x85700000/0x2800000`（40 MiB），**必须改常量** |
| SMEM | `/reserved-memory/smem_region@80900000`，`0x80900000/0x200000`（2 MiB） | `FDT`；与 Pong 的 `smem_base=0x80900000/0x200000` 相同 |
| IPCC | `/soc/qcom,ipcc@ed18000`，`0xed18000/0x1000`，IRQ 261；ADSP `glink-edge` transport=smem、mbox `adsp_smem`、remote-pid=2 | `FDT`；与 Pong `ipcc_base=0xed18000/irq261` 相同 |
| GPR | `/soc/remoteproc-adsp@03000000/glink-edge/qcom,gpr`：`qcom,glink-channels="adsp_apps"`、`qcom,intents=<0x200 0x14>`、`reg=<2>` | `FDT`；与 Sheng/Pong 的 `adsp_apps` 相同 |
| SPMI（仅 PMIC） | `/soc/qcom,spmi@c42d000`：cnfg `0xc42d000/0x4000`、core `0xc400000/0x3000`、obsrvr `0xc440000/0x80000`、intr `0xc4c0000/0x10000`；第二个 `spmi@c432000` bus 1 | `FDT`；AGENT-COORDINATION:459 已实测同一组 `CORE 0x0c400000 / OBS 0x0c440000 / CNFG 0x0c42d000` |
| PMIC 组 | `pmk8350@0`、`pm8350@1`、`pm8350c@2`、`pm8350b@3`、`pmr735a@4`、`pmr735b@5`、`pm8450@7` | `FDT`；与 FEATURES 一致 |
| Audio CMA | `/reserved-memory/audio_cma_region`，`size=0x1c00000`（28 MiB），`shared-dma-pool`/reusable | `FDT`；可留给 DSP；Pong 的 64 KiB low DMA 是另一块 |

### 2.3 Pong TFA9873 参考值（仅在硬件确认是 TFA 时使用）

| 项目 | Pong 值 | 出处 |
|---|---|---|
| 功放型号/版本 | TFA9873 ×2，I2C `0x34/0x35`，revision `0x0b73`（也接受 `0x1a73`） | `PongAudio.cpp:110`；`services70:7`/`services72:9` |
| I2C 控制器 | QUP1 SE5 `0xa94000/0x4000`，pinctrl `qupv3_se13_i2c_active`，GPIO48/49，qup13 mux1，pull-up/2 mA | `PongAudio.cpp:96-104`；`services71:23` |
| 复位 | GPIO1/GPIO89；DT 无 reset-polarity，按 Nothing 驱动默认 active HIGH：HIGH 10 ms → LOW 10 ms | `PongAudio.cpp:99-103`；`configs/pong-power-sm8475.json:90-99` |
| 地址/寄存器访问 | `regRead/regWrite`：8-bit reg，16-bit big-endian data（`regWrite` 先高字节后低字节） | `PongAudio.cpp:81-83` |
| revision 寄存器 | reg `0x03`，期望 `0x0b73`/`0x1a73` | `PongAudio.cpp:110` |
| KEY2 解锁 | reg `0x0f = 0x5a6b`；读 reg `0xfb` 的 key；写 reg `0xa0 = key ^ 0x5a` | `PongAudio.cpp:113` |
| 初始化寄存器 | `{0x02=0x0628, 0x61=0x0183, 0x63=0x005a, 0x6f=0x0082, 0x70=0xa3eb, 0x73=0x0187, 0x83=0x071c, 0x85=0x0380, 0xd5=0x004d}` | `PongAudio.cpp:114` |
| 32-bit TDM 格式字段 | `0x0480=0`、`0x2000=0`、`0x20c3=2`、`0x2144=31`、`0x2224=31`、`0x2000=1`、`0x0101=0`、`0x0000=1`、`0x0030=0` | `PongAudio.cpp:116-120` |
| 功放开/关字段 | 开：`0x0000=0`、`0x0120=1`、`0x0030=1`；关：`0x0030=0`、`0x0000=1` | `PongAudio.cpp:122` |
| TDMSPKE | field `0x2300` = TDM sink0 输入使能；TDMSPKS 只选 slot；**必须显式置 TDMSPKE** | `services133:26` |
| B0 hard_mute | field `0x5810` = PWM hard_mute；播放时解除 | `services140:9` |
| B0 TDM 格式 | 32-bit stereo：TDMNBCK=2、slot length=31、sample size=31；左右功放分别取 slot0/slot1 | `services144:21` |
| PCM 格式 | 48 kHz、stereo、32-bit Q31；PRM clock id `0x104`，3.072 MHz；SID1801；64 KiB DMA；8×3840 B periods；lead 30×480 frames | `services133:7`、`services136:21`、`services140:9`、`PongAudio.cpp:32-33,124-132` |

> 这张表的价值是：**如果 K60 上 I2C 0x34/0x35 读出的 revision 是 0x0b73，说明是 TFA9873，可直接复用 `PongAudio.cpp` 的寄存器序列**；如果读出的不是，则按 AW882xx 另行实现。不要把 TFA 寄存器写死到 K60 代码里。
>
> Pong 的部分 TFA 初始化数值来自 `PongAmpProfiles.h`，由 `scripts/prepare-pong-audio.py` 从厂商容器 `tfa98xx.cnt` 生成（Pong `configs/pong-power-sm8475.json:102`、`scripts/build-pong-power-native.py:39`）。K60 若确认是 TFA，需要提供对应的 `tfa98xx.cnt`；若是 AW882xx，需要厂商 `awini` 校准文件/默认寄存器表，二者不能互换。

### 2.4 需要的 ADT 节点

#### 2.4.1 `/arm-io/pong-audio`（自定义平台节点）

建议在 `dts/mondrian.dts` 中以绝对地址属性提供（或扩展核心 `devicetree.py` 的 ADT 生成表）：

```dts
pong-audio {
    compatible = "pong,sm8475-audio";
    pong,i2c-base = <0x880000 0x4000>;
    pong,i2c-pins = <56 57>;
    pong,amp-addresses = <0x34 0x35>;
    pong,amp-reset-gpios = <&tlmm 1 0>, <&tlmm 3 0>;
    pong,amp-irq-gpios = <&tlmm 88 0x2008>, <&tlmm 63 0x2008>;
    pong,amp-spksw-gpio = <&tlmm 52 0>;
    pong,tdm-pins = <121 122 123 124>;
    pong,tdm-clk-rate = <1536000>;
    pong,smmu-base = <0x15000000 0x100000>;
    pong,audio-sid = <0x1801>;
    pong,adsp-region = <0x9fd00000 0x3100000>;
    pong,smem-region = <0x80900000 0x200000>;
    pong,ipcc = <0xed18000 0x1000 261>;
};
```

这些属性是 **B（设计）**，还没有生成脚本/驱动读取它们；实现时应统一从该节点取值，而不是像 Pong 那样把地址写死在 `PongAudio.cpp`。

#### 2.4.2 `/chosen/pong-audio-dma`

Pong 的 UEFI/DarwinBoot 会从主 XNU 窗口之外分配 **64 KiB `EfiReservedMemoryType`**，通过 `/chosen/pong-audio-dma` 传给 XNU：16 字节 = `[u64 PA, u64 size=65536]`。`PongAudio.cpp:124` 校验 `lease[1] == BufferBytes`、4 KiB 对齐、`lease[0]+65536 <= 0x100000000`；Pong 的 ADT 生成器只放 `bytes(16)` 占位（`scripts/make-pong-adt-ipados18.py:183`），由 loader 填充。

K60 现状：`AGENT-COORDINATION.md:3253` 明确“`DarwinBootPkg` 里 pong 专属 DT 契约（`pong-allocatable-ram` / `pong-audio-dma` / `darwinboot-memory-ranges`）保留未删，K60 DTB 无这些节点 → `ClaimPongRam` 提前返回，等价 no-op”。因此 **K60 音频的第一硬前置之一是改 `uefi-mondrian`/DarwinBoot22 或 ADT 生成器：分配 64 KiB 低地址 DMA 并写 `/chosen/pong-audio-dma`**。这不是音频驱动自身能补的。

#### 2.4.3 可选的原生 `audio-data` 节点

若走原生 `IOAudio2Device` 路径（见 2.5），需要类似 Apple 的 `audio-data,pong-speaker` 节点、`device UID`/`device name` 和 `IOProviderClass=AppleARMIISDevice` 的 personality。K60 没有这些；**C**，不建议第一版做。

### 2.5 内核匹配点（AppleAudio / IOAudio2）

**20G81 kernelcache 实测**：

| 符号/类 | 结果 | 用途 |
|---|---|---|
| `com.apple.iokit.IOAudio2Family` | 存在；`CFBundleExecutable=IOAudio2Family`，`IOKitPersonalities` 为空；**已列在 K60 `profile.toml:33` prelink roots**（同处还有 `com.apple.driver.AppleIISController`、`com.apple.driver.AppleAudioClockLibs`） | 音频设备基类，K60 不需要 port，直接复用 |
| `IOAudio2Device` / `IOAudio2DeviceUserClient` | 存在（字符串/类名） | 原生 IOAudio2 子类的基类 |
| `AppleARMIISController` / `AppleARMIISDevice` | 存在（`AppleIISController/AppleARMIIS.cpp`；K60 `profile.toml:33` prelink roots 已含 `com.apple.driver.AppleIISController`） | Apple I2S 控制器/设备；可作为原生 provider |
| `AppleAudioClock` / `AppleAudioFirmwareDownloader` | 存在 | Apple 私有音频时钟/固件加载，不是 K60 直接匹配点 |
| `AppleSecondaryAudio` | 存在，`IOProviderClass=AppleARMIISDevice`，支持 `audio-data,bluetooth-voice` 等 | 蓝牙语音/次级音频路由的 Apple personality，后续 HFP 可参考 |

**两条实现路径**：

| 路径 | 内核匹配点 | 优点 | 风险/等级 |
|---|---|---|---|
| **路径 A（推荐，Pong 已验证）**：用户态 `AudioServerPlugIn` + 自定义 `PongAudio` IOService | `IOClass=PongAudio`（自定义 `IOService`），`IOUserClientClass=PongAudioUserClient`；不匹配 `IOAudio2Device` | 不依赖 `IOAudio2` 私有子类；Pong `PongAudioPlugIn.c`/`PongAudioService.cpp` 可复用；HAL 可控 | **A/B**；需要 20G81 `AudioServerPlugIn` ABI 重对 |
| **路径 B（原生）**：`PongAudio2Device : IOAudio2Device`，provider `AppleARMIISDevice` | `IOClass=PongAudio2Device`，`IOProviderClass=AppleARMIISDevice`，`IONameMatch=audio-data,pong-speaker` | 可能直接得到 `Speaker` 原生 UID，CoreAudio 走原生 IOAudio2 | **B/C**；`PongIOAudio2.h` 只在 pong-power 子模块（本工作区未展开），20G81 ABI 未核实 |

**建议**：第一版走路径 A，把 `PongAudioService.cpp` 的 `PongAudio`/`PongAudioUserClient` 结构照搬到 K60，先把 PCM 打通；路径 B 仅作为后续“减少自定义 HAL”的优化，不作为前置。若一定要用原生路径，需要先取得 `PongIOAudio2.h` 并逐行核对 20G81 的 `IOAudio2Device` vtable；否则 **C**。

### 2.6 用户态插件设计（参照 `services109`）

`services109` 的核心不是“写一个 HAL”，而是**正确查询 22H374 的 VirtualAudio 插件对象**：`pibi` 是 32 字节 `AudioValueTranslation`，`gCMSM+0x80` 是插件 ID，不是 VAD 设备 ID；`prts`/`rtcf` 发给插件，`vcsp` 才在 default VAD 上读。K60 目标 20G81 需要重新验证同一组 selector 是否存在/同义。

建议的 `PongAudio.driver` 设计：

| 层 | 设计 | 参考 |
|---|---|---|
| Bundle | `/System/Library/Audio/Plug-Ins/HAL/PongAudio.driver`（`CFBundlePackageType=BNDL`，`AudioServerPlugIn` 工厂 `PongAudio_Create`，`AudioServerPlugIn_IOKitUserClients=PongAudioUserClient`） | `userland/build-ipados18.py:891-907`（Pong 22H374） |
| 对象 | plugin(1)、device(2)、output stream(3)、input stream(4，不发布)、volume(5)、mute(6) | `PongAudioPlugIn.c:22-24` |
| 设备身份 | device UID `PongAudioDevice`；真实 Speaker 优先；transport `bltn`；不要伪装 Thunderbolt/HDMI | `services126:13-16`；`PongAudioPlugIn.c:390-414` |
| 端口查询 | `pibi`（system object）→ 32 字节 `{bundle ptr, bytes, out ptr, bytes}` → 插件 `AudioObjectID`；再用 `prts`（`kAudioObjectPropertyScopeGlobal`）+ `ptbo`/`pspk` 取 CFArray；对每个 port 用 `puid` 匹配真实 device UID | `PongAudioRoute.h:79-95,145-219`；`services109:10-15`；`services112:18-24` |
| 路由设置 | `rtcf` 的 32 字节请求：`allowed port types`、`overridden ports`、`routable ports`；只在端口变化时提交，避免每秒拆建音频图 | `PongAudioRoute.h:145-219`；`services126:13-16` |
| 音量/静音 | `vcsp` 在 default VAD 上读；`volm`/`vold`/`mute` 控制属性可写；真实增益、保护不伪造 | `PongAudioPlugIn.c:22-24,326-423`；`services127:6` |
| `dOut/sOut` | **不要**直接设置；22H374 上返回 `nope`（1852797029）；必须走 native `rtcf` | `services112:18-24` |
| 共享内存 | `ShengAudioControl` + 输出 ring：control 4 KiB，ring `65536` frames × 4 B（int16 stereo）；`StartIO` 才让内核启动 | `PongAudioService.cpp:58-132`；`PongAudio.cpp:134` |
| 状态页 | type0 status page 必须是 **kernel/user shared writable 4 KiB**；`HALS_IOA2Engine2::_FirstIOThreadStarted` 会写 status+0x18/+0x20 | `services127:6` |
| 时钟 | CoreAudio 在共享 cache 中把主机时钟当 **24 MHz**（`0x4176e36000000000`）；K60 arch timer 是 19.2 MHz；要么按 Pong `setHostClock` 改 double，要么在 `audio_clock18.h` 用 `mach_timebase` 换算 | `PongAudioService.cpp:24-50`；`services165:19-35` |
| 启动/停止 | `StartIO` 只发内核 start；`StopIO` 先停新提交、等 DSP/功放退出，再停图；错误真实返回 | `PongAudioPlugIn.c:561-592`；`services162:11-14` |
| 编解码 | `audio_codecs18.h` 的软件 AAC/ALAC 回退；不伪造硬件解码器 | `userland/audio_codecs18.h` |
| Sandbox | 内核服务 `NativeSandboxGrantProcess="audiomxd,mediaserverd"` | `PongAudioService.cpp:61-65` |

**20G81 与 22H374 的差异**：`PongAudioRoute.h` 内嵌 22H374 MediaExperience 的 `CMSMVAUtility_*` 地址/指令匹配（`0x7c14`、`0x14cde8`、`0x700ec` 等）**不能直接用于 20G81**。K60 侧必须先按 20G81 的 `MediaExperience.framework` 重新定位 `pibi`/`prts`/`rtcf` 路径，或只使用公开 `AudioObjectSetPropertyData` 的 API 路径；这部分 **B/C**，不是“照抄即可”。

### 2.7 音频数据通路（ADSP → AudioReach → TDM → 功放）

```
CoreAudio/audiomxd
  → PongAudio.driver (AudioServerPlugIn)
  → PongAudioUserClient (kernel)
  → PongAudio service (shared control + 65536-frame ring)
  → AudioReach APM graph on ADSP (adsp_apps, GPR/GLINK/SMEM/SMP2P)
  → LPASS TDM (K60: GPIO121-124, 1.536 MHz, tx-lines=2)
  → AW882xx @ I2C 0x34/0x35 (sound-channel 0/1)
  → speakers
```

关键常量/序列（来自 `PongAudio.cpp`，K60 需替换的值已在 2.2 标出）：

| 项目 | Pong（TFA） | K60（AW882xx） | 处理 |
|---|---|---|---|
| ADSP region | `0x85700000/0x2800000` | `0x9fd00000/0x3100000` | 改常量 |
| SMEM | `0x80900000/0x200000` | 同 | 保留 |
| IPCC | `0xed18000/0x1000`, IRQ261 | 同 | 保留 |
| GPR channel | `adsp_apps`, intents 0x200/0x14 | 同 | 保留 |
| DMA | 64 KiB low, SID 0x1801 | 同 | 保留，但需补 K60 ADT/UEFI |
| 周期 | 480 frames, 3840 B, 8 slots, lead 30×480 | 同（按 48k stereo 32-bit） | 保留 |
| I2S/TDM | 3.072 MHz PRM 0x104, SD1 双 slot | **1.536 MHz**、双 data line（tx-lines=3） | 改 PRM/分频/线路映射 |
| 功放 | TFA9873 I2C `0xa94000`, GPIO48/49, reset 1/89 | AW882xx I2C `0x880000`, GPIO56/57, reset 1/3, IRQ88/63, spksw52 | 重写功放层 |
| 电源 | PongPower `PongPlatformResources` 管理 ADSP/TFA 轨 | PMIC S5/S10/S11/S12/L7 等 | 复用 PMIC 三板斧，核对 K60 轨 |

**AudioReach 消息**（`ShengAudioReach.c`）：

- `PARAM_SG_CONFIG=0x08001001`、`PARAM_CONTAINER_CONFIG=0x08001000`、`PARAM_MODULE_LIST=0x08001002`、`PARAM_MODULE_PROP=0x08001003`、`PARAM_MODULE_CONN=0x08001004`、`PARAM_SG_LIST=0x08001005`、`PARAM_HW_EP_MF=0x08001017`、`PARAM_MEDIA_FORMAT=0x0800100C` 等。
- `CONTAINER_GC=0x0B001001`、`MEDIA_PCM=0x09001000`、`PERF_LOW_LATENCY=2`、`DIR_TX=1`/`DIR_RX=2`、`SCENARIO_PLAYBACK=1`、`POS_GLOBAL_DEV=4`、`DOMAIN_ADSP=2`。
- `PongAudio.cpp:136-153` 顺序：`ar_open_speaker_device` → `ar_config_speaker_device(48000,32,2)` → `ar_open_playback_stream` → `ar_config_playback_stream` → `ar_config_playback_shmem` → `ar_map(64KiB)`。
- `ShengAudioReach.c` 的 I2S 参数使用 `I2S_SECONDARY=1`、`I2S_SD1=2`、`WS_INTERNAL=1`、`LPAIF_RXTX=1`；K60 需要把 `I2S_SD1`/接口索引改成 K60 的 2 条 TX line 配置（具体值见 2.2）。
- `PongAudio.cpp:203-231` 启动顺序：`graph(PREPARE)` → `graph(START)` → `amps(true)`；停止：`graph(STOP)` → `amps(false)`。`services162` 要求功放先关、等 MANSTATE/SWS/AMPS 退出，再停 APM/MI2S clock；AW882xx 的对应状态位需查 AW882xx 数据手册（C）。

### 2.8 音频验证阶梯

| 阶段 | 成功判据 | 证据 |
|---|---|---|
| A0 | I2C `0x34/0x35` 有 ACK；读 chip/revision（AW882xx 或 TFA 0x0b73）；I2C 引脚 GPIO56/57 正常 | 内核日志；示波器/逻辑分析仪 |
| A1 | ADSP PAS 启动：`PongAudio: APM framework ready`；SMEM/SMP2P/GLINK/GPR `adsp_apps` 通道握手 | 内核日志 |
| A2 | AudioReach speaker/playback graph open/config/map 成功；TDM GPIO121-124 有 clock/WS；AW882xx 初始化完成（无 PCM） | 内核日志；示波器 |
| A3 | 提交 480-frame period，DSP 返回 `WRITE_DONE`；`PongAudio: stereo PCM output started`；PCM 非零 | 内核日志 |
| A4 | HAL `PongAudio: physical stereo service connected`；`StartIO` 成功；系统音量/静音可读写 | 用户态日志 |
| A5 | 可听声音（左右声道正确、无爆音/无长期静音）；48 kHz stereo Q31 | 人耳 + 示波器/录音 |
| A6 | 休眠/唤醒后恢复；StopIO 干净；无 TFA/AW 保护异常 | 多轮日志 |
| A7（可选） | 原生 `IOAudio2Device` 路径，设备 UID 为 `Speaker`，不依赖自定义 HAL | ioreg/CoreAudio |

---

## 3. 证据分级总表（实现项）

> 本表只列“实现/移植项”，不重复列硬件事实表里的 FDT 值。`M` 见硬件事实表；本表用 **A/B/C** 三类回答“能不能直接抄”。组合标签（如 `A/B`、`A（框架）/ B（接入）`）表示主体代码可抄、但仍有明确的平台/ABI 适配工作（B）；`B/C` 表示设计有、关键实现未核实。

### 3.1 蓝牙

| # | 实现项 | 等级 | 依据/说明 |
|---|---|---|---|
| B1 | `IOSerialFamily` 作为 UART provider 基座 | **A（框架）/ B（接入）** | `com.apple.iokit.IOSerialFamily 9.1` 存在于 20G81 kernelcache；但 K60 `profile.toml:33` 的 prelink roots 未含它，需要加入 roots（或自编）后才能用；`IOSerialStreamSync`/`IOSerialBSDClient` 类存在 |
| B2 | `PongBtPower` 电源/复位 | **C** | 无 PongBt；只有 `FDT` 的 BT_EN/SW_CTRL/XO/vdd 值；Apple `BTReset` 只作参考 |
| B3 | `PongBtUart` GENI UART 初始化 | **C** | K60 无现成 UART 驱动；只有 FDT + mainline `hci_qca` 结构 |
| B4 | `PongBtFirmware` QCA TLV/NVM 下载 | **C** | 无本机源码/无固件清单；expected `htbtfw21.tlv`/`htnv21.bin` 未核实 |
| B5 | `PongBtHCI` HCI 核心 | **C** | 无 PongBt；可参考 btstack 的 HCI 层，但传输/固件需自写 |
| B6 | `pong-btstack` 用户态栈 | **B** | btstack 是外部纯 C 项目；本机无源码，只有设计判断 |
| B7 | `AppleBluetooth` BTReset 复用 | **C** | 20G81 有 `BTReset`，但 K60 `profile.toml:33` prelink roots 未含 `com.apple.driver.AppleBluetooth`；`function-*` 属性契约、GPIO specifier 格式未核实 |
| B8 | `IOBluetoothFamily`/Apple HCI 复用 | **C（负面）** | 20G81 kernelcache 0 命中；不可 prelink/复用 |
| B9 | Apple `bluetoothd`/CoreBluetooth 复用 | **C（负面）** | 用户态闭源、无 Apple HCI 传输类；Pong 已明确不做 |
| B10 | `bluetoothd` 的 `_LimitLoadToDeviceTree` 门控 | **A** | Pong `userland/board_services18.py:84-89` 有可照抄的 gating 逻辑 |
| B11 | BT `qcom,wcn-bt=1` 的 HFP/SCO 音频 | **C** | `FDT` 有标志，但音频图/固件均未做；依赖音频先通 |

### 3.2 音频

| # | 实现项 | 等级 | 依据/说明 |
|---|---|---|---|
| A1 | ADSP PAS / `PongAdsp.cpp` 移植 | **A** | `PongAdsp.cpp` 30,783 B；`AdspFirmware.c` 7,165 B；K60 只改 carveout 0x9fd00000/0x3100000 等常量 |
| A2 | SMEM/SMP2P/GLINK/GPR | **A** | `ShengGpr.c`/`QcomSmem.c`/`QcomSmp2p.c`/`QcomGlink.c` 在 PongPower/Sheng；K60 FDT 的 `adsp_apps`/intents 与 Pong 相同 |
| A3 | AudioReach APM graph | **A** | `ShengAudioReach.c` 17,119 B；参数/容器/媒体格式齐全；K60 改 TDM 线路/时钟 |
| A4 | 64 KiB low DMA + SID1801 + SMMU | **A（驱动）/ B（UEFI）** | `PongAudio.cpp:124-132` 有完整驱动；K60 UEFI/DarwinBoot 的 `pong-audio-dma` 分配器缺失（AGENT-COORDINATION:3253），需要新写 |
| A5 | `PongAudio` 内核服务/UserClient | **A** | `PongAudioService.cpp` 6,346 B；`NativeSandboxGrantProcess`/shared memory/selector 齐全 |
| A6 | `PongAudioPlugIn.c` HAL 插件 | **A（代码）/ B（20G81 ABI）** | 41,210 B；对象/属性/StartIO/StopIO 完整；22H374 地址需要按 20G81 重对 |
| A7 | `PongAudioRoute.h` VirtualAudio 路由 | **A（代码）/ B（20G81 地址）** | 17,861 B；`pibi`/`prts`/`rtcf`/`vcsp` 逻辑完整；22H374 MediaExperience 指令偏移不能直接用 |
| A8 | `audio_clock18.h` 24→19.2 MHz 时钟 | **A（代码）/ B（20G81）** | `PongAudioService.cpp:24-50`/`audio_clock18.h` 有实现；20G81 的 CoreAudio double 地址需重找 |
| A9 | `audio_codecs18.h` 软件解码回退 | **A** | 本机 Pong userland 完整 |
| A10 | AW882xx 功放驱动 | **C** | K60 实测器件，但无 AW882xx 源码/寄存器表/awini 校准；必须从 Xiaomi 内核或厂商驱动取得 |
| A11 | TFA9873 功放驱动（仅在硬件确认时） | **A** | `PongAudio.cpp:99-122` 有完整寄存器序列；仅当 I2C 0x34/0x35 revision=0x0b73/0x1a73 |
| A12 | K60 TDM 1.536 MHz/双数据线配置 | **B** | `FDT` 给出 DT 值；Pong 代码是 3.072 MHz/单 SD1，需按 K60 `tx-lines=3`/`tdm-clk-rate=0x177000` 重算 |
| A13 | 原生 `PongAudio2Device : IOAudio2Device` | **B/C** | `IOAudio2Family`/`IOAudio2Device` 存在；`PongIOAudio2.h` 在 pong-power 子模块但本工作区未展开；20G81 vtable 未核实 |
| A14 | `AppleARMIISDevice` 原生 provider | **C** | 20G81 有 `AppleARMIISController/Device`，但没有 K60 `apple,iis`/`audio-data` 节点和绑定；需反汇编/实验 |
| A15 | WCD938x 麦克风/耳机捕获 | **B/C** | `FDT` 有 codec；Pong 明确只做输出、不做输入；第一版不做 |
| A16 | `pong-audio`/`pong-audio-dma` ADT 节点 | **B** | 2.4 的设计；尚无生成器/驱动读取 |
| A17 | 音量/静音/保护 | **A（框架）/ C（AW882xx 寄存器）** | Pong HAL/音量框架可抄；AW882xx 的保护/校准寄存器未知 |

### 3.3 共用/平台

| # | 实现项 | 等级 | 依据/说明 |
|---|---|---|---|
| P1 | K60 PMIC 电源轨（SPMI/RPMh/TCS） | **A/B** | Pong `QcomRpmh.c`/`ShengBattmgr.c` 可参考；K60 `FDT` 的 SPMI 地址/PPID 已实测；具体轨投票需按 K60 PMIC 表重对 |
| P2 | `pong-audio-dma` / `pong-bt` ADT 生成 | **B** | 设计；需改 `board.toml`/`dts`/核心 `devicetree.py`，并改 `uefi-mondrian` 分配器 |
| P3 | 内存窗口 4 GiB / `owned_memory_size` | **M/A** | `board.toml:98,148-162` 已有；不要改成 12 GiB（`PITFALLS`/`TRUST-LEDGER T1`） |
| P4 | `apply()` OS 窗口 + launchd | **A（Pong 脚本）/ 现状未做** | `userland/build.py:449`；K60 当前是 stock 20G81，launchd SIGSEGV 是硬阻断（`STATE:10`） |

---

## 4. 依赖顺序与前置条件

### 4.1 前置矩阵

| 前置条件 | 蓝牙 | 音频 | 说明 |
|---|---|---|---|
| `apply()` 后的 OS 窗口 / launchd 正常 | **是**（要跑用户态 btstack/测试工具） | **是**（要跑 audiomxd/HAL） | 当前 K60 唯一硬阻断（`STATE-2026-11-07.md:10`）；在此之前只能做内核级/裸机级 bring-up |
| 4 GiB 高内存窗口 | **是**（内核要起来） | **是**（内核要起来） | 当前 `board.toml` 4.75 GiB window、4096 MiB 实测；不要重开 12 GiB |
| UFS/OS root + Data | **是**（用户态） | **是**（用户态） | `NEXT-STEPS:53-55` 的顺序 |
| `pong-audio-dma` 64 KiB 低地址 DMA | 否 | **是** | K60 DarwinBoot 目前无此节点（`AGENT-COORDINATION:3253`） |
| ADSP PAS/GPR/SMEM/SMP2P/GLINK | 否（HCI 不依赖 ADSP） | **是** | 音频第一硬前置；`PongAdsp.cpp`/Sheng 代码可抄 |
| PMIC SPMI/RPMh 轨（S5/S10/S11/S12/L7、ADSP rails） | **是** | **是** | BT 与 WLAN/音频共用；需要共享锁/串行化 |
| WiFi/PCIe0 | 否 | 否 | 共享 QCA6490 XO GPIO204 + 部分电源轨；WiFi 先做时可复用其 PMU 上电序列，但不应当成 BT 前置 |
| GPU / Metal | **否** | **否** | 音频 PCM 与 BT HCI 不需要 GPU；软件 framebuffer 已可跑 SpringBoard（`STATE:25` 说明 GPU 仍是 stub） |
| 触摸 / HID | **否** | **否** | 只影响 UI 操作；不影响音频/BT 驱动 |
| 20G81 `AudioServerPlugIn`/CoreAudio ABI | 否 | **是**（路径 A） | 22H374 代码不能直接用于 20G81；需要重对 selector/对象模型 |
| `IOSerialFamily` | **是**（复用 provider，但需先加入 K60 prelink roots；当前 `profile.toml:33` 不含） | 否 | 20G81 kernelcache 有该类；K60 自定义内核只 prelink roots 中的 kext |
| `IOAudio2Family` | 否 | **是**（路径 B 可选） | 20G81 已存在；路径 A 不需要 |

### 4.2 推荐执行顺序

1. **系统基线（不属于本方案代码）**：在 macOS runner 上跑 `userland/build.py prepare()+apply()`，修好 stock OS 窗口；确认 launchd 不再 SIGSEGV、SpringBoard 稳定。没有这一步，音频 HAL/BT 用户态测试都无法可靠进行。
2. **共用平台资源**：把 K60 PMIC 轨（S5/S10/S11/S12/L7、ADSP CX/MX）封装成 `PongPlatformResources` 的只读/投票接口；与 WiFi（若并行）共享 APSS active TCS4 锁。先做 SPMI 只读观测，再写 enable。
3. **音频 A 阶段（推荐先做）**：
   a. `PongAdsp` + `AdspFirmware` + SMEM/SMP2P/GLINK/GPR（A 级）。
   b. `pong-audio-dma` UEFI 分配器 + `PongAudio` DMA/SMMU（A/B 级）。
   c. `PongAudio.cpp` 的 AudioReach graph + 64 KiB ring（A 级）。
   d. K60 TDM/PRM（1.536 MHz、tx-lines=3）+ AW882xx 驱动（C 级，最大新增）。
   e. `PongAudioService.cpp` + `PongAudioPlugIn.c` HAL（A 级，20G81 ABI 重对）。
   f. 音量/路由/休眠恢复（A/B 级）。
4. **蓝牙 B 阶段（音频之后或并行，依赖更少）**：
   a. `PongBtPower` 电源/复位（C）。
   b. `PongBtUart` + `IOSerialFamily`（B/A）；先把 `com.apple.iokit.IOSerialFamily` 加入 `profile.toml:33` 的 prelink roots。
   c. `PongBtFirmware` TLV/NVM（C）。
   d. `PongBtHCI` + btstack 扫描/连接（C/B）。
   e. 可选 HFP/SCO（C，依赖音频）。
5. **集成验收**：音频先出 PCM/可听声；BT 先出 HCI Reset/BD_ADDR/扫描；最后再做 HFP/A2DP 和 UI 集成。

> 不建议的顺序：先做 Apple `bluetoothd`/CoreBluetooth、先做原生 `IOAudio2Device`、先改 GPU/触摸来“等音频”。前两者是 XL/未核实，后者不是前置。

---

## 5. 风险与工作量分级

### 5.1 工作量

| 工作包 | 主要内容 | 估算 | 风险 |
|---|---|---|---|
| 音频 ADSP/GPR/GLINK/SMEM | `PongAdsp.cpp`/`AdspFirmware.c`/`ShengGpr.c`/`ShengAudioReach.c` SM8475 化 | **M/L：2–4 人周** | 中（同代 IP，代码可抄；K60 carveout 不同） |
| 音频 DMA/UEFI | 64 KiB low DMA、SID1801、SMMU 4K、table/lease | **M：2–3 人周** | 中（Pong 代码完整；UEFI 分配器新增） |
| 音频 TDM/PRM | K60 1.536 MHz、双 TX line、GPIO121-124、LPASS clock | **M：2–3 人周** | 中（DT 值明确；AudioReach 参数需实测） |
| 音频功放 AW882xx | I2C 驱动、寄存器表、awini 校准、保护/音量 | **L：3–5 人周** | **高（本机无源码/无寄存器表）** |
| 音频 HAL/内核服务 | `PongAudioService` + `PongAudioPlugIn` + 20G81 ABI | **M/L：3–4 人周** | 中（代码可抄，ABI 重对） |
| 音频路由/时钟 | `pibi/prts/rtcf/vcsp`、24→19.2 MHz、状态页 | **M：2–3 人周** | 中（22H374 实现可参考） |
| **音频合计** |  | **L：10–16 人周** | 中高 |
| 蓝牙电源/UART | `PongBtPower` + `PongBtUart` + `IOSerialFamily` | **M：2–3 人周** | 中（UART 简单，PMIC 轨多） |
| 蓝牙 QCA 固件/HCI | TLV/NVM、HCI 初始化、BD_ADDR/scan | **L：4–6 人周** | **高（无源码/无固件清单）** |
| 蓝牙用户态 btstack | HCI transport、L2CAP/SDP/RFCOMM/GATT | **M/L：3–4 人周** | 中（btstack 成熟，QCA 适配是新增） |
| **蓝牙基础合计** |  | **L：10–16 人周** | 高 |
| Apple `bluetoothd`/CoreBluetooth 集成 | 逆向用户态 HCI/transport 契约 | **XL：8+ 人周，成功概率低** | **极高/未核实**；不建议第一版 |

### 5.2 风险清单

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R1 | **K60 实测为 AW882xx，不是 TFA9873**；若按 TFA 写代码会完全跑不通 | 音频全盘返工 | 第一颗板级动作：I2C 0x34/0x35 读 ID/revision；按实际芯片分支 |
| R2 | AW882xx 无本机源码/寄存器表/awini 校准 | 功放不响/音质/保护异常 | 从 Xiaomi/LineageOS 内核拉 `aw882xx` 驱动与 `awini` 校准；先只做基本 init + TDM，再做音量/保护 |
| R3 | K60 TDM 1.536 MHz、双 data line 与 Pong 3.072 MHz/单 SD1 不同 | AudioReach 图/时钟不匹配，无声 | 以 `FDT` 的 `qcom,msm-cpudai-tdm-clk-rate=0x177000`、`tx-lines=0x3` 重算；用示波器验 SCK/WS |
| R4 | `pong-audio-dma` 在 K60 DarwinBoot 不存在 | 音频 DMA 无合法低地址 lease，PongAudio 直接失败 | 在 `uefi-mondrian` 增加 64 KiB `EfiReservedMemoryType` 分配器并写 `/chosen/pong-audio-dma`；先打印 PA/size |
| R5 | 20G81 与 22H374 的 `AudioServerPlugIn`/MediaExperience 地址不同 | HAL 路由/状态页崩溃或找不到设备 | 按 20G81 二进制重新定位 `pibi/prts/rtcf/vcsp`；先只做音量/设备发现，不照抄 22H374 绝对地址 |
| R6 | QCA6490 BT 固件实际文件/分区布局未核实 | 固件下载失败，HCI 起不来 | 先列 `modem_a/modem_b/image/qca6490` 清单；确认 `htbtfw21.tlv`/`htnv21.bin`；保留 fallback 文件路径 |
| R7 | BT 无 Apple HCI 栈，`bluetoothd` 不可用 | 只能自研栈，CoreBluetooth 应用不可用 | 第一版明确“btstack only”；CoreBluetooth 另立项/不承诺 |
| R8 | PMIC 轨与 WiFi/ADSP 争用（TCS4/RPMh） | 上电顺序冲突、死机 | 共用 `PongPlatformResources` 锁；BT/音频各自 stage gate，不在未上电时访问 MMIO |
| R9 | 无外部 UART 调试；BT UART 是内部 SE20，不是主机 COM | 无法直接抓 HCI 日志 | 屏幕/Advanced Logger/QR；PITFALLS P-10；BT 驱动内部环缓冲导出 |
| R10 | 当前 launchd SIGSEGV/stock OS 窗口未 apply | 所有用户态验证不可靠 | 先按 `APPLY-PIPELINE` 修 OS 窗口，再谈音频/BT 用户态 |

**历史坑检索**：`docs/reference/PITFALLS-FROM-HISTORY.md` 全篇没有 TFA/AW882/I2S/Bluetooth/QCA6490 的专项条目；它登记的是通用坑（12 GiB 内存窗口不可行、SPMI/RSC 访问、日志通道缺失等）。因此本方案的主要风险来自“K60 新增硬件缺口”，不是旧坑复现。可复用的通用教训是：不要试图加 12 GiB 窗口、不要在没有 PMIC 读数时访问 MMIO、不要把主机 COM3/COM4 当 SoC 调试串口（`docs/reference/PITFALLS.md:97-104`）。

---

## 6. 本次只出方案，不改代码

- **本文是方案文档，不是实现。** 没有修改 `patches/`、`series`、`drivers/`、`userland/`、`board.toml`、`dts/`、`uefi-mondrian` 或任何构建脚本。
- 没有在设备上执行 `fastboot boot`、没有写任何分区、没有读写固件分区。
- 没有新增/删除 `porting.toml` 记录；实现阶段应按仓库规则同步更新 `porting.toml` 和 `docs/state/TRUST-LEDGER.md`（本文的 K60 数值尚未登记为 trust 条目）。
- 建议下一步：先按 §4.2 的 1–2 步做系统基线与 PMIC 观测；音频/蓝牙各自开独立 `feat/` 分支，按 §3 的 A/B/C 分级逐项落地。

---

## 附录 A：Pong main 21 篇 `services*.md` 逐篇可执行硬件事实

> 读取命令：`git -C E:/hackios/UniXNU-pong show origin/main:migration/ipados18/<name>`。以下只摘“可执行硬件事实”，不重复设计论证。

| # | 篇目 | 可执行硬件事实 | 对 K60 的用途 |
|---|---|---|---|
| 1 | `services67-desktop-audio-pcie.md` | QCA6490 PCIe link：`target_link_speed=2`（Gen2 x1），aux 19.2 MHz、refgen 100 MHz；链路重启顺序为关 LTSSM、PERST 低、WLAN_EN 低 150 ms，再按 BT/XO/WLAN 时序上电；音频 HAL 崩溃点 `HALS_AHPManager::Activate()+48` 只是软件事实 | 证明 QCA6490 WLAN 是 PCIe0；BT 只出现在上电时序里，无 UART/HCI 参数。K60 的 PCIe0 常量可参考 |
| 2 | `services69-wifi-power-pipe.md` | WLAN 82 项 PHY 表、GPIO80/94/95/96/204、GCC 时钟、SPMI v7 只读 observer；AON smpe2 SID4/page9e/type1c/subtype0e，其他 buck type03/0a | BT/WLAN 共用 XO GPIO204 与电源；K60 的 SPMI 只读路径可照此 |
| 3 | `services70-audio-input-wifi.md` | APM ready；TFA9873 地址 `0x34/0x35`、revision `0xb73`；SID1801 DMA；立体声服务就绪但无 PCM | TFA 参考的入口；K60 若读 TFA 版本可用 |
| 4 | `services71-pinmux-audio.md` | MI2S active pinctrl 121/122/123/124，function1，8 mA，bias-disable；I2C 48/49；reset 1/89；LPAIF RX；TFA CNT profile；Wi-Fi PCIe0/SPI140/SID1c01/hw2 | K60 的 TDM 引脚相同（121–124），但 I2C 改为 0x880000/GPIO56/57、reset 改为 1/3；这是“同引脚不同板”的核心对照 |
| 5 | `services72-wifi-dma-audio.md` | Wi-Fi 128 MiB 物理连续 DMA（后改 VM 页）；TFA `0x34/0x35` rev b73；SID1801；无 StartIO | 音频 DMA 的失败模式参考；K60 用 64 KiB low DMA，不用 128 MiB |
| 6 | `services73-smmu-audio.md` | SMMU context 写序：先 TCR2/TCR 后 TTBR；AudioServerPlugIn `.driver`；audiomxd `RPCTimeout` 是 route discoverer 等待，不是硬件 | K60 SMMU 4K 表/context 代码可参考；audio HAL 路径 |
| 7 | `services106-mobilewifi-ui-wait.md` | 无音频硬件地址；恢复 `PongSpeakerNative` 优先和 PowerUI 注入 | 说明音频服务可能被 WiFi/UI 等待掩盖；K60 先排除 launchd |
| 8 | `services108-native-audio-port-query.md` | `prts` 要用 **glob** scope；`ptbo` qualifier；错误 2003332927=`who?`；`vaemGetVADPortIDFromVADPortType` 的真实查询 | K60 HAL 路由查询的 ABI 参考；20G81 需重对 |
| 9 | `services109-audio-plugin-keyboard.md` | `pibi` 是 32 字节 `AudioValueTranslation`；`gCMSM+0x80` 是 VirtualAudio 插件 ID（bundle `com.apple.audio.CoreAudio.VirtualAudio`）；`prts`/`rtcf` 发插件，`vcsp` 发 default VAD；HID Consumer usage `0x0c:e9/ea` | **用户态插件设计的核心篇**；K60 的 `PongAudioRoute.h` 直接沿用这套对象模型 |
| 10 | `services112-wifi-audio-phone-input.md` | 真实物理端口/两个 VirtualAudio 端口/`rtcf` 存在；`dOut/sOut` 返回 1852797029=`nope`；`prts` 返回 CFNumber 端口对象，`puid` 为设备 UID | K60 HAL 不能直接设 `dOut/sOut`；必须走 native `rtcf` |
| 11 | `services126-audio-package-latency.md` | 原生 Speaker UID、`bltn` transport；`pspk`/legacy `ptbo`；`read only=false`；IOAudio2 contract | K60 HAL 设备身份/音量控制的模板 |
| 12 | `services127-native-audio-rootful.md` | `HALS_IOA2Engine2::_FirstIOThreadStarted` 写 status+0x18/+0x20；type0 状态页必须 shared writable 4 KiB | K60 内核 `PongAudio` 状态页必须按此实现，否则 audiomxd SIGBUS |
| 13 | `services133-parity-audio-usb.md` | 两个 TFA9873；MI2S PRM 3.072 MHz；TDMSPKS 只选 slot，**TDMSPKE(0x2300)** 才连接 sink0；左右 slot 保持 | K60 TFA 分支的 TDM 使能；K60 AW882xx 需对应字段（C） |
| 14 | `services136-usb-mux-manual-reset-audio.md` | `MI2S-LPAIF-RX-TERTIARY` 硬件端点用 RX 方向；48 kHz stereo Q31、3.072 MHz PRM；不写 MTP/OTP | K60 的 TDM 方向/dev-id 需按 `FDT` 的 `qcom,msm-dai-q6-mi2s-tert` 重对（K60 `tx-lines=3`） |
| 15 | `services140-native-lockdown-audio-volume.md` | `media_format.payload_size` 只计 PCM 格式体（立体声 20 B），不要混 16 B 外层头；TFA B0 field `0x5810` PWM hard_mute；48 kHz stereo Q31、SD1、3.072 MHz、SID1801 | K60 的 AudioReach media format 打包必须按此；AW882xx 需要自己的 hard-mute 字段（C） |
| 16 | `services142-wake-usb-audio.md` | 原生 S16→Q31；音量 0..16 线性幅度；实测 volume5/gain414/PCM peak42135；TFA 保护/MTP 保持 | K60 音量曲线/转换的参考；AW882xx 需重映射 |
| 17 | `services144-data128-components-audio.md` | TFA9873 B0：TDMNBCK=2、slot length=31、sample size=31；左右功放 slot0/slot1；16 段音量；不写 MTP | K60 TFA 分支的 32-bit TDM 配置；AW882xx 的 TDM 槽位需查数据手册 |
| 18 | `services161-active-import-audio-resume.md` | StartIO 请求代次；显示休眠后 producer epoch/consumer 位置；只读已提交范围 | K60 HAL 休眠恢复的 ABI 参考；不直接给硬件地址 |
| 19 | `services162-sleep-audio-active-acquire.md` | 关功放先于 APM/MI2S clock；等 MANSTATE/SWS/AMPS；每次启动恢复 32-bit TDM/输入/sink，MANSCONF 先于 PWDN | K60 AW882xx 的关断顺序需按 datasheet 重写（C）；TFA 分支可直接用 |
| 20 | `services163-audio-prepare-command-stages.md` | 每次 APM 重启在 PREPARE 前重配 MI2S SD1 endpoint、PCM converter、shared-memory media format；StopIO 后 5 秒静音 DMA 保活 | K60 AudioReach 图重建顺序的模板 |
| 21 | `services165-scheduling-metal-audio-clock.md` | CoreAudio 24 MHz 常量 `0x4176e36000000000`；`AudioGetHostClockFrequency` getter；`AudioConvertHostTimeToNanos`=125/3、`AudioConvertNanosToHostTime`=3/125（22H374 地址 `0x1b756b38c`/`0x1b756b3b8`）；实际用 mach_timebase 19.2 MHz | K60 20G81 要重新定位这些常量/地址；不能直接套 22H374 地址 |

## 附录 B：源文件/命令索引

### B.1 Pong 21 篇读取命令

```sh
git -C E:/hackios/UniXNU-pong show origin/main:migration/ipados18/services67-desktop-audio-pcie.md
# 其余 20 篇同理；完整清单见任务书
```

### B.2 K60 FDT 解析命令

本文件使用的解析脚本为临时只读工具（不在仓库内）：

```sh
python E:/k60-work/tmp/fdt_dump.py E:/k60-work/reports/live-6033dbec-fdt.dtb node /soc/bt_qca6490
python E:/k60-work/tmp/fdt_dump.py E:/k60-work/reports/live-6033dbec-fdt.dtb node /soc/qcom,qup_uart@894000
python E:/k60-work/tmp/fdt_dump.py E:/k60-work/reports/live-6033dbec-fdt.dtb node /soc/i2c@880000/aw882xx_smartpa@34
python E:/k60-work/tmp/fdt_dump.py E:/k60-work/reports/live-6033dbec-fdt.dtb node /soc/spf_core_platform/sound
```

### B.3 关键源文件

| 文件 | 用途 |
|---|---|
| `E:/hackios/UniXNU-zizhan/drivers/PongPower/PongAudio.cpp` | ADSP/AudioReach/TFA/DMA 实现（20,428 B） |
| `E:/hackios/UniXNU-zizhan/drivers/PongPower/PongAudioService.cpp` | `PongAudio` IOService/UserClient（6,346 B） |
| `E:/hackios/UniXNU-pong/userland/PongAudioPlugIn.c` | AudioServerPlugIn 实现（41,210 B） |
| `E:/hackios/UniXNU-pong/userland/PongAudioRoute.h` | VirtualAudio `pibi/prts/rtcf/vcsp` 路由（17,861 B） |
| `E:/hackios/UniXNU-pong/userland/audio_clock18.h` | CoreAudio 24→19.2 MHz 时钟适配 |
| `E:/hackios/UniXNU-sheng/package/ShengAudioReach.c` | AudioReach 参数/消息构造（17,119 B） |
| `E:/hackios/UniXNU-sheng/package/ShengGpr.c` | GPR 传输（4,165 B） |
| `E:/hackios/UniXNU-sheng/package/AdspFirmware.c` | ADSP `modem_a/modem_b` 固件分片读取（7,165 B） |
| `E:/hackios/UniXNU-pong/configs/pong-power-sm8475.json` | Pong 音频/电源常量（TFA/SID/PRM/DMA） |
| `E:/hackios/UniXNU-mondrian/docs/reference/ZCODE-RESEARCH-REPORT.md` | K60 U9-C1..C15 事实/推断分级 |
| `E:/hackios/UniXNU-mondrian/docs/reference/FEATURES-DRIVERS-RESEARCH-2026-10-31.md` | K60 器件清单与 T1/T2 分层 |
| `E:/hackios/UniXNU-mondrian/docs/state/STATE-2026-11-07.md` | 当前 launchd/GPU/触摸/内存真相 |
| `E:/hackios/UniXNU-mondrian/docs/reference/PITFALLS.md` | P-10：无 UART 日志、COM3/4 是蓝牙虚拟口 |

### B.4 本次未核实项（C 级清单）

- QCA6490 BT 实际固件文件名与 K60 `modem_a/modem_b` 分区文件清单。
- QCA6490 BT UART 实际运行波特率、流控时序、`qcom,wakeup-byte` 的精确用法。
- AW882xx 的寄存器表、reset 极性、IRQ flags 语义、awini 校准数据。
- K60 TDM 1.536 MHz 与 AudioReach PRM 的实际分频/线路映射；需要示波器验证。
- K60 ADSP firmware `adsp.mbn` 的实际分区路径/文件名（应从 `modem_a/image/` 读取）。
- 20G81 的 `AudioServerPlugIn`/MediaExperience `pibi/prts/rtcf/vcsp` 选择器地址（22H374 的 `PongAudioRoute.h` 不可直接用）。
- 20G81 的 `IOAudio2Device` vtable / `PongIOAudio2.h` 兼容性（`PongIOAudio2.h` 不在本工作区）。
- 音频/BT 在 K60 上的任何上机结果（本文没有执行任何设备操作）。
