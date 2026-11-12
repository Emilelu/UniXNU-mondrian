# WiFi 差距分析（SA-03）

> 来源：subagent SA-03，2026-11-12
> 状态：只读调研完成，结论已落库
> 关联：`docs/research/wifi/RESEARCH.md`（①②③④⑤⑥）、`patches/wifi/`

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

46 步寄存器序列与 82 条 PHY 表已全部提取，地址换算成绝对地址。

## 2. 端点与平台地址（实测值）

```
端点       17CB:1103
subsys     17CB:0108
BAR0       0x60200000 / 2 MiB
SID        root 0x1C00 / BDF100 → 0x1C01
IOVA       0xA0000000（DT pool 256 MiB，代码用 64 MiB arena）
MSI        PARF MSI0 (bit23) → GIC INTID 172 (SPI 140)，不是 ITS
```

| 窗口 | 基址 | 大小 |
|---|---|---|
| GCC | 0x100000 | 0xA0000 |
| TLMM | 0xF100000 | 0xD0000 |
| PARF | 0x1C00000 | 0x3000 |
| PHY | 0x1C06000 | 0x2000 |
| DBI | 0x60000000 | 0x1000 |
| ATU | 0x60001000 | 0x1000 |
| CFG | 0x60100000 | — |
| SPMI core | 0xC400000 | — |
| SPMI cfg | 0xC42D000 | — |
| SPMI obs | 0xC440000 | — |
| cmd-db | 0x80860000 | 0x20000 |

## 3. ⚠️ 重大发现：我们不是「没有」，是「有但从未应用」

`patches/wifi/` 已有 **0001-0009 共 9 个补丁，232 KB**，含：
- 14 个 PongWifi 文件
- K60 profile
- 4 个构建脚本
- defconfig
- UFS lease/ready
- DTPlatform 钩子

`impl/wifi` 证据显示主机侧真编译过：`ATH11K_RC=0` / `BUILD_RC=0`。

**但三件事让它完全无效**：

| 问题 | 证据 | 后果 |
|---|---|---|
| **没有任何 series/applier 引用 `patches/wifi`** | 全仓 grep | **永不应用** |
| README 说必需的 `0010`（`build-xnu-4k-baseline` 加 `-force_load libPongWifiNative.a`）**在最终系列和本仓里都不存在** | grep 0010 | 就算编出 archive 也不链进内核 |
| 工作树里 `drivers/PongWifi`、`configs/mondrian-wifi-sm8475.json`、`nw_abi.h` 都不存在 | `ls` | 补丁从未落盘 |

**这和 `0403` 是同一个模式**：数据在，没人引用，等于不存在。

## 4. ⚠️ 一个真 bug：refgen 索引写错

`PongWifiPlatform.cpp:221`：

```c
gcc.w(0x7b04c, (1u << 8) | 11u);   // 11 = Pong 的 refgen 索引
```

**K60 profile 的 100 MHz 在 index 10**（index 11 全 0），而 `0009` 的脚本也断言 `[10]`。

**首次 bring-up 必选错父时钟 → 链路训练会失败。**

`:335` 的 `gcc.w(0x7b04c, 1)` 也要按 K60 重算。

## 5. 固件不在我们手里

`/mnt/d/Android/k60-ios/firmware/` 只有 GPU 固件（`a730_sqe.fw` 74,676 B 等 5 个）
+ `history/mondrian-fdt.img` 920,992 B + `pong-boot.img` 1,277,952 B。**无 qca6490/amss。**

全机唯一 PWF2 是 23 字节假固件打出的 16,407 B 测试包（`impl/wifi/work/build/wifi-native/PongWifiFirmware.bin`）。
C:/D: 全盘 `qca6490` / `amss.bin` / `.pwf` 均 0 命中。

**真实固件只能从设备 `/vendor/firmware_mnt/image/qca6490/` 只读提取**：
```
amss.bin        5,470,128
amss20.bin      5,296,128
Data.msc          889,524
Data20.msc        916,071
bd_m11agf.elf      60,000
```

## 6. DMA：我们**没有**官方说的那套接口

`drivers/NativeUfs` 没有 `native_ufs_extra_*` / `native_ufs_part_*`，也没有导出的
`dma_alloc` / `read_partition`。

那套名字只在 Sheng 的 `NativeUfs.cpp:299-303,1641`，**且是全局变量不是函数**。

**Pong 路线不用它**：自建 64 MiB `IOBufferMemoryDescriptor` arena + `ArmSmmu4K` 页表。
只需要：
- `planUfsSmmu`（我们 `SmmuTakeover.h:98` **有**）
- `pong_ufs_ready` 与 `pong_smmu_lease_lock/unlock`（`patch 0004` 补）

`hostRead4k(lun, lba, blocks, dst)` 存在但是 `static`，非导出。

## 7. 最小路径：读端点 ID 不需要 DMA/SMMU/MSI/固件

`coldLink()` 在 `isolation()` 之前就做 `cfg.r(0)` / `cfg.r(0x2C)` 校验。

**第一阶段只需**：
1. GPIO 时序
2. 六路电源
3. GCC 时钟 / GDSC / reset
4. 82 条 PHY 表
5. DBI
6. iATU

**真正拦路的两件事**：
- **RSC 默认被 `0003` 门禁死**（`k60_wifi_rsc=0` → `supplies()` 必失败）
- **refgen 索引 11→10**

## 8. 建议优先级

| # | 做什么 | 理由 |
|---|---|---|
| 1 | 修 refgen 索引并参数化 | 一行 bug，不修必然失败 |
| 2 | 决定 RSC 策略 | 只读探针 or 信任 bootloader 已上电的 fallback |
| 3 | 补 `0010` force_load + 建 `patches/wifi/series` | 否则 232 KB 永远不生效 |
| 4 | 从设备提固件生成真 PWF2 | 只读提取，设备在线时可做 |

## 结论

**WiFi 是三块空白区里最接近可用的**：代码有了（1,919 行）、补丁有了（232 KB）、
主机侧编译过了，只差**接进系列 + 修一个索引 + 拿固件**。

这是「有但没接线」的典型，和 `0403` 固件补丁、`1e1a70e` ADT 修复同一个模式。
