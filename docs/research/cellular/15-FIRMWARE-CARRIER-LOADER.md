# 15 — 固件载具装载器实现规格（K60ModemImage）

- **状态**：规格（尚无实现；本线未修改、未构建、未出镜像 uefi-mondrian）
- **日期**：2026-11-15
- **实现 Owner**：uefi-mondrian 线（Lead 排期）；**验收 Owner**：本线（用 13 号门禁）
- **勘察版本**：`uefi-mondrian` `main` @ `9b79562`（工作树只有 6 个子模块脏，无源码改动）
- **相关**：`12-DXE-CONTRACT.md`（为什么是库调用）、`13-FIRMWARE-ACCEPTANCE.md`（18 行门禁）、`14-DXE-REQUEST.md`（需求与裁决）、`06-MODEM-PAS.md`（内核侧）

本文所有行号都相对 `9b79562`。每条断言后面带 `文件:行`，或明确写「此文件不存在，需新建」。

---

## 0 一句话

在 DarwinBoot 的 `Boot()` 里、ADT 解析之后（`DarwinBoot.c:721`）、主窗口分配之前（`DarwinBoot.c:751`）调用一个新库 `ImageCarrierLib`：它把 payload 里 `EFI/UniXNU/MODEM/` 的 27 个平铺文件按 30 行段表写进 `0x8BC00000`，把 16 字节 `{base, span}` 写进 `/chosen/memory-map`，并打三行 level-1 日志。**不新增 DXE 驱动**。

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

| 动作 | 文件 | 具体做法 |
| --- | --- | --- |
| 新建 | `Platforms/Xiaomi/mondrianPkg/Include/Library/ImageCarrierLib.h` | 此文件不存在，需新建；内容见 §5.2 |
| 新建 | `Platforms/Xiaomi/mondrianPkg/Library/ImageCarrierLib/ImageCarrierLib.c` | 此文件不存在，需新建；规模约 450-550 行（§5.7） |
| 新建 | `Platforms/Xiaomi/mondrianPkg/Library/ImageCarrierLib/ImageCarrierLib.inf` | 此文件不存在，需新建；形状见 §5.6 |
| 新建（生成物） | `Platforms/Xiaomi/mondrianPkg/Include/K60ModemImageTable.h` | 由 k60-cellular 的 `scripts/gen-modem-table.py --firmware-header` 生成，**禁止手改**（13 的 B5 会与生成器输出逐字节 diff） |
| 改 | `Platforms/Xiaomi/mondrianPkg/mondrian.dec` | 在 `:14-15` 的 `[Includes]` 之后加 `[LibraryClasses]` 段，一行 `ImageCarrierLib|Include/Library/ImageCarrierLib.h`（照 `UniXNUPkg.dec:17-20` 的形状） |
| 改 | `Platforms/Xiaomi/mondrianPkg/mondrian.dsc` | `:83` 的 `MemoryMapLib|...` 后面加 `ImageCarrierLib|mondrianPkg/Library/ImageCarrierLib/ImageCarrierLib.inf` |
| 改 | `Platforms/Xiaomi/DarwinBootPkg/DarwinBoot.dsc` | `:26` 的 `DebugLib|...` 后面加同一行（独立 DSC 也要能编） |
| 改 | `Platforms/Xiaomi/DarwinBootPkg/Driver/DarwinBoot.inf` | `:20` 后加 `mondrianPkg/mondrian.dec`；`:30` 后加 `ImageCarrierLib` |
| 改 | `Platforms/Xiaomi/DarwinBootPkg/Driver/DarwinBoot.c` | `:18`（`#include "WindowSize.h"`）之后加 `#include <Library/ImageCarrierLib.h>`；`:665` 后加两个变量；`:721` 后加调用（§1.3）；`:801` 后加三行打印（§1.6） |

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
- **第 3 行** 的 `AblEnd` 由 §2.3 的内存图扫描得到（`Display Reserved` 起点 `0xB8000000`，`MemoryMapLib.c:52`），不是硬编码常量。
- 三行都用 `Print()`，**不能用 `DEBUG()`**：13 的 B4 会在固件源码里 `grep -F "modem-image:"`，只要有一行含 `DEBUG(` 就直接判红。

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
3. 顺带取 `AblEnd`：找 `PhysicalStart == 0xB8000000` 的描述符（`Display Reserved`，`MemoryMapLib.c:52`），把它的起点作为「ABL staging 结束」；找不到就填 0 并继续（它只是诊断数，不阻断）。

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

a) `:18` 的 `#include "WindowSize.h"` 之后（`:1-18` 是现有 include 块）：

```c
#include <Library/ImageCarrierLib.h>
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

### 5.6 库 INF（照 `UniXNULib.inf:8-46` 的形状）

```ini
[Defines]
  INF_VERSION    = 0x00010019
  BASE_NAME      = ImageCarrierLib
  FILE_GUID      = <新生成一个 GUID>
  MODULE_TYPE    = UEFI_DRIVER
  VERSION_STRING = 0.1
  LIBRARY_CLASS  = ImageCarrierLib|UEFI_DRIVER

[Sources]
  ImageCarrierLib.c

[Packages]
  MdePkg/MdePkg.dec
  mondrianPkg/mondrian.dec

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

[Protocols]
  gEfiSimpleFileSystemProtocolGuid
```

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

### 5.8 与 ADSP 的关系（已裁）

14 §4 的裁决：DXE 只服务 modem；ADSP 走内核内嵌 blob（main `996aac6`，符号 `k60_adsp_blob`，23,506,184 B）。所以库里**不要**出现 ADSP 分支，也不要做通用容器解析（12 §1.6 已拒容器）。

## 6 与 13 号门禁的对照

| 门禁行 | 本规格哪一节满足 | 备注 |
| --- | --- | --- |
| A1 / A2 payload 与 boot.img 尺寸 | 不由代码决定 | 27 个文件总量决定；13 已给 234881024 / 235446272 |
| A3 27 个文件名集合 | §2.4 第 4 步 | 名字不带 `.bin`，与 manifest 同名 |
| A4 逐个大小 | §2.4 第 4 步 | 大小不符在固件里就硬失败，A4 只是外部复核 |
| A5 ADT 16 B 属性 | §3.1、§3.2 | 构建期占位 + 运行时写入 |
| B1 `ImageCarrierLib` 存在 | §1.5 | 三个新文件（`.h`/`.c`/`.inf`） |
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

1. **P-154 是硬前置**：固件卷重建必须可复现、且能装下 224 MiB 的 payload。历史实测重建卷会报 `UNIXNU: config: no boot entry found`、默认项变成 exit。在卷能稳定装 payload 之前，本规格的代码没有意义。
2. **段表单一数据源**：任何段表改动先回 Lead（14 §6）。本规格不改表。
3. **文件名不带 `.bin`**：与 manifest 一致（13 A3）。如果打包脚本坚持要 `.bin`，先改 13 的 A3/A4 与 manifest，再改本规格——不要两边各写一套。
4. **固件表随 modem 固件升级**：换 modem 固件必须同时改三处（`pong_modem_table.h`、`K60ModemImageTable.h`、payload 的 27 个文件），否则 B5/A4 会红。
5. **未验证项**：306 MiB 非缓存写的耗时（估计 1-3 s，未实测）；`AblEnd` 扫描在真机 `GetMemoryMap` 上的命中情况（若命中 0，D3 第三行会打 0，C1 仍绿，但要在日志里标注）。
6. **不带 `MODEM/` 的镜像照常启动**：这是设计目标，不是遗留缺陷（§4.4）。

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
