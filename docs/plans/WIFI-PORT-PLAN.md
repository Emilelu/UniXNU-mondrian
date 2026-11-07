# K60（Redmi K60 / mondrian / SM8475）WiFi 移植方案

> 状态：**方案稿（2026-11-08）**。本次**只出方案**，不改任何代码、补丁、构建脚本或设备镜像。
>
> 权威参照：`E:/hackios/UniXNU-pong` 的 `origin/main`，commit `e0ee6df109b4b5dc706cac660d4f8210dc911dac`（iPadOS 18.7.10 / 22H374 / Darwin 24）。
>
> K60 目标：`board.toml` 的 `ipados-16.6.1-20G81`（Darwin 22 / XNU 8796.141.3）。
>
> 证据约定：`repo:` 是仓库文件与行号；`FDT:` 是 `E:/k60-work/reports/live-6033dbec-fdt.dtb` 的解析结果；`device:` 是 K60 设备侧只读采集；`未核实` 表示现有材料不能证明，不用推测补齐。

## 0. 一页结论

**PongWifi 是当前最接近 K60 的完整实现，应直接移植 Pong 的 QCA6490 + ath11k 路线，不要沿用 K60 `porting.toml` 里指向 Ath12kWifi 的旧规划。** PongWifi 是 PCIe0 + MHI + QRTR/QMI 的真实 Linux v7.0.14 ath11k，向 UniXNU station ABI 提供 `nw_wifi_start/step/stop`，并从 Darwin 侧发布 en0/IO80211Interface（`pong:README.md:3-10`、`pong:README.md:25-32`）。

K60 与 Pong 的板级重合度很高：PCIe0 六个 `reg` 窗口、BAR0 `0x60200000`/2 MiB、GPIO 80/81/82/94/95/96/204、82 项 PHY 序列、`gdsc@17b004` + collapse vote `0x162128` bit0、SID `0x1c01`、IOVA `0xA0000000`/256 MiB、MSI SPI140 全部在 K60 live FDT 或 `/proc/iomem` 中能对上（见 §2）。真正需要改的是：K60 的时钟表索引、供电轨的 PMIC 物理身份、cnss 的 `use-nv-mac` 策略、固件路径与子设备 ID，以及 16.6.1 的 IO80211 ABI。

两个非 WiFi 代码的前置缺口必须先补：**PongPower 的 `PongPlatformResources`/`QcomRpmh` 不在 K60 树里**，以及 K60 的 NativeUfs 没有 Pong 的 `pong_ufs_ready()` 导出。前者是 WiFi 供电与 SMMU 租约的底座，后者让 WiFi worker 等 UFS/SMMU 就绪；不补这两项，`PongWifiPlatform.cpp` 连编译/链接都过不去（`pong:PongWifiPlatform.cpp:17-20`、`:33`、`:38`）。

建议按 §4 的六阶段实施：先补依赖和板级 profile，再抓固件，最后才是内核接入与上机。**本文不修改任何文件。**

---

## 1. Pong main 的 WiFi 实现结构

### 1.1 子模块、URL 与固定 commit

| 项 | 值 | 来源 |
|---|---|---|
| `UniXNU-pong` main | `e0ee6df109b4b5dc706cac660d4f8210dc911dac` | `git rev-parse origin/main`（本次读取） |
| `drivers/PongWifi` | `https://github.com/Chengdong-Yu/pong-wifi.git`，commit `d2e33ca6e0f6a3b3e7881a45ab36c6920e7afb07` | `git ls-tree origin/main drivers/PongWifi`；`.gitmodules:34-36` |
| `drivers/PongPower` | `https://github.com/Chengdong-Yu/pong-power.git`，commit `c37179ed12ba7f981b2b088aea482b969085eb84` | `git ls-tree origin/main drivers/PongPower`；`.gitmodules:28-30` |
| `PongWifi` 的共享 station 源码 | `https://github.com/UniXNU/Ath12kWifi.git`，commit `f6bf561f92cc42761bdd417fce1d53fe1db9477c` | `pong:configs/pong-native-sources.toml:9-14` |
| `PongWifi` 的 Linux ath11k 源码 | `https://github.com/gregkh/linux.git`，`ref = v7.0.14`，commit `458c6079fc1d41d564c37679c8ace02cd83ee817` | `pong:configs/pong-native-sources.toml:16-22` |
| `PongWifi` 的 `QcomRpmh` 源码 | `https://github.com/UniXNU/UniXNU-sheng.git`，commit `08cde20edc3254ed6f7df8d0f5384fb887786e8f` | `pong:configs/pong-native-sources.toml:4-8`；`pong:prepare-pong-wifi.py` 构建时使用 `sheng_source/package/QcomRpmh.c` |

`drivers/PongWifi` 的目录/文件清单（本地参考 clone `E:/k60-work/references/pong-wifi` 与 submodule commit 一致）：

```text
PongWifiPlatform.cpp     电源、PCIe/PHY、BAR、SID 1c01、native 4KiB 页表、MSI、worker
PongWifiNet.cpp          ifnet、Apple80211 ioctl、IO80211 user client、RX/TX、网络事件
PongWifiPci.cpp/.h       早期 PCI 交接适配器；不是完整路径，不另作 PCIe owner
ath11k/PongAth11k.c      nw_wifi_start/step/stop、ath11k hooks、MAC、固件错误收口
ath11k/compat/*.h        Linux 编译兼容头
README.md                适配硬件、接口和当前证据
proprietary-files.txt   固件清单（不存固件本体）
```

### 1.2 源文件职责（按调用顺序）

| 文件 | 职责 | 关键锚点 |
|---|---|---|
| `PongWifiPlatform.cpp` | 板级冷启动：GCC/TLMM 映射、WLAN_EN/XO/PERST/CLKREQ/WAKE、RPMh 轨、PHY 表、PCIe link、BAR、SID1c01 native4K 页表、MSI 接收器、`pong_wifi_start_optional()` worker | `pong:PongWifiPlatform.cpp:17-20`（依赖 `ArmSmmu4KProgram.h`、`PongWifiInputs.h`、`QcomRpmh.h`、`PongPlatformResources.h`）；`:36-42`（Iova `0xa0000000`、MSI 寄存器、SPI140、64 MiB arena）；`:340`（端点 ID 校验）；`:397-470`（SMMU/隔离）；`:555-585`（worker）；`:598-605`（boot-arg `pong_wifi` 入口） |
| `PongWifiNet.cpp` | Darwin 网络侧：`IONetworkStack`、`IO80211Controller`、`IO80211Interface`、`Pong80211UserClient`、ifnet、Apple80211 请求、scan/join/DHCP/事件 | `pong:PongWifiNet.cpp:71-100`（scan/channels/assoc/link 布局）；`:500-511`（22H374 type-0 用户客户端与 0x3c30 envelope）；`:513-612`（user client）；`:617-631`（IO80211Interface stub）；`:752`（`pong_wifi_net_start`） |
| `ath11k/PongAth11k.c` | 把 Linux ath11k PCI/MHI/QMI 接到 UniXNU `nw_abi`；检查 `device_id == 0x1103`、BAR ≥ 2 MiB；`nw_wifi_step` 泵 dispatcher；固件错误时停止并保留 DMA | `pong:PongAth11k.c:71-104`（`nw_wifi_start`）；`:107-140`（`nw_wifi_step/stop`）；`:26-64`（station identity 与 MHI 失败处理） |
| `ath11k/PongAth11k.c` + `ath11k/compat` | Linux v7.0.14 ath11k 的 PCI/MHI/QRTR/QMI 编译面；不伪造成功实现 | `pong:PongWifiPlatform.cpp:2-4`；`pong:README.md:14` |
| `PongWifiPci.cpp/.h` | 只接收已有 PCI 交接的辅助代码；完整路径由 `PongWifiPlatform.cpp` 负责 | `pong:README.md:67-68`；`pong:PongWifiPci.cpp:117`（端点身份 `0x110317cb`/`0x010817cb`） |

### 1.3 构建脚本入口

| 入口 | 作用 | 关键点 |
|---|---|---|
| `scripts/prepare-pong-wifi.py` | 从 REC 只读抓 Pong 当前活动槽的 live DT + PCI sysfs + `modem<slot>` 的 `image/qca6490` 固件；生成 board profile 和 `local-inputs.json` | `pong:prepare-pong-wifi.py:63-140`（`describe()` 解析 DT/PCI）；`:134`（`nv_mac_required='use-nv-mac' in wlan`）；`:135-138`（device/runtime path 与 required）；`:143-203`（REC、槽位、只读挂载、pull） |
| `scripts/build-pong-ath11k.py`（merged 版本 `kits/PongPlatform24/build-support/merged-scripts/build-pong-ath11k.py`） | 编译 Linux v7.0.14 ath11k + MHI/QRTR/QMI，产出 `build/pong-ath11k/libPongAth11k.a` | `pong:kits/PongPlatform24/build-support/merged-scripts/build-pong-ath11k.py:24-231`；`:174-181` 是 clang flags（含 `-target arm64-apple-ios18.0`、`-I drivers/PongWifi/ath11k/compat`）；`:216` 输出 archive |
| `scripts/build-pong-wifi-native.py` | 从 `configs/pong-wifi-sm8475.json` 生成 `PongWifiInputs.h`；把固件打成 `PongWifiFirmware.bin`/`.s`；编译 `PongWifiPlatform.cpp`、`PongWifiNet.cpp`；合并 `libPongWifiNative.a` | `pong:build-pong-wifi-native.py:22-66`（profile→header）；`:67-92`（PWF2 固件包）；`:98-129`（编译/归档） |
| `build-xnu-ipados18.sh` | 顶层构建：`XNU_PONG_WIFI=1` 时调用上面两个脚本，并把 `libPongWifiNative.a` 强制链入内核 | `pong:build-xnu-ipados18.sh:260-266`（构建）；`:1016-1020`（`-Wl,-force_load`） |
| `configs/pong_ipados18_defconfig` | `CONFIG_XNU_PONG_WIFI=y` | `pong:configs/pong_ipados18_defconfig:61` |
| 运行时开关 | `pong_wifi=1` 启动板级 worker；`pong_wifi=0`/缺省时完全不启动 | `pong:PongWifiPlatform.cpp:598-601`；`pong:README.md:32` |

### 1.4 `configs/pong-wifi-sm8475.json` 字段逐项

以下行号均指 `pong:configs/pong-wifi-sm8475.json`。

| 字段 | Pong 值 | 含义/备注 |
|---|---|---|
| `format` | `"pong-qca6490-board-v1"` | 板级 profile schema 版本（`:2`） |
| `board` | `"pong"` | 板名（`:3`） |
| `soc` | `"SM8475"` | SoC（`:4`） |
| `pci.vendor` | `6091` = `0x17CB` | Qualcomm PCI vendor（`:6`） |
| `pci.device` | `4355` = `0x1103` | QCA6490/WCN6855 端点（`:7`） |
| `pci.subsystem_vendor` | `6091` = `0x17CB` | 子系统 vendor（`:8`） |
| `pci.subsystem_device` | `264` = `0x0108` | Pong 的子系统 device；K60 未核实（见 §2） |
| `pci.revision` | `1` | PCI revision（`:10`） |
| `pci.bar0.base` | `1612709888` = `0x60200000` | BAR0 基址（`:12`） |
| `pci.bar0.bytes` | `2097152` = `0x200000` | 2 MiB BAR0（`:13`） |
| `radio` | `"QCA6490"` | WiFi 芯片（`:16`） |
| `driver_family` | `"ath11k"` | 不是 ath12k（`:17`） |
| `transport` | `"PCIe/MHI/QRTR"` | MHI + QRTR/QMI 传输（`:18`） |
| `source.wlan` | `/soc/qcom,cnss-qca6490@b0000000` | 抓取时的 live DT 节点（`:20`） |
| `source.pcie` | `/soc/qcom,pcie@1c00000` | PCIe0 控制器节点（`:21`） |
| `source.input` | `REC /sys/firmware/fdt and PCI sysfs` | 输入来源说明（`:22`） |
| `pcie.index` | `0` | PCIe0（`:25`） |
| `pcie.regions.parf` | `0x1c00000` / `0x3000`（12288） | PARF 窗口（`:27-30`） |
| `pcie.regions.phy` | `0x1c06000` / `0x2000`（8192） | QMP PHY 窗口（`:31-34`） |
| `pcie.regions.dm_core` | `0x60000000` / `0xf1d`（3869） | DBI/DWC core（`:35-38`） |
| `pcie.regions.elbi` | `0x60000f20` / `0xa8`（168） | ELBI（`:39-42`） |
| `pcie.regions.iatu` | `0x60001000` / `0x1000`（4096） | iATU（`:43-46`） |
| `pcie.regions.conf` | `0x60100000` / `0x100000`（1 MiB） | 配置空间（`:47-50`） |
| `pcie.gpio.wlan-en-gpio` | `80` | WLAN_EN（`:53`） |
| `pcie.gpio.qcom,bt-en-gpio` | `81` | BT_EN（`:54`） |
| `pcie.gpio.qcom,sw-ctrl-gpio` | `82` | SW_CTRL（`:55`） |
| `pcie.gpio.qcom,xo-clk-gpio` | `204` | XO_CLK latch（`:56`） |
| `pcie.gpio.perst` | `94` | PERST#（`:57`） |
| `pcie.gpio.wake` | `96` | WAKE#（`:58`） |
| `pcie.clock_names` | 14 项：`pcie_0_pipe_clk` … `pcie_pipe_clk_ext_src` | 与 `PongWifiPlatform.cpp` 的 GCC 分支表配套（`:60-75`） |
| `pcie.clock_specifiers` | 28 个 cell（14 对 clock/id） | `clocks` 属性（`:76-105`） |
| `pcie.reset_specifiers` | `36,4,36,7` | `resets`（`:106-111`） |
| `pcie.sid_map` | `0,93,7168,1,256,93,7169,1` | iommu-map；SID `0x1c00/0x1c01`（`:112-121`） |
| `pcie.phy_sequence` | 82 × `{offset,value,delay}` | 完整 QMP PHY 表；K60 与 Pong 逐 cell 相同（`:122-533`；见 §2） |
| `pcie.phy_status_offset` | `532` = `0x214` | PHY 状态寄存器（`:534`） |
| `pcie.phy_status_bit` | `6` | PHY 状态位（`:535`） |
| `pcie.analogue_rails` | `vreg-1p8` → `ldoc10` 1200000 µV；`vreg-0p9` → `ldob5` 880000 µV | 模拟 LDO（`:536-547`） |
| `pcie.power_domain.control` | `1552388` = `0x17B004` | PCIe0 GDSC 控制寄存器（`:548-553`） |
| `pcie.power_domain.collapse_vote` | `1450280` = `0x162128` | APSS collapse vote 寄存器（`:548-553`） |
| `pcie.power_domain.collapse_bit` | `0` | collapse bit（`:548-553`） |
| `pcie.phy_power_down_offset` | `576` = `0x240` | PHY power-down 偏移（`:553`） |
| `pcie.max_clock_frequency_hz` | 15 项；`[3]=19200000`、`[11]=100000000` | **K60 同数组索引不同，见 §2**（`:554-569`） |
| `pcie.aux_clock_mhz` | `20` | `qcom,aux-clk-freq`（`:571`） |
| `pcie.endpoint_latency_ms` | `10` | `qcom,ep-latency`（`:572`） |
| `pcie.perst_delay_us` | `1000` | `qcom,perst-delay-us-min` 缺省 1000（`:573`） |
| `pcie.pinmux_source` | `NothingOSS pinctrl-cape.h ... GPIO94 gpio, GPIO95 pcie0_clkreqn (mux1), GPIO96 gpio` | 引脚复用来源（`:574`） |
| `pcie.target_link_speed` | `2` | Gen2 x1，来自 Pong REC CNSS IPC 日志（`:575-576`） |
| `pcie.target_link_speed_source` | `Pong REC CNSS/msm_pcie IPC log: target_link_speed=2, negotiated Gen2x1` | 证据说明（`:576`） |
| `pcie.clock_sequence` | `TCXO PIPE enabled during host reset/table setup, external PIPE selected before PCS reset release/start...` | Pong 的 QMP 交接顺序（`:577`） |
| `dma.iova_pool` | `[2684354560, 268435456]` = `0xA0000000`, `0x10000000`（256 MiB） | SMMU IOVA 池（`:580-583`） |
| `dma.msi_bytes` | `4096` | MSI landing page（`:584`） |
| `dma.cache_policy` | `"coherent"` | 页表 cache policy（`:585`） |
| `msi.map` | `0,565,22912,1,256,565,22913,1` | msi-map（`:588-597`） |
| `msi.controller` | `/soc/interrupt-controller@17100000/msi-controller@17140000` | GIC ITS MSI controller（`:598`） |
| `msi.compatible` | `"arm,gic-v3-its"` | `:599-603` |
| `msi.reg` | `[387186688, 131072]` = `0x17140000`, `0x20000` | MSI controller 寄存器（`:601-603`） |
| `msi.legacy_spi_node_status` | `"disabled"` | 旧 `qcom,pci-msi` 节点 disabled（`:604`） |
| `rails` | 7 条：`vdd-wlan-aon` → `smpe2`/`pmr735a_s2`，`vdd-wlan-dig` → `smpb11`/`pm8350_s11`，`vdd-wlan-io` → `smpb10`/`pm8350_s10`，`vdd-wlan-rfa1` → `smpc1`/`pm8350c_s1`，`vdd-wlan-rfa2` → `smpb12`/`pm8350_s12`，`wlan-ant-switch` → `ldoe7`/`pmr735a_l7`，`vdd-wlan-ipa` → `smpe3`/`pmr735a_s3` | 每条含 `request`（min/max/…）与 `physical`（SPMI slave/peripheral/type/subtype）（`:606-733`） |
| `nv_mac_required` | `true` | Pong 的 live DT 有 `use-nv-mac`；K60 无此属性（`:734`；§2） |
| `firmware.device_path` | `/mnt/pong-wifi-firmware/image/qca6490` | REC 只读挂载点（`:736`） |
| `firmware.runtime_path` | `/pong/firmware/qca6490` | 运行时路径（`:737`） |
| `firmware.required` | `amss.bin`、`amss20.bin`、`m3.bin`、`regdb.bin` | 必需固件（`:738-743`） |
| `firmware.board_data` | `select from actual QMI chip/board ID; no default variant` | BDF 选择策略（`:744`） |
| `readiness.board_inputs` | `true` | 板级输入已抓（`:747`） |
| `readiness.ath11k_backend` | `true` | 后端源码已接（`:748`） |
| `readiness.darwin24_apple80211` | `true` | Darwin24 网络侧已接（`:749`） |
| `readiness.firmware_boot_observed` | `false` | 设备未确认固件启动（`:750`） |
| `readiness.scan_observed` | `false` | 设备未确认扫描（`:751`） |
| `readiness.link_observed` | `false` | 设备未确认联网（`:752`） |
| `readiness.meaning` | `backend/ABI flags describe source integration; firmware/scan/link flags require phone observations` | 静态/设备证据分离（`:753`） |

补充：`readiness` 的静态 flags 是“源码已接”标记，不代表 Pong 设备上没扫到过热点；Pong 迁移记录里 services94/104 已观察 en0/扫描，见 `pong:migration/ipados18/services94-native-volume-wlan.md:9`、`pong:migration/ipados18/services104-system-peripheral-order.md:10-11`。

---

## 2. K60 与 Pong 的板级差异表

### 2.1 K60 live FDT 解析摘录

解析对象：`E:/k60-work/reports/live-6033dbec-fdt.dtb`，919210 bytes，SHA-256 `95c02052b773a1b8df8ec20f6368ba80c87717206ed40682046e2ad6f29fdac8`（`docs/audits/MEASURED-HIGH-WINDOW-2026-11-02.md:33-34`）。解析方法：复用 `pong:prepare-pong-wifi.py:21-61` 的 `fdt_nodes()/cells()/text()`，遍历 `qcom,cnss-qca6490@b0000000`、`qcom,pcie@1c00000`、`mhi_qrtr_cnss`、`cnss_wlan_region`。关键输出：

```text
/soc/qcom,cnss-qca6490@b0000000
  compatible = "qcom,cnss-qca6490"
  reg = <0xb0000000 0x10000>, reg-names = "smmu_iova_ipa"
  qcom,wlan-rc-num = <0>
  wlan-en-gpio = <&tlmm 0x50 0>         # GPIO80
  qcom,bt-en-gpio = <&tlmm 0x51 0>      # GPIO81
  qcom,sw-ctrl-gpio = <&tlmm 0x52 0>    # GPIO82
  qcom,xo-clk-gpio = <&tlmm 0xcc 0>     # GPIO204
  vdd-wlan-aon-supply -> /soc/rsc@17a00000/rpmh-regulator-smpe2/regulator-pmr735a-s2
  vdd-wlan-dig-supply -> /soc/rsc@17a00000/rpmh-regulator-smpb11/regulator-pm8350-s11
  vdd-wlan-io-supply -> /soc/rsc@17a00000/rpmh-regulator-smpb10/regulator-pm8350-s10
  vdd-wlan-rfa1-supply -> /soc/rsc@17a00000/rpmh-regulator-smpc1/regulator-pm8350c-s1
  vdd-wlan-rfa2-supply -> /soc/rsc@17a00000/rpmh-regulator-smpb12/regulator-pm8350-s12
  wlan-ant-switch-supply -> /soc/rsc@17a00000/rpmh-regulator-ldoe7/regulator-pmr735a-l7
  qcom,vreg_ipa = "s3e"
  qcom,vdd-wlan-aon-config = <0xf7120 0xfde80 0 0 1>
  qcom,vdd-wlan-dig-config = <0xebd70 0x11da50 0 0 1>
  qcom,vdd-wlan-io-config = <0x1b7740 0x1b7740 0 0 1>
  qcom,vdd-wlan-rfa1-config = <0x1cfde0 0x1ee240 0 0 1>
  qcom,vdd-wlan-rfa2-config = <0x149970 0x1f20c0 0 0 1>
  qcom,wlan-ant-switch-config = <0x2ab980 0x2ab980 0 0 1>
  # 无 use-nv-mac 属性

/soc/qcom,pcie@1c00000
  compatible = "qcom,pci-msm"; cell-index = <0>
  reg-names = "parf phy dm_core elbi iatu conf"
  reg = <0x1c00000 0x3000 0x1c06000 0x2000 0x60000000 0xf1d
         0x60000f20 0xa8 0x60001000 0x1000 0x60100000 0x100000>
  ranges = <0x1000000 0 0x60200000 0x60200000 0 0x100000
            0x2000000 0 0x60300000 0x60300000 0 0x3d00000>
  perst-gpio = <&tlmm 0x5e 0>; wake-gpio = <&tlmm 0x60 0>
  iommu-map = <0 0x5b 0x1c00 1 0x100 0x5b 0x1c01 1>
  msi-map = <0 0x237 0x5980 1 0x100 0x237 0x5981 1>
  qcom,phy-sequence = 246 cells = 82 × {offset,value,delay}
  qcom,phy-status-offset = <0x214>; qcom,phy-status-bit = <6>
  qcom,phy-power-down-offset = <0x240>
  qcom,aux-clk-freq = <0x14>; qcom,ep-latency = <0xa>
  interrupt-names = "int_global_int int_a int_b int_c int_d"
  interrupt-map 中 int_global_int 路由到 0x8c = SPI140（GIC INTID 172）

/soc/qcom,pcie@1c00000/pcie0_rp/cnss_pci/cnss_pci_iommu_group
  qcom,iommu-msi-size = <0x1000>
  qcom,iommu-dma-addr-pool = <0xa0000000 0x10000000>
  qcom,iommu-pagetable = "coherent"

/soc/mhi_qrtr_cnss
  compatible = "qcom,qrtr-mhi"; qcom,dev-id = <0x1103>

/reserved-memory/cnss_wlan_region
  compatible = "shared-dma-pool"; size = <0x2000000>   # 32 MiB
```

设备侧 `/proc/iomem` 进一步确认 BAR0：

```text
60200000-63ffffff : qcom,pcie@1c00000
  60200000-603fffff : PCI Bus 0000:01
    60200000-603fffff : 0000:01:00.0
      60200000-603fffff : cnss
```

来源：`E:/k60-work/reports/live-6033dbec-iomem.utf8.txt:279-282`（同内容 UTF-16 原件 `live-6033dbec-iomem.txt:279-282`）。这证明 `0000:01:00.0` 的 BAR0 为 `0x60200000`、长度 2 MiB，与 Pong 配置一致。

### 2.2 差异表

| 项目 | Pong main（22H374） | K60（mondrian / live 6033dbec） | 结论与来源 |
|---|---|---|---|
| SoC / 平台 | SM8475 / cape；Pong DTS 由 live Android DT 生成 | SM8475 / cape（`board.toml:5`） | 同 SoC；Pong 的 A730/QCA6490/TFA9873/Goodix 与 K60 同款或同族（`docs/audits/PONG-FEASIBILITY.md:31-33`） |
| PCIe 控制器 | `/soc/qcom,pcie@1c00000`，`qcom,pci-msm`，`cell-index=0`，六窗口 | 同路径、同 compatible、同 `cell-index=0`，六窗口逐项相同 | 相同；K60 FDT `reg/reg-names` vs `pong:configs/pong-wifi-sm8475.json:26-51` |
| PCIe 六窗口 | parf `0x1c00000`/`0x3000`；phy `0x1c06000`/`0x2000`；dm_core `0x60000000`/`0xf1d`；elbi `0x60000f20`/`0xa8`；iatu `0x60001000`/`0x1000`；conf `0x60100000`/`0x100000` | 完全相同 | 逐值比对：K60 FDT `reg = <0x1c00000 0x3000 ...>` vs Pong 配置 `:26-51` |
| BAR0 基址 | `0x60200000`（1612709888） | `0x60200000`（`/proc/iomem` 60200000-603fffff） | 相同；`pong:configs/pong-wifi-sm8475.json:11-13`；`live-6033dbec-iomem.utf8.txt:279-282` |
| BAR0 大小 | `0x200000`（2 MiB） | 2 MiB（60200000-603fffff 含 0x200000 字节） | 相同；同上 |
| PCI vendor/device | `0x17CB:0x1103` | `qcom,dev-id = <0x1103>`（device 实证）；vendor 未在 FDT 出现 | device 相同；vendor 0x17CB 是 Qualcomm 分配与 Pong 同端点，K60 PCI 配置空间未实读（未核实） |
| 子设备 ID（subsystem device） | `0x0108`（264） | **未核实**（FDT/`/proc/iomem` 不含 subsystem ID） | Pong：`pong:configs/pong-wifi-sm8475.json:9`；`pong:PongWifiPci.cpp:117` 硬校验 `0x010817cb`；K60 需在 Android 侧读 `/sys/bus/pci/devices/0000:01:00.0/subsystem_device` |
| revision | `1` | **未核实** | Pong `:10`；K60 未采集 |
| cnss 节点 | `/soc/qcom,cnss-qca6490@b0000000`；`use-nv-mac` 存在 → `nv_mac_required=true` | 同路径；`reg = <0xb0000000 0x10000>`、`reg-names="smmu_iova_ipa"`、`qcom,wlan-rc-num=<0>`；**无 `use-nv-mac`**；有 `qcom,wlan`、`qcom,wlan-cbc-enabled`、`use-pm-domain`、`cnss-enable-self-recovery`、`qcom,bus-bw-cfg` | 路径相同；属性差异见 K60 FDT；`pong:configs/pong-wifi-sm8475.json:20`、`:734`。K60 的 MAC 来源未核实（可能由固件/QMI 或本地生成） |
| cnss WLAN 保留内存 | Pong profile 未记录 | `/reserved-memory/cnss_wlan_region` 32 MiB；`pcie0_rp/cnss_pci` 的 `memory-region` 指向它 | K60 FDT 实证；Pong 对应值未核实 |
| GPIO | WLAN_EN 80、BT_EN 81、SW_CTRL 82、XO_CLK 204、PERST 94、CLKREQ 95、WAKE 96 | 完全相同 | K60 FDT 属性 `wlan-en-gpio/qcom,bt-en-gpio/qcom,sw-ctrl-gpio/qcom,xo-clk-gpio/perst-gpio/wake-gpio`；pinctrl：GPIO80 `gpio`、GPIO95 `pcie0_clkreqn`、GPIO94/96 `gpio`；Pong `:52-59`、`:574` |
| 82 项 PHY 序列 | `phy_sequence` 82 项 | 完全相同（逐 cell 比较 `identical: True`） | K60 FDT `qcom,phy-sequence` 246 cells；Pong `:122-533`；本次比较脚本输出 |
| PHY 参数 | status 0x214/bit6、power-down 0x240、aux 20 MHz、ep-latency 10 ms | 完全相同 | K60 FDT `qcom,phy-status-offset/bit`、`qcom,phy-power-down-offset`、`qcom,aux-clk-freq`、`qcom,ep-latency`；Pong `:534-535`、`:553`、`:571-572` |
| 模拟 LDO | `vreg-1p8`→`ldoc10` 1200000 µV；`vreg-0p9`→`ldob5` 880000 µV | `qcom,vreg-1p8-voltage-level = <0x124f80 0x124f80 0x4650>`（1.2 V）；`vreg-0p9 = <0xd6d80 0xd6d80 0x125c0>`（0.88 V） | 数值相同；K60 FDT + Pong `:536-547` |
| 数字供电轨 | 6 条 WLAN 专轨 + `vdd-wlan-ipa`（smpe3/pmr735a_s3，2200000 µV） | 6 条 WLAN 专轨的 min/max 值与 Pong 完全相同；**没有 `vdd-wlan-ipa-supply`，只有 `qcom,vreg_ipa = "s3e"`** | 6 条：K60 FDT `qcom,vdd-wlan-*-config`；Pong `:606-733`。IPA 轨：K60 以字符串声明，Pong 是独立 rail；K60 是否需 `smpe3` 投票及物理 PPID **未核实** |
| 供电轨物理身份（SPMI slave/peripheral/type/subtype） | 完整：aon S4/158/1c/0e、dig S1/185/3/0a、io S1/182/3/0a、rfa1 S2/155/3/0a、rfa2 S1/188/3/0a、ipa S4/161/3/0a | **未核实**；K60 FDT 只给 PMIC regulator 节点名（pmr735a_s2 等），不给 SPMI PPID/type/subtype | Pong `:618-732`；K60 需 PMIC SPMI observer 或 regmap 取证后才能填 `physical` |
| PCIe power domain | `gdsc@17b004` control `0x17b004`、collapse vote `0x162128` bit0 | `/soc/qcom,gdsc@17b004` `reg=<0x17b004 4>`、`qcom,collapse-vote=<&syscon@162128 0>` | 完全相同；K60 FDT；Pong `:548-553` |
| `max-clock-frequency-hz` | 15 项：`[3]=19200000`、`[11]=100000000` | 15 项：`[2]=0x124f800`（19.2 MHz）、`[10]=0x5f5e100`（100 MHz） | **不同索引**；K60 FDT 属性；Pong `:554-569`。Pong 的 `build-pong-wifi-native.py:55-56` 硬断言 `[11]==100000000`，直接套用会失败 |
| `qcom,bw-scale` / interconnect | Pong 代码用 cmd-db `SN7` 带宽投票；profile 未记录 `qcom,bw-scale` | K60 FDT 有 `qcom,bw-scale`，并有 `/soc/interconnect@16c0000`（`qcom,waipio-pcie_anoc`） | K60 FDT 实证；K60 cmd-db `SN7` 是否存在 **未核实**（`PongWifiPlatform.cpp` 的 `bcmVote("SN7")` 会硬失败） |
| SID / IOVA / MSI | iommu-map `0,93,0x1c00,1,0x100,93,0x1c01,1`；IOVA `0xA0000000`/256 MiB；MSI 4096 B；SPI140 | `iommu-map = <0 0x5b 0x1c00 1 0x100 0x5b 0x1c01 1>`；`qcom,iommu-dma-addr-pool=<0xa0000000 0x10000000>`；`qcom,iommu-msi-size=<0x1000>`；`interrupt-map` int_global_int=SPI140 | 相同（phandle 数值不同，SID/IOVA/SPI 相同）；K60 FDT；Pong `:112-121`、`:580-604` |
| 目标链路速度 | `target_link_speed=2`（Gen2 x1，Pong REC CNSS 日志） | **未核实** | Pong `:575-576`；K60 需上机读 LTSSM/训练结果 |
| 固件路径 | device `/mnt/pong-wifi-firmware/image/qca6490`；runtime `/pong/firmware/qca6490` | **未核实**（FDT 无 firmware-name；FEATURES 报告明确未核实） | Pong `:736-737`；`D:/Android/k60-ios/deliverables/FEATURES-DRIVERS-RESEARCH-2026-10-31.md:90`、`:269` |
| 固件文件清单 | `amss.bin`、`amss20.bin`、`m3.bin`、`regdb.bin`、`bdwlan*/bdwlang*` | **未核实**；需从 K60 modem/fsg/vendor 分区实列 | Pong `:738-744`；`pong:proprietary-files.txt:1-8`；K60 未列 |
| `use-nv-mac` / MAC | `nv_mac_required=true`；`PongWifiPlatform.cpp:494-518` 在 `wlan_mac.bin` 缺失时用安装 UUID 生成 `Intf0MacAddress=02...` | K60 FDT 无 `use-nv-mac`；实际 MAC 来源 **未核实** | K60 FDT；Pong `:734`、`PongWifiPlatform.cpp:494-518` |
| PCIe 参考时钟/PHY 版本 | `qcom,pcie-phy-ver` 未记录 | `qcom,pcie-phy-ver = 0x63` | 仅 K60 实证；Pong 是否同为 0x63 **未核实**（PHY 表本身相同） |

**差异结论（按影响排序）**：

1. `max-clock-frequency-hz` 索引偏移是**构建级硬失败**：Pong 脚本 `build-pong-wifi-native.py:55-56` 检查 `[11] == 100000000`，K60 在 `[10]`。K60 profile 必须先按实际数组重算，并确认 `pci-msm` 的 refgen 时钟索引语义。
2. `PongWifiPci.cpp:117` 硬校验 subsystem device `0x0108`；K60 如果不同，端点身份检查会拒绝。必须先读 K60 PCI 配置空间，或把身份检查参数化。
3. K60 没有 `vdd-wlan-ipa-supply`，只有 `qcom,vreg_ipa="s3e"`；Pong 的 `kPongWifiRails` 会按 7 条轨逐条查 cmd-db，K60 若照抄会多查一条不存在的 rail。K60 profile 应只生成 6 条已证实轨，IPA 作为可选分支（未核实）。
4. `use-nv-mac` 缺失使 MAC 策略必须显式决定；不能直接假设 `wlan_mac.bin` 存在。
5. `qcom,bw-scale`/`SN7`、目标链路速度、固件路径、子设备 ID、供电轨物理身份均需上机取证，不能从 Pong profile 直接抄。

---

## 3. iOS 16.6.1 与 iPadOS 18 的 IOKit / IO80211 接口差异点

本节只列能从本机材料证明的差异；不能证明的明确写“未核实”。

| 接口点 | iPadOS 18 / 22H374（Pong main） | iOS 16.6.1 / 20G81（K60 目标） | 证据与判断 |
|---|---|---|---|
| IO80211Family 存在性 | Pong 运行时的 22H374 IO80211 库从接口节点绑定 `IO80211Controller`/`IO80211Interface`；PongWifi 自己定义同名 stub 类发布服务 | 20G81 `kernelcache.decompressed` 含 `IO80211Family`、`IO80211Interface`（strings offset `0x9d28ae`）、`IO80211Controller`（`0x9bbef0`）；K60 profile 的 prelink `roots` **不含** `IO80211Family`/`AppleBCMWLAN` | 20G81 kernelcache 字符串扫描（本次）；`E:/hackios/UniXNU/profiles/os/ipados-16.6.1-20G81/profile.toml:33`。结论：16.6.1 也有 IO80211 类，但 K60 不 prelink 它；Pong 的 stub 方式仍可作为起点，**类继承/重复注册需按 20G81 头文件重新核对（未核实）** |
| 接口 user client | 22H374 IO80211 在接口节点打开 **type 0** 用户客户端；`Pong80211UserClient` selector 0 处理 `Apple80211MethodRequest`（`0x3c30` envelope：`command`、`length`、`0x3c00` payload、`0x28` request），selector 1 表示标准 ioctl 转交，selector 7 表示未实现快速路径 | 20G81 kernelcache 有 `IO80211APIUserClient`（`0xf6e2b9`）、`IO80211AsyncEventUserClient`（`0xf5dc01`）、`IO80211AsyncUserClientParameters`（`0xf6e1a3`）；类实现字符串含 `_runDriverCommandHelper`、`_runLargeBufferCommandHelper`、`ClientMemoryForType`。**selector 编号、envelope 大小、entitlement 是否与 22H374 相同：未核实** | 22H374：`pong:README.md:88`、`pong:PongWifiNet.cpp:500-511`、`:541-612`；20G81：本次 kernelcache strings 扫描（偏移见左）。结论：16.6.1 **有同族 API user client**，但必须对 20G81 的 IO80211 二进制做 selector/ABI 审计后再决定是否复用 `Pong80211UserClient` |
| Apple80211 ioctl 路径 | Pong 仍保留 `SIOCSA80211=0x802869c8` / `SIOCGA80211=0xc02869c9`、40 字节 `apple80211req` | 20G81 IO80211 同样有 `apple80211_ioctl_set_handlers.cpp`（strings `0xf4fb25`）与 `Apple80211` 相关串；结构大小是否仍为 40 字节 **未核实** | 22H374：`pong:PongWifiNet.cpp:44-49`、`:561-590`；20G81：kernelcache strings。Pong 的 `apple80211()` 走 `if_ioctl` 的 socket 路径，理论上 16.6.1 可先走该路径 |
| association 请求布局 | 22H374 `__performAssociation` 发 `0x384`（900）字节：SSID 长度 `0x10`、SSID `0x14`、BSSID `0x34`、key length `0x40`、key type `0x44`、key `0x4c`；认证上下层为 32 位 | 旧 `0x250`（592）布局：认证上下层为 16 位；PongWifi 的 `struct assoc_request` 明确注释 `592 bytes`；`services111` 明确说旧解析会把 auth 字段读成 SSID 长度。**16.6.1 是否实际走 0x250：未核实** | `pong:migration/ipados18/services111-association-metal-route.md:16-19`；`pong:PongWifiNet.cpp:78-100`（`static_assert(sizeof(assoc_request)==592)`）；PongWifiNet 已按 `req_len==sizeof(assoc_request24)` 选择布局（`:353`），16.6.1 可复用旧布局分支 |
| scan result / channels / link event | `scan_result` 1164 B（`ssid_length` 0x60、`age_ms` 0x84、`elements` 0x8c）；`channels_list` 4824 B；`link_event` 32 B | 20G81 未给出同结构静态布局；sheng（24A446）也使用 1164/4824/32，说明这类 Apple80211 结构跨代较稳定，但 **16.6.1 精确值未核实** | `pong:PongWifiNet.cpp:71-100`；`E:/hackios/UniXNU-sheng/package/WifiNet.cpp:83-113`（24A446 同样 1164/4824/32） |
| IO80211 接口属性 | `IOBuiltin`、`IOPrimaryInterface`、`IO80211InterfaceRole=Infrastructure`、`IOUserClientClass=Pong80211UserClient` | 20G81 IO80211Interface 类存在；这些属性是否足够让 16.6.1 的 `wifid`/InterfaceNamer 绑定 **未核实** | 22H374：`pong:PongWifiNet.cpp:679-695`；20G81：kernelcache strings |
| wifid / XPC 接线 | 22H374 `wifid` 作业需要在原有 `com.apple.wifid` job 里补 `com.apple.wifi.manager` Mach service；否则 WiFiManagerCreate 失败 | 16.6.1 `wifid`/MobileWiFi 的 Mach service 名、job 结构、`IO80211` 用户态框架 **未核实**（20G81 IPSW 未做同类审计） | 22H374：`pong:migration/ipados18/services93-wifi-checkin.md:9`；16.6.1：未核实。不要把 services93 的 22H374 plist 改动直接套到 16.6.1 |
| 构建 ABI / target | PongWifi 脚本硬编码 `-target arm64-apple-ios18.0`；使用 Darwin24 IO80211 布局 | K60 工具链目标 `arm64-apple-ios16.0`（`scripts/build-pong-platform-macos.py:33`）；Darwin 22 头文件 | 必须把所有 PongWifi 构建脚本改为 `arm64-apple-ios16.0`，并对 20G81 Kernel.framework 重新编译；**16.6.1 API 兼容性未核实** |
| 类注册 API | Pong 使用 `OSMetaClass::preModLoad(g_kernel_kmod_info.name)` / `postModLoad` 延迟注册 `PongWifiNet` 类 | XNU 8796 上是否存在同签名 `preModLoad` **未核实**；K60 当前没有同类延迟注册代码 | `pong:PongWifiPlatform.cpp:580-582`；编译时用 8796 头文件验证 |

**结论**：16.6.1 与 22H374 的最大差异不在“有没有 IO80211”，而在**用户客户端 selector 协议、association 请求布局、以及 wifid 的用户态接线**。`PongWifiNet.cpp` 已经为 0x250/0x384 两种 association 布局留了分支，这是移植的有利条件；但 `Pong80211UserClient` 的 0x3c30 envelope 和 selector 0/1/7 只对 22H374 有实证，必须在 20G81 上重新审计后才能照搬。

---

## 4. 移植步骤（按依赖顺序）

### 4.0 前置核对（不写代码，先取证）

1. 记录 K60 当前构建基线：`git -C E:/hackios/UniXNU-mondrian status -sb`、`git rev-parse HEAD`、`board.toml` 的 `dram_size`/`owned_memory_size`/`kernel_args`（`board.toml:98,125,162`）。
2. 在 Android 侧只读读取 K60 PCI 端点身份和 BAR，填掉“未核实”：
   ```sh
   adb -s 6033dbec shell 'cat /sys/bus/pci/devices/0000:01:00.0/vendor'
   adb -s 6033dbec shell 'cat /sys/bus/pci/devices/0000:01:00.0/device'
   adb -s 6033dbec shell 'cat /sys/bus/pci/devices/0000:01:00.0/subsystem_vendor'
   adb -s 6033dbec shell 'cat /sys/bus/pci/devices/0000:01:00.0/subsystem_device'
   adb -s 6033dbec shell 'cat /sys/bus/pci/devices/0000:01:00.0/revision'
   adb -s 6033dbec shell 'cat /sys/bus/pci/devices/0000:01:00.0/resource'
   ```
   这是 `prepare-pong-wifi.py:156-165` 的同一读取方式，只读、不写分区。
3. 在 Android 侧列 modem/fsg/vendor 中的固件候选路径（只列目录，不复制）：
   ```sh
   adb -s 6033dbec shell 'ls -l /dev/block/by-name/modem*'
   adb -s 6033dbec shell 'find /vendor/firmware -maxdepth 3 -iname "*qca*" -o -iname "*bdwlan*" 2>/dev/null'
   ```
   若 `modem<slot>` 可挂载，必须按 `prepare-pong-wifi.py:178-186` 的只读 vfat 方式挂载并检查 `image/qca6490`。
4. 确认 K60 `board.toml` 的 `kernel_args` 当前不包含 `pong_wifi=1`（`board.toml:125`）；WiFi 首轮应保持关闭，先证明内核/启动无回归。

### 4.1 阶段一：拉子模块与源码

| 步骤 | 操作 | 验收 |
|---|---|---|
| 1.1 | 在 `E:/hackios/UniXNU-mondrian` 添加 `drivers/PongWifi` 子模块：URL `https://github.com/Chengdong-Yu/pong-wifi.git`，pin `d2e33ca6e0f6a3b3e7881a45ab36c6920e7afb07` | `git submodule status drivers/PongWifi` 显示该 commit；`drivers/PongWifi/PongWifiPlatform.cpp` 存在 |
| 1.2 | 添加 `drivers/PongPower` 子模块：URL `https://github.com/Chengdong-Yu/pong-power.git`，pin `c37179ed12ba7f981b2b088aea482b969085eb84` | `drivers/PongPower/PongPlatformResources.{h,cpp}` 存在；`QcomRpmh.h` 来自 `sheng_source/package`（`pong:configs/pong-native-sources.toml:4-8`） |
| 1.3 | 确认 `drivers/PongAdreno/ArmSmmu4K` 与 Pong main 的 `3e8ffa2...` 版本对齐。K60 当前 `PongAdreno` 是普通树（`git ls-tree HEAD drivers/PongAdreno` 为 `040000 tree`），不是 submodule；K60 版本缺少 `ArmSmmu4KMmio.{c,h}`。若 PongWifi 编译依赖新 API，先同步/抽取 `ArmSmmu4K` 或建立共享 `libPongSmmu4K.a` | `ArmSmmu4KProgram.h` 中 `ArmSmmu4KBuild`、`ArmSmmu4KProgramDisabledContext` 可用；`nm` 无重复符号 |
| 1.4 | 确认 `drivers/NativeUfs/SmmuTakeover.h` 的 `planUfsSmmu()` 可用于 WiFi 的 SID `0x1c01`；同时补 `PongUfsTransport.cpp` 的 `gWifiUfsReady`/`pong_ufs_ready()`（K60 当前没有，Pong 在 `pong:drivers/NativeUfs/PongUfsTransport.cpp:49,225,620` 有） | `pong_ufs_ready()` 链接可解析；`transport ready` 时置位 |
| 1.5 | 准备公共源码输入：`wifi_shared`（Ath12kWifi `f6bf561...`）、`wifi_linux`（Linux v7.0.14 `458c6079...`）、`sheng_source`（`08cde20...`，至少 `QcomRpmh.c/h`） | 对应目录存在 `include/nw_abi.h`、`drivers/net/wireless/ath/ath11k/pci.c`、`package/QcomRpmh.c` |

### 4.2 阶段二：改 K60 板级值（新建 `configs/mondrian-wifi-sm8475.json`）

以 `pong:configs/pong-wifi-sm8475.json` 为模板，逐项替换：

| 字段 | 改为 K60 值 | 依据 |
|---|---|---|
| `board` | `"mondrian"` | `board.toml:4` |
| `soc` | `"SM8475"` | `board.toml:5` |
| `pci.subsystem_vendor` / `subsystem_device` | 用 §4.0 读到的实际值；未读到就不填 | 防止 `PongWifiPci.cpp:117` 的 `0x0108` 误拒 |
| `pci.revision` | 实际值 | §4.0 |
| `pcie.max_clock_frequency_hz` | 按 K60 FDT 的实际 15 项写；当前是 `[2]=0x124f800`、`[10]=0x5f5e100` | K60 FDT；Pong `:554-569` |
| `rails` | 6 条 K60 FDT 专轨；`vdd-wlan-ipa` 暂不生成，除非 PMIC 取证证明 `smpe3` 可用 | K60 FDT；`PongWifiPlatform.cpp:163` 的 `kPongWifiRails` 会逐条查 cmd-db |
| `pcie.gpio` / `regions` / `phy_sequence` / `power_domain` / `sid_map` / `dma` / `msi` | 全部按 K60 FDT 的已证实值；PHY 表可直接沿用 Pong（逐 cell 相同） | K60 FDT；Pong `:26-121`、`:122-533`、`:548-604` |
| `target_link_speed` | 先写 `2`（Pong 先验），上机 LTSSM 确认后修正 | Pong `:575-576`；K60 未核实 |
| `nv_mac_required` | 按 K60 实测决定；若 K60 无 `use-nv-mac`，不要写死 true | K60 FDT；Pong `:734` |
| `firmware.device_path` / `runtime_path` / `required` | 用 §4.0 实际路径和 §4.3 inventory 填；未核实前不写“已确认” | K60 FDT 无 firmware-name；`FEATURES...:90,269` |

验收：`configs/mondrian-wifi-sm8475.json` 能通过一个与 `build-pong-wifi-native.py:55-56` 类似的校验器；所有 K60 值都有 `FDT` 或 `device` 出处；没有从 Pong 直接抄来的未核实字段。

### 4.3 阶段三：固件提取

以 Pong 的 `prepare-pong-wifi.py` 为蓝本写 K60 版（只读、不写分区）：

| 步骤 | 操作 | 验收 |
|---|---|---|
| 3.1 | 确认 REC：`adb -s 6033dbec get-state` 为 `recovery`；`ro.product.device` 必须为 `mondrian`（Pong 版检查 `pong`，K60 改为 `mondrian`，见 `pong:prepare-pong-wifi.py:150-157`） | 产品名、槽位 `_a`/`_b` 正确 |
| 3.2 | 确定 modem 分区：`/dev/block/by-name/modem<slot>`；只读挂载 `-t vfat -o ro` 到临时目录（`pong:prepare-pong-wifi.py:178-186`） | `mount` 只读；不写任何分区 |
| 3.3 | `adb pull` `image/qca6490` 到本地 `out/.../qca6490/`；生成 `local-inputs.json`（`firmware_directory`、`files`、`source.product/slot/partition/capture`） | `local-inputs.json` 与 `prepare-pong-wifi.py:188-201` 同结构 |
| 3.4 | 固件 inventory 至少包含以下文件名/模式；按 QMI chip/board ID 选 BDF，不按 PCI revision 选 | 见下方清单 |
| 3.5 | 构建时校验 `local-inputs.json`：product=mondrian、capture=`REC read-only active modem`、slot `_a/_b`、partition 匹配（Pong `build-pong-wifi-native.py:67-77` 的校验逻辑） | 构建脚本拒绝任何非本机/非活动槽来源 |

**需要的 ath11k 文件名**（Pong 的 `firmware.required` + `proprietary-files.txt` + `build-pong-wifi-native.py:80-83` 的正则）：

```text
amss.bin          # 基础 AMSS 镜像
amss20.bin        # 硬件 major=2 时实际加载（Pong services81 实测）
m3.bin            # M3 固件
regdb.bin         # 监管数据库
bdwlan*.elf       # 板级数据（如 bdwlan.elf）
bdwlang*.elf      # QCA6490 常见 bdwlang.elf
bdwlan*.eXX       # 变体板级数据（XX 为十六进制）
bdwlang*.eXX      # 变体
wlan_mac.bin      # 可选；Pong 在缺失时用本地安装 UUID 生成 02:xx 本地管理地址
```

**Pong 实测的加载例子**（作为 K60 对照预期）：`services81` 的 QMI 返回 chip `0x12`、board `0xff`、SoC `0x400c1211`，加载 `amss20.bin`、`bdwlang.elf`、`m3.bin`、`regdb.bin`，注册 102 个通道（`pong:migration/ipados18/services81-wifi-firmware.md:5-8`）。K60 若 chip/board ID 不同，BDF 文件可能变成 `bdwlan.eXX` 或 `bdwlan.elf`，由 `ath11k` core 的 `pong_bdf` 逻辑按 QMI ID 选择（`pong:build-pong-ath11k.py:61-72`）。

### 4.4 阶段四：构建接入

按依赖顺序：

| 步骤 | 改动 | 验收 |
|---|---|---|
| 4.1 | 新建 `scripts/prepare-k60-wifi.py`：复制 `prepare-pong-wifi.py` 的 `fdt_nodes/cells/text/describe`，把 product 检查改为 `mondrian`，把 `configs/pong-wifi-sm8475.json` 路径改为 `configs/mondrian-wifi-sm8475.json`，保留 `--dtb`/`--firmware-dir` 离线入口 | 可在无设备时用 `--dtb E:/k60-work/reports/live-6033dbec-fdt.dtb --firmware-dir ...` 生成 profile |
| 4.2 | 新建 `scripts/build-k60-ath11k.py`：从 `build-pong-ath11k.py` 复制；把 `-target arm64-apple-ios18.0` 改为 `arm64-apple-ios16.0`；`ROOT` 指向 K60 设备仓；`--shared` 指向 Ath12kWifi；`--linux` 指向 Linux v7.0.14；输出 `build/k60-ath11k/libPongAth11k.a` | 编译零错误；`nm -u` 只有允许的 libc/随机数符号（Pong 的 allowed 集见 `build-pong-ath11k.py:223-225`） |
| 4.3 | 新建 `scripts/build-k60-wifi-native.py`：从 `build-pong-wifi-native.py` 复制；`profile` 改 K60；`-target` 改 `ios16.0`；保留 `PongWifiInputs.h` 生成、PWF2 打包、`PongWifiNet` 延迟注册逻辑 | 生成 `build/k60-wifi/PongWifiInputs.h`、`PongWifiFirmware.bin`、`libPongWifiNative.a` |
| 4.4 | 新建 `scripts/build-k60-wifi-resources.py`（最小）：编译 `drivers/PongPower/PongPlatformResources.cpp` + `sheng_source/package/QcomRpmh.c`，输出 `build/k60-wifi-resources/libPongWifiPlatformResources.a`；不要编译 PongPower 的音频/ADSP 全套 | `pong_rpmh_init`、`pong_rpmh_vote`、`pong_smmu_lease_lock/unlock` 可解析 |
| 4.5 | 共享 SMMU：将 K60 `drivers/PongAdreno/ArmSmmu4K` 抽成 `libPongSmmu4K.a`（Pong 的 `build-pong-smmu4k.py` 清单：`ArmSmmu4K`, `Context`, `Program`, `Streams`, `Audit`, `Live`, `TableMemory`, `Mmio`）；或暂时由 `libPongAdrenoPlatform.a` 提供，但要在报告中记录“WiFi 链接依赖 GPU archive” | `ArmSmmu4KProgramDisabledContext`/`ArmSmmu4KBuild` 等符号唯一来源；不重复 |
| 4.6 | `configs/mondrian_defconfig` 增加 `CONFIG_XNU_PONG_WIFI=y`（参考 `pong:configs/pong_ipados18_defconfig:61`）；若采用共享 SMMU，另加 `CONFIG_XNU_PONG_SMMU4K=y` 或等价开关 | `unixnu build kernel` 能读到开关 |
| 4.7 | `scripts/build-pong-platform-macos.py` 增加 `-DXNU_PONG_WIFI=` 编译定义（参考 `pong:build-pong-platform-macos.py:43-44`） | `ArmDTPlatform.cpp` 的 `#if XNU_PONG_WIFI` 生效 |
| 4.8 | `drivers/ArmDTPlatform/ArmDTPlatform.cpp` 增加 `extern "C" void pong_wifi_start_optional(void);`，并在 `pong_cpu_start(this)` 之后调用（Pong 的顺序：`pong_power_start_optional()` → `pong_wifi_start_optional()` → `pong_adreno_start_optional()`，`pong:drivers/ArmDTPlatform/ArmDTPlatform.cpp:243-254`） | 启动日志出现 `PongWifi` 线程；`pong_wifi=0` 时不出现 |
| 4.9 | `scripts/build-xnu-4k-baseline.sh` 增加 WiFi archive 的构建与 `-Wl,-force_load`（参考 `pong:build-xnu-ipados18.sh:260-266`、`:1016-1020`）；把 `libPongWifiNative.a`、`libPongWifiPlatformResources.a`、`libPongSmmu4K.a` 加入 `PLATFORM_ARCHIVES` | 链接产物含 `_pong_wifi_start_optional`、`_nw_wifi_start`；`nm` 无未解析 |
| 4.10 | `board.toml` 的 `[payload] kernel_args` 增加 `pong_wifi=1`（首轮验证后才加；`board.toml:125`） | 启动参数出现在 boot_args；可用 `pong_wifi=0` 快速回退 |

构建产物验收：

```text
build/k60-ath11k/libPongAth11k.a
build/k60-wifi/libPongWifiNative.a
build/k60-wifi-resources/libPongWifiPlatformResources.a
build/pong-smmu4k/libPongSmmu4K.a
```

### 4.5 阶段五：上机判据日志

按阶段开 `pong_wifi=1`，每阶段只读取日志，不改代码。以下日志字符串均来自 PongWifi 源码，K60 首轮可直接 grep：

| 判据 | 期望日志（K60 上应出现） | 说明 |
|---|---|---|
| L0 构建 | `libPongAth11k.a`、`libPongWifiNative.a` 存在；`nm -u` 无 `pong_ath11k_*`/`nw_wifi_*` 缺失 | 构建成功 ≠ 硬件成功 |
| L1 电源 | `PongWifi: rail vdd-wlan-aon physical ready PPID=...` 至 6 条轨全部出现；`SM8475 WLAN rail requests acknowledged` | 任一条 `not ready` 即停；重点看 PPID/type/subtype 是否与 K60 实测一致（`PongWifiPlatform.cpp:116-138`） |
| L2 PCIe | `PCIe0 cold start; power and bus clocks precede host MMIO`；`QCA6490 PCIe0 link and BAR established, bus master held off`；`PongWifi: cold REFCLK PHY_CTRL=...` | 没有 link 日志则查 GDSC/clock/PHY 表；`PongWifiPlatform.cpp:185,245,351` |
| L3 SMMU/DMA | `PongWifi: 64MiB wired DMA mapped from N spans, M native4K table pages`；`exclusive SID1c01 native4K DMA and retained MSI landing page established` | 失败信息：`WiFi DMA page outside SM8475 output range`、`WiFi native4K page tables failed`（`:441,470`） |
| L4 MSI | `DesignWare MSI receiver armed on Pong PCIe0 SPI140`；`QCA6490 MSI delivered by GIC` | 没有 MSI 则查 `interrupt-map`/SPI140/GIC（`:570,577`） |
| L5 固件 | `Pong: actual QMI board firmware bdwlang.elf`（或实际 BDF）；`PongWifi: firmware amss20.bin bytes=...`；`Pong: installed board station identity before WMI vdev creation` | 固件文件缺失或 MHI RDDM 时会出现 `Pong QCA6490 firmware stopped: MHI reason=...`（`PongAth11k.c:50-60`） |
| L6 station/scan | `QCA6490 station ready; starting actual scan`；`wifi-net: scan result N: ... MHz, ... dBm, SSID` | 102 个硬件 channel、至少 1 个 BSS；`PongWifiPlatform.cpp:582`、`PongWifiNet.cpp` scan 日志 |
| L7 关联/DHCP | `wifi-net: join finished: module result 0`；`wifi-net: dhcp in type 5 ...`；`wifi-net: en0 address 192.168...` | 需要 K60 OS 窗口/launchd 已修复并运行到 wifid；否则只能到 L6 |
| L8 持续流量 | `wifi-net: en0 address ... packets in N out M` 中 N/M 持续增长；10 分钟无 `MHI reason` | 只有 L8 才算“WiFi 可用”，不是构建或扫描成功 |

**失败定位矩阵**：

| 现象 | 首查 | 处理 |
|---|---|---|
| `rail ... no observer channel` / `not ready` | K60 PMIC SPMI PPID/type/subtype；RSC `0x17a20000` 是否可读 | 先做只读 RSC/PMIC 探针；不要盲目改电压 |
| `PCIe0 GDSC off` / `clock remains halted` | GCC `0x7b004`/`0x7b020-0x7b03c`；`qcom,bw-scale`；GPIO94/95/96/204 | 对照 Pong `PongWifiPlatform.cpp:185-260` 的冷启动顺序；K60 缺 `gdsc` 状态时不继续 MMIO |
| `QCA6490 endpoint identity mismatch` | K60 subsystem device 是否 0x0108；vendor/device 是否 0x17cb/0x1103 | 用 §4.0 实读值填入 profile；或参数化 `PongWifiPci.cpp:117` 的检查（实施阶段） |
| `WiFi DMA page outside SM8475 output range` | XNU 可用内存页是否 < 36-bit；`pmap_valid_page` | 检查 K60 内存窗口/高端地址配置；不要请求 128 MiB 连续物理区 |
| `MHI reason` / `RDDM` | `amss20.bin` vs `amss.bin` 选择；QMI chip/board ID；BDF 文件 | 用 Pong services81 的 chip/board 日志对照；换正确固件变体 |
| 无 `QCA6490 station ready` | `nw_wifi_start` 返回值、`nw_wifi_step` 阶段、MAC 是否有效 | 先确认 MHI/QMI 完成、102 通道注册；再查 `wlan_mac.bin`/MAC |
| 有 station 无 `en0` / wifid 不弹设置 | 16.6.1 `Pong80211UserClient` selector ABI；`com.apple.wifid` job；InterfaceNamer | 按 §3 先审 20G81 IO80211；再查 wifid/MobileWiFi |

---

## 5. 风险与前置条件

### 5.1 是否依赖 GPU / 触摸 / 内存窗口

| 依赖 | 结论 | 依据与影响 |
|---|---|---|
| GPU 渲染 | **不依赖 GPU 渲染**；但当前 K60 构建用 `libPongAdrenoPlatform.a` 顺带提供 `ArmSmmu4K` 符号（`scripts/build-pong-adreno-platform.py:44-46`、`scripts/build-xnu-4k-baseline.sh:982-986`）。若关闭 `CONFIG_XNU_PONG_ADRENO_PLATFORM`，WiFi 会因为缺 `ArmSmmu4KProgramDisabledContext` 等符号而链接失败 | 建议把 `ArmSmmu4K` 抽成独立 `libPongSmmu4K.a`（Pong 的 `build-pong-smmu4k.py` 做法）；这样 WiFi 不依赖 GPU 开关，只共享硬件 SMMU 驱动 |
| 触摸 | **不依赖**。触摸缺失只影响 Settings 交互，不影响内核 worker 的电源/PCIe/MHI/扫描路径 | K60 当前触摸未通（`docs/state/STATE-2026-11-07.md:88-94`）；首轮可用 `pong_wifi=1` 自动扫描验证，不必等触摸 |
| 内存窗口 | **不依赖 7 GiB 高窗口**；PongWifi 只需要 `ArenaBytes=64 MiB` 的可回收 wired 页 + `TableBytes=512 KiB` 表 + 4 KiB MSI page（`PongWifiPlatform.cpp:42`、`:353-376`）。K60 当前 `dram_size=0x140000000`（5 GiB arena）、`owned_memory_size=0x130000000`（4.75 GiB window，`board.toml:98,162`），余量足够。 | 但 64 MiB arena 必须是 XNU 可管理、`pmap_valid_page` 且在 36-bit 输出范围；Pong 的 `services72` 记录过“128 MiB 物理连续失败”，K60 不要重蹈（`pong:migration/ipados18/services72-wifi-dma-audio.md:7-8,14`）。若 K60 的 `owned_memory_size` 再缩小到不足 ~70 MiB 空闲页，WiFi 会 `WiFi DMA arena allocation failed` |
| UFS | **硬依赖**：`PongWifiPlatform` worker 先等 `pong_ufs_ready()` 最多 90 秒（`:555-559`），且需要 `planUfsSmmu(0x1c01,...)` 与 `pong_smmu_lease_lock()`（`:408-470`）。K60 当前 `CONFIG_XNU_NATIVE_UFS=y`（`configs/mondrian_defconfig:28`），但 NativeUfs **缺 `pong_ufs_ready`**，必须补（见 §4.1） | UFS 未就绪时日志 `UFS prerequisites absent; WiFi skipped`，不会崩溃但 WiFi 不启动；UFS/SMMU 冲突时可能 `WiFi SMMU context programming failed` |
| RSC / PMIC | **高风险硬依赖**：`PongPlatformResources.cpp:34-42` 映射 RSC `0x17a20000`，`rawVote()` 直接操作 TCS4；`PongWifiPlatform::supplies()` 对每条轨做 SPMI observer 读。K60 触摸文档记录 `0x17a00000` 读即死机，0240 头声称 `0x17a20000` drv-2 可读，0246 又说首读 TCS 死机——两者矛盾，原因未核实（`docs/state/STATE-2026-11-07.md:94`、`docs/K60-TOUCH-PARAMS.md:120,174`） | 上机前先写只读探针：只读 RSC 版本/TCS 状态，不写；若 `0x17a20000` 不可读，WiFi 的 RPMh 供电/PMC 路径不可用，需改走 Pong 的另一套 SPMI observer 或先解决 RSC。**这是 K60 WiFi 最大的板级风险之一** |
| PongPower / QcomRpmh | **硬依赖**：`PongWifiPlatform.cpp:19-20` 包含 `QcomRpmh.h` 与 `../PongPower/PongPlatformResources.h`；`pong_rpmh_init/vote`、`pong_smmu_lease_lock` 不在 K60 树中 | 按 §4.1/4.4 添加 `drivers/PongPower` 或至少 `PongPlatformResources.cpp` + `QcomRpmh.c`；不添加则编译/链接失败 |
| 构建环境 | Pong 的构建脚本是 macOS 路径（`pong_paths.py` 默认 `/Volumes/PongDev`，`build-pong-wifi-native.py` 用 `xcrun`）；K60 主线在 Linux/WSL 用 `/opt/unixnu-linux` | 需把 Pong 的 `pong_native_inputs/pong_paths` 和 `xcrun` 路径改成 K60 构建环境；**Linux 下 iOS SDK/xcrun 兼容性未核实**。建议首轮在 macOS 侧构建 `libPongAth11k.a`/`libPongWifiNative.a`，或把 Pong 的 clang 调用改成 K60 的 `xnu-host-cc`/`ld` 组合 |
| iOS 16.6.1 ABI | 最大软件未知：`Pong80211UserClient` 0x3c30/selector 0/1/7 只对 22H374 有实证；association 0x384/0x250 分支有旧布局但 16.6.1 实际请求长度未核实；`OSMetaClass::preModLoad`、`IO80211Interface` 类继承需 8796 头文件验证 | 在写 `PongWifiNet` 的 16.6.1 适配前，先做 20G81 IO80211 二进制/头文件审计（见 §3）；否则可能在“station 已起、en0 不出现/wifid 不绑定”处停住 |
| 子设备 ID / 端点身份 | `PongWifiPci.cpp:117` 硬校验 `0x010817cb`；K60 subsystem device 未核实 | §4.0 先读；若不同，实施时参数化或改校验；这是“第一行 dispatch 就失败”的风险 |
| 固件路径 / 变体 | K60 firmware 路径/文件名未核实；`amss20.bin` vs `amss.bin` 由 TCSR major 选，BDF 由 QMI chip/board ID 选 | 按 §4.3 先做只读 inventory；没有 `bdwlang.elf`/`bdwlan.eXX` 就无法过 MHI BHI，后续全部免谈 |
| OS 用户态 / launchd | K60 当前唯一硬阻断是 launchd（PID 1）SIGSEGV（`docs/state/STATE-2026-11-07.md:27-50`）；WiFi 内核侧可先跑，但 Settings/关联/DHCP 需要 OS 窗口 `apply()` 后 wifid 运行 | 把 WiFi 验证分两层：内核 L1-L6 不依赖 launchd；L7-L8 需要先按 `docs/plans/APPLY-PIPELINE.md` 修好 OS 窗口。不要因为 WiFi 日志出现就宣称系统可用 |

### 5.2 前置条件清单

1. `drivers/PongWifi` 子模块固定 `d2e33ca...`，`drivers/PongPower` 固定 `c37179e...`；否则 PongWifi 头文件与 Pong main 不匹配。
2. `PongPlatformResources.cpp` + `QcomRpmh.c` 可用；`pong_rpmh_init/vote`、`pong_smmu_lease_lock` 链接成功。
3. K60 NativeUfs 暴露 `pong_ufs_ready()`，且 UFS transport 成功置位。
4. `ArmSmmu4K` 版本与 PongWifi 的 `ArmSmmu4KProgramDisabledContext` 兼容；不重复定义。
5. K60 的 PCI 端点身份（vendor/device/subsystem/revision）已实读；BAR0 2 MiB 已在 `/proc/iomem` 核对。
6. 固件 `amss.bin`/`amss20.bin`/`m3.bin`/`regdb.bin` + 正确 BDF 已从 K60 活动槽只读提取。
7. `pong_wifi=1` 仅作为 boot-arg 开关；首轮默认关闭，失败时 `pong_wifi=0` 可回退，不影响正常启动。
8. 只做 `fastboot boot` 临时启动，不写 boot/system/vendor/modem 分区；固件只读提取。

---

## 6. 本次只出方案，不改代码

**本次任务只写这一份 `docs/plans/WIFI-PORT-PLAN.md`，未修改任何代码、补丁、构建脚本、设备树、配置文件或镜像；未运行构建、未连接/写入设备、未 push。** 文中所有命令/字段/改动均为后续实施清单；实际实施前应按 §4.0 取证和 §5.2 前置条件逐项确认。

---

## 附录 A：复现本次 K60 事实的最小命令

```sh
# 1) FDT 解析（复用 Pong prepare-pong-wifi.py 的 fdt_nodes/cells/text）
python3 - <<'PY'
import importlib.util, struct
from pathlib import Path
spec = importlib.util.spec_from_file_location('p', 'E:/hackios/UniXNU-pong/kits/PongPlatform24/build-support/merged-scripts/prepare-pong-wifi.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
nodes = m.fdt_nodes(Path('E:/k60-work/reports/live-6033dbec-fdt.dtb').read_bytes())
for path in ('/soc/qcom,cnss-qca6490@b0000000','/soc/qcom,pcie@1c00000','/soc/mhi_qrtr_cnss','/reserved-memory/cnss_wlan_region'):
    print('\n##', path)
    for k, v in nodes[path].items():
        if k in ('compatible','reg','reg-names','ranges','interrupt-map','iommu-map','msi-map','qcom,phy-sequence','qcom,phy-status-offset','qcom,phy-status-bit','qcom,phy-power-down-offset','qcom,aux-clk-freq','qcom,ep-latency'):
            print(k, '=', m.cells(nodes[path], k) if k != 'compatible' else m.text(nodes[path], k))
PY

# 2) K60 BAR0（设备侧只读文件已保存）
#    E:/k60-work/reports/live-6033dbec-iomem.utf8.txt:279-282
#    60200000-603fffff : 0000:01:00.0 / cnss

# 3) K60 PCI 身份（需用户在 Android 侧只读执行，见 §4.0）
```

---

## 附录 B：关键参考文件索引

| 路径 | 用途 |
|---|---|
| `E:/hackios/UniXNU-pong/configs/pong-wifi-sm8475.json` | Pong 板级 profile；本文 §1.4 所有行号来源 |
| `E:/hackios/UniXNU-pong/kits/PongPlatform24/build-support/merged-scripts/{prepare-pong-wifi.py,build-pong-ath11k.py,build-pong-wifi-native.py}` | Pong WiFi 三个构建入口 |
| `E:/hackios/UniXNU-pong/migration/ipados18/services69-wifi-power-pipe.md` | Pong 电源/PIPE 时钟 |
| `E:/hackios/UniXNU-pong/migration/ipados18/services72-wifi-dma-audio.md` | 128 MiB 连续 DMA 失败与 64 MiB 页式 arena |
| `E:/hackios/UniXNU-pong/migration/ipados18/services81-wifi-firmware.md` | QMI chip/board、amss20/bdwlang 实际加载、102 通道、RDDM |
| `E:/hackios/UniXNU-pong/migration/ipados18/services88-native-peripherals.md` | 22H374 type0 user client、selector 0 envelope |
| `E:/hackios/UniXNU-pong/migration/ipados18/services93-wifi-checkin.md` | wifid/`com.apple.wifi.manager` 接线 |
| `E:/hackios/UniXNU-pong/migration/ipados18/services111-association-metal-route.md` | 0x384 vs 0x250 association 布局 |
| `E:/hackios/UniXNU-pong/migration/ipados18/services104-system-peripheral-order.md` | en0、102 channel、10 BSS 扫描 |
| `E:/hackios/UniXNU-mondrian/docs/reference/AGENT-COORDINATION.md` | K60 侧 WiFi/PCIe 相关行：`:484`（官方状态 Wi-Fi 不可用）、`:1619`（FDT 的 pcie 节点不能直接用于 XNU 常量） |
| `E:/hackios/UniXNU-mondrian/docs/audits/MEASURED-HIGH-WINDOW-2026-11-02.md` | K60 live FDT SHA、内存窗口事实（`:33-34`、`:120-144`） |
| `D:/Android/k60-ios/deliverables/FEATURES-DRIVERS-RESEARCH-2026-10-31.md` | K60 WiFi 现状与固件缺口（`:86-91`、`:245`、`:269`） |
| `E:/k60-work/reports/live-6033dbec-fdt.dtb` | K60 live merged FDT（919210 B，SHA-256 `95c02052...`） |
| `E:/k60-work/reports/live-6033dbec-iomem.utf8.txt` | K60 `/proc/iomem`；BAR0 `60200000-603fffff : 0000:01:00.0` |
| `E:/hackios/UniXNU-mondrian/configs/mondrian_defconfig` | `CONFIG_XNU_NATIVE_UFS=y`（`:28`）、`CONFIG_XNU_PONG_ADRENO_PLATFORM=y`（`:52`） |
| `E:/hackios/UniXNU-mondrian/board.toml` | `dram_size`（`:98`）、`kernel_args`（`:125`）、`owned_memory_size`（`:162`） |
| `E:/hackios/UniXNU-mondrian/scripts/build-xnu-4k-baseline.sh` | K60 内核链接入口；WiFi archive 需接入 `PLATFORM_ARCHIVES`（`:956-1020`） |
| `E:/hackios/UniXNU-mondrian/drivers/ArmDTPlatform/ArmDTPlatform.cpp` | WiFi `pong_wifi_start_optional()` 的调用点（`:216-226` 现有 Adreno 模式） |
| `E:/hackios/UniXNU-mondrian/drivers/NativeUfs/SmmuTakeover.h` | `planUfsSmmu()`；K60 缺 `pong_ufs_ready()`（见 `pong:drivers/NativeUfs/PongUfsTransport.cpp:620`） |
