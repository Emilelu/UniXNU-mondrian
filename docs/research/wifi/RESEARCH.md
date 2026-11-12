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

---

## ④ 广域：官方文档给出的完整适配路径

来源：https://unixnu.com/zh/porting/network （2026-11-12 读取）

### 硬前置

> 先完成[平台中断和 DMA](/zh/porting/platform)。

**WiFi 排在整个驱动顺序里平台之后。** 我们的 UFS 已提供 DMA 与中断，这是有利条件。

### 组件接口（`include/nw_abi.h`）

必须实现三组回调：

| 结构 | 内容 |
|---|---|
| `lx_platform` | 时间、休眠、轮询、日志、内存分配、DMA 分配/映射/同步、`fw_get` |
| `nw_board` | BAR、PCI 身份、配置空间访问、MSI 目标 |
| `nw_wifi_events` | 事件回调（在工作线程执行，须及时返回）|

所有权约定（文档明确写出）：
- `dma_alloc` 返回清零的 CPU 内存 + 端点可达的 bus 地址
- `dma_map` 对范围外缓冲返回 0
- `dma_sync` 按传输方向同步缓存
- `fw_get` 按文件名返回数据与长度，保证组件消费期间有效
- 先装 `nw_wifi_events` 再启动工作线程；`nw_wifi_step` 非零则继续推进
- 接收回调若要交给异步 OS 路径，返回前必须复制到 OS 拥有的缓冲

### 阶段选择

参考探针用 `wifi` boot-arg 选阶段：

```
1  检查交接状态
2  启动链路
4  检查端点
5+ 进入可复用协议栈（由协议栈执行 MHI 和固件启动）
```

### 板级启动的六步（文档第 2 节）

1. 检查已供电、已启用时钟的寄存器状态
2. 执行目标板的电源、时钟、PHY 配置和复位顺序
3. 训练链路并读取端点 vendor/device ID
4. 分配并映射 BAR，检查 PCI capability，启用 memory 与 bus-master
5. 建立端点 DMA 范围，确认缓冲区在选定缓存策略下可达
6. 接入 MSI 并确认中断到达，再依赖中断推进驱动

**预期结果**：端点正确、BAR 可读、DMA 可用、中断到达。

### 参考实现（sheng / WCN7850 on SM8550 PCIe0）的实测结论

| 方面 | 结论 |
|---|---|
| 供电 | 六路 PMU 电源都需要 RPMh 的模式、电压和使能请求；**缺少模式请求时有两路不上电，链路无法训练** |
| PCIe | PCIe0 训练到 Gen2 x1；端点 ID `17cb:1107` |
| 中断 | 芯片的 MSI 经 PCIe0 自己的 MSI 接收器送到 **SPI 141**；工作线程在中断之间睡眠 |
| 固件 | `c7-00108` 可运行；`c2-00259` 卡在按需分页器 |
| MAC | 固件上报的 MAC 为零，由板级用芯片 ID 生成 |
| 扫描 | 不扫描 6 GHz（其 59 个被动信道会占用大部分扫描时间）|
| 关联 | 对端条目使用接入点自己的 HT/VHT 能力，而不是本机的；加入与四次握手约 100 ms |
| 链路 | 5 s 内仍收到帧时忽略固件的 beacon 丢失；**VHT MCS 10 和 11 的帧会被丢弃** |
| 系统 | 无法保存网络密码，因此不把该网络视为已知网络 |

### DMA 与固件的来源

> 参考实现使用 `native_ufs_extra_*` 提供 DMA 内存区，使用 `native_ufs_part_*` 读取固件。

**这意味着 WiFi 复用了 UFS 的 DMA 与分区读取服务。** 我们已有 `NativeUfs` 与
`PongUfsTransport`，但需确认是否暴露了等效接口；若没有，WiFi 需要自己的 DMA 分配路径。

固件文件名、board data 与校准数据来源需记录在 `proprietary-files.txt`。

### 与 K60 的差异（必须注意）

| 项 | 官方参考 | K60 |
|---|---|---|
| SoC | SM8550 | **SM8475（与 Pong 相同）** |
| 芯片 | WCN7850（ath12k 族）| **QCA6490 / WCN6855（ath11k 族）** |
| 端点 ID | `17cb:1107` | 预期 `17cb:1103`（Pong 配置 device=4355=0x1103，待实测）|
| MSI | SPI 141 | 待实测 |
| 板级实现 | sheng 的 `WifiProbe.cpp` + `WifiNet.cpp` | **Pong 的 `PongWifiPlatform.cpp`（40,764 B，同 SoC 同芯片）** |

**结论**：官方文档给的是「怎么做」的骨架和 sheng 的 SM8550/WCN7850 实测值；
K60 的板级数值必须来自 Pong（同 SoC 同芯片）或实测，不能照抄 sheng。

---

## ⑤ 方案（基于 ④ 的证据）

分三步，每步都有独立的验证点：

### 第一步：板级 PCIe0 冷启动（只到端点可读）

照 Pong 的 `PongWifiPlatform.cpp` 移植，不改协议栈：

- 平台地址（SM8475 真值，Pong 已核对）：GCC `0x100000`、TLMM `0xf100000`、
  PARF `0x1c00000`、DBI `0x60000000`、PHY `0x1c06000`、ATU `0x60001000`、
  SPMI core `0xc400000`、SPMI config `0xc42d000`
- 六步按官方顺序，每步独立打印与判据
- **验证点**：链路训练成功，读到端点 vendor/device ID `17cb:11xx`

### 第二步：决定协议栈归属

两条路，必须先量再选：

| 路 | 条件 | 代价 |
|---|---|---|
| A. 用 `Ath12kWifi` | 仅在它支持 ath11k/WCN6855 时可行 | 官方组件面向 ath12k，MHI/QRTR 细节不同 |
| B. 自建 ath11k 路径 | 参考 Pong 的 `PongWifiNet.cpp`（47,656 B）| 工作量大，但不依赖上游是否支持 |

**判据**：读 `nw_abi.h` 与 `nw_wifi.c`，核对端点协议版本与固件族是否覆盖 WCN6855。

### 第三步：固件与校准数据

Pong 用 PWF2 包（`/pong/firmware/qca6490.pwf`，magic `0x32465750`）。
我们要么复刻 PWF2 打包，要么直接从 vendor 分区读：

```
/vendor/firmware_mnt/image/qca6490/
  amss.bin 5.47 MB   amss20.bin 5,296,128 B
  Data.msc 889,524 B Data20.msc 916,071 B
  bd_m11agf.elf 60,000 B（蓝牙）
```

**判据**：固件启动成功 + 扫描产生 BSS 记录（官方文档的两个独立预期结果）。

---

## ⑥ 深挖待办

- [ ] K60 的端点 ID、BAR0、subsystem_device（实测）
- [ ] K60 的 MSI 目标（官方参考是 SPI 141，K60 待测）
- [ ] K60 的六路 PMU 电源与 RPMh 请求（Pong 用 SPMI 观察者，K60 待核对）
- [ ] `nw_abi.h` 是否覆盖 WCN6855（决定第二步走 A 还是 B）
- [ ] UFS 是否暴露 `native_ufs_extra_*` / `native_ufs_part_*` 等效接口
