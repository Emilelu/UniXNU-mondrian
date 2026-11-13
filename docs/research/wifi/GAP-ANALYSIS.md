# WiFi 差距分析（SA-03）

> 初版：subagent SA-03，2026-11-12
> 修订：2026-11-14（③ 反编译补证完成；§3–§5 的旧结论已按实测更正）
> 关联：`docs/research/wifi/RESEARCH.md`、`docs/research/wifi/FIRMWARE.md`、`patches/wifi/`

---

## 1. Pong WiFi 源码全貌

位置：`references/pong-wifi/`（子模块仓，分支 `origin/port/ios18e-native-302`，HEAD `20e1e5b`），14 文件。
**5 个实现文件共 1,919 行**：

| 文件 | 大小 | 行数 | 作用 |
|---|---|---|---|
| `PongWifiPlatform.cpp` | 40,764 B | 617 | **PCIe0 冷启动全流程**（`coldLink()` 有完整 **46 步寄存器序列 + 82 条 PHY 表**）|
| `PongWifiNet.cpp` | 47,656 B | 779 | `IO80211Controller` / `IO80211Interface` / `Pong80211UserClient` + Apple80211 ioctl |
| `PongWifiPci.cpp` | 6,010 B | 137 | 只读接管 |
| `PongWifiFirmware.cpp` | 3,984 B | 76 | PWF2 加载 |
| `ath11k/PongAth11k.c` | 7,248 B | 162 | `nw_wifi_start` / `nw_wifi_step` |

K60 采用的版本是 `patches/wifi/0001`（源自 zizhan `087416a`），应用后
`drivers/PongWifi/PongWifiPlatform.cpp` 为 **736 行**，比 Pong 版多 119 行
（K60 profile 解析、6 条 rail、boot-arg 门控）。

---

## 2. ③ 反编译补证：四个关键值的逐项出处

本节的每个数字都能追到两个独立来源：**设备实机 live FDT**（`dtc` 反编译
`E:\k60-work\reports\live-6033dbec-fdt.dtb` → `/tmp/live.dts`，34,801 行）
与**代码常量**（`drivers/PongWifi/PongWifiPlatform.cpp`，`patches/wifi/0001` 应用后 736 行）。

### 2.1 端点 ID 17CB:1103

| 证据 | 位置 | 内容 |
|---|---|---|
| live FDT | `/soc/mhi_qrtr_cnss`（live.dts:12321） | `compatible = "qcom,qrtr-mhi"`、**`qcom,dev-id = <0x1103>`** |
| 代码 | `PongWifiPlatform.cpp:356` | `if(cfg.r(0)!=0x110317cb) return fail("QCA6490 endpoint identity mismatch");` |
| 代码 | `PongWifiPlatform.cpp:639` | `board={...,0x1103,...}` —— `nw_board.device_id` |
| Linux 对照 | `linux-7.0.14/.../ath11k/pci.c:32` | `#define WCN6855_DEVICE_ID 0x1103` |

`cfg.r(0)` 读的是 PCI 配置空间偏移 0 的 32 位，低 16 位 device、高 16 位 vendor，
所以期望值 `0x110317cb` = vendor 0x17cb + device 0x1103。**这是"端点可枚举"的最小判据。**

subsystem 值在补丁版里**不再作为门禁**：zizhan 实测 `0x010817cb`，Pong 板级 JSON
写 `subsystem_device=264`，两者不一致但链路正常。K60 profile
`configs/mondrian-wifi-sm8475.json` 因此把 `subsystem_vendor`/`subsystem_device`
都设为 0 并只记录不校验。

### 2.2 BAR0 基址 0x60200000 / 2 MiB

| 证据 | 位置 | 内容 |
|---|---|---|
| live FDT | `/soc/qcom,pcie@1c00000` `ranges` | `<0x01000000 0x00 0x60200000 0x60200000 0x00 0x100000>` + prefetch 段 `<0x02000000 0x00 0x60300000 0x60300000 0x00 0x3d00000>` |
| 代码 | `PongWifiPlatform.cpp:368-369` | `if(cap||!pcieCap||!msiCap||!bar.open(0x60200000,0x200000)) return false;` → **2 MiB** |
| 代码 | `PongWifiPlatform.cpp:351` | 注释 "actual 0x60200000..0x63ffffff range rather than Sheng's 0x60300000." |
| 代码 | `PongWifiPlatform.cpp:364` | ATU 编程：`atu.w(b+8,0x60200000); atu.w(b+16,0x63ffffff); atu.w(b+20,0x60200000); atu.w(b+4,0x80000000);` |
| 代码 | `PongWifiPlatform.cpp:533` | `mapPhys()` 接受 `pa>=0x60200000 && pa<0x60400000` |

**注意与 Sheng（SM8550）的差异**：Sheng 用 `0x60300000` 起。K60/SM8475 的
memory 窗口从 `0x60200000` 开始，长度 `0x100000`（1 MiB）落在 mem32 段，
prefetch 段接着 `0x60300000`+`0x3d00000`。DBI 编程 `dbi.w(0x20, 0x63f06020)`
（Type-1 memory aperture）覆盖到 `0x63ffffff`，与 ranges 的并集一致。

### 2.3 IOVA 0xA0000000（DT 256 MiB 池 / 代码 64 MiB arena）

| 证据 | 位置 | 内容 |
|---|---|---|
| live FDT | `/soc/qcom,pcie@1c00000/pcie0_rp/cnss_pci/cnss_pci_iommu_group`（live.dts:19604） | **`qcom,iommu-dma-addr-pool = <0xa0000000 0x10000000>`** → 基址 0xA0000000、**256 MiB** |
| live FDT | 同节点 | `qcom,iommu-msi-size = <0x1000>`、`qcom,iommu-dma = "fastmap"`、`qcom,iommu-pagetable = "coherent"` |
| live FDT | `/reserved-memory/cnss_wlan_region`（live.dts:342） | `compatible="shared-dma-pool"`、`reusable`、`alignment=<0 0x400000>`(4 MiB)、**`size=<0 0x2000000>`(32 MiB)** |
| 代码 | `PongWifiPlatform.cpp:40` | `constexpr uint64_t Iova = 0xa0000000;` |
| 代码 | `PongWifiPlatform.cpp:436` | `ranges[0] = {Iova, msiPa, 4096, 3, 0, 2};` |
| 代码 | `PongWifiPlatform.cpp:532` | `*lo = uint32_t(Iova + 0x40);` —— MSI 目标地址 |
| 代码 | `PongWifiPlatform.cpp:499` | log "exclusive SID1c01 native4K DMA and retained MSI landing page established" |

**IOVA 起点是硬约束**：固件与主机共享的地址必须落在 DT 声明的 dma-addr-pool 里，
否则 SMMU 会按 non-fatal fault 处理。Pong 代码只从 `0xA0000000` 起分配，
arena 大小由 boot-arg `pong_wifi_dma_mib` 控制（`PongWifiPlatform.cpp:382` 只接受
64 或 128；zizhan 实测 128 MiB wired 分配失败、64 MiB 通过）。

SID 侧对应关系（live FDT `iommu-map`）：`<0x00 0x5b 0x1c00 0x01 0x100 0x5b 0x1c01 0x01>`
+ `qcom,smmu-sid-base = <0x1c00>` → root SID `0x1c00`、BDF 0x100 映射到 `0x1c01`。
Pong 用的是 `0x1c01`（`PongWifiPlatform.cpp:499` 的日志文本可证）。

### 2.4 MSI：PARF MSI0 (bit23) → GIC INTID 172 (SPI 140)

| 证据 | 位置 | 内容 |
|---|---|---|
| live FDT | `/soc/qcom,pcie@1c00000` `msi-map` | `<0x00 0x237 0x5980 0x01 0x100 0x237 0x5981 0x01>` —— RID 0x00/0x100 映射到 phandle `0x237`(ITS) 的 ITS 事件号基址 0x5980/0x5981，**不是** SPI 140 |
| live FDT | `interrupt-map` | 首项 `<0x00 0x00 0x00 0x00 0x01 0x00 0x8c 0x04>` → GIC 侧 `0x8c = 140`，type `0x04`(level-high) |
| live FDT | `interrupts = <0x00 0x01 0x02 0x03 0x04>` + `interrupt-names = "int_global_int\0int_a\0int_b\0int_c\0int_d"` | PCIe 控制器自身 5 条中断 |
| live FDT | GIC `/soc/interrupt-controller@17100000` | `compatible="arm,gic-v3"`、`#interrupt-cells=<0x03>`；子节点 `msi-controller@17140000`（phandle `0x237`）是 ITS |
| 代码 | `PongWifiPlatform.cpp:42` | `constexpr unsigned PcieGlobalIntid = 32 + 140, ParfMsi0 = 1u << 23;` |
| 代码 | `PongWifiPlatform.cpp:634` | `armcpu_spi_attach(PcieGlobalIntid, false, irq, nullptr, &ctl, &route)`，失败信息 "PCIe0 SPI140 MSI receiver attach failed" |
| 代码 | `PongWifiPlatform.cpp:636` | log "DesignWare MSI receiver armed on Pong PCIe0 SPI140" |
| 代码 | `PongWifiPlatform.cpp:611-612` | `if(pending){dbi.w(MsiStatus,pending); __atomic_fetch_add(&msiArrivals,1,...);}`，注释 "Only this port's MSI group is enabled in PARF." |

**关键判定：不走 ITS。** DT 里确实有 `msi-controller@17140000`（`arm,gic-v3-its`，
`/aliases` 里叫 `gic_its`），`msi-map` 也指向它。但 Pong 的实现完全绕开 ITS：

1. PARF 里置 `MSI0` 使能位（`1u << 23`）；
2. DesignWare 核把 MSI 写到 `dbi` 编程的 MSI 目标地址（`Iova + 0x40`）；
3. 该写操作在 PARF 侧被翻译成 **SPI 140**，进 GIC 后是 **INTID 172**（= 32 + 140）。

所以 `armcpu_spi_attach(172, ...)` 是唯一的中断接收路径，ITS 全程未用。
这也是为什么 `msi-map` 里的 `0x5980`（22912 = 32 + 22880）不是我们要的号——
那个是 ITS 的 DeviceID→EventID 表，跟 PARF 直连 SPI 无关。

**上机风险点**：`drivers/ArmCpu/ArmCpu.cpp:403` 有
`if(!owner) panic("ArmCpu: unowned SPI %u", intid);` —— SPI 172 必须先有 owner
publish，否则 `armcpu_spi_attach` 会直接 panic。这是 ⑧ 上机第一次尝试最可能踩的坑。

### 2.5 平台窗口（与 §2.1–2.4 同源）

| 窗口 | 基址 | 大小 | 出处 |
|---|---|---|---|
| GCC | 0x100000 | 0xA0000 | Pong `PongWifiPlatform.cpp:184/236/239` |
| TLMM | 0xF100000 | 0xD0000 | 同上 :91/94 |
| PARF | 0x1C00000 | 0x3000 | live FDT `reg` 第 1 项 + `PongWifiPlatform.cpp:248` `parf.open(0x1c00000,0x3000)` |
| PHY | 0x1C06000 | 0x2000 | live FDT `reg` 第 2 项（`reg-names="parf\0phy\0dm_core\0elbi\0iatu\0conf"`） |
| DBI | 0x60000000 | 0x1000 | live FDT `reg` 第 3 项 `dm_core` |
| ATU | 0x60001000 | 0x1000 | live FDT `reg` 第 5 项 `iatu` |
| CFG | 0x60100000 | 0x100000 | live FDT `reg` 第 6 项 `conf` |
| SPMI core | 0xC400000 | — | `PongWifiPlatform.cpp:163` |
| SPMI cfg | 0xC42D000 | — | 同上 |
| SPMI obs | 0xC440000 | — | 同上 |
| cmd-db | 0x80860000 | 0x20000 | `QcomRpmh.c` `qcom_cmd_db_find` |

live FDT 的 `reg` 原文：`<0x1c00000 0x3000 0x1c06000 0x2000 0x60000000 0xf1d 0x60000f20 0xa8 0x60001000 0x1000 0x60100000 0x100000>`。

### 2.6 GPIO 与电源（板级）

| 信号 | GPIO | 出处 |
|---|---|---|
| `perst-gpio` | 94 | live FDT `perst-gpio = <0x3c 0x5e 0x00>` |
| `wake-gpio` | 96 | live FDT `wake-gpio = <0x3c 0x60 0x00>` |
| `wlan-en-gpio` | 80 | live FDT `/soc/qcom,cnss-qca6490@b0000000` `wlan-en-gpio = <0x3c 0x50 0x00>` |
| `qcom,bt-en-gpio` | 81 | 同上 `<0x3c 0x51 0x00>` |
| `qcom,sw-ctrl-gpio` | 82 | 同上 `<0x3c 0x52 0x00>` |
| `qcom,xo-clk-gpio` | 204 | 同上 `<0x3c 0xcc 0x00>` |

六条 rail（`PongWifiPlatform.cpp` `kPongWifiRail[]`，由
`build-k60-wifi-native.py` 从 profile 生成）：

| rail | PPID | 电压范围 (µV) |
|---|---|---|
| `smpe2` | — | vdd-wlan-aon 1,012,000–1,040,000 |
| `smpb11` | — | vdd-wlan-dig 966,000–1,170,000 |
| `smpb10` | — | vdd-wlan-io 1,800,000（固定） |
| `smpc1` | — | vdd-wlan-rfa1 1,900,000–2,024,000 |
| `smpb12` | — | vdd-wlan-rfa2 1,350,000–2,040,000 |
| `ldoe7` | — | wlan-ant-switch 2,800,000（固定） |

live FDT 的对应 `*-supply` phandle：aon=`0xbe`、dig=`0x3e`、io=`0x3d`、
rfa1=`0x3f`、rfa2=`0x40`、ant-switch=`0x41`。
Pong 版多一条 `smpe3`，K60 没有。

### 2.7 refgen 索引

| 证据 | 内容 |
|---|---|
| live FDT `max-clock-frequency-hz` | `<0 0 0x124f800 0 0 0 0 0 0 0 0x5f5e100 0 0 0 0>` → **index 10 = 0x5f5e100 = 100,000,000 Hz**，index 2 = 19,200,000 |
| live FDT `clock-names` | 14 条，`[8] = "pcie_phy_refgen_clk"` |
| `build-k60-wifi-native.py` 硬断言 | `pcie.clock_names[8]=='pcie_phy_refgen_clk'` 且 `pcie.max_clock_frequency_hz[10]==100000000`，否则 `raise 'k60 pci-msm refgen clock plan changed; adapt its RCG before building'` |
| 补丁版代码 | `PongWifiPlatform.cpp:233` `gcc.w(0x7b04c,(1u<<8)|10u);` —— **已用 10** |

**旧结论（"refgen 索引 bug 未修"）已作废**：`patches/wifi/0001` 里已经是 `10u`。
唯一残留是同一行上方的注释还写着 "refgen is index 11, 100 MHz"，属文档瑕疵，
不影响行为（2026-11-14 实测确认）。

---

## 3. 补丁状态：从"有但从未应用"到"10 个全部干净应用"

初版 SA-03 的结论是"patches/wifi 有 0001-0009 但没有任何 series/applier 引用，
永不应用"。**2026-11-14 复测结果：**

| 项 | 初版结论 | 实测（2026-11-14） |
|---|---|---|
| 补丁数量 | 0001–0009 共 9 个 | **0001–0010 共 10 个**，`series` 10 行 |
| `git apply --check` | 未做 | **10 个全部干净应用，零冲突**（在 `feat/wifi-bringup` 与 `/opt/k60/trees/wifi-device` 两处独立验证） |
| 0004 冲突 | "无法应用到我们的 PongUfsTransport.cpp（47,569 B vs 上游 30,473 B）" | **可以应用**：我们的 `drivers/NativeUfs/PongUfsTransport.cpp` 644 行，补丁上下文能匹配 |
| 0010 是否存在 | "在最终系列和本仓里都不存在" | **存在**（1,629 B），作用见 §3.2 |
| 有无 applier | 无 | **仍无** —— `board.toml:20` 的 `patch_series` 只有 `device:patches/xnu/series` |

### 3.1 十个补丁

| # | 文件 | 大小 | 作用 |
|---|---|---|---|
| 0001 | `0001-drivers-PongWifi-vendor-zizhan-087416a.patch` | 134,576 B | 14 个 PongWifi 文件 + `ath11k/` |
| 0002 | `0002-drivers-PongWifi-ath11k-compat-28de7b91.patch` | 953 B | `PongCompat.h` |
| 0003 | `0003-drivers-PongWifi-k60-rsc-gate.patch` | 2,181 B | `pong_rpmh_vote` 加 `k60_wifi_rsc` 两级门 |
| 0004 | `0004-drivers-NativeUfs-pong-ufs-ready.patch` | 2,987 B | `pong_ufs_ready()` + SMMU lease |
| 0005 | `0005-drivers-ArmDTPlatform-pong-wifi-hook.patch` | 953 B | `configure()` 末尾调 `pong_wifi_start_optional()` |
| 0006 | `0006-scripts-build-pong-platform-xnu-pong-wifi.patch` | 799 B | 传 `-DXNU_PONG_WIFI` |
| 0007 | `0007-configs-mondrian-wifi-defconfig.patch` | 3,141 B | `configs/mondrian_wifi_defconfig` |
| 0008 | `0008-configs-mondrian-wifi-sm8475.patch` | 12,759 B | `configs/mondrian-wifi-sm8475.json`（K60 profile） |
| 0009 | `0009-scripts-k60-wifi-build.patch` | 51,753 B | 4 个构建脚本 |
| 0010 | `0010-scripts-build-xnu-wifi-archive.patch` | 2,164 B | `build-xnu-4k-baseline.sh` 两条归档路径都加 `-force_load` |

### 3.2 0010 为什么是必需的

`patches/xnu/series` 里 223 个补丁**没有一个**会改
`scripts/build-xnu-4k-baseline.sh` 的归档块。0010 加的是：

```bash
if [ "${XNU_PONG_WIFI:-0}" = 1 ]; then
  PONG_WIFI_ARCHIVE=${XNU_PONG_WIFI_ARCHIVE:-$ROOT/build/pong-wifi/libPongWifiNative.a}
  test -f "$PONG_WIFI_ARCHIVE"
  KERNEL_EXTRA_ARCHIVES="$KERNEL_EXTRA_ARCHIVES -Wl,-force_load,$PONG_WIFI_ARCHIVE"
  KERNEL_ARCHIVE_DEPENDENCIES=...
fi
```

没有它，即使 `libPongWifiNative.a` 编出来了也**永远不会被链进内核**。
2026-11-14 实测：device 仓的 `scripts/build-xnu-4k-baseline.sh`
（sha256 `37fc72e3…`）`grep -c XNU_PONG_WIFI` = **0**；打上双 hunk 的 0010 后 = 4。

**必须改两条路径，只改一条会静默失效。** 该脚本的归档装配分成两个互斥分支：

| 分支 | 变量 | 生效条件 | 行 |
|---|---|---|---|
| A | `KERNEL_EXTRA_ARCHIVES` | `XNU_SOURCE_CORECRYPTO14=1` | 整块 :892–:1077 |
| B | `PLATFORM_ARCHIVES` | `ARM_DT_PLATFORM=1` 且 `XNU_SOURCE_CORECRYPTO14 != 1` | :1120 起 |

mondrian 走 **B**：`out-*/…/mondrian/.config` 里 `CONFIG_XNU_SOURCE_CORECRYPTO14`
出现两次（:2 `=y`、:88 `=n`），`config.py parse_config()` 后者覆盖前者 → False。

初版 0010 只加了 A，链接期因此报：

```
Undefined symbols for architecture arm64:
  "_pong_smmu_lease_lock", referenced from: __ZN12_GLOBAL__N_111hostBringUpEv in libNativeUfs.a(PongUfsTransport.o)
  "_pong_smmu_lease_unlock", referenced from: __ZN12_GLOBAL__N_111hostBringUpEv in libNativeUfs.a(PongUfsTransport.o)
  "_pong_wifi_start_optional", referenced from: __ZN13ArmDTPlatform9configureEP9IOService in libArmDTPlatform.a(ArmDTPlatform.o)
```

三个符号都在 `libPongWifiNative.a` 里（`T _pong_smmu_lease_lock` 0x3a4c /
`T _pong_smmu_lease_unlock` 0x3a80 / `T _pong_wifi_start_optional` 0x134），
所以不是缺符号而是没 force_load：`kernel.log` 里 `force_load` 与
`LD_KERNEL_ARCHIVES` 的计数都是 **0**。0010 已重写为双 hunk，两条路径都加。

**注意**：`tree/scripts/` 的内容来自 **device 仓**（`unixnu/tree.py` 的
`_copy_scripts` 从 `ctx.device` 拷），不是从 `k60-wifi` 工作树。所以
0010 必须应用到 **device 仓**才算接线。

---

## 4. 接线缺口：三处必须由 Lead 合并

这三处都在本 agent 的写作用域之外（`board.toml` / defconfig / 构建环境），
需 Lead 合并：

| # | 文件 | 需要的改动 | 不做的后果 |
|---|---|---|---|
| 1 | `board.toml:20` | `patch_series` 加 `"device:patches/wifi/series"` | 10 个补丁永不应用 |
| 2 | 构建配置 | 用 `configs/mondrian_wifi_defconfig`（比 `mondrian_defconfig` 只多 `CONFIG_XNU_PONG_WIFI=y`） | `XNU_PONG_WIFI` 不会 = 1 |
| 3 | 构建环境 | `export XNU_PONG_WIFI=1` + `XNU_PONG_WIFI_ARCHIVE=<abs>/libPongWifiNative.a` | 0010 的默认路径是 `$ROOT/build/pong-wifi/`，与实际产物位置不符 |

机制链（已逐行读过框架源码确认）：

```
.config 的 CONFIG_XNU_PONG_WIFI=y
  → kernel.py:19 xnu_env() 把 CONFIG_XNU_* 转成 XNU_*=1
  → build-xnu-4k-baseline.sh:922 if [ "$XNU_PONG_WIFI" = 1 ]
  → -Wl,-force_load,$XNU_PONG_WIFI_ARCHIVE
```

另有两条**非阻塞但要注意**的：

- `kernel.py:166` 收尾校验：所有 `*_ARCHIVE` 键且值以 `.a` 结尾的文件必须存在，
  否则 `Error('<KEY>: <path> not found; supply the archive or its build recipe')`。
- `gates.py`：`build` 属 GATED 命令，要求 `ctx.device/scripts/check-rules.py` 与
  `K60_REPO or ctx.device` 下的 `docs/engineering/RULES.toml`。**device 仓没有
  `docs/engineering/RULES.toml`** → 正式构建必须设 `K60_REPO` 指向有该文件与
  `scripts/check-rules.py` 的仓（如 `/mnt/e/hackios/k60-wifi`），
  或用 `UNIXNU_SKIP_GATES=1`（仅限 trial，`build-strict.sh` 会硬拒）。

---

## 5. 固件：已从设备取回

初版结论"固件不在我们手里"**已作废**。2026-11-14 把设备启动到 Android 后
`adb pull` 取回 `/vendor/firmware_mnt/image/qca6490/` 全部 222 个文件，
其中 PWF2 打包需要的 4 个已齐（`amss.bin` / `amss20.bin` / `m3.bin` / `regdb.bin`，
合计 11,067,094 B）。

详细清单、sha256、PWF2 包结构、每个文件的角色见
`docs/research/wifi/FIRMWARE.md`。

**打包必须用干净四文件目录** `E:\k60-work\firmware\qca6490-wifi\`：
`build-k60-wifi-native.py` 会把 `--firmware` 目录下所有文件打进包，
指向原始目录会得到 13 MB / 10 文件的包。

---

## 6. DMA：我们**没有**官方说的那套接口

`drivers/NativeUfs` 没有 `native_ufs_extra_*` / `native_ufs_part_*`，也没有导出的
`dma_alloc` / `read_partition`。

那套名字只在 Sheng 的 `NativeUfs.cpp:299-303,1641`，**且是全局变量不是函数**。

**Pong 路线不用它**：自建 64 MiB `IOBufferMemoryDescriptor` arena + `ArmSmmu4K` 页表。
只需要：

- `planUfsSmmu`（我们 `SmmuTakeover.h:98` **有**）
- `pong_ufs_ready` 与 `pong_smmu_lease_lock/unlock`（`patch 0004` 补）

`hostRead4k(lun, lba, blocks, dst)` 存在但是 `static`，非导出。

0004 的实际落点（`drivers/NativeUfs/PongUfsTransport.cpp`，应用后 644 行）：

- `:29-30` `extern "C" bool pong_smmu_lease_lock(void) __attribute__((weak_import));` 与 `pong_smmu_lease_unlock`
- `:53` `static uint32_t gWifiUfsReady;`
- `:176-179` `~Lease(){if(held)pong_smmu_lease_unlock();}` 与 `if(pong_smmu_lease_lock&&pong_smmu_lease_unlock){lease.held=pong_smmu_lease_lock();}`
- `:234` `__atomic_store_n(&gWifiUfsReady,1,__ATOMIC_RELEASE);`（READ CAPACITY 之后）
- `:644` `extern "C" bool pong_ufs_ready(void){return __atomic_load_n(&gWifiUfsReady,__ATOMIC_ACQUIRE)!=0;}`

**符号面实测**（2026-11-14）：`libPongWifiNative.a` 未定义符号 341 个 →
与 `kernel.macho` 已定义 47,806 个比对后剩 31 个 → 与 archive 自身已定义 3,362 个
比对后**只剩 `_pong_ufs_ready` 一个** → 再与 `tree/build/*/*.a`
（armcpu / native-ufs / armdt-platform / pong-adreno 共 981 个定义符号）比对，
**仍是 `_pong_ufs_ready`**。

原因：现有 `libNativeUfs.a` 是 0004 应用**之前**编的，不含该符号。
→ 应用 0004 后重编 `libNativeUfs.a` 即可解析。这是接线问题，不是缺符号。

---

## 7. 最小路径：读端点 ID 不需要 DMA/SMMU/MSI/固件

`coldLink()` 在 `isolation()` 之前就做 `cfg.r(0)` / `cfg.r(0x2C)` 校验。

**第一阶段只需**：

1. GPIO 时序（perst 94、wake 96、wlan-en 80）
2. 六路电源（smpe2 / smpb11 / smpb10 / smpc1 / smpb12 / ldoe7）
3. GCC 时钟 / GDSC / reset（`0x7b004` GDSC、`0x7b04c` refgen index 10）
4. 82 条 PHY 表（K60 与 Pong 逐 cell 相同，different=0）
5. DBI（`0x60000000`）
6. iATU（`0x60001000`）

**真正拦路的两件事**：

- **RSC 默认被 0003 门禁死**：`k60_wifi_rsc` 未设 → 0 → `supplies()` 必失败。
  设计意图是 fail-safe：默认不投票，靠 bootloader 已上电的状态。
- ~~refgen 索引 11→10~~ **已修**（见 §2.7）。

---

## 8. 建议优先级

| # | 做什么 | 理由 | 状态 |
|---|---|---|---|
| 1 | 修 refgen 索引并参数化 | 一行 bug，不修必然失败 | ✅ 补丁里已是 10u |
| 2 | 决定 RSC 策略 | 只读探针 or 信任 bootloader 已上电的 fallback | 0003 已实现两级门，待上机验证 |
| 3 | 补 0010 force_load + 建 `patches/wifi/series` | 否则 232 KB 永远不生效 | 0010 ✅ / series 引用 ❌（Lead 合并项）|
| 4 | 从设备提固件生成真 PWF2 | 只读提取，设备在线时可做 | ✅ 已取回并打包 |

---

## 结论

**WiFi 是三块空白区里最接近可用的**：代码有了（1,919 行）、补丁有了（10 个，全部
干净应用）、主机侧编译过了、固件拿到了、③ 反编译真值逐项落库。

剩下的全部是**接线**：让 device 仓的 `patch_series` 引用 `patches/wifi/series`、
切到 `mondrian_wifi_defconfig`、把 archive 路径传进构建环境。三处都不涉及新代码。

这是「有但没接线」的典型，和 `0403` 固件补丁、`1e1a70e` ADT 修复同一个模式。
