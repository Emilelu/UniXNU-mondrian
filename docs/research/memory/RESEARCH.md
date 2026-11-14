# memory/RESEARCH.md —— 内存布局与跨板边界（K60 mondrian / SM8475）

> **结论层。** 证据行在 [REFERENCE-INDEX.md 第 12 节](../REFERENCE-INDEX.md)（12.1 DDR 保留区 / 12.2 寄存器窗口 / 12.3 固件与启动配置）与 9.1（liuqin 交叉验证）。
> 主数据源：`uefi-mondrian/Platforms/Xiaomi/mondrianPkg/Library/MemoryMapLib/MemoryMapLib.c`（2026-10-27 实测生成）+ 设备 6033dbec 的 live FDT。
> 第 5 节说明这两份数据源本身从哪来（`uefiplat.cfg` 已删、`FdtBlob` 是 mainline 派生），**引用地址前先读第 5 节**。
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
| `Kernel` 0xBB000000+0xC000000 | **绝不可抄**：K60 `0xBB000000+0x0C000000` vs liuqin `0xA8000000+0x10000000`，差 0x13000000 | `MemoryMapLib.c:75` ↔ `liuqin-hardware.md:39` |
| `UEFI FD` 窗口 | **形状可抄、位置不可抄**：K60 挪到 `0xA7400000+0x300000` 以避开 ramoops（`uefi-mondrian/Resources/Configs/mondrian.toml:9-13`，注意**不在** `mondrianPkg/` 下），liuqin 是 `0xA7000000+0x400000`（+ Reserved `0xA7400000+0x200000`） | 两板都自洽，但布局不同 |
| `SMMU` 窗口 | **长度不可抄**：K60 2 MiB（`MemoryMapLib.c:111`），Pong 驱动映射 1 MiB | `PongUfsTransport.cpp:190` |
| ADSP 基址 | **不可抄 Pong 的**：K60 `0x9FD00000`，Pong 是另一个值（REFERENCE-INDEX 14.2） | 两处独立记录 |

**一句话规则**：DDR 保留区里「固件/协处理器共享的」跨板往往同值；「给 OS 装载器自己分配的」（Kernel、DXE Heap、UEFI FD）**必须逐板取**，因为它们取决于该板 UEFI 的 `MemoryMapLib` 与 DarwinBoot 的连续段要求。

## 4. 启动链上的三个硬约束（改内存表前必读）

1. **ABL Staging 必须存在且连续**：`MemoryMapLib.c:39-50` 注释说明 ABL 在这里停 DTB 并拼接 initrd，缺 descriptor 时报 level-2 translation fault——即 `0xA8300000+0x0FD00000` 不是「留白」，是 ABL 的运行区。
2. **UEFI FD 挪位是为了避 ramoops**：`Resources/Configs/mondrian.toml:9` 原文注释（ramoops 占 0xA7000000，FD 挪到 0xA7400000），`MemoryMapLib.c:63` 的 `UEFI FD 0xA7400000 + 0x300000` 与之对应。动 ramoops 或 FD 任一处，另一处必须同步。
3. **DarwinBoot 需要一段连续 256 MiB**，且高 DDR 从 `0x800000000` 起、`[0x100000000,0x800000000)` 是空洞；`XNU High Arena` 只暴露实测连续的 8 GiB（`MemoryMapLib.c:76-94`）。任何「把别的东西塞进 DXE Heap 区间」的想法先读这三行注释。

## 5. 内存表与 DTB 的来源：改之前先确认你改的是哪一份

### 5.1 内存表的唯一权威是 `MemoryMapLib.c`，不是 `uefiplat.cfg`

`Platforms/Xiaomi/mondrianPkg/RawFiles/uefiplat.cfg` **已被删除**：提交 `43e245ea16b4dfa57c4295739b8fc1eb9d11a0a6`（"mondrian: repo hygiene (Mu patch list, dead files, panel note, gitignore)"，2026-10-28）把它连同 `MemoryMapLib.c.pong-orig` 一起删掉，`RawFiles/` 现在是空目录（0 个文件），`git grep uefiplat` 在全树**零命中**。`mondrian.dsc:83` 只编 `MemoryMapLib|mondrianPkg/Library/MemoryMapLib/MemoryMapLib.inf`，所以**内存表的唯一权威是 `MemoryMapLib.c`**。

旧快照仍可恢复（`git show 43e245e^:Platforms/Xiaomi/mondrianPkg/RawFiles/uefiplat.cfg`，81 行，`Version = 3`、`MaxMemoryRegions = 74`），但**不要引用它的数值**：它写着 `Kernel 0xBB000000+0x10000000`、`DXE Heap 0xCB000000+0x4000000`，而现行 `MemoryMapLib.c:75` 是 `Kernel 0xBB000000+0x0C000000`、`:83` 是 `DXE Heap 0xC7000000+0x18000000`。它是 2026-10-27 从 live FDT 生成的**历史快照**，之后内核窗口与 DXE 堆都被重新划过。

### 5.2 本板跑的是编进固件的 mainline 派生 DTB，不是厂商 DTB

`mondrian.fdf:114` 把 `mondrianPkg/FdtBlob/sm8475-xiaomi-mondrian.dtb`（480,692 B，sha256 `d09f4f10bb84d0e5481433b61bc969ea31b793ead394da18a5363d2e9d4b655c`）作为 `FILE FREEFORM = 25462CDA-221F-47DF-AC1D-259CFAA4E326` / `SECTION UI = "DeviceTreeBlob"` 编进固件，由 `EmbeddedPkg/Drivers/DtPlatformDxe` 消费；`FdtBlob/Source.txt`（全文仅 2 行）写明它来自 `https://github.com/sm8450-mainline/linux` 的 `tyalie` 分支，并加了 `usb-role-switch` 修 USB OTG Mode——注意原文 `Source.txt:2` 的措辞是 `With usb-role-switch; added on line 1003 to fix USB OTG Mode`，其中的 **1003 是上游 DTS 的行号，不是 `Source.txt` 的行号**（该文件只有 2 行，别去 grep `Source.txt:1003`）。

### 5.3 两棵 DTB 的差异：保留区可互换，面板不可

| | 树内 `FdtBlob/sm8475-xiaomi-mondrian.dtb` | 设备 `live-6033dbec-fdt.dtb` |
|---|---|---|
| 节点数 | 3,034 | 4,206 |
| `/reserved-memory` 带 reg 区域 | 36 | 38 |
| `mdss@ae00000` 直接子节点 | 4 | 34 |
| 其中 DSI 面板节点 | **0** | **30** |

- **保留区**：36 条同名区域**地址与大小逐条相同**，无「同名不同址」。live 侧只多 `ramoops@0xa7000000` 与 `splash_region`（运行时才写死地址；树内 `ramoops_region` 的 `alloc-ranges` 是全 0/全 F 的动态分配）。→ 查保留区两棵可互换，**要写死地址就用 live 侧**。
- **面板**：树内 DTB 的 `mdss` 只有 4 个直接子节点（`qcom,platform-supply-entries` 与三个 `qcom,sde-*-blocks`），**一个面板都没有**；m11a 的 init 串只存在于 live DTB 或 `dispdcbx` 分区。做显示不要指望树内 DTB（见 `display/RESEARCH.md` 1.1）。
- **`/chosen`**：只差 `kaslr-seed`、`linux,initrd-start/end` 三个运行时字段，`bootargs` 前缀两边完全相同。

复现：`/mnt/e/k60-work/scratch/refmine/treeparse.py`（纯 Python FDT 解析器；头字段顺序 magic、totalsize、**off_struct**、**off_strings**、off_rsv、version、last_comp、bootcpuid、**size_strings**、**size_struct**；BEGIN_NODE 的 name 与 PROP 值之后都要 4 字节对齐）、`resmem.py`、`dtbdiff.py`、`mdss_count.py`。**不要用 `fdt_dump.txt` 做逐字节比对——它会截断长 hex 串。**

## 6. 使用规则

1. 新增/修改一个区域 = 改 `MemoryMapLib.c` + 核对本文的三条首尾相接关系 + 在 REFERENCE-INDEX 12.1 补一行证据（带行号）。
2. 引用本表时**带行号**，不要只写地址：地址本身没有可信度，行号才有。
3. 跨板对照一律标注来源板；只有第 3 节表格里标「可抄」的四条允许直接用于 liuqin 之外的对照，其余必须重新取证。

## 7. 交叉引用

- 证据行与 liuqin 明细：[`../REFERENCE-INDEX.md`](../REFERENCE-INDEX.md) 第 12 节、9.1、14.2
- 显示占用 `Display Reserved` / `video_region`：[`display/RESEARCH.md`](../display/RESEARCH.md)（第 6 节）
- UFS 用到的 SMMU 窗口：[`storage/RESEARCH.md`](../storage/RESEARCH.md)（第 1 节）
- 12 GiB 与高窗计划（不是本文的证据来源，改动前先读）：`docs/plans/MEMORY-12G-PLAN.md`、`docs/audits/MEASURED-HIGH-WINDOW-2026-11-02.md`
- 门禁数据源：`docs/research/SOURCES.toml` 的 `[subsystem.power]`、`[subsystem.display]`
- 面板/DSI 与两棵 DTB 的面板缺口：[`display/RESEARCH.md`](../display/RESEARCH.md) 1.1、第 8 节
- 跨板 `uefiplat.cfg` 普查（74 份，无一份含本板 DXE Heap/video_region）：[`REFERENCE-INDEX.md`](../REFERENCE-INDEX.md) 第 15 节
