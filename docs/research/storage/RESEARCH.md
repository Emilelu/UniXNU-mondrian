# storage/RESEARCH.md —— 存储 / UFS（K60 mondrian / SM8475）

> **结论层。** 证据行在 [REFERENCE-INDEX.md 第 9 节](../REFERENCE-INDEX.md)（含 9.1 与 liuqin 的双源交叉验证）；
> 本文只写可用值、不可抄的值、以及卡住的地方。
> `fdt_dump.txt:NNNN` 指 `E:/k60-work/scratch/refmine/fdt_dump.txt`（live FDT `E:/k60-work/reports/live-6033dbec-fdt.dtb`）。
> **铁则④：绝不写设备分区，只用序列号 6033dbec，只用 `fastboot boot`。** 本文任何地址都不是写盘许可。

## 1. UFS 控制器 / PHY 真值（本板 live FDT）

| 块 | 值 | 出处 | 可信度 |
|---|---|---|---|
| UFS PHY | **`0x1d80000 + 0x2000`** | `fdt_dump.txt:9577-9578` `/soc/ufsphy_mem@1d80000` | 本板实测 |
| PHY compatible | **`qcom,ufs-phy-qmp-v4-cape`** | `:9587` | 本板实测 |
| PHY 供电 | `vdda-phy-supply=<0x232>` / `vdda-pll-supply=<0x233>`；max 0x30188 µA / 0x5c94 µA | `:9588-9591` | 本板实测 |
| 控制器 | `0x1d84000 + 0x3000` | `:9593-9596` | 本板实测 |
| ICE / HWKM | `0x1d88000 + 0x8000` / `0x1d90000 + 0x9000` | 同上，`reg=<0x1d84000 0x3000 0x1d88000 0x8000 0x1d90000 0x9000>`，`reg-names=ufs_mem,ufs_ice,ufs_ice_hwkm` | 本板实测 |
| 中断 | `interrupts=<0 0x109 4>` = **GIC SPI 265，level high** | `:9597` | 本板实测 |
| 亲和 / 通路 | `prime-mask 0x70` / `silver-mask 0xf`、**lanes 2** | `:9601-9603` | 本板实测 |
| APPS SMMU | `0x15000000 + 0x200000`（**2 MiB**） | `uefi-mondrian/Platforms/Xiaomi/mondrianPkg/Library/MemoryMapLib/MemoryMapLib.c:111` | 本板实测 |

**关键点 1：PHY 是 `0x1d80000`，不是 SM8450 的 `0x1d87000`。** 抄 SM8450 会把 PHY 打到邻居的寄存器上。
**关键点 2：compatible 是 `qmp-v4-cape`** —— 不是 `v4`、不是 `v4-2.0`；PHY 初始化序列按这个 compatible 选。
**关键点 3：SMMU 窗口 K60 是 2 MiB，而 Pong 的驱动只映射 1 MiB**（`references/pong-ufs/PongUfsTransport.cpp:190`），照抄会漏掉高半段。

## 2. 双源交叉验证（liuqin，同 SM8475 / Xiaomi Pad 6 Pro）

`0x1d80000` + `qmp-v4-cape` 这两条在 liuqin 侧有第二份独立确认（`E:/hackios/UniXNU-liuqin/docs/liuqin-hardware.md:23`，另同仓 `board.toml:103`；**注意 `k60-work/references/` 下没有 `UniXNU-liuqin` 软链**，只能按绝对路径读），并与 K60 的 live FDT 逐条吻合 → 从单点升为两处独立来源一致。
PHY 供电、中断号、ICE/HWKM 偏移**目前只有 K60 侧单源**（live FDT），liuqin 那边没记。

## 3. 移植参考（能借什么、不能借什么）

| 来源 | 能借 | 不能借 |
|---|---|---|
| `references/pong-ufs/PongUfsTransport.cpp:219-238` | 初始化序列：QUERY power mode → SCSI `0xd0` START STOP UNIT → TEST UNIT READY 轮询 → READ CAPACITY，**要求 blockSize==4096** 否则报 `unsupported LUN geometry`（`:157` 控制器 `0x01d84000` 与 K60 同值） | SMMU 只映射 1 MiB；LUN0 LBA 范围 `0x413248..0x75a40ea`（`:54-55`）是 Pong 自己的盘 |
| `references/pong-ufs/RootLayout.h:67` `:72` `:157` | GPT 头校验（`EFI ` / `PART` / `128`）、分区项大小 `0x10000`、headerBytes ∈ [92,4096]、窗口 magic `SHNGROOT` | — |
| `references/ShengUfs/`（`NativeUfs.cpp` 148,723 B） | 官方完整实现，`RootCommands.h`（29,932 B）与 `tests/` 下 18 个文件（13 个 `.cpp`/`.S` 用例 + 5 个 `.py` 检查脚本）是移植范本 | **整体替换**：它硬编码 SM8550 |

## 4. 本板已登记的盘面事实（不要重新发明）

| 事实 | 出处 |
|---|---|
| `CONFIG_XNU_NATIVE_UFS=y`；owner data volume UUID `E313398B-D70A-4EB8-9425-4B1A7BE3E1F5`；`CONFIG_XNU_PONG_RAMOOPS_CONSOLE=y` | `references/yibiya-upstream/configs/mondrian_defconfig:28` / `:46` / `:55`（`references/` 软链下可达） |
| 官方记录里的 `board.toml [userdata]`：first_lba **53342976** / last_lba **61731583** / lba_bytes **4096** | `references/UniXNU-upstream/docs/devices/mondrian-mzyxsl.md:45`（另 `:249`）；fork 自报，未经本线复核 |

## 5. 缺口（下一步该做的只读验证）

| 缺口 | 怎么补（只读，不写盘） |
|---|---|
| 本板扇区大小 / 容量未实测 | 只读 `READ CAPACITY(10)`；liuqin 是 1 TB SK Hynix HN8T35DZHKX079 / 4096 B 逻辑与物理扇区（`E:/hackios/UniXNU-liuqin/docs/liuqin-hardware.md:4`），K60 盘型号未知 |
| UFS 初始化从未在本核上跑过 | 需要 ⑦ 三类核验（静态 / 动态 / 上机）后才谈 ⑧ |
| `qmp-v4-cape` 的 PHY 初始化序列没有 XNU 侧实现 | 只能从 Linux `ufs-qcom` 的同名 compatible 反推，属「反编译/推断」，必须上机验证 |
| ICE / HWKM 是否需要在本核初始化 | 取决于是否启用 XNU 侧 inline crypto；当前无人取证 |

## 6. 交叉引用

- 证据行：[`../REFERENCE-INDEX.md`](../REFERENCE-INDEX.md) 第 9 节与 9.1、第 12.2 节（SMMU 窗口）
- 内存布局与跨板边界：[`memory/RESEARCH.md`](../memory/RESEARCH.md)
- 门禁数据源：`docs/research/SOURCES.toml` 的 `[subsystem.storage]`
