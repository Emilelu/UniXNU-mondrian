# memory/RESEARCH.md —— 内存布局与跨板边界（K60 mondrian / SM8475）

> **结论层。** 证据行在 [REFERENCE-INDEX.md 第 12 节](../REFERENCE-INDEX.md)（12.1 DDR 保留区 / 12.2 寄存器窗口 / 12.3 固件与启动配置）与 9.1（liuqin 交叉验证）。
> 主数据源：`uefi-mondrian/Platforms/Xiaomi/mondrianPkg/Library/MemoryMapLib/MemoryMapLib.c`（2026-10-27 实测生成）+ 设备 6033dbec 的 live FDT。
> **本文的目的不是复述地址，而是划出「哪些值可以跨板用、哪些一抄就崩」的边界。**

## 1. DDR 保留区（会挡住别人写代码的那些）

| 名称 | 基址 | 大小 | 结束 | 来源行 |
|---|---|---|---|---|
| `video_region` | 0x85700000 | 0x00700000 | 0x85E00000 | `MemoryMapLib.c:22` |
| `SMEM` | 0x80900000 | 0x00200000 | 0x80B00000 | `:19` |
| `aop_cmd_db_region` | 0x80860000 | 0x00020000 | 0x80880000 | `:14` |
| `adsp_region` | **0x9FD00000** | **0x03100000** | 0xA2E00000 | `:34` |
| `xbl_ramdump` / `xbl_sc` | 0xA6B80000 / 0xA6E00000 | 0x00280000 / 0x00040000 | — | `:35-36` |
| `ramoops` | 0xA7000000 | 0x00400000 | 0xA7400000 | `:38` |
| `ABL Staging` | 0xA8300000 | 0x0FD00000 | 0xB8000000 | `:51`（注释 `:39-50`：ABL 在此停 DTB 与拼接 initrd，**无 descriptor 时 level-2 translation fault**） |
| `Display Reserved` | 0xB8000000 | 0x02B00000 | 0xBB000000 | `:52` |
| `Kernel` | 0xBB000000 | 0x0C000000 | 0xC7000000 | `:75` |
| `DXE Heap` | 0xC7000000 | 0x18000000 | 0xDF000000 | `:83`（注释 `:76-82`：DarwinBoot 需要**一段连续 256 MiB**；堆给到 320 MiB 时最大连续 run 只有 0xF0A0000） |
| `XNU High Arena` | 0x900000000 | 0x140000000 | 0xA40000000 | `:94`（注释 `:85-93`：高 DDR 在 >= 0x800000000，`[0x100000000,0x800000000)` 是**空洞**；只暴露实测连续的 8 GiB） |

三条可以当校验用的**首尾相接**关系（写新映射前先对一遍，错一个就说明表被改坏了）：

1. `ABL Staging` 结束 = `Display Reserved` 开始 = `0xB8000000`；
2. `Display Reserved` 结束 = `Kernel` 开始 = `0xBB000000`；
3. `Kernel` 结束 = `DXE Heap` 开始 = `0xC7000000`。

## 2. 寄存器区窗口（AP 视角的 MMIO 归属）

| 名称 | 基址 | 大小 | 来源行 | 谁在用 |
|---|---|---|---|---|
| `QUP` | 0x00800000 | 0x00300000 | `:103` | 触摸 GENI SPI `0x990000` 在其内 |
| `USB` | 0x0A600000 | 0x00200000 | `:108` | DWC3（REFERENCE-INDEX 第 10 节） |
| `AOSS` | 0x0B000000 | 0x04000000 | `:109` | `kAoss=0xc300000` 在其内（音频 ADSP 线） |
| `TLMM` | 0x0F000000 | 0x01000000 | `:110` | 所有 GPIO（触摸 / 面板 / BT 使能脚） |
| `SMMU` | 0x15000000 | **0x00200000** | `:111` | UFS / 显示等 Dma 通路；**Pong 驱动只映射 1 MiB** |
| `APSS_HM` | 0x17000000 | 0x02000000 | `:112` | RPMh RSC `0x17a00000` 在其内（供电线最贵的阻塞点，见 REFERENCE-INDEX 14.1） |
| `PMIC ARB SPMI` | 0x0C400000 | 0x2800000 | `:65` | PMIC 寄存器访问（REFERENCE-INDEX 3.3） |

## 3. 跨板边界：哪些能抄、哪些不能

对照板是 **liuqin**（Xiaomi Pad 6 Pro，同 SM8475），数值来自它的 stock 固件 + live FDT，明细见 REFERENCE-INDEX 9.1。

| 区域 | 跨板结论 | 依据 |
|---|---|---|
| `adsp_region` 0x9FD00000+0x3100000 | **可抄（两板同值）** | `liuqin-hardware.md:21` ↔ `MemoryMapLib.c:34` |
| `ramoops` 0xA7000000+0x400000 | **可抄（两板同值）** | `liuqin-hardware.md:19` ↔ `MemoryMapLib.c:38` |
| `xbl_ramdump` / `xbl_sc` | **可抄（两板同值）** | `liuqin-hardware.md:20` ↔ `MemoryMapLib.c:35-36` |
| `Display Reserved` 0xB8000000+0x2B00000 | **可抄（两板同值）** | `liuqin-hardware.md:18` ↔ `MemoryMapLib.c:52` |
| `DXE Heap` | **绝不可抄**：K60 `0xC7000000+0x18000000` vs liuqin `0xF8000000+0x7C00000` | `MemoryMapLib.c:83` ↔ `liuqin-hardware.md:40` |
| `Kernel` 0xBB000000+0xC000000 | **绝不可抄**：liuqin 的 Kernel 预留值本索引未取证，凡对照必重新取证 | `MemoryMapLib.c:75` |
| `UEFI FD` 窗口 | **形状可抄、位置不可抄**：K60 挪到 `0xA7400000+0x300000` 以避开 ramoops（`Resources/Configs/mondrian.toml:9-13`），liuqin 是 `0xA7000000+0x400000`（+ Reserved `0xA7400000+0x200000`） | 两板都自洽，但布局不同 |
| `SMMU` 窗口 | **长度不可抄**：K60 2 MiB（`MemoryMapLib.c:111`），Pong 驱动映射 1 MiB | `PongUfsTransport.cpp:190` |
| ADSP 基址 | **不可抄 Pong 的**：K60 `0x9FD00000`，Pong 是另一个值（REFERENCE-INDEX 14.2） | 两处独立记录 |

**一句话规则**：DDR 保留区里「固件/协处理器共享的」跨板往往同值；「给 OS 装载器自己分配的」（Kernel、DXE Heap、UEFI FD）**必须逐板取**，因为它们取决于该板 UEFI 的 `MemoryMapLib` 与 DarwinBoot 的连续段要求。

## 4. 启动链上的三个硬约束（改内存表前必读）

1. **ABL Staging 必须存在且连续**：`MemoryMapLib.c:39-50` 注释说明 ABL 在这里停 DTB 并拼接 initrd，缺 descriptor 时报 level-2 translation fault——即 `0xA8300000+0x0FD00000` 不是「留白」，是 ABL 的运行区。
2. **UEFI FD 挪位是为了避 ramoops**：`Resources/Configs/mondrian.toml:9` 原文注释（ramoops 占 0xA7000000，FD 挪到 0xA7400000），`MemoryMapLib.c:63` 的 `UEFI FD 0xA7400000 + 0x300000` 与之对应。动 ramoops 或 FD 任一处，另一处必须同步。
3. **DarwinBoot 需要一段连续 256 MiB**，且高 DDR 从 `0x800000000` 起、`[0x100000000,0x800000000)` 是空洞；`XNU High Arena` 只暴露实测连续的 8 GiB（`MemoryMapLib.c:76-94`）。任何「把别的东西塞进 DXE Heap 区间」的想法先读这三行注释。

## 5. 使用规则

1. 新增/修改一个区域 = 改 `MemoryMapLib.c` + 核对本文的三条首尾相接关系 + 在 REFERENCE-INDEX 12.1 补一行证据（带行号）。
2. 引用本表时**带行号**，不要只写地址：地址本身没有可信度，行号才有。
3. 跨板对照一律标注来源板；只有第 3 节表格里标「可抄」的四条允许直接用于 liuqin 之外的对照，其余必须重新取证。

## 6. 交叉引用

- 证据行与 liuqin 明细：[`../REFERENCE-INDEX.md`](../REFERENCE-INDEX.md) 第 12 节、9.1、14.2
- 显示占用 `Display Reserved` / `video_region`：[`display/RESEARCH.md`](../display/RESEARCH.md)（第 6 节）
- UFS 用到的 SMMU 窗口：[`storage/RESEARCH.md`](../storage/RESEARCH.md)（第 1 节）
- 12 GiB 与高窗计划（不是本文的证据来源，改动前先读）：`docs/plans/MEMORY-12G-PLAN.md`、`docs/audits/MEASURED-HIGH-WINDOW-2026-11-02.md`
- 门禁数据源：`docs/research/SOURCES.toml` 的 `[subsystem.power]`、`[subsystem.display]`
