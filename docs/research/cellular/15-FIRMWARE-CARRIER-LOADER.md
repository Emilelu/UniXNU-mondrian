# 15 — 固件载具装载器实现规格（K60ModemImage）

- **状态**：规格；第一交只读骨架已落 `uefi-mondrian` `feat/cellular` `a8d6bd4`，Lead 已接线并真机验证（`a9cd70d`：编译通过、FD 3,145,728 B 不变、进 SpringBoard 128 次、panic 0）；**拷贝与属性发布这一交未写**。本线未构建、未出镜像。
- **日期**：2026-11-15（2026-11-16 补 §1.7 容量约束与 §1.7.1 LZMA 三问、按落地版改写 §1.5/§5.5/§5.6、改 §7 第 1 条）
- **实现 Owner**：uefi-mondrian 线（Lead 排期）；**验收 Owner**：本线（用 13 号门禁）
- **勘察版本**：`uefi-mondrian` `main` @ `9b79562`（工作树只有 6 个子模块脏，无源码改动）
- **相关**：`12-DXE-CONTRACT.md`（为什么是库调用）、`13-FIRMWARE-ACCEPTANCE.md`（19 行门禁）、`14-DXE-REQUEST.md`（需求与裁决）、`06-MODEM-PAS.md`（内核侧）

本文所有行号都相对 `9b79562`。每条断言后面带 `文件:行`，或明确写「此文件不存在，需新建」。

---

## 0 一句话

在 DarwinBoot 的 `Boot()` 里、ADT 解析之后（`DarwinBoot.c:721`）、主窗口分配之前（`DarwinBoot.c:751`）调用一个新库 `ImageCarrierLib`：它把 payload 里 `EFI/UniXNU/MODEM/` 的 27 个平铺文件按 30 行段表写进 `0x8BC00000`，把 16 字节 `{base, span}` 写进 `/chosen/memory-map`，并打三行 level-1 日志。**不新增 DXE 驱动**。

> **前置已裁（2026-11-16 05:10 / 05:24）**：这 27 个文件在当前 192 MiB payload 里装不下（缺 14,114,816 B），Lead 选**出路 D：lzma 压缩进 payload**。三问验证见 **§1.7.1**（全部通过：目标缓冲可直指窗口物理地址、scratch 只需 16,256 B、构建期须改写 8 B size 字段并加 CRC32 列）。容量算术与 A/B/C 的否证见 **§1.7**。

## 1 驱动形态

### 1.1 结论表

| 问题 | 答案 | 依据 |
| --- | --- | --- |
| 形态 | 库 + `Boot()` 调用点，**不是** `DXE_DRIVER` | 见 §1.2 |
| 谁调用 | `DarwinBoot::Boot()` 内，ADT 解析之后 | `DarwinBoot.c:613-914`、`:721` |
| 注册哪个 event | **不注册任何事件** | `DarwinBoot.c:929-969` 入口只装/换协议 |
| ExitBootServices 前还是后 | 之前（`BootServices` 阶段） | `ExitBootServices` 在 `:884`，`Enter` 在 `:891` 且不再返回（`:892`） |
| 与现有 ADT 扫描器的先后 | 之后 | 属性偏移只有 `AdtNode` 跑完（`:721`）才存在 |
| 失败能否拒绝启动 | 能，走现有 `Fail:` | `DarwinBoot.c:898-913` 会画 `BOOT FAILED <stage> <status>` 并回菜单 |

### 1.2 为什么不是 DXE_DRIVER

三条路都堵死，逐条给证据：

1. **独立 DXE + `ReadyToBoot` 事件**：先例是 `MondrianBootMemoryDxe.c:174` 的 `CreateEventEx (..., &gEfiEventReadyToBootGuid, ...)`。但 `ReadyToBoot` 在 UniXNU 调用 `Boot()` **之前**就触发，那时 ADT 还没被读（`DarwinBoot.c:710`），属性根本没有地方可写。
2. **DXE 里晚一点做**：没有「晚一点」——`Boot()` 内部没有对外暴露的钩子，`ExitBootServices`（`:884`）之后一切 BootServices 都不可用。
3. **DXE 失败不能拒绝启动**：这正是 P-197 的形态（固件里根本没有装载器、属性恒全零、启动照常）。`Boot()` 内部调用失败可以直接 `goto Fail`，屏幕上有阶段名，行为可判。

只有 `Boot()` 内部这个位置同时具备三件东西：`Root` 已经打开（`:695`）、`Tree` 已经在内存里（`:710`）、失败还能走 `Fail`（`:898`）。

### 1.3 插入点（精确到行）

位置：`DarwinBoot.c:721` 之后、`:722` 之前。

原样上下文：

```c
  if (!AdtNode (Tree, TreeSize, &Offset, 0, 3, &RamdiskOffset, &TrustCacheOffset, &WindowSize, &KeepPacked) || (Offset != TreeSize)) { Status = EFI_COMPROMISED_DATA; goto Fail; }
  if (KeepPacked && (!RamdiskPacked || (RamdiskOffset == MAX_UINTN))) { Status = EFI_COMPROMISED_DATA; goto Fail; }
```

新增（插在中间）：

```c
  Stage = L"MODEM CARRIER";
  Status = ImageCarrierLoad (Root, Tree, TreeSize, &Carrier, &CarrierOffset);
  if (EFI_ERROR (Status)) { goto Fail; }
```

- `Stage` 是 `CONST CHAR16 *Stage`（`:664`），赋值后 `Fail:` 的 `UnicodeSPrint`（`:899`）会把它画到屏幕上，失败原因一眼可见。
- 局部变量加在函数头部的声明块（`:621-665`）：`IMAGE_CARRIER Carrier;`、`UINTN CarrierOffset;`。照现有风格全部声明在头部，不要用嵌套块，因为 `Carrier` 在 `:801` 之后还要用（§1.6）。
- 为什么不是 `:722` 之后：`:722-:748` 是 ramdisk/trustcache/boot-video 校验，与载体无关；插在 `:721` 直接跟上 ADT 解析，任何 ADT 结构错误都在载体之前就报出来，失败归因更干净。

### 1.4 与现有 `AdtNode` 的关系

- **不复用** `AdtNode`：它是 `DarwinBoot.c` 里的 `STATIC` 递归整树扫描（`:206-309`），语义是「顺手记下几个偏移」，不是通用查询。
- 库自己扫，但只认一条路径：父节点名 `chosen`、子节点名 `memory-map`，然后按 `:233-240` 的格式读属性表：节点头 8 字节（u32 属性数 + u32 子节点数），每条属性 36 字节头（32 B 名 + u32 长度）+ 数据补 4 字节对齐。
- 找不到节点或属性 ⇒ `EFI_COMPROMISED_DATA`（12 §3.7 第 1 条：构建期必须发布 16 B 占位，见 §3.1）。

### 1.5 构建接线：4 个新文件 + 5 处改动

**这一节已按实际落地的形状改写（2026-11-16，Lead 提交 `a9cd70d`）**：库最终放在
`DarwinBootPkg/Library/` 下（不是本节最初建议的 `mondrianPkg`），并且**不需要动 `mondrian.dec`**
——头文件用引号包含，不经过 `<Library/...>` 的搜索路径。

| 动作 | 文件 | 状态 |
| --- | --- | --- |
| 已建 | `Platforms/Xiaomi/DarwinBootPkg/Library/ImageCarrierLib/ImageCarrierLib.h` | 57 行，内容即 §5.2 的契约（`a8d6bd4`） |
| 已建 | `Platforms/Xiaomi/DarwinBootPkg/Library/ImageCarrierLib/ImageCarrierLib.c` | 只读半边（`a8d6bd4`；`a9cd70d` 把两个 include 改成引号形式） |
| 已建 | `Platforms/Xiaomi/DarwinBootPkg/Library/ImageCarrierLib/ImageCarrierLib.inf` | `MODULE_TYPE = BASE`、`LIBRARY_CLASS = ImageCarrierLib`、Sources 三文件、`[Packages]` 只 `MdePkg/MdePkg.dec`、`[LibraryClasses]` 七条、`[Guids] gEfiFileInfoGuid`（形状见 §5.6） |
| 已建（生成物） | `Platforms/Xiaomi/DarwinBootPkg/Library/ImageCarrierLib/K60ModemImageTable.h` | 2,993 B / 46 行，由 `scripts/gen-modem-table.py --firmware-header` 生成，**禁止手改**（13 的 B5 与生成器输出逐字节 diff） |
| 已改 | `Platforms/Xiaomi/mondrianPkg/mondrian.dsc:92` | `ImageCarrierLib|DarwinBootPkg/Library/ImageCarrierLib/ImageCarrierLib.inf`（紧跟 `:83` 的 `MemoryMapLib` 之后） |
| 已改 | `Platforms/Xiaomi/DarwinBootPkg/Driver/DarwinBoot.inf:26` | `[LibraryClasses]` 加 `ImageCarrierLib` —— **这一行才是真正触发编译的那一行**，见下面坑 ① |
| 不需要 | `Platforms/Xiaomi/mondrianPkg/mondrian.dec` | 最初建议加 `[Includes]`+`[LibraryClasses]`，实测**不需要**：引号包含绕过了 `<Library/...>` 搜索 |
| 不需要 | `Platforms/Xiaomi/DarwinBootPkg/DarwinBoot.dsc` | 独立 DSC 只在单独编 DarwinBoot 时用；平台构建走 `mondrian.dsc:120` 编同一个 `.inf`，库从 `mondrian.dsc` 的 `[LibraryClasses]` 取 |
| 待改 | `Platforms/Xiaomi/DarwinBootPkg/Driver/DarwinBoot.c` | 第二交：`:18` 之后加 `#include "ImageCarrierLib.h"`（引号）；`:665` 后加变量；`:721` 后加调用（§1.3）；`:801` 后加三行打印（§1.6） |

**两个构建坑（Lead 2026-11-16 05:24 实测踩到，写拷贝半边时会再遇到）**：

1. **只在 DSC 的 `[LibraryClasses]` 里写一行，EDK2 什么都不会编译**。它只构建被某个组件
   `[LibraryClasses]` 引用的库。第一次重建 FD 尺寸不变、连 `Build/.../ImageCarrierLib/` 对象目录
   都不存在，看起来像「改动生效了」，其实是惰性的。必须在 `DarwinBoot.inf` 里也引用。
2. **`DarwinBootPkg` 没有 `.dec`**，所以 `#include <Library/ImageCarrierLib.h>` 没有 include 路径可解析，
   报 `fatal error: 'Library/ImageCarrierLib.h' file not found`。改成引号包含
   `#include "ImageCarrierLib.h"` / `#include "K60ModemImageTable.h"` 即可。**新增头文件同样用引号。**

**「链接进去但不调用不改变启动」是实测结论**（不是论证）：`a9cd70d` 之后
`ImageCarrierLib.obj` 29,036 B 编译通过、FD 仍精确 3,145,728 B，用该卷打图真机飞到 SpringBoard 128 次、
`Early boot complete` 1 次、`K60DATA mounted` 1 次、panic 0、`no boot entry` 0
（证据 `E:\k60-work\evidence\usblog-20261116-052044`）。

**为什么库放 `mondrianPkg` 而不是 `DarwinBootPkg`**：`DarwinBootPkg` 没有 `.dec`（该目录只有 10 个文件：`DarwinBoot.dsc`、`Driver/*`、`VENDORED.md`），没有 `[Includes]` 就没有 `<Library/...>` 的搜索路径；`mondrianPkg/mondrian.dec:14-15` 已有 `[Includes] Include`，且这个载具本来就是板级事实（固定 `0x8BC00000`、27 个固定文件名），放板级包是对的。

**构建接线风险（要实测）**：`DarwinBoot.dsc` 是独立 DSC，它的 `[Packages]` 来自 `DarwinBoot.inf`。加了 `mondrianPkg/mondrian.dec` 之后，独立构建要求 `PACKAGES_PATH` 里有 `Platforms/Xiaomi`；平台构建（`mondrian.dsc:120` 编同一个 `.inf`）本来就有（`:83` 已经在用 `mondrianPkg/Library/MemoryMapLib/...`），独立构建要看 `build_uefi.py` 传的路径。第一次编译若报「package not found」，先查这里，不要改代码。

### 1.6 三行 D3 日志（Lead 裁决，缺一不可）

位置：`DarwinBoot.c:801` 的 `CopyMem` 之后（此时 `TreeAddress` 已有值）、`:884` 的 `ExitBootServices` 之前。三行必须**各出现一次**（13 的 C1 用 `grep -acF` 要求等于 1）。

```c
  Print (L"modem-image: chosen dtb at 0x%016lx\n", TreeAddress);
  Print (L"modem-image: window 0x8bc00000..0x9ee00000\n");
  Print (L"modem-image: abl staging ends at 0x%016lx\n", AblEnd);
```

- **第 2 行写死字面量**：13 的 C1 用 `grep -F` 逐字符比对，`%lx` 拼出来的大小写/补零不可控；常量写进字符串，另用 `ASSERT (Carrier.Base == 0x8bc00000ULL && Carrier.Span == 0x13200000ULL)` 保真。
- **第 1 行打物理地址** `TreeAddress`（`:766` 算出来的值）。`:798` 的 `Args->DeviceTree = Kernel.Base + TreeAddress - Address` 是同一地址的 VA 形式，不要打那个。
- **第 3 行** 的 `AblEnd` 由 §2.3 的内存图扫描得到：取覆盖 metadata 页 `0xB7FF0000..0xB7FF16FC` 的 `EfiReservedMemoryType` 描述符，再以 `0xB8000000` 为上限收敛；它不是硬编码常量，且只作诊断（真正的门是 `MetadataCovered`）。
- 三行都用 `Print()`，**不能用 `DEBUG()`**：13 的 B4 会在固件源码里 `grep -F "modem-image:"`，只要有一行含 `DEBUG(` 就直接判红。

### 1.7 payload 容量约束（2026-11-16 实测）

§1 的装载逻辑成立的前提是「27 个文件能躺进 payload 卷」。这个前提**在当前卷尺寸下不成立**，
而它跟代码无关，是纯算术。三个数字（全部实测，不是估算）：

| 量 | 值 | 来源 |
| --- | --- | --- |
| payload 卷容量 | **201,326,592 B（192 MiB）** | `board.toml:96` `size_mib = 192` |
| 卷内已用 | 105,524,920 B（`kernel.macho` 105,508,864 + `kernel.macho.adt` 16,056） | `mdir` 实测 |
| 卷内剩余 | **94,990,336 B（90.6 MiB）** | 同上 |
| modem 27 个文件（原始） | **109,060,761 B** | `gen-modem-table.py --manifest` 求和 |
| 同上，按 FAT 4 KiB 簇落盘 | 109,105,152 B（pad 44,391） | 逐文件 `ceil(size/4096)*4096` |

**缺口 = 109,105,152 − 94,990,336 = 14,114,816 B（13.5 MiB）。** 按 manifest 顺序装，到第 21 个
文件（`modem.b23`）累计 99,012,608 B 就超过 94,990,336 B 的剩余空间；它和它之后的 7 个文件
（`b23`..`b30` 段里仍有字节的那些）无处落盘。这与 §2.4 的拷贝循环、§3 的属性发布都无关，是卷本身装不下。

> 上一版笔记里写的「free 87 MB」是早一张镜像的粗略值；以 94,990,336 B 为准（`fdtest-20261116a`，
> 2026-11-16 02:52）。差 8 MB 不改变结论，但会影响下面「最小扩容档」的边界，所以按实测算。

四条出路的代价（A/B/C 沿用 `11-CARRIER.md` §二 的编号，D 是本线新补的一条）：

#### 出路 A：把 payload 扩容

`board.toml` 的 `size_mib` 是整数 MiB，boot.img = payload + 561,152 B（实测恒定），
而 ABL 的 staging 窗口有硬下界（`MemoryMapLib.c:39-51`：上界 `0xB6760000` 是 1 MiB 镜像时的 DTB
落点，下界墙 `0xA8300000` 是 staging 起点，跨度 239,468,544 B）：

| payload | boot.img | image_base | ABL 余量 | 卷内 free | free − 109,105,152 |
| --- | --- | --- | --- | --- | --- |
| 192 MiB | 201,887,744 | `0xAA6D7000` | 37,580,800 | 94,990,336 | **−14,114,816** |
| 196 MiB | 206,082,048 | `0xAA2D7000` | 33,386,496 | 99,184,640 | −9,920,512 |
| 200 MiB | 210,276,352 | `0xA9ED7000` | 29,192,192 | 103,378,944 | −5,726,208 |
| 204 MiB | 214,470,656 | `0xA9AD7000` | 24,997,888 | 107,573,248 | −1,531,904 |
| 205 MiB | 215,519,232 | `0xA99D7000` | 23,949,312 | 108,621,824 | −483,328（差 472 KiB） |
| **208 MiB** | 218,664,960 | `0xA96D7000` | 20,803,584 | 111,767,552 | **+2,662,400** |
| 212 MiB | 222,859,264 | `0xA92D7000` | 16,609,280 | 115,961,856 | +6,856,704 |
| 216 MiB | 227,053,568 | `0xA8ED7000` | 12,414,976 | 120,156,160 | +11,051,008 |
| 220 MiB | 231,247,872 | `0xA8AD7000` | 8,220,672 | 124,350,464 | +15,245,312 |
| 224 MiB | 235,442,176 | `0xA86D7000` | 4,026,368 | 128,544,768 | +19,439,616 |

- **208 MiB 是能装下 27 个文件的最小整数档**，余量只有 2.5 MiB。205 MiB 差 472 KiB 就够，但
  `size_mib` 只能取整数，所以实际最小档是 208。
- 代价：boot.img 从 201,887,744 涨到 **218,664,960 B（+16 MiB）**，ABL 余量从 37.6 MB 降到 20.8 MB。
  后者是硬约束：ABL 余量随 boot.img 1:1 减少，余量归零就是 staging 撞到 `0xA8300000` 的墙
  （`docs/reference/AGENT-COORDINATION.md:1840` 记过这条教训）。20.8 MB 够，但不宽裕。
- `11-CARRIER.md` §2.2 建议的 224 MiB 是按「连 `modem.mdt`/`b00`/`b31` 一起带」
  （109,072,529 B）并留富余算的；只带 27 个装载文件时 208 MiB 就够。**带哪些文件是裁决项，不是算术项。**
- 改 `board.toml` 不在本线 scope（Lead 定），且 13 号门禁的 A1/A2 是硬编码数字
  （`234881024` / `235446272`），一旦改档必须同步改成 `218103808` / `218664960`，否则门禁会假红。

#### 出路 B：编进内核（ADSP 的 `k60_adsp_blob` 那条路）—— 已被内核读上限直接否决

不是「体积紧张」，是**读不进来**：

- `DarwinBoot.c:699` 读内核用 `ReadFile (Root, Request->KernelPath, SIZE_128MB, &Image, &ImageSize)`，
  `ReadFile` 在 `:111-112` 对 `FileSize > Limit` 直接返回 `EFI_BAD_BUFFER_SIZE`。`SIZE_128MB` = 134,217,728。
- 现状内核 105,508,864 + ADT 16,056 = 105,524,920；加 27 文件 109,060,761 ⇒ **214,585,681 B（204.6 MiB）**，
  **超上限 80,367,953 B**。也就是说即使 payload 装得下，DarwinBoot 也读不进内存——这比
  「段跨度上限 254 MiB」更早触发，是决定性的一条。
- 压缩也救不了：整窗 xz -9 = 49,046,916 B（ratio 0.1529）、gzip -9 = 53,409,772 B；加上内核后
  154,571,836 / 159,025,961，**仍超 20,354,108 / 24,808,233 B**。
- 结论：出路 B 在「内核必须过 `ReadFile`」这个既有约束下不可行，与 `11-CARRIER.md` §2.3 的
  「不可行」结论一致，但这里给出了更硬的理由（不是「卷不够」，是「内核读不进来」）。
- **这条上限是通用的，不只针对 modem**：`DarwinBoot.c:699` 的 `SIZE_128MB` 是整台 K60 上
  「把东西编进内核」的硬天花板——内核本体已经 105,508,864 B（78.6% 的上限），剩下约 28.7 MB。
  将来 GPU addon（约 51 MB）、第二个 DSP blob 都过不去，且它比「段跨度 254 MiB」
  （`DarwinBoot.c:196`）**更早**触发，所以任何「内核内嵌」提案都要先过这一关再看别的。
  真要走内嵌，得先单独裁决「抬 `SIZE_128MB`」——那是改一条所有线共用的启动路径，不属本规格。

#### 出路 C：从别处读（分区 / Data 卷）—— 固件侧没有块设备栈

- `uefi-mondrian` 的平台 DSC **没有** UFS 栈：`UfsDxe` 只出现在
  `Silicon/Samsung/SamsungPkg/SamsungPkg.dsc.inc:64`，而 `Platforms/Xiaomi/mondrianPkg/mondrian.dsc:35`
  只 `!include PalimaPkg/PalimaPkg.dsc.inc`；`Platforms/Xiaomi` 下 grep `UfsDxe`/`SamsungPkg` 零命中。
- 现有块栈只有 FAT 这一层：`mondrianPkg/Include/DXE.inc:26-29`（DiskIoDxe / PartitionDxe /
  EnhancedFatDxe / EnglishDxe）、`:6`（RamPartitionDxe）、`:33`（UniXNURamDiskDxe）。
  没有 UFS 驱动 ⇒ 挂不到 `modem_a`（`/dev/block/sde7`，380 MiB）。
- 走这条路要新接 Samsung UFS DXE + `PlatformUfsLib` + GPT 解析，是三条路里唯一需要**新硬件驱动**的，
  风险最高；且它把「固件能不能读盘」变成新的失败面（UFS 初始化失败时连启动都受影响）。
- 内核侧读 `modem_a` 也不通（`11-CARRIER.md` §一：`drivers/NativeUfs/RootCommands.h:289` 的
  `hostRead4k()` 是 `static`，没有 IOKit 导出），所以「固件读盘」不能指望内核替它读。

#### 出路 D（本线补的一条，成本介于 A 与 C 之间）：压缩进 payload

- 27 个文件逐个压缩实测：raw 109,060,761 ⇒ **lzma 48,591,795 B**（ratio 0.446）、gzip 53,205,109 B。
  192 MiB 卷下余量变成 **+46,398,541 B（lzma）**，不需要扩容。
- 但固件侧必须解压：树里有 `Mu_Basecore/MdeModulePkg/Library/LzmaCustomDecompressLib`
  （`LzmaDecompress.c:137` `LzmaUefiDecompressGetInfo`、`:182` `LzmaUefiDecompress`），
  **没有 zlib/inflate**（`Mu_Basecore` 下 `*Inflate*`/`*zlib*` 零命中）⇒ 走 gzip 得自带 inflate，
  走 lzma 只需在 `DarwinBoot.inf` 加一条库。
- **解压是整块，不是流式**：`LzmaUefiDecompress` 的签名是
  `(Source, SourceSize, Destination, Scratch)`，调用方必须提供**完整目标缓冲**；
  `LzmaUefiDecompressGetInfo` 只回 `DestinationSize` 与 `ScratchSize`（`:154` 固定
  `SCRATCH_BUFFER_REQUEST_SIZE` = `SIZE_64KB`，`:14`）。64 KiB 只是概率表的 scratch，
  目标必须按文件整块给出（最大单文件 `modem.b23` 40,935,488 B）。
- 代价一（**已由 §1.7.1 消除**）：目标缓冲不需要中转——`LzmaDecode` 直接把调用方缓冲当字典窗口
  （`Sdk/C/LzmaDec.c:1229-1230`），可以就地解压到窗口内该段的物理地址，§2.2 的「禁止中转」不破例。
  剩下的只是「解压中途失败会留下半写状态」，由「失败一律 `goto Fail` 拒启动」兜住。
- 代价二：§2.4 的「64 KiB 分块直写」循环作废，改成「读压缩文件 → 校验 → 解压到段地址」，
  13 号门禁 A3/A4 的判据从「文件大小 == 段表 `bytes`」改成「解压后大小 == 段表 `bytes`」，
  B5 的表不变；另需一条新判据「payload 里的 modem 文件是压缩形态」，否则 A4 会把压缩尺寸
  当成不符而假红。
- 代价三（构建期）：`xz --format=lzma` 的 8 B 声明大小必须改写成真值，且表里要加一列压缩数据的
  CRC32——理由见 §1.7.1 ③。
- 收益：不动 `board.toml`、不动 ABL 余量、boot.img 尺寸不变。

#### 1.7.1 出路 D 的三个前置问题（2026-11-16 实测作答）

Lead 2026-11-16 05:10 选定 D 之前要求先证明「EDK2 的 `LzmaUefiDecompress` 能直接解压到窗口内的
目标物理地址、不需要 39 MiB 中转」。三问逐条作答，代码依据是
`Mu_Basecore/MdeModulePkg/Library/LzmaCustomDecompressLib/` 下的原文件，实测用同一份
`Sdk/C/LzmaDec.c` 在 host 上编（`E:/k60-work/artifacts/cap/harness2.c`..`harness4.c`）。

**① `Destination` 接受任意物理地址——是，没有分配也没有对齐假设。**

- `Sdk/C/LzmaDec.c:1204` 的 `LzmaDecode (Byte *dest, SizeT *destLen, ...)` 在 `:1229-1230` 直接把
  调用方的缓冲当字典窗口：`p.dic = dest; p.dicBufSize = outSize;`。解码器**不分配输出**，
  也不要求 `dest` 对齐（只有概率表指针按 `Align` 索引，`:793`；`dest` 本身没有强制类型转换写入）。
- 全程唯一的一次分配是概率表：`:1228` `LzmaDec_AllocateProbs` → `:1122` → `:1133`
  `p->probs = ISzAlloc_Alloc (alloc, numProbs * sizeof (CLzmaProb))`，而 `alloc` 就是 `Scratch`
  （`LzmaDecompress.c:195-198` 把 `Scratch` 塞进 `ISzAllocWithData`）。所以「中转缓冲」根本不存在。
- 实测：`dest` 用 `mmap(MAP_FIXED_NOREPLACE)` 钉在 `0x700000000000`（与任何分配无关）并在其后紧跟一页
  `PROT_NONE` 保护页，解压 `modem.b23` 的 40,935,488 B 成功、逐字节等于原文件、保护页未 fault；
  `dest + 1`（非对齐）同样成功且逐字节相等。
- 实测：27 个文件分别钉在 `0x600000000000 + i * 0x4000000` 各自解压 →
  `decoded 27 files, 109060761 bytes from 48591795 compressed, 0 failures, 3.4 s, 32.6 MB/s`
  （host x86、`gcc -O2`；单文件 `modem.b23` 1.68 s ≈ 24.3 MB/s）。
- 结论：**把 `Destination` 直接设成窗口内该段的物理地址即可**，39 MiB 中转不需要。上面「代价一」按此
  收窄为「无中转」，§2.2 的「禁止中转缓冲」原则**不需要破例**。代价只剩「解压中途失败会留下半写状态」，
  由下面的 ③ 和「失败一律 `goto Fail` 拒启动」兜住。

**② 64 KiB scratch 够——够，实测只需 16,256 B。**

- 概率表大小 `LzmaDec.c:157`：`LzmaProps_GetNumProbs (p) = NUM_BASE_PROBS + (0x300 << (lc + lp))`；
  `NUM_BASE_PROBS` = 1984（`:145`，`:151` 有 `#if NUM_BASE_PROBS != 1984 #error`）；`CLzmaProb` 是 2 B。
- 27 个文件用 `xz -9 --format=lzma` 压出的 props 全是 `lc=3 lp=0 pb=2`（dict 声明 64 MiB）⇒
  1984 + (0x300 << 3) = 8128 项 ⇒ **16,256 B**，只占 `SCRATCH_BUFFER_REQUEST_SIZE` = `SIZE_64KB`
  （`LzmaDecompress.c:14`）的 25%。
- props 里的 `dict = 64 MiB` 只是**声明**，解码器不按它分配：`:1229` 是 `dic = dest`、`dicBufSize = outSize`。
  只有走 `LzmaDec_Allocate` 的「字典接口」才按 `dicBufSize` 分配（`:1192`），EDK2 的 one-call
  `LzmaDecode` 不走那条。
- 实测：把 `Scratch` 缩到 16,383 B 仍成功（真实请求 ≤ 16,383 B，与算出的 16,256 B 吻合）；
  `SzAlloc` 是 bump allocator（`LzmaDecompress.c:31-50`），不够时 `ASSERT (FALSE)` 返回 `NULL`。

**③ 解压前的完整性校验——size 字段能，CRC 要自己带。**

- `LZMA_ALONE` 头 = 5 B props + 8 B uncompressed size（`LzmaDecompress.c:71`
  `#define LZMA_HEADER_SIZE (LZMA_PROPS_SIZE + 8)`；`:80-95` `GetDecodedSizeOfBuf` 小端读这 8 B）。
  **格式里没有 CRC 字段**（CRC32/CRC64 属于 `.xz` 容器，不属于 `.lzma`）。
- `xz --format=lzma` 写出的 size 字段是 `0xFFFFFFFFFFFFFFFF`（27 个文件实测全是 18446744073709551615），
  必须由打包工具把它改写成真实大小。否则 `LzmaUefiDecompressGetInfo`（`LzmaDecompress.c:148-153`）对
  `> MAX_UINT32` 返回 `RETURN_UNSUPPORTED`，而 `LzmaUefiDecompress`（`:200`）会把 `destLen` 设成天文数字。
- 实测边界：头未改也能解完并逐字节正确（靠流尾 end mark，`status = LZMA_STATUS_FINISHED_WITH_MARK`）；
  把声明大小改成 `want + 65536` 而流不变时 `res = 0`、`decoded` 仍是 `want` ⇒ **声明偏大抓不住**，
  所以必须另外比 `decoded == 段表 bytes`。反过来，流被破坏（翻转中间一字节）或截断（去掉尾部 64 B）
  都返回 `res != 0`，能在解压结束时报错，但那时窗口已经被写了一部分。
- 因此「写第一个字节之前」能做的校验只有两道：
  1. **声明 size == 段表 `bytes`**（读头 8 B，一行比较）；
  2. **压缩数据 CRC32**：`MdePkg/Include/Library/BaseLib.h:5020` `CalculateCrc32`（实现
     `MdePkg/Library/BaseLib/CheckSum.c:600`），`BaseLib` 已在 `DarwinBoot.inf` 的 `[LibraryClasses]` 里，
     **不新增库依赖**；期望值由构建工具写进表（`K60ModemImageTable.h` 加一列 `crc32`）。
- 半写窗口的处置：本规格要求「任何失败一律 `goto Fail` 拒启动」，所以半写不需要回滚；这两道校验的
  作用是把**可检测的**损坏挡在第一次写之前，剩下的（流损坏）只能解压失败后拒启动。

**结论：D 的三问全部通过，D 可走。** 代价清单因此收敛为两条构建期工作：

1. 打包工具要把 `xz --format=lzma` 产物的 8 B size 字段改写成真实大小（不改则 `GetInfo` 直接拒绝）；
2. `K60ModemImageTable.h` 增加 `crc32` 列（压缩数据的 CRC32），固件侧解压前比对。

**建议（本线的意见，裁决权在 Lead）**：

1. **出路 A 的 208 MiB 档**：唯一「零新代码路径、零新驱动、零解压逻辑」的方案，代价是
   boot.img +16 MiB、ABL 余量从 37.6 MB 降到 20.8 MB（这块余量要留给 GPU addon / audio DSP）。
2. **出路 D**（lzma 进 payload）：§1.7.1 的三问已全部通过，不动 `board.toml`、不动 ABL 余量、
   boot.img 尺寸不变，代价收敛为「固件多一条解压路径 + 构建期改 size 字段并加 CRC32 列 + 门禁 A3/A4 改判据」。
   Lead 2026-11-16 05:10 已选 D；上面第 1 条保留为「D 若在实现中被推翻时的退路」。
3. **出路 B 不要再评估**：`SIZE_128MB` 已经把门关上，任何「内核内嵌」变体都要先改
   `DarwinBoot.c:699` 的上限，那等于改一条所有线共用的启动路径。
4. 出路 C 只在「A/D 都被否」时才值得立项，且它是独立工程（新 UFS DXE），不该塞进本规格。

**与数据源有关的坑（会直接让 13 号 A3/A4 假红）**：`/mnt/e/k60-work/firmware/modem` 里
无扩展名的那 27 个文件是 **CRLF 污染的副本**（`sum_plain` = 109,549,510 B ≠ 109,060,761；25/27 个
文件从第 100~2,180,553 字节起就与 `.bin` 不同）。`scripts/gen-modem-table.py:28-44` 的 `find()`
因此优先取 `.bin`。裁决「文件名不带 `.bin`」指的是 **payload 里的落盘名**，数据源必须继续用
`.bin` 逐字节副本——谁去准备 payload assets，就得照这个来。

### 1.8 D 路线：解压到固定物理地址（2026-11-16 定案）

Lead 2026-11-16 05:38 定路线 D。本节把「GetInfo 预检 → 解压返回 SUCCESS → 失败不发布」三条
安全规则落成可判定门禁，每条带 `文件:行`；命名与落盘结构见 §1.8.5；13 号门禁 A3/A4 的替换
文字见 §1.8.6。**本节仍是规格，拷贝与解压代码尚未写**（Lead 要求路线定案后再写）。

#### 1.8.1 一个段文件的完整流程

1. 打开 `EFI\UniXNU\MODEM`；`modem.b01.lzma` 不在 ⇒ 唯一可继续分支（§2.4 第 1 步，日志
   `no carrier in payload, skipped`）。
2. 读该文件全部内容入池（最大 `modem.b23.lzma` 37,475,838 B；源必须整块，理由见 §1.8.7）。
3. **规则一** `LzmaUefiDecompressGetInfo` 预检（§1.8.2）：四个条件同时成立才允许解压。
4. **规则二** `LzmaUefiDecompress` 直接解压到 `0x8bc00000 + paddr - MODEM_IMAGE_BASE`（§1.8.3）：
   只接受 `RETURN_SUCCESS`。
5. 解压成功后 `ZeroMem` 该段的 bss 部分（`memsz - filesz`，§2.4 第 5 步）。
6. 27 段全绿后一次性打 C2 行，再按 §3 发布属性；任何一步失败 ⇒ **不发布**、`goto Fail`（§1.8.4）。

#### 1.8.2 规则一：GetInfo 预检（解压前，四条全成立才允许解压）

`LzmaUefiDecompressGetInfo (IN CONST VOID *Source, IN UINT32 SourceSize, OUT UINT32 *DestinationSize,
OUT UINT32 *ScratchSize)` — `Mu_Basecore/MdeModulePkg/Library/LzmaCustomDecompressLib/LzmaDecompress.c:137-156`。

| 条件 | 判据 | 依据 |
| --- | --- | --- |
| a | `SourceSize >= 13` **由我们判** | `:146` 只有 `ASSERT (SourceSize >= LZMA_HEADER_SIZE)`，release 构建不执行，漏判则 `:148` 越界读 8 B |
| b | 返回 `RETURN_SUCCESS` | `:148` 读 8 B 声明长度；`:149-151` `DecodedSize > MAX_UINT32` ⇒ `RETURN_UNSUPPORTED`（`xz --format=lzma` 默认写 `0xFFFFFFFFFFFFFFFF`，**27 个实测全是**，不改写则每个文件都在这里被拒） |
| c | `*DestinationSize == 段表 bytes`（相等，不是 ≥） | 实测声明偏大 65,536 B 时 `LzmaDecode` 仍 `res=0`、`decoded` 恰为真实长度（`E:/k60-work/artifacts/cap/harness5.c`）⇒ 偏大抓不住 |
| d | `*ScratchSize <= 64 KiB` | `:14` `SCRATCH_BUFFER_REQUEST_SIZE = SIZE_64KB`、`:154` 原样回填；我们给 64 KiB 静态缓冲，EDK2 若改成更大值必须在这里红 |

通过后把 `DestinationSize` 记成「应写字节数」——它同时是 §2.4 第 4 步的循环上界、13 号 A4 的
判据、以及 C2 行 `copied` 的累加项。

#### 1.8.3 规则二：解压返回 SUCCESS（解压中，唯一可接受的返回值）

`LzmaUefiDecompress (Source, SourceSize, Destination, Scratch)` — `:182-219`：

- `:200-201` `DecodedBufSize = GetDecodedSizeOfBuf (Source)`、`EncodedDataSize = SourceSize - 13`；
- `:203-213` `LzmaDecode (Destination, &DecodedBufSize, Source + 13, &EncodedDataSize, Source,
  `LZMA_PROPS_SIZE, LZMA_FINISH_END, &Status, &AllocFuncs.Functions)`；
- `:215-219` `Status == SZ_OK ? RETURN_SUCCESS : RETURN_INVALID_PARAMETER` —— **不区分
  `SZ_ERROR_DATA` / `SZ_ERROR_INPUT_EOF` / `SZ_ERROR_MEM`**。所以门禁只认 `RETURN_SUCCESS`，
  其余一律拒启动（P-204：不许把「没检查」当成「检查通过」）。

`Destination` 可以直接是窗口物理地址，不需要中转（§1.7.1 的实测复核）：

- `Sdk/C/LzmaDec.c:1229-1230` `p.dic = dest; p.dicBufSize = outSize;` ⇒ 解码字典就是调用方给的缓冲区；
- 唯一的堆分配是概率表：`:1228 → :1133 ISzAlloc_Alloc (alloc, numProbs * sizeof (CLzmaProb))`，
  实测 8,128 项 × 2 B = **16,256 B**，落在 `Scratch`（`:195-198` 把 `Scratch` 当 `ISzAlloc` 的
  bump 缓冲，`SzAlloc` 见 `LzmaDecompress.c:31-50`）；
- 实测：`dest` 钉在 `0x700000000000` 且紧接 `PROT_NONE` 页，解 `modem.b23` 40,935,488 B 逐字节
  相等、保护页未 fault；27 个文件合计 109,060,761 B 全部成功（`E:/k60-work/artifacts/cap/harness2.c`
  – `harness4.c`，用 EDK2 原文件编）。

三条必须写进代码的补充判据：

1. **窗口是「非缓存」，不是「不可执行」**：`Platforms/Xiaomi/mondrianPkg/Library/MemoryMapLib/MemoryMapLib.c:31`
   用 `UNCACHED_UNBUFFERED`；`Silicon/Silicium/SiliciumPkg/Include/Library/MemoryMapLib.h:100-110` 把
   `UNCACHED_UNBUFFERED_XN` 与 `UNCACHED_UNBUFFERED` 定义成同一个
   `ARM_MEMORY_REGION_ATTRIBUTE_UNCACHED_UNBUFFERED`；`Mu_Basecore/UefiCpuPkg/Library/ArmMmuLib/AArch64/ArmMmuLibCore.c:93-94`
   对它是 `TT_ATTR_INDX_MEMORY_NON_CACHEABLE | Permissions`，而 `Permissions` 只在 `DEVICE` /
   `WRITE_BACK_XP` 分支非零（`:66-78`）⇒ **窗口页属性没有 XN 位，既不需要也无法在解压前「清 XN」**。
   真正相关的是写直达：`:877 MAIR_ATTR (TT_ATTR_INDX_MEMORY_NON_CACHEABLE, MAIR_ATTR_NORMAL_MEMORY_NON_CACHEABLE)`
   ⇒ 解压写进去立刻对其它 master 可见，不需要 `FlushRange`（`DarwinBoot.c:47-59` 是缓存版写法，本路线不用）。
2. **Scratch 耗尽会静默失败**：`LzmaDecompress.c:31-50` 的 `SzAlloc` 是 bump 分配器，不够时
   `ASSERT (FALSE)` 后 `return NULL` ⇒ `LzmaDec_AllocateProbs` 回 `SZ_ERROR_MEM` ⇒ 包装层只剩
   `RETURN_INVALID_PARAMETER`。release 构建 ASSERT 不生效，所以不能靠「没崩」判断成功。
3. **解压后无法从返回值得知写了多少字节**：`LzmaUefiDecompress` 的 `DecodedBufSize` 是局部变量、
   不出参（`:200`、`:203`），`LzmaDecode` 的 `*destLen`（`LzmaDec.c:1234`）也被丢弃 ⇒ 「实际写入 ==
   「段表 bytes」只能靠规则一的 `DestinationSize` 与构建期 CRC32 兜住（§1.7 代价三）。**不要**
   读窗口回比——那是 306 MiB 非缓存读。

#### 1.8.4 规则三：失败不发布（解压后）

| 结果 | 固件动作 | 日志字面量（13 号 `grep -F` 锚点） |
| --- | --- | --- |
| 27 段全部 `RETURN_SUCCESS` 且 CRC 全对 | 写 `K60ModemImage`（§3.2）并打 C2 行 | `modem-image: 30 segments, copied 109060761, zeroed 211012967, gaps 790528 untouched` |
| `GetInfo` 任一条件不成立 | 不写属性、`goto Fail` | `modem-image: modem.bNN header says X, table says Y` |
| `LzmaUefiDecompress != RETURN_SUCCESS` | 不写属性、`goto Fail` | `modem-image: modem.bNN did not decompress (%r)` |
| CRC32 不符 | 不写属性、`goto Fail` | `modem-image: modem.bNN crc 0x… expected 0x…` |
| 目录不存在 | 不写属性、继续启动 | `modem-image: no carrier in payload, skipped` |

半写窗口在 PAS1 认证前无害，两条理由：窗口不是 Boot Services 资源，没人会 `FreePages` 它（§2.1）；
内核侧在 PAS1 认证成功前不会 publish mpss（`drivers/PongCellular/K60ModemPas.c` 的
`k60_modem_pas_probe` 是唯一发布者）。但**日志必须能把「载具没实现」与「解压失败」分开**——
这正是 P-197 的形状：有 `copied` 行却 `carrier absent` 是最严重的一类。

#### 1.8.5 payload 里的命名与落盘结构

**结论：27 个段各一个文件，名字 = 段表 `name` + `.lzma`**，即 `EFI\UniXNU\MODEM\modem.b01.lzma`
… `modem.b30.lzma`。`modem.b14/b21/b30` 是 bss-only（`bytes == 0`），没有文件，直接 `ZeroMem`。

| 选项 | 结论 | 理由 |
| --- | --- | --- |
| 逐段 `.lzma`（选定） | 27 个文件 | 段表仍是唯一数据源（`gen-modem-table.py --manifest` 只多一个后缀）；每段独立校验、独立 CRC；单文件最大 37.5 MB |
| 单个 `modem.lzma` 容器 | 否决 | 要新增容器头（P-169 自造字段表）；整包 48.6 MB 必须一次性入池；一段坏要整包重来；CRC 只能全窗一个 |

落盘要点：

- 文件内容 = `xz --format=lzma -9` 的原始输出，**但 8 B size 字段必须改写成真实 `bytes`**
  （`LzmaDecompress.c:148` 读它；默认 `0xFFFFFFFFFFFFFFFF` 会被 `:149-151` 拒）。
- 不加外层头、不加扩展名以外的元数据；13 B 头（5 B props + 8 B size）就是格式本身。
- FAT 4 KiB 簇：27 个文件 48,591,795 B ⇒ 卷内占 **48,652,288 B**（pad 60,493）；192 MiB 卷
  `free` 94,990,336 ⇒ 余 **46,338,048 B**。
- props 首字节实测全为 `0x5D`（lc=3 lp=0 pb=2）；打包工具必须保留原 props，不许重编码。
- 数据源仍是 `/mnt/e/k60-work/firmware/modem` 的 `.bin` 副本（CRLF 陷阱见 §1.7 末），压缩是
  **打包期**动作，不进仓库。

#### 1.8.6 13 号门禁 A3/A4 的替换文字

给 13 号表 A 直接替换的五行（A1/A2 走 D 仍是 192 MiB 档；**A-208 的 218,103,808 / 218,664,960
不再使用**）：

| 行 | 断言 | 工具与命令（WSL） | 通过标准 |
| --- | --- | --- | --- |
| A1 | payload 卷恰好 192 MiB | `stat -c %s "$PL"` | `== 201326592` |
| A2 | boot.img 恰好 201,887,744 B | `stat -c %s "$BOOT"` | `== 201887744` |
| A3 | `EFI/UniXNU/MODEM/` 恰好 27 个文件，名字 = manifest 名字列各加 `.lzma` | `mcopy -o -s -i "$PL" '::EFI/UniXNU/MODEM/*' /tmp/accept-modem` 后 `ls` 与 `gen-modem-table.py --manifest` 名字列（加 `.lzma`）diff | 行数 27 且 diff 空 |
| A4 | 每个文件 13 B 头合法、props 首字节 `0x5D`、8 B 声明长度 == 段表 `bytes` | `python3 scripts/check-modem-lzma.py --dir /tmp/accept-modem --manifest <manifest>` | rc 0；任一文件声明长度 ≠ `bytes`、props ≠ `0x5D`、size == `0xFFFFFFFFFFFFFFFF` 即 rc 1 |
| A6 | 头里声明长度总和 == 109,060,761（= C2 的 `copied`） | 同 A4 脚本的 `--sum` 输出 | `== 109060761` |

**「拷贝字节数 == 段表 bytes」这句话在 D 下作废**，改成「`GetInfo` 的 `DestinationSize` ==
「段表 `bytes`，且解压返回 `SUCCESS`」。C2 的 `copied 109060761` 现在指「解压后写入的字节总和」，
判据仍是日志字面量（13 号 C2）。

#### 1.8.7 D 的新代价：DXE 堆峰值多 37.5 MB（不改 ABL、不改 boot.img）

- 压缩源必须整块入池：`LzmaUefiDecompress` 要完整 `Source`（`:200-201` 用 `SourceSize` 算
  `EncodedDataSize`，`:203` 把 `Source` 当 props），不能像 §2.4 第 4 步那样 64 KiB 分块 ⇒ 峰值 =
  最大单文件 `modem.b23.lzma` **37,475,838 B**。
- 与 DarwinBoot 自己读内核的 105,508,864 B 池**同时存在**（`:699` 读内核、`:821` 才释放，而载具
  插在 `:721` 之后）⇒ 峰值 ≈ 105.5 + 16 KB + 37.5 = **143 MB**，DXE 堆 384 MiB
  （`MemoryMapLib.c:76-83`）够，但这是 D 唯一的固件侧内存代价。
- 目标侧零缓冲（直接写窗口）⇒ §2.2「禁止中转缓冲」仍成立：被禁止的是 39 MB 的**目标**块，不是
  37.5 MB 的**源**块。
- 代价二（§1.7 的「§2.4 分块循环作废」）现在明确：§2.4 第 4 步的 64 KiB 分块只用于**读文件**，
  写入改为「整块解压到窗口」。

#### 1.8.8 实现期抓到的坑：`LzmaDecode` 的 `*srcLen` 是「已消费」不是「剩余」

2026-11-16 在宿主用同一份 `Sdk/C/LzmaDec.c` 跑 27 个真 `.lzma` 时，**首轮 27/27 全部报
`modem-image: %a did not decompress (Invalid Parameter)`**，而文件本身完好。真因不在文件、也不在
props，而在包装层对 `srcLen` 出参的误读。

- 调用形状：`LzmaDecode (Dest, &DestLen, Source + 13, &SourceLength, Source, LZMA_PROPS_SIZE,
  LZMA_FINISH_END, &Status, &Alloc)`，其中 `SourceLength` 入参 = `SourceSize - 13`。
- `Sdk/C/LzmaDec.c:1219-1234`：函数先把 `*srcLen` 置 0（`:1221`），进 `LzmaDec_DecodeToDic`
  后由 `:1232` 的 `*srcLen = inSize` 暂存入参，**返回前 `:1233` 把它改写成「已消费的输入字节数」**。
  所以出参语义是 *consumed*，不是 *leftover*。
- 错误判据（第一版代码）：`if (SourceLength != 0) return RETURN_INVALID_PARAMETER;` ——
  按「剩余必须为 0」写，于是每个文件都被判失败，且错误串长得像「文件坏了」，极易把排查引向
  打包侧（P-204 家族：判据的形状错了，报错文本却指着一个无辜的对象）。
- **正确判据**：`if (SourceLength != (SizeT)(SourceSize - CARRIER_HEADER_SIZE))
  return RETURN_INVALID_PARAMETER;` —— 解压器必须**正好消费掉 13 B 头之后的全部字节**，
  少消费说明尾部有垃圾、多消费说明越界，两种都拒。
- 判据之外还要求 `Status ∈ {LZMA_STATUS_FINISHED_WITH_MARK, LZMA_STATUS_MAYBE_FINISHED_WITHOUT_MARK}`
  （`LzmaDec.h:108-114` 五个枚举里只认这两个；`SZ_OK` 本身不区分「解完了」与「输入不够」）。

宿主 harness 的实测（`E:/k60-work/artifacts/host/lztest.c`，用 EDK2 原文件编，不依赖固件）：

- 分配器：`typedef struct { ISzAlloc Funcs; unsigned char *buf; size_t cap; size_t used; } POOL;`
  —— **`Funcs` 必须是第一个成员**，因为 `LzmaDecode` 拿到 `ISzAllocPtr` 后会直接把它当 `POOL *`；
  第一版没放首位 ⇒ 解到一半 Segmentation fault（宿主上是段错误，固件里会是静默写坏窗口）。
- 语料：从 `K60ModemImageTable.h` 抽 30 行（含三个 `((const char *)0)` 的 bss-only 段），
  27 个 `.lzma` 从已改写 8 B 声明长度的 `payload-modem.img` 里 `mcopy` 抽出。
- 结果：**files 27 ok 27 fail 0**；每个文件的概率表用量恰好 **16,256 B**（8,128 项 × 2 B），
  远小于 64 KiB scratch ⇒ `CARRIER_SCRATCH_SIZE = SIZE_64KB` 有余量；`modem.b23` 37,475,838 B
  压缩源解出 40,935,488 B 且逐字节等于原始 `.bin`。
- 该 harness 的价值：解压一旦在真机上出错就是黑屏，而黑屏不告诉你是哪个文件、哪一步；
  在宿主用**同一份解码器源码 + 真语料 + 逐字节比对**能提前把这类错误全部消灭。

## 2 内存

### 2.1 三种写法的判决

| 方案 | 会发生什么 | 证据 | 结论 |
| --- | --- | --- | --- |
| `AllocatePool (306 MiB)` | DXE 堆只有 384 MiB（`0xC7000000` + `0x18000000`），且 UniXNU 的 52 MiB 内核镜像常驻其中；池块不保证物理连续，拿到的地址也不是 `0x8BC00000` —— 而 modem 按绝对地址取指（段表里 `paddr` 就是 `0x8BC00000` 起） | `MemoryMapLib.c:76-83` | 不可行 |
| `AllocatePages (AllocateAddress, ..., 0x8BC00000)` | 该区间在内存图里是 `MEM_RES` / `EfiReservedMemoryType`（不是 Conventional），分配器直接 `EFI_NOT_FOUND`；而且这段本来就不属于「谁分配谁拥有」，它属于 modem | `MemoryMapLib.c:31`；`DarwinBoot.c:478` 只认 Conventional | 不可行 |
| **固定地址直写 `0x8BC00000`** | 图里已有 identity mapping（`AddMem`，`:31`），属性 `UNCACHED_UNBUFFERED_XN` ⇒ 不需要 cache 维护，也不会被分配器挪走 | `MemoryMapLib.c:31`、`:94` 的 `AddMem` 注释 | 唯一可行 |

### 2.2 与 4.5 GiB 连续窗口的冲突分析

- 窗口来自 `XNU High Arena` `0x900000000`（`MemoryMapLib.c:94`；`docs/plans/MEMORY-12G-PLAN.md:49-50`；`board.toml:235` 的 `owned_memory_size = 0x120000000`）。
- `AllocateWindow` 只扫 Conventional（`DarwinBoot.c:478`），按 `:483-484` 取一段 ≥ `WindowSize` 的连续区；`0x8BC00000` 那段是 Reserved，不会被它选中，也不会因为载体占用来回挪。
- **真正的冲突只有一种**：把 306 MiB 的「中转缓冲」放进低区池/堆，就会挤压 `:483` 那次 256 MiB 连续分配。`:76-83` 记录过一次堆只有 320 MiB 时 `biggest run 0xF0A0000` 的失败。所以规格禁止中转：文件流式直写目标地址（§2.4 第 5 步）。
- 结论：载具不影响窗口，`AllocateWindow` 不需要为它跳过任何东西。

### 2.3 写之前的内存图校验

不能只信编译期常量，必须先 `GetMemoryMap` 确认 `[Base, Base+Span)` 仍被一个非 Conventional 描述符完整覆盖：

1. 两遍调用 `gBS->GetMemoryMap`（第一遍 `Size = 0` 拿 `EFI_BUFFER_TOO_SMALL`，再 `AllocatePool`），照 `DarwinBoot.c:343-359` 的 `GetMap` 逻辑（带 3 次尝试）。
2. 找 `PhysicalStart <= Base` 且 `PhysicalStart + NumberOfPages * 4096 >= Base + Span` 的描述符；找不到，或 `Type == EfiConventionalMemory` ⇒ `modem-image: window 0x8bc00000..0x9ee00000 is not reserved, refusing`，硬失败。
3. 同时记录两个覆盖门：metadata 页 `0xB7FF0000..0xB7FF16FC` 与 IPA 固定窗口 `0x8B900000..0x8B90E000` 都必须被 `EfiReservedMemoryType` 描述符完整覆盖；任一不覆盖就硬失败。`AblEnd` 仅作为诊断数，取覆盖 metadata 的保留描述符终点并以 `0xB8000000` 收敛，不再单独决定是否阻断。

为什么要查：`MemoryMapLib.c` 的数组是构建期写进去的，真机上 `GetMemoryMap` 反映的是 HOB 处理后的结果。`ABL Staging` 的教训（`MemoryMapLib.c:39-51`）就是「数组里有的段没进描述符 ⇒ 首次读 translation fault」。

### 2.4 拷贝循环（27 个文件 → 30 行表）

1. 打开目录：`Root->Open (Root, &Dir, L"EFI\\UniXNU\\MODEM", EFI_FILE_MODE_READ, 0)`。`EFI_NOT_FOUND` ⇒ 打 `modem-image: no carrier in payload, skipped`，返回 `EFI_SUCCESS` 且 `Carrier->Files = 0`（**唯一允许继续启动的分支**，12 §四 第 1 条）。
2. 打开 `modem.b01` 当哨兵：它不在 ⇒ `modem-image: modem.b01 missing`，硬失败（避免「目录在但是空的」被当成合法跳过）。
3. 逐行走 30 行：`bytes == 0` 的行（`b14`/`b21`/`b30`）没有文件，直接对 `paddr` 处 `ZeroMem (bss)`。
4. `bytes > 0` 的行：打开同名文件，取 `EFI_FILE_INFO.FileSize`，必须等于表里的 `bytes`，否则 `modem-image: <name> size <actual>, table says <expected>`，硬失败。**文件名不带 `.bin`**：表里就是 `modem.b01`，manifest 同名，13 的 A3 按名字集合比对。
5. 读：`AllocatePool (64 * 1024)` 一次，循环 `File->Read` 直到 `bytes` 写完，每次直接落到 `Base + (paddr - Base)` 的目标偏移。**不要先整文件入池**——`ReadFile`（`:85-125`）就是整文件 `AllocatePool`，`b21` 的 163 MB 会直接把堆打穿。
6. 每段拷完补 bss：`ZeroMem (target + bytes, bss)`。**不要整窗清零**：13 的 B6 会红，而且空洞必须保持原样（12 §2.3）。
7. 累计 `Copied`、`Zeroed`；收尾算 `Gaps = MODEM_IMAGE_WINDOW - Copied - Zeroed`，必须是 `790528`。
8. 打印 `modem-image: 30 segments, copied 109060761, zeroed 211012967, gaps 790528 untouched`（13 的 C2 逐字符比对，所以这一行必须一次打全、数字用 `%d` 拼出来）。
9. 表自身的校验：行数 = `MODEM_IMAGE_SEGMENTS`、每行 `paddr` 4 KiB 对齐、`paddr + bytes + bss <= Base + Window`、`name == NULL` 当且仅当 `bytes == 0`、末行结束于 `Base + Window`；任一不满足 ⇒ `modem-image: row N ...` / `modem-image: table inconsistent`，硬失败（12 §四 第 3-5 条）。

### 2.5 缓存与可见性

- 目标属性来自 `MemoryMapLib.c:31` 的 `UNCACHED_UNBUFFERED_XN` ⇒ 写直达内存，**不需要** `FlushRange`；`DarwinBoot.c` 里 `FlushRange` 只用在音频 DMA（`:762`）和 trampoline（`:782`，定义在 `:49`）。
- 如果将来有人为了「拷得快」把 `mpss_region` 改成 `WRITE_BACK`，必须在 PAS 之前对整段做 clean（`FlushRange` 或 `ArmCleanDataCacheToPoU`），否则 modem 取到旧字节。这一句写进实现注释里，别只写在文档里。
- 不要改 `:31` 的属性：这段是 modem 与 AP 共享的窗口，非缓存是当前唯一验证过的选择。

### 2.6 2026-11-18 k14 M2 启动失败与 fixed-window 载具

k14 M2 C 镜像（boot `002d9a57...`，payload `c-diagnostic-m2`，内嵌 UEFI FD `e007de8a...`）在 16:11 启动后停在 UEFI 菜单：DXE 日志只有 `UNIXNU: xnu: handing off 0 staged kext(s) to loader`，随后 `UNIXNU: menu: entry 0 returned Device Error`（00:03:42.711 与 00:06:40.644 两次），XNU 从未开始，串口没有内核日志。这不是 0621 的 io_submap 早期 panic（k14 已含 0621），也不是 IPA M2 内核 panic，而是 **DarwinBoot 的 MODEM CARRIER 阶段**。

离线取证把常见怀疑排除：payload 内 kernel 与 ADT 的 SHA-256 与 `payload.json` 一致；FAT 链全部连续；27 个 `.lzma` 都存在且 LZMA-alone 头声明长度与 `K60ModemImageTable.h` 逐行相等；修正解析顺序后 LFN/SFN 校验和也全部匹配；k14 与可启动 k15 的内嵌 UEFI FD 字节相同，所以不是 FD 差异。失败点因此落在 `ImageCarrierLoad()` 的读文件/内存图路径，而不是内核或 IPA。

源码复核另发现一个风险，但它**没有**在 16:11 的现场得到证明：旧 FD 在 `CarrierLoadSegment()` 读完 13 字节 LZMA 头后可能没有可靠的 `SetPosition(0)` 回绕，整文件读会短 13 字节并返回 `EFI_DEVICE_ERROR`；工作树已经补上回绕（`ImageCarrierLib.c:719-730`），但 k14 镜像用的是旧 FD，不能代表新代码。把这条当作待验证假设，不能当作 16:11 的根因。

修复方向是把 IPA 固件也改成 **固定窗口载具**，与 modem 载具同一条 DXE 路径：

- `ImageIpaLoad()`（`ImageCarrierLib.c:1049-1168`）在 MODEM CARRIER 之后、ramdisk/trustcache 之前运行，打开 payload 根目录 `\IPA\ipa_fws.mbn`，要求 1..`0xE000` 字节，清零并写入 `0x8B900000`，回写 cache 后打印 `ipa-image: %d bytes at 0x%lx`；没有 `\IPA` 时打印 `ipa-image: no IPA directory, skipped` 并继续。
- `CarrierScanMap()` 同时要求 metadata 页 `0xB7FF0000..0xB7FF16FC` 和 IPA 窗口 `0x8B900000..0x8B90E000` 被 `EfiReservedMemoryType` 完整覆盖，任一缺口硬失败（`ImageCarrierLib.c:163-280`）。
- XNU 侧 `k60_ipa_probe_from_handoff()` 只映射 `0x8b900000` 的前 `0xE000` 字节，再调用 `k60_ipa_firmware_start()`；不再读 payload FAT，也不再依赖 md0。md0 的旧路线是手工拼接镜像里的 `vmd0=0x83b5000.0x2000000` 由 XNU `memdev.c` 创建，首次 FAT 读触发 synchronous external abort `esr 0x96000010`，不可复用。

UEFI 侧提交 `05df05f`（`wip/m2-carrier-debug`）包含上述两段；新 FD `E:/k60-work/artifacts/uefi-debug/SILICIUM_UEFI.carrierfix-fixedwindow.fd` 为 3,145,728 B、sha256 `9b7155f674f2654334cf5c97260e5cd36844e7d3ba8786b4dd9c39d62599c1f8`，Clean DEBUG 构建。它已经进入 k16 的八个启动镜像（标准与 M2 各四张，共享 kernel `03a3aeab`，boot 均 201,895,936 B），但还没有上机验证；k16 镜像显式嵌入这个 FD，没有使用旧的 active `e007de8a`。在 fixed-window C-M2 上机并取得串口证据之前，M2 仍然只能记为“代码完成、硬件未观察”。

## 3 发布 K60ModemImage

### 3.1 构建期：ADT 里先有 16 字节占位

- k60-cellular 的 `scripts/make-pong-adt.py:231-233` 里 `memory-map` 子节点现在只可能有 `PackedRAMDisk`；加一行 `("K60ModemImage", bytes(16))`，**无条件**（不挂任何开关）。
- 为什么必须无条件：13 的 A5 要求「有 `K60ModemImage` ⇒ 长度 16 且值 ∈ {(0,0), (base,span)}」；12 §3.7 第 2 条要求「卷里有 `MODEM/` ⇒ 属性必须存在」。固件要写它，就得先有占位。
- 构建期检查按 12 §3.7 的三条加到 `scripts/pong_adt_contract.py`（本线负责，不在 uefi-mondrian）。

### 3.2 运行时：定位偏移并写 16 字节

```c
  WriteUnaligned64 ((UINT64 *)(UINTN)((UINT8 *)Tree + Offset),     MODEM_IMAGE_BASE);
  WriteUnaligned64 ((UINT64 *)(UINTN)((UINT8 *)Tree + Offset + 8), MODEM_IMAGE_WINDOW);
```

- 写之前先判这 16 字节全零：非零 ⇒ `modem-image: range already published`，硬失败（照 `DarwinBoot.c:726-727` 的先例：占位非零即视为损坏）。
- 只需要 `<Library/BaseLib.h>` 的 `WriteUnaligned64`（`DarwinBoot.c:803-804` 已在用同样的写法）。
- 属性名 `K60ModemImage` 是 32 字节名域里的逐字符比较，其余补零。

### 3.3 时机

- 必须早于 `:801` 的 `CopyMem`：那一刻 `Tree`（池里）被复制进窗口，之后 `:819` 就 `FreePool` 了。所以在 `:721` 之后、`:801` 之前写进 `Tree`。
- 不要写进 `TreeAddress`（窗口里的那份副本）：那要把调用挪到 `:801` 之后，失败路径就会带着已经分配好的 256 MiB 窗口回滚（`:911` 的 `FreePages`），多一层回退，没有必要。
- 分工：**库写属性**（与拷贝同源，一次调用完成两件事），**`Boot.c` 读回并打印发布行**。`Boot.c` 里因此会真的出现 `K60ModemImage` 字面量（13 的 B3 只数 `DarwinBoot.c` 里的出现次数，≥2 才绿：一次是 `AdtFindMemoryMapProperty` 调用的属性名，一次是发布行）。

`Boot.c` 里的发布行（12 §生成日志第 5 行）：

```c
  Print (L"modem-image: range 0x8bc00000..0x9ee00000 published as K60ModemImage\n");
```

### 3.4 属性查询 API（库内部）

```c
STATIC
EFI_STATUS
AdtFindMemoryMapProperty (
  IN  CONST VOID   *Tree,
  IN  UINTN         TreeSize,
  IN  CONST CHAR8  *Name,
  OUT UINTN        *Offset,
  OUT UINT32       *Length
  );
```

返回 `EFI_SUCCESS` / `EFI_NOT_FOUND`（没有该属性）/ `EFI_COMPROMISED_DATA`（节点或长度不对）。第一版做 `STATIC` 就够；将来别的属性也要查时再抽到 `mondrianPkg/Include/Library/AdtLib.h`（此文件不存在，需新建）。

### 3.5 include 清单

库 `.c`：`<Uefi.h>`、`<Guid/FileInfo.h>`、`<Library/BaseLib.h>`、`<Library/BaseMemoryLib.h>`、`<Library/DebugLib.h>`、`<Library/MemoryAllocationLib.h>`、`<Library/PrintLib.h>`、`<Library/UefiBootServicesTableLib.h>`、`<Protocol/SimpleFileSystem.h>`、`<Library/ImageCarrierLib.h>`、`<K60ModemImageTable.h>`。

内存图用 `gBS->GetMemoryMap`，**不要**引 `MemoryMapLib.h`（那是构建期建 HOB/映射用的，不是查询接口）。`DarwinBoot.c` 只多一个 `<Library/ImageCarrierLib.h>`。

### 3.6 属性内容的边界

- 只有 16 字节：u64 `base` + u64 `span`。**`span` 是窗口，不是拷贝量**（12 §3.6、14 §1.3）：消费者一律用段表算拷贝量。
- 不写段表、不写文件数、不写 hash：段表在固件里是 `K60ModemImageTable.h`，在内核里是 `pong_modem_table.h`，属性不是第二份真值（防 P-169 的自造字段表）。
- 全零 = 未发布。内核现在**不读**它（`K60ModemBoot.c:124-139` 用常量映射 + 16 B 签名自检），所以写错不会改内核行为，但会让 13 的 A5 红——门禁就是为这个存在的。

## 4 失败语义

### 4.1 固件侧的行（沿用 12 §四，补「谁打」）

| 情况 | 打印（源码里的字面量） | 返回码 | 谁打 | 拒绝启动 |
| --- | --- | --- | --- | --- |
| 卷里没有 `MODEM/` | `modem-image: no carrier in payload, skipped` | —（`EFI_SUCCESS` + `Files = 0`） | 库 | 否 |
| 目录在、缺文件 | `modem-image: modem.bNN missing` | `EFI_NOT_FOUND` | 库 | 是 |
| 文件大小 != 表 | `modem-image: modem.bNN size 12345, table says 67890` | `EFI_COMPROMISED_DATA` | 库 | 是 |
| 行越界 | `modem-image: row N outside 0x8bc00000..0x9ee00000` | `EFI_COMPROMISED_DATA` | 库 | 是 |
| 行未 4 KiB 对齐 | `modem-image: row N paddr 0x... unaligned` | `EFI_COMPROMISED_DATA` | 库 | 是 |
| 表不自洽 | `modem-image: table inconsistent` | `EFI_COMPROMISED_DATA` | 库 | 是 |
| 属性已非零 | `modem-image: range already published` | `EFI_COMPROMISED_DATA` | 库 | 是 |
| 内存图不覆盖窗口 | `modem-image: window 0x8bc00000..0x9ee00000 is not reserved, refusing` | `EFI_DEVICE_ERROR` | 库 | 是 |
| 读错误 | `modem-image: read modem.bNN failed: %r` | `EFI_DEVICE_ERROR` | 库 | 是 |

拒绝启动不需要新机制：`Fail:`（`:898-913`）会画 `BOOT FAILED <stage> <status>`、打 `DARWINBOOT: boot refused: %r; firmware retained`、回菜单。`Stage` 由调用点设成 `L"MODEM CARRIER"`。

### 4.2 内核侧对应的行（本线已落地，行号是 k60-cellular HEAD）

| 内核打印 | 文件:行 | 含义 |
| --- | --- | --- |
| `K60MODEM carrier absent: no modem image staged at 0x8bc00000` | `K60ModemBoot.c:134` | 头页 16 B 签名不对 |
| `K60MODEM pas skipped, nothing was handed to the secure monitor` | `K60ModemBoot.c:136` | 因此没发任何 SMC |
| `K60MODEM carrier present at 0x8bc00000` | `K60ModemBoot.c:139` | 签名命中 |
| `K60MODEM plan rows=30 copied=... zeroed=... base=... window=...` | `K60ModemBoot.c:48` | 段表计划校验通过 |
| `K60MODEM plan failed rc=n` | `K60ModemBoot.c:45` | 段表自身有问题（不该出现） |
| `K60MODEM auth_reset ok` / `auth_reset failed rc=n` | `K60ModemBoot.c:70` / `:67` | PAS peripheral 4 第一步 |
| `K60MODEM init_image failed seg=n addr=0x... bytes=n rc=n` | `K60ModemBoot.c:81` | 段级失败，带段号 |
| `K60MODEM mem_setup failed rc=n` | `K60ModemBoot.c:92` | 最后一步 |
| `K60MODEM scm cmd=0x... rc=n x0=0x... x1=0x...` | `K60ModemPas.c:53` | SMC 原始返回 |
| `K60MODEM qrtr: glink fifo not fresh (...), not adopted` | `K60ModemLink.c:211` | 设计行为：活 FIFO 不 reset |
| `K60MODEM qrtr: verdict ok|no reply services=N node0=M wanted=K ...` | `K60ModemLink.c:262` | L3 判据 |

### 4.3 判定矩阵：载具没实现 / 载具跑了 / PAS 失败 / QRTR 失败

内核的 `carrier absent` **只能说明 `0x8BC00000` 的头 16 字节不对**，它区分不了「固件没做载具」和「固件做了但没写对」。真正的判据是固件侧有没有 `modem-image:` 行：

| 固件日志 | 内核日志 | 结论 |
| --- | --- | --- |
| 有 `no carrier in payload, skipped` | `carrier absent` + `pas skipped` | 合法形态：卷里确实没装镜像，不是故障 |
| **完全没有** `modem-image:` 行 | `carrier absent` + `pas skipped` | 载具没实现（P-197 形态），不是 QRTR/PAS 问题 |
| 有 `30 segments, copied ...` | `carrier absent` | **最严重**：写了但地址或内容不对，只查这一种 |
| 有 `30 segments, copied ...` + 发布行 | `carrier present` + PAS 失败行 | 进 PAS/SCM 领域（peripheral=4、CX/MX 电源域） |
| 同上 | `carrier present` + `qrtr: ... not fresh` | GLINK epoch 问题，不是镜像问题 |

### 4.4 为什么只有「目录不存在」允许继续启动

这张 payload 是共用的（display/audio/wifi 的镜像也走它）。没装 modem 镜像不该把别人的镜像变成砖。而「目录在但缺文件 / 大小不对 / 表不自洽」说明装载器与表已经不同源，继续启动只会把不可预测的字节交给 secure monitor —— 那比不启动更糟。

这条判据的落点是顺序：**先开目录、再查占位**（`5d96806`）。反过来写时，一份共用 payload
（`/chosen/memory-map` 只有 `name`，没有任何属性）会在占位检查处 `EFI_COMPROMISED_DATA`，
把所有不用 modem 的镜像一起变砖。教训一句话：**共用的 payload 上，任何新增的强校验都必须有
「本镜像不需要」的出口**——出口要是一条明确的成功路径（这里：目录不存在 ⇒ `EFI_SUCCESS` +
`Files = 0` + 一行日志），不是注释里的假设。

## 5 ImageCarrierLib 契约

### 5.1 规模估计

| 部分 | 估计行数 |
| --- | --- |
| 读文件循环（打开/取 FileSize/64 KiB 分块/直写） | 90-110 |
| 表校验（对齐/越界/末段/name 与 bytes 一致） | 60-80 |
| 内存图校验 + `AblEnd` | 50-70 |
| 属性定位/零检查/写入 | 60-80 |
| 日志与收尾 | 50-60 |
| 注释与文件头 | 120-150 |
| **合计** | **约 450-550** |

### 5.2 头文件（照抄）

```c
#ifndef IMAGE_CARRIER_LIB_H_
#define IMAGE_CARRIER_LIB_H_

#include <Uefi.h>

typedef struct {
  UINT64  Base;      // MODEM_IMAGE_BASE, 0x8bc00000
  UINT64  Span;      // MODEM_IMAGE_WINDOW, 0x13200000
  UINT64  AblEnd;    // Display Reserved start, 0 if the map lacks it
  UINT32  Files;     // 27 when a carrier was loaded, 0 when skipped
  UINT32  Copied;    // sum of bytes, expected 109060761
  UINT32  Zeroed;    // sum of bss, expected 211012967
  UINT32  Gaps;      // Window - Copied - Zeroed, expected 790528
  UINT32  Segments;  // MODEM_IMAGE_SEGMENTS, 30
  UINT32  Reserved;
} IMAGE_CARRIER;

EFI_STATUS
EFIAPI
ImageCarrierLoad (
  IN  EFI_FILE_PROTOCOL  *Root,
  IN OUT VOID            *Tree,
  IN  UINTN               TreeSize,
  OUT IMAGE_CARRIER      *Carrier,
  OUT UINTN              *PropertyOffset
  );

#endif
```

契约：函数在**每条返回路径**上都把 `*Carrier` 和 `*PropertyOffset` 初始化（全零）；`Files == 0` 当且仅当「卷里没有 `MODEM/`」。

### 5.3 返回码

| 码 | 何时 | 调用方（`Boot.c`）动作 |
| --- | --- | --- |
| `EFI_SUCCESS` | 成功，或卷里没有 `MODEM/`（`Files == 0`） | 继续启动，打印三行 D3 与（`Files > 0` 时的）发布行 |
| `EFI_NOT_FOUND` | 目录在、`modem.b01` 不在 | `goto Fail` |
| `EFI_COMPROMISED_DATA` | 大小不符 / 表不自洽 / 区间越界或不对齐 / 属性缺失或已非零 | `goto Fail` |
| `EFI_DEVICE_ERROR` | 文件读错误、`GetMemoryMap` 失败、内存图不覆盖窗口 | `goto Fail` |
| `EFI_OUT_OF_RESOURCES` | 64 KiB 缓冲或内存图缓冲分配失败 | `goto Fail` |
| `EFI_BAD_BUFFER_SIZE` | `Tree` 太小、节点结构越界 | `goto Fail` |

### 5.4 所有权

| 对象 | 谁分配 | 谁释放 |
| --- | --- | --- |
| `Root` | `Boot.c:695` 的 `OpenVolume` | `Boot.c:821` 的 `Root->Close`；**库不得关** |
| `Tree` / `TreeSize` | `Boot.c:710` 的 `ReadFile` | `Boot.c:819` 的 `FreePool`；库只读写其中 16 字节 |
| 目标窗口 `0x8BC00000` | **没有人分配**（内存图里就是 Reserved，`MemoryMapLib.c:31`） | 没有人释放；它不是 BootServices 资源，`Fail:` 也无需回滚（对比 `:911` 的 `FreePages`） |
| 库内 64 KiB 缓冲 | 库 | 库，单出口释放 |
| 库内内存图缓冲 | 库 | 库，单出口释放 |

### 5.5 调用点改动（`DarwinBoot.c`，四处）

a) `:18` 的 `#include "WindowSize.h"` 之后（`:1-18` 是现有 include 块）。
**用引号包含，不要用 `<Library/...>`**（`DarwinBootPkg` 没有 `.dec`，见 §1.5 的坑 ②）：

```c
#include "ImageCarrierLib.h"
```

b) 声明块 `:665` 的 `CHAR16 Failure[96];` 后：

```c
  IMAGE_CARRIER                   Carrier;
  UINTN                           CarrierOffset;
```

c) `:721` 之后（§1.3）。

d) `:801` 的 `CopyMem` 之后：

```c
  Print (L"modem-image: chosen dtb at 0x%016lx\n", TreeAddress);
  Print (L"modem-image: window 0x8bc00000..0x9ee00000\n");
  Print (L"modem-image: abl staging ends at 0x%016lx\n", Carrier.AblEnd);
  if (Carrier.Files != 0) {
    Print (L"modem-image: range 0x8bc00000..0x9ee00000 published as K60ModemImage\n");
  }
```

未使用 `CarrierOffset` 时加 `(VOID)CarrierOffset;`，避免 `-Wunused-but-set`；若编译器仍报，把 d) 的第一行改成引用它的 `ASSERT (CarrierOffset != 0)`。

### 5.6 库 INF（实际落地版，`a9cd70d`）

```ini
## SPDX-License-Identifier: BSD-2-Clause-Patent
[Defines]
  INF_VERSION    = 0x00010019
  BASE_NAME      = ImageCarrierLib
  FILE_GUID      = 8E4C1F62-3A57-4B0D-9C21-6D5F7A0E3B14
  MODULE_TYPE    = BASE
  VERSION_STRING = 0.1
  LIBRARY_CLASS  = ImageCarrierLib

[Sources]
  ImageCarrierLib.c
  ImageCarrierLib.h
  K60ModemImageTable.h

[Packages]
  MdePkg/MdePkg.dec

[LibraryClasses]
  BaseLib
  BaseMemoryLib
  DebugLib
  MemoryAllocationLib
  PrintLib
  UefiBootServicesTableLib
  UefiLib

[Guids]
  gEfiFileInfoGuid
```

与本规格最初草稿的三处差异（都是实测后收窄的，照落地版写）：

1. `MODULE_TYPE = BASE` 而不是 `UEFI_DRIVER`：库本身不产生驱动镜像，纯函数集合。
2. `[Packages]` **只列 `MdePkg/MdePkg.dec`**：头文件用引号包含，不需要 `mondrian.dec` 的 `[Includes]`。
3. **没有 `[Protocols]` 段**：`gEfiSimpleFileSystemProtocolGuid` 由调用方（`DarwinBoot.inf`，`:32-36`）声明，
   库只用传进来的 `EFI_FILE_PROTOCOL *`，自己不 `LocateProtocol`。

### 5.7 实现顺序（可直接拆成多个 commit）

1. 表校验（行数、对齐、越界、末段等于窗口末尾、`name` 与 `bytes` 一致）；
2. 内存图校验 + `AblEnd`；
3. 打开目录与哨兵文件（`modem.b01`）；
4. 逐行拷贝 + 逐段清零；
5. 合计与 gaps 行；
6. 属性定位、零检查、16 B 写入；
7. 返回 `IMAGE_CARRIER`（含 `PropertyOffset`）；
8. `Boot.c` 的三行 D3 + 发布行 + `Stage` 设置。

建议第 1-2 步先落一个只读版（只校验、打日志、返回 `EFI_SUCCESS` 且 `Files = 0`），上机确认三行日志与桩行为，再开写真实拷贝 —— 这样固件线的第一次上机就不必同时验证「读文件」和「不弄坏启动」。

**只读版已完成并实测**（`a8d6bd4` 代码、`a9cd70d` 接线）：编译通过、FD 尺寸不变、真机飞到 SpringBoard。
所以第 3-8 步就是「拷贝与属性发布」这一交的全部内容，不需要再回头验证构建链。

### 5.8 与 ADSP 的关系（已裁）

14 §4 的裁决：DXE 只服务 modem；ADSP 走内核内嵌 blob（main `996aac6`，符号 `k60_adsp_blob`，23,506,184 B）。所以库里**不要**出现 ADSP 分支，也不要做通用容器解析（12 §1.6 已拒容器）。

## 6 与 13 号门禁的对照

| 门禁行 | 本规格哪一节满足 | 备注 |
| --- | --- | --- |
| A1 / A2 payload 与 boot.img 尺寸 | 不由代码决定 | 路线已定 D（05:38 裁决）⇒ 卷仍是 192 MiB，13 已改成 **201326592 / 201887744**（`fdtest-20261116a` 实测值）。A-208 后备档的 218103808 / 218664960 只留在 13 的备注里，不启用 |
| A3 27 个文件名集合 | §2.4 第 4 步 | 名字不带 `.bin`，与 manifest 同名；**走 D 时卷里是 `modem.bNN.lzma`**，A3 的名单要带 `.lzma` 后缀，否则集合比对失败 |
| A4 逐个大小 | §1.8.2 | 走 D 后判据是「13 B 头里的声明长度 == 段表 `bytes`」，压缩尺寸本身不是断言值；13 已换成 `scripts/check-modem-lzma.py`，并新增 A6 判「声明长度之和 == 109060761」 |
| A5 ADT 16 B 属性 | §3.1、§3.2 | 构建期占位 + 运行时写入 |
| B1 `ImageCarrierLib` 存在 | §1.5 | 三个新文件（`.h`/`.c`/`.inf`）+ 生成物 `K60ModemImageTable.h`；已落 `a9cd70d` |
| B2 `DarwinBoot.c` 里有 `ImageCarrierLoad` | §5.5(c) | 调用点在 `Boot()` 内 |
| B3 `DarwinBoot.c` 里 `K60ModemImage` >= 2 处 | §3.3 | 属性名字面量 + 发布行都在 `Boot.c` 里，不能只放库里 |
| B4 三行 D3、无 `DEBUG(` | §1.6 | 全部 `Print()` |
| B5 固件表 == 生成器输出 | §1.5 | `K60ModemImageTable.h` 是生成物 |
| B6 无整窗清零 | §2.4 第 6 步 | 逐段 `ZeroMem (bss)` |
| C1 三行日志各一次 | §1.6 | 各打一次，不要放在重试循环里 |
| C2 `copied 109060761, zeroed 211012967, gaps 790528` | §2.4 第 8 步 | 数字由表求和得到，必须与生成器 stdout 一致 |
| C3 区间发布行 | §3.3 | 只在一个分支打一次 |
| C4 内核 `carrier present at 0x8bc00000` | §2.4、§2.5 | 由真实拷贝 + 非缓存写保证 |
| C5 内核 `plan rows=30` | 已由 L2 代码保证 | 与载具无关 |

## 7 前置与未决

1. **~~P-154 是硬前置~~（2026-11-16 已由 refmine 推翻，Lead 裁决不再阻塞）**：现存唯一重建卷 `4bbe76017eb4` 在 audio-probe j、k 两张镜像上真机进过 SpringBoard（j: `evidence/audio-probe-j/run1/` console 222,415 B、SpringBoard ×129；k: `usblog-20261115-012317` 220,748 B、×129），且它的 `SOURCE_DATE_EPOCH` 精确等于 uefi HEAD `9b79562` 的提交时间（1794541119 = 2026-11-13 03:38:39Z）⇒ 同源同 pin 得同一 FD。`cf448571` 那个不可复现卷来自 2026-11-02 已消失的 Linux 检出，不再是障碍。**剩下的是 §1.7 的容量问题，不是可复现性问题。**
2. **段表单一数据源**：任何段表改动先回 Lead（14 §6）。本规格不改表。
3. **文件名不带 `.bin`**：与 manifest 一致（13 A3）。如果打包脚本坚持要 `.bin`，先改 13 的 A3/A4 与 manifest，再改本规格——不要两边各写一套。
4. **固件表随 modem 固件升级**：换 modem 固件必须同时改三处（`pong_modem_table.h`、`K60ModemImageTable.h`、payload 的 27 个文件），否则 B5/A4 会红。
5. **未验证项**：306 MiB 非缓存写的耗时（估计 1-3 s，未实测）；`AblEnd` 扫描在真机 `GetMemoryMap` 上的命中情况（若命中 0，D3 第三行会打 0，C1 仍绿，但要在日志里标注）。
6. **不带 `MODEM/` 的镜像照常启动**：这是设计目标，不是遗留缺陷（§4.4）。
7. **走 D 后新增三项构建期职责**（本线，不是固件线）：打包工具改写 `.lzma` 头里 8 B 的声明大小（§1.7.1 ③）；
   `gen-modem-table.py --firmware-header` 增加 `crc32` 列（压缩数据的 CRC32，供固件解压前比对）；
   13 号门禁按 §6 的 A1–A4 新判据一次性改。三者都在「段表单一数据源」的前提下做，改表仍先回 Lead。

## 8 引用

- `Platforms/Xiaomi/DarwinBootPkg/Driver/DarwinBoot.c:613-914`（`Boot()`）、`:693-696`（卷）、`:710`（ADT）、`:721`（解析）、`:751`（窗口）、`:766`（`TreeAddress`）、`:798`（DT VA）、`:801`（拷贝）、`:884`/`:891`（EBS/Enter）、`:898-913`（`Fail:`）；`:929-969`（入口，不注册事件）
- `Platforms/Xiaomi/DarwinBootPkg/Driver/DarwinBoot.inf:6`（`UEFI_DRIVER`）、`:18-20`（`[Packages]`）、`:22-30`（`[LibraryClasses]`）
- `Platforms/Xiaomi/DarwinBootPkg/DarwinBoot.dsc:14-26`（`[LibraryClasses]`）、`:33`（`[Components]`）
- `Platforms/Xiaomi/mondrianPkg/mondrian.dsc:70-93`（`[LibraryClasses]`）、`:120`（`DarwinBoot.inf`）
- `Platforms/Xiaomi/mondrianPkg/mondrian.dec:14-15`（`[Includes]`）
- `Platforms/Xiaomi/UniXNUPkg/UniXNUPkg.dec:14-20`（`[Includes]` + `[LibraryClasses]` 的写法范例）、`Platforms/Xiaomi/UniXNUPkg/Library/UniXNULib/UniXNULib.inf:8-46`（库 INF 范例）
- `Platforms/Xiaomi/mondrianPkg/Library/MemoryMapLib/MemoryMapLib.c:31`（`mpss_region`）、`:39-52`（ABL Staging / Display Reserved）、`:76-83`（DXE Heap）、`:94`（XNU High Arena）
- `Platforms/Xiaomi/mondrianPkg/Drivers/MondrianBootMemoryDxe/MondrianBootMemoryDxe.c:154-174`（`ReadyToBoot` 先例）
- k60-cellular：`scripts/gen-modem-table.py:124-146`（`--firmware-header`）、`:148-151`（`--manifest`）；`scripts/make-pong-adt.py:231-233`（`/chosen/memory-map`）；`drivers/PongCellular/K60ModemBoot.c:45-139`；`drivers/PongCellular/K60ModemLink.c:211`/`:262`；`drivers/PongCellular/K60ModemPas.c:53`
