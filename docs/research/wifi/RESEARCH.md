# WiFi 八步调研（① 同型 / ② 官方 / ③ 反编译）

> 目标子系统：WiFi（QCA6490 / WCN6855）
> 日期：2026-11-12
> 状态：①②③ 完成，④⑤⑥ 待办

---

## ① 同型：Pong 的 WiFi 实现

**来源**：`references/pong-wifi`，分支 `origin/port/ios18e-native-302`

| 文件 | 大小 | 作用 |
|---|---|---|
| `PongWifiPlatform.cpp` | 40,764 B | **PCIe0 冷启动全流程**：SPMI PMIC 观察者、GCC 时钟、TLMM、PARF、DBI、PHY、ATU |
| `PongWifiNet.cpp` | 47,656 B | 网络栈 |
| `PongWifiPci.cpp` | 6,010 B | PCIe 寄存器定义 |
| `PongWifiPci.h` | 1,416 B | |
| `PongWifiFirmware.cpp` | 3,984 B | **PWF2 固件包加载器** |

**关键：Pong 是 SM8475 + QCA6490，与 K60 完全相同。**

`PongWifiPlatform.cpp` 第 2 行注释：
```
/* Pong / SM8475 QCA6490 PCIe0 cold start. Board facts come from live DT. */
```

### 平台地址（SM8475 真值）

| 块 | 基址 | 大小 | 代码位置 |
|---|---|---|---|
| GCC | `0x100000` | `0xa0000` | `PongWifiPlatform.cpp:184` |
| TLMM | `0xf100000` | `0xd0000` | `:184` |
| PARF | `0x1c00000` | `0x3000` | `:236` |
| DBI | `0x60000000` | `0x1000` | `:239` |
| PHY | `0x1c06000` | `0x2000` | `:239` |
| ATU | `0x60001000` | `0x1000` | `:239` |
| SPMI core | `0xc400000` | `0x3000` | `:91` |
| SPMI config | `0xc42d000` | `0x4000` | `:91` |
| SPMI observer | `0xc440000` | 动态 | `:94` |
| 寄存器块 | `0x80860000` | `0x20000` | `:163` |

### 与 Sheng（SM8550）的关键差异（Pong 注释中明确）

```
:205  // 0x162128 bit0 in Pong's live DT, not Sheng's 0x152020 register.
:207  // SM8475 has a single PCIe0 GDSC at 7b004, no SM8550 PHY GDSC.
:226  // to vote bit11, not Sheng's SM8550 cnoc clock. Do not omit this path.
:339  // actual 0x60200000..0x63ffffff range rather than Sheng's 0x60300000.
:340  dbi.w(0x20,0x63f06020);
```

**这四条注释说明 Pong 已经踩过 SM8550 抄 SM8475 的坑。这是最高价值的信息。**

### 固件加载机制（PWF2）

`PongWifiFirmware.cpp` 不是从 vendor 分区读，而是读**本机 root 文件系统**的
`/pong/firmware/qca6490.pwf`：

```cpp
constexpr const char *path="/pong/firmware/qca6490.pwf";
constexpr uint64_t maximum=64u*1024u*1024u;
struct Entry {char name[32];uint32_t offset,bytes;};
// 魔数 0x32465750 = "PWF2"
// 头部 8 字节：[magic][entry count]，之后是 entry 数组，载荷按需加载
```

**优点**：固件不依赖 vendor 分区、不依赖音频或其他板级输入，纯 OS 内自包含。
**缺点**：需要生成 `.pwf` 包（把 `amss.bin`、`bd_m11agf.elf` 等打包）。

### 板级配置

`configs/pong-wifi-sm8475.json`（`UniXNU-pong` 仓库）：

```json
{
  "format": "pong-qca6490-board-v1",
  "board": "pong",
  "soc": "SM8475",
  "pci": {
    "vendor": 6091,          // 0x17CB Qualcomm
    "device": 4355,          // 0x1103 QCA6490
    "subsystem_vendor": 6091,
    "subsystem_device": 264,
    "revision": 1,
    "bar0": { "base": 1612709888, "bytes": 2097152 }   // 0x60200000, 2 MiB
  }
}
```

**NVIDIA/K60 需要核对 `subsystem_device`** —— Pong 是 264，K60 可能不同。

---

## ② 官方：UniXNU 组件目录

### `Ath12kWifi`（唯一的 WiFi 组件）

| 字段 | 值 |
|---|---|
| function | ath12k Wi-Fi transport with MHI and QRTR |
| hardware | `ath12k PCI devices`, `qcc2072`, `qcn9274`, `wcn7850` |
| os_abi | `nw_abi platform interface` |
| board_dependencies | PCI configuration, BAR, MSI, DMA operations |
| source_files | `include/nw_abi.h` |
| build_stage | embedded |
| revision | （见 components.toml） |

**⚠️ 不适用**：`Ath12kWifi` 针对 **ath12k** 驱动族（`qcc2072` / `qcn9274` / `wcn7850`），
K60 是 **QCA6490 / WCN6855**（`ath11k` 族）。两者 MHI/QRTR 接口不同。

**结论**：官方没有覆盖 QCA6490 的组件。WiFi 只能参考 Pong 的实现，
外加 Linux `ath11k/qca6490` 的 mainline 驱动。

### 官方文档

`https://unixnu.com/zh/porting/network`（待读，④ 阶段补）

---

## ③ 反编译：K60 本机真值

来自 `docs/engineering/ANDROID-HW-TRUTH.md`（2026-11-10 Android 实测）：

| 项 | 真值 |
|---|---|
| 驱动 | `qca6490` + `cnss2` + `wlan_firmware_service` |
| 固件目录 | `/vendor/firmware_mnt/image/qca6490/` |
| 连接状态 | ✅ 已连 5G（`Connecting to Emilelu_5G rssi:-53 freq:5180`）|

### 固件文件清单（全部实测大小）

| 文件 | 大小 |
|---|---|
| `amss.bin` | 5,47x,xxx |
| `amss20.bin` | 5,296,128 |
| `Data.msc` | 889,524 |
| `Data20.msc` | 916,071 |
| `bd_m11agf.elf`（蓝牙）| 60,000 |

### 待补的 ③ 项

- [ ] K60 的 **PCI 设备 ID**（`lspci` 或 `/sys/bus/pci/devices/*/`）
- [ ] K60 的 **BAR0 基址与大小**
- [ ] K60 的 **subsystem_device**（Pong 是 264，K60 可能不同）
- [ ] K60 的 **PCIe0 GDSC 偏移**（Pong 注释说 SM8475 是 `7b004`）
- [ ] K60 的 **PMIC SPMI 通道号**（Pong 用 SPMI 观察者读，K60 可能不同）

---

## ④⑤⑥ 待办

- ④ 广域：读 `unixnu.com/zh/porting/network`；查 mainline `ath11k` 的 qca6490 支持；
  查 zizhan（SM8475）的 WiFi 实现
- ⑤ 方案：决定用 PWF2 包还是直接读 vendor 分区
- ⑥ 深挖：PCIe 训练失败的诊断路径

---

## 风险与约束

1. **PCIe 冷启动是硬骨头**。Pong 的 40 KB 代码里大部分是 PCIe PHY 训练、PARF 配置、
   ATU 映射、DBI 预设。失败模式是"链路起不来"，没有任何日志。
2. **固件必须从 K60 自己的 Android 分区提取**（`amd.bin` / `amss.bin` / `bd_m11agf.elf`），
   不能用 Pong 的。
3. **`subsystem_device` 可能不同**。如果不同，PCIe 设备枚举会失败。
4. **PWF2 打包工具需要先实现**（Pong 的打包脚本在 `scripts/build-pong-wifi-native.py`）。

---

## 优先级建议

WiFi 是 P3（新子系统），低于：
- P0 触摸 ⑦ 核验（卡住刷机）
- P1 GPU Metal 追平
- P2 UFS 对齐官方架构

**但 WiFi 的 ① 已完成且质量很高**（同 SoC 同芯片 + 已踩过 SM8550 的坑），
如果要做新子系统，WiFi 是首选。
